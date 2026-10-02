"""Where jobs come from. Each stage uses a different TinyFish tool.

1. Search  -> discovers live postings and which companies are hiring
              on Greenhouse, Lever, Ashby and Workday.
2. Fetch   -> reads each company's full job board (structured JSON) and
              the posting pages themselves (for visa and skills info).
3. Agent   -> operates Workday career sites, which need a real browser:
              it types the search, waits for results and extracts them.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from .rank import Job, dedupe_key, parse_date, title_relevant
from .tinyfish import TinyFish, TinyFishError, parse_json_text

ATS_DOMAINS = {
    "greenhouse": "job-boards.greenhouse.io,boards.greenhouse.io",
    "lever": "jobs.lever.co",
    "ashby": "jobs.ashbyhq.com",
}
WORKDAY_DOMAIN = "myworkdayjobs.com"

BOARD_API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


@dataclass
class Prefs:
    role: str
    location: str = ""
    seniority: str = "Internship"
    keywords: list = field(default_factory=list)
    remote_ok: bool = True
    need_visa: bool = False
    companies: list = field(default_factory=list)
    agent_urls: list = field(default_factory=list)
    use_agent: bool = True
    use_linkedin: bool = True     # public LinkedIn search via Fetch
    linkedin_me: bool = False     # signed-in LinkedIn via Agent + saved profile
    max_boards: int = 10
    max_agent_sites: int = 3


def pretty_company(slug: str) -> str:
    slug = re.sub(r"(usa|careers|jobs|inc)$", "", slug.lower())
    return slug.replace("-", " ").replace("_", " ").strip().title() or slug


# ---------------------------------------------------------------- Search
def parse_ats_url(url: str):
    """Return (ats, slug, job_id) for a Greenhouse/Lever/Ashby/Workday URL."""
    p = urlparse(url)
    host = p.netloc.lower()
    parts = [x for x in p.path.split("/") if x]
    if "greenhouse.io" in host and parts:
        job_id = parts[2] if len(parts) > 2 and parts[1] == "jobs" else None
        job_id = job_id or (parse_qs(p.query).get("gh_jid") or [None])[0]
        return "greenhouse", parts[0].lower(), job_id
    if host == "jobs.lever.co" and parts:
        return "lever", parts[0].lower(), parts[1] if len(parts) > 1 else None
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", parts[0].lower(), parts[1] if len(parts) > 1 else None
    if host.endswith(WORKDAY_DOMAIN) and parts:
        site = parts[1] if re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]) and len(parts) > 1 else parts[0]
        return "workday", f"https://{host}/{site}", None
    return None, None, None


def discover(tf: TinyFish, prefs: Prefs) -> tuple[list[Job], dict, list[str]]:
    """Search the live web for postings. Returns (jobs, board_counts, workday_sites)."""
    level = {"Internship": "intern", "New grad": "new grad"}.get(prefs.seniority, "")
    role = prefs.role if level in prefs.role.lower() else f"{prefs.role} {level}"
    queries = []
    for ats, domains in ATS_DOMAINS.items():
        queries.append((f"{role} {prefs.location}".strip(), domains, 0))
        queries.append((f"{role} {prefs.location}".strip(), domains, 1))
        queries.append((role, domains, 0))
    queries.append((f"{role} {prefs.location}".strip(), WORKDAY_DOMAIN, 0))
    for company in prefs.companies:
        queries.append((f"{company} {role}", ",".join(ATS_DOMAINS.values()) + "," + WORKDAY_DOMAIN, 0))

    purpose = f"Find currently open {role} job postings for a student job search"
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(tf.search, q, d, pg, purpose) for q, d, pg in queries]
        for f in as_completed(futures):
            try:
                results.extend(f.result())
            except TinyFishError as e:
                tf.usage.note("Search", f"one query failed: {e}")

    jobs, boards, workday = [], {}, []
    seen = set()
    for r in results:
        url = r.get("url", "")
        ats, slug, job_id = parse_ats_url(url)
        if not ats:
            continue
        if ats == "workday":
            if slug not in workday:
                workday.append(slug)
            continue
        boards[(ats, slug)] = boards.get((ats, slug), 0) + 1
        if job_id and (ats, slug, job_id) not in seen:
            seen.add((ats, slug, job_id))
            title = re.sub(r"^(job application for|apply for)\s+", "", r.get("title", ""), flags=re.I)
            title = re.sub(r"\s+(at|@)\s+[A-Z][\w&.']*(\s[A-Z][\w&.']*)?\s*$", "", title).strip(" -|")
            jobs.append(Job(
                title=title, company=pretty_company(slug), url=url.replace("http://", "https://"),
                description=r.get("snippet", ""), posted=parse_date(r.get("date")),
                source=f"{ats.title()} (search)", tool="Search", key=f"{ats}:{slug}:{job_id}",
            ))
    tf.usage.stats.update(searches=len(queries), postings=len(jobs), companies=len(boards), workday=len(workday))
    tf.usage.note("Search", f"{len(queries)} searches found {len(jobs)} postings at "
                  f"{len(boards)} companies and {len(workday)} Workday sites")
    return jobs, boards, workday


# ---------------------------------------------------------------- Fetch (boards)
def _board_jobs(ats: str, slug: str, data) -> list[Job]:
    company = pretty_company(slug)
    out = []
    if ats == "greenhouse":
        for j in data.get("jobs", []):
            out.append(Job(
                title=j.get("title", ""), company=company, url=j.get("absolute_url", ""),
                location=(j.get("location") or {}).get("name", ""),
                posted=parse_date(j.get("first_published") or j.get("updated_at")),
                source="Greenhouse board", tool="Fetch", key=f"greenhouse:{slug}:{j.get('id')}",
            ))
    elif ats == "lever":
        for j in data if isinstance(data, list) else []:
            cats = j.get("categories") or {}
            desc = " ".join(filter(None, [j.get("descriptionPlain"), j.get("additionalPlain")]))
            for lst in j.get("lists") or []:
                desc += " " + re.sub(r"<[^>]+>", " ", lst.get("content", ""))
            out.append(Job(
                title=j.get("text", ""), company=company, url=j.get("hostedUrl", ""),
                location=cats.get("location", "") or ", ".join(cats.get("allLocations") or []),
                posted=parse_date(j.get("createdAt")), description=desc,
                source="Lever board", tool="Fetch", key=f"lever:{slug}:{j.get('id')}",
            ))
    elif ats == "ashby":
        for j in data.get("jobs", []):
            loc = j.get("location", "")
            if j.get("isRemote") and "remote" not in loc.lower():
                loc = f"{loc} (Remote)".strip()
            out.append(Job(
                title=j.get("title", ""), company=company, url=j.get("jobUrl", ""),
                location=loc, posted=parse_date(j.get("publishedAt")),
                description=j.get("descriptionPlain", ""),
                source="Ashby board", tool="Fetch", key=f"ashby:{slug}:{j.get('id')}",
            ))
    return out


def read_boards(tf: TinyFish, boards: dict, prefs: Prefs, groups) -> list[Job]:
    """Fetch the full job board of the companies Search found most often."""
    ranked = sorted(boards.items(), key=lambda kv: -kv[1])[: prefs.max_boards]
    urls = {BOARD_API[ats].format(slug=slug): (ats, slug) for (ats, slug), _ in ranked}
    if not urls:
        return []
    try:
        fetched = tf.fetch(list(urls), purpose="Read the complete list of open jobs on this company job board")
    except TinyFishError as e:
        tf.usage.note("Fetch", f"board read failed: {e}")
        return []
    jobs, total, read = [], 0, 0
    for url, (ats, slug) in urls.items():
        res = fetched.get(url)
        if not res or not res.get("text"):
            continue
        try:
            data = parse_json_text(res["text"])
        except ValueError:
            continue
        read += 1
        board = _board_jobs(ats, slug, data)
        total += len(board)
        jobs.extend(j for j in board if title_relevant(j.title, groups, prefs.seniority, prefs.keywords))
    tf.usage.stats.update(boards=read, board_openings=total, board_fit=len(jobs))
    tf.usage.note("Fetch", f"read {read} company job boards ({total} openings), {len(jobs)} fit your role")
    return jobs


# ---------------------------------------------------------------- Fetch (postings)
_LOC_LINE = re.compile(r"^\s*(?:\*\*)?(?:location|locations|office)s?(?:\*\*)?\s*[:\-]\s*(.+)$", re.I | re.M)
_CITY = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)*, (?:[A-Z]{2}\b|[A-Z][a-z]+)|\bRemote\b|\bNew York\b|\bSan Francisco\b|\bSeattle\b|\bBoston\b|\bPalo Alto\b")


def guess_location(text: str) -> str:
    m = _LOC_LINE.search(text[:4000])
    if m:
        return m.group(1).strip(" *")[:80]
    # Posting pages usually list the location as a short line right under the title.
    for line in text[:1500].splitlines()[1:15]:
        line = line.strip(" *-#\t")
        if 2 < len(line) < 90 and _CITY.search(line):
            return line
    return ""


def read_postings(tf: TinyFish, jobs: list[Job], limit: int = 20) -> None:
    """Open the top postings to read the full description (visa, skills, location)."""
    targets = [j for j in jobs if len(j.description) < 400 and j.url][:limit]
    if not targets:
        return
    batches = [targets[i:i + 10] for i in range(0, len(targets), 10)]
    fetched: dict = {}
    with ThreadPoolExecutor(max_workers=len(batches)) as pool:
        futures = [pool.submit(tf.fetch, [j.url for j in b],
                               "markdown", "Read job description, location and visa sponsorship policy")
                   for b in batches]
        for f in as_completed(futures):
            try:
                fetched.update(f.result())
            except TinyFishError as e:
                tf.usage.note("Fetch", f"posting read failed: {e}")
    read = 0
    for j in targets:
        res = fetched.get(j.url)
        if not res or not res.get("text"):
            continue
        read += 1
        j.read = True
        text = res["text"].split("## Similar Jobs")[0]
        j.description = text[:20000]
        if not j.location:
            j.location = guess_location(text)
    tf.usage.stats["postings_read"] = read
    tf.usage.note("Fetch", f"opened {read} postings to check visa policy, skills and location")


# ---------------------------------------------------------------- Agent
def agent_goal(prefs: Prefs) -> str:
    level = {"Internship": "intern", "New grad": "new grad"}.get(prefs.seniority, "")
    query = re.sub(r"\b(intern(ship)?|new grad)\b", "", prefs.role, flags=re.I).strip()
    query = f"{query} {level}".strip()
    return (
        f'Use the search box on this careers site to search for "{query}". '
        "Wait for results to load. Return the first 15 job listings as JSON: "
        '{"company":"company name","jobs":[{"title":"...","location":"...",'
        '"url":"full link to the posting","posted":"posted date text"}]}. '
        "Do not open individual postings. If the site blocks access or shows no results, "
        'return {"jobs":[],"error":"reason"}.'
    )


def run_agents(tf: TinyFish, sites: list[str], prefs: Prefs, groups) -> list[Job]:
    sites = sites[: prefs.max_agent_sites]
    if not sites:
        return []
    goal = agent_goal(prefs)
    jobs: list[Job] = []
    with ThreadPoolExecutor(max_workers=2) as pool:  # wallet allows 2 concurrent runs
        futures = {pool.submit(tf.agent, url, goal): url for url in sites}
        for f in as_completed(futures):
            url = futures[f]
            host = urlparse(url).netloc.split(".")[0]
            try:
                result = f.result()
            except TinyFishError as e:
                tf.usage.note("Agent", f"{host}: {e}")
                continue
            company = result.get("company") or pretty_company(host)
            found = result.get("jobs") or []
            kept = 0
            for j in found:
                title = j.get("title", "")
                if not title_relevant(title, groups, prefs.seniority, prefs.keywords):
                    continue
                kept += 1
                link = re.sub(r"\?q=.*$", "", j.get("url") or url)
                jobs.append(Job(
                    title=title, company=company, url=link, location=j.get("location", ""),
                    posted=parse_date(j.get("posted")), source="Workday (agent)", tool="Agent",
                    key=link,
                ))
            st_ = tf.usage.stats
            st_["agent_sites"] = st_.get("agent_sites", 0) + 1
            st_["agent_listings"] = st_.get("agent_listings", 0) + len(found)
            st_["agent_fit"] = st_.get("agent_fit", 0) + kept
            tf.usage.note("Agent", f"searched {company}'s careers site in a real browser: "
                          f"{len(found)} listings, {kept} fit your role")
    return jobs


# ---------------------------------------------------------------- Merge
def merge(*lists: list[Job]) -> list[Job]:
    """De-duplicate by ATS job id first, then by company + title + location."""
    by_key: dict[str, Job] = {}
    by_soft: dict[str, list[str]] = {}

    def same_place(a: Job, b: Job) -> bool:
        if not a.location or not b.location:
            return True
        return dedupe_key("", "", a.location) == dedupe_key("", "", b.location)

    for lst in lists:
        for j in lst:
            if not j.title or not j.url:
                continue
            soft = dedupe_key(j.company, j.title, "")
            existing_key = j.key if j.key in by_key else None
            if not existing_key:
                for k in by_soft.get(soft, []):
                    if same_place(by_key[k], j):
                        existing_key = k
                        break
            if existing_key:
                old = by_key[existing_key]
                # Keep the richer record (board data beats search snippets).
                old.location = old.location or j.location
                old.posted = old.posted or j.posted
                if len(j.description) > len(old.description):
                    old.description = j.description
                if old.tool == "Search" and j.tool != "Search":
                    old.source, old.tool, old.url = j.source, j.tool, j.url or old.url
                continue
            by_key[j.key] = j
            by_soft.setdefault(soft, []).append(j.key)
    return list(by_key.values())
