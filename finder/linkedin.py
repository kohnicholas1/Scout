"""LinkedIn as a source.

Public mode (anyone):  TinyFish Fetch reads LinkedIn's public job search page.
My LinkedIn (owner):   TinyFish Agent browses LinkedIn signed in as you, using a
                       saved Browser Context Profile (your saved cookies), and can
                       apply with Easy Apply.
"""

from __future__ import annotations

import html as _html
import re
from urllib.parse import quote_plus

from .rank import Job, parse_date, title_relevant
from .tinyfish import TinyFish, TinyFishError

LEVEL_FILTER = {"Internship": "1", "New grad": "2", "Any level": ""}

_CARD = re.compile(r"<li>(.*?)</li>", re.S)


def _clean(s: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def search_url(prefs, days: int = 14) -> str:
    level = LEVEL_FILTER.get(prefs.seniority, "")
    q = re.sub(r"\s+", " ", prefs.role).strip()
    url = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(q)}"
    if prefs.location:
        url += f"&location={quote_plus(prefs.location)}"
    if level:
        url += f"&f_E={level}"
    return url + f"&f_TPR=r{days * 86400}"


def parse_cards(markup: str) -> list[Job]:
    jobs = []
    for card in _CARD.findall(markup):
        href = re.search(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', card) or \
            re.search(r'href="(https://[a-z]+\.linkedin\.com/jobs/view/[^"]+)"', card)
        title = re.search(r'base-search-card__title">(.*?)</h3>', card, re.S)
        company = re.search(r'base-search-card__subtitle">(.*?)</h4>', card, re.S)
        if not (href and title):
            continue
        url = _html.unescape(href.group(1)).split("?")[0]
        loc = re.search(r'job-search-card__location">(.*?)</span>', card, re.S)
        date = re.search(r'<time[^>]*datetime="([^"]+)"', card)
        logo = re.search(r'data-delayed-url="(https://media\.licdn\.com/[^"]+)"', card)
        job_id = re.search(r"jobPosting:(\d+)", card)
        jobs.append(Job(
            title=_clean(title.group(1)), company=_clean(company.group(1)) if company else "",
            url=url, location=_clean(loc.group(1)) if loc else "",
            posted=parse_date(date.group(1)) if date else None,
            source="LinkedIn", tool="Fetch",
            key=f"linkedin:{job_id.group(1) if job_id else url}",
            logo=_html.unescape(logo.group(1)) if logo else "",
        ))
    return jobs


def read_public(tf: TinyFish, prefs, groups) -> list[Job]:
    """Fetch LinkedIn's public job search (no sign-in needed)."""
    url = search_url(prefs)
    try:
        res = tf.fetch([url], fmt="html", purpose="Read LinkedIn public job search results",
                       include_selectors=["ul.jobs-search__results-list"]).get(url)
    except TinyFishError as e:
        tf.usage.note("Fetch", f"LinkedIn read failed: {e}")
        return []
    jobs = parse_cards((res or {}).get("text", ""))
    kept = [j for j in jobs if title_relevant(j.title, groups, prefs.seniority, prefs.keywords)]
    tf.usage.stats["linkedin"] = len(jobs)
    tf.usage.note("Fetch", f"read LinkedIn job search: {len(jobs)} listings, {len(kept)} fit your role")
    return kept


def read_signed_in(tf: TinyFish, prefs, groups) -> list[Job]:
    """Agent browses LinkedIn Jobs signed in as you (saved Browser Context Profile)."""
    url = search_url(prefs) + "&f_AL=true"  # Easy Apply only
    goal = (
        "You are signed in to LinkedIn. Wait for the job results list to load. "
        "Return the first 15 job cards as JSON: "
        '{"jobs":[{"title":"...","company":"...","location":"...","url":"full job link",'
        '"posted":"posted text","easy_apply":true}]}. Do not apply to anything. '
        'If you are not signed in, return {"jobs":[],"error":"not signed in"}.'
    )
    try:
        result = tf.agent(url, goal, max_steps=25, use_profile=True)
    except TinyFishError as e:
        tf.usage.note("Agent", f"My LinkedIn: {e}")
        return []
    if result.get("error"):
        tf.usage.note("Agent", f"My LinkedIn: {result['error']}. Set up your LinkedIn profile in TinyFish.")
        return []
    jobs = []
    for j in result.get("jobs") or []:
        title = j.get("title", "")
        if not title_relevant(title, groups, prefs.seniority, prefs.keywords):
            continue
        link = (j.get("url") or "").split("?")[0]
        jobs.append(Job(title=title, company=j.get("company", ""), url=link or url,
                        location=j.get("location", ""), posted=parse_date(j.get("posted")),
                        source="My LinkedIn · Easy Apply", tool="Agent", key=f"linkedin:{link}"))
    st = tf.usage.stats
    st["agent_sites"] = st.get("agent_sites", 0) + 1
    st["agent_listings"] = st.get("agent_listings", 0) + len(result.get("jobs") or [])
    tf.usage.note("Agent", f"browsed LinkedIn signed in as you: {len(jobs)} Easy Apply roles fit")
    return jobs


def apply_easy(tf: TinyFish, job_url: str) -> dict:
    """Agent applies with LinkedIn Easy Apply, signed in as you.

    Safety rule: it only submits when LinkedIn already has everything it needs.
    If the form asks new questions, it stops and reports them instead of guessing.
    """
    goal = (
        "You are signed in to LinkedIn. On this job page, click the Easy Apply button. "
        "Go through the steps using the information LinkedIn has already filled in and the "
        "resume already on file. Only press Submit if every required field is already filled. "
        "If any required question is empty or needs a new answer, do NOT guess and do NOT submit: "
        "close the dialog and report the questions. If there is no Easy Apply button, do nothing. "
        'Return JSON: {"status":"submitted" | "needs_answers" | "no_easy_apply" | "not_signed_in",'
        '"questions":["..."],"note":"..."}'
    )
    return tf.agent(job_url, goal, max_steps=40, use_profile=True)
