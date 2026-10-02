"""Matching, visa detection, de-duplication and ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

STOP = {"and", "or", "the", "a", "an", "of", "for", "to", "in", "at", "with", "&", "-", "/"}

SENIORITY = {
    "Internship": {
        "include": ["intern", "internship", "co-op", "coop", "student", "summer 20", "apprentice"],
        "exclude": ["senior", "staff", "principal", "manager", "director", "head of", "sr.", "sr ", "lead "],
    },
    "New grad": {
        "include": ["new grad", "new graduate", "university grad", "graduate", "entry level", "entry-level",
                    "early career", "junior", "associate", "rotational", " i ", " 1 "],
        "exclude": ["senior", "staff", "principal", "manager", "director", "head of", "sr.", "intern"],
    },
    "Any level": {"include": [], "exclude": []},
}

SYNONYMS = {
    "machine learning": ["ml", "machine learning", "ai", "deep learning", "applied science", "applied scientist",
                         "research science", "research scientist", "computer vision", "nlp", "llm"],
    "artificial intelligence": ["ai", "artificial intelligence", "machine learning", "ml"],
    "ai": ["ai", "artificial intelligence", "machine learning", "ml", "llm", "applied science", "applied scientist",
           "research scientist", "deep learning"],
    "ml": ["ml", "machine learning", "ai"],
    "software engineer": ["software engineer", "software engineering", "swe", "software developer", "developer"],
    "software engineering": ["software engineer", "software engineering", "swe", "software developer"],
    "swe": ["software engineer", "software engineering", "swe"],
    "data science": ["data science", "data scientist"],
    "data scientist": ["data science", "data scientist"],
    "backend": ["backend", "back-end", "back end", "server"],
    "quant": ["quant", "quantitative"],
}

LOCATION_ALIASES = {
    "nyc": ["new york", "nyc", "ny,", "manhattan", "brooklyn"],
    "new york": ["new york", "nyc", "ny,", "manhattan", "brooklyn"],
    "sf": ["san francisco", "sf", "bay area"],
    "san francisco": ["san francisco", "sf", "bay area"],
    "bay area": ["san francisco", "bay area", "palo alto", "mountain view", "sunnyvale", "san jose", "menlo park"],
    "seattle": ["seattle", "bellevue", "redmond"],
    "boston": ["boston", "cambridge, ma"],
}

VISA_NEGATIVE = [
    r"(unable|not able|cannot|can't|can not|will not|won't|do not|does not|don't|doesn't|not)\s+(to\s+)?"
    r"(currently\s+)?(provide|offer|support|sponsor)[^.]{0,40}sponsor",
    r"(unable|not able|cannot|can't|will not|won't|do not|does not|don't|doesn't)\s+(to\s+)?sponsor",
    r"no\s+(visa\s+|immigration\s+)?sponsorship",
    r"without\s+(the\s+need\s+for\s+)?(current\s+or\s+future\s+)?(employer\s+|visa\s+|immigration\s+)?sponsorship",
    r"sponsorship\s+(is\s+)?not\s+(available|offered|provided)",
    r"must\s+be\s+(a\s+)?u\.?s\.?\s+citizen",
    r"u\.?s\.?\s+citizenship\s+(is\s+)?required",
    r"(active|current)\s+security\s+clearance",
]
VISA_POSITIVE = [
    r"(visa|h-?1b|immigration)\s+sponsorship\s+(is\s+)?(available|provided|offered|supported)",
    r"(we|company)\s+(will|can|do|does)\s+(provide\s+)?sponsor",
    r"sponsorship\s+(is\s+)?(available|offered|provided)",
    r"open\s+to\s+sponsor",
    r"\b(CPT|OPT)\b",
]


@dataclass
class Job:
    title: str
    company: str
    url: str
    location: str = ""
    posted: datetime | None = None
    description: str = ""
    source: str = ""          # e.g. "Greenhouse board", "Search", "Agent: Workday"
    tool: str = ""            # TinyFish tool that found it: Search / Fetch / Agent
    key: str = ""             # de-duplication key
    score: int = 0
    reasons: list = field(default_factory=list)
    visa: str = "Not stated"  # "Sponsors" / "No sponsorship" / "Not stated"
    read: bool = False        # full posting opened with TinyFish Fetch
    logo: str = ""            # company logo URL when the source provides one

    @property
    def posted_label(self) -> str:
        if not self.posted:
            return ""
        days = (datetime.now(timezone.utc) - self.posted).days
        if days <= 0:
            return "today"
        if days == 1:
            return "1 day ago"
        if days < 60:
            return f"{days} days ago"
        return self.posted.strftime("%b %Y")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def dedupe_key(company: str, title: str, location: str) -> str:
    loc = norm(location).split(" ")[0] if location else ""
    return f"{norm(company)}|{norm(title)}|{loc}"


def parse_date(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):  # Lever: epoch ms
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    s = str(value).strip()
    low = s.lower()
    now = datetime.now(timezone.utc)
    if "today" in low or "just" in low or "hour" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*(day|week|month)", low)
    if m:
        n = int(m.group(1))
        mult = {"day": 1, "week": 7, "month": 30}[m.group(2)]
        return now - timedelta(days=n * mult)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def role_terms(role: str) -> list[list[str]]:
    """Turn 'Machine Learning Intern' into groups of acceptable phrases."""
    text = norm(role)
    for seniority_word in ["internship", "intern", "new grad", "new graduate", "entry level", "summer", "2026", "2027"]:
        text = text.replace(seniority_word, " ")
    text = re.sub(r"\s+", " ", text).strip()
    groups: list[list[str]] = []
    used = text
    for phrase, alts in SYNONYMS.items():
        if re.search(rf"\b{re.escape(phrase)}\b", used):
            groups.append(alts)
            used = re.sub(rf"\b{re.escape(phrase)}\b", " ", used)
    for w in used.split():
        if w not in STOP and len(w) > 1:
            groups.append(SYNONYMS.get(w, [w]))
    return groups


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def _inc(text: str, term: str) -> bool:
    """Seniority terms: 'intern' must not match 'internal'."""
    if term.strip() != term or term.endswith("20"):
        return term in text
    return _has(text, term)


def title_relevant(title: str, groups: list[list[str]], seniority: str, keywords: list[str]) -> bool:
    t = f" {title.lower()} "
    rules = SENIORITY.get(seniority, SENIORITY["Any level"])
    if rules["include"] and not any(_inc(t, w) for w in rules["include"]):
        return False
    if any(w in t for w in rules["exclude"]):
        return False
    if not groups and not keywords:
        return True
    return any(any(_has(t, p) for p in g) for g in groups) or any(_has(t, k) for k in keywords)


def location_match(location: str, description: str, wanted: str, remote_ok: bool) -> tuple[bool, str]:
    loc = (location or "").lower()
    if not wanted.strip():
        return True, ""
    w = wanted.lower().strip()
    aliases = LOCATION_ALIASES.get(w, [w])
    if any(a in loc for a in aliases):
        return True, f"in {wanted}"
    if remote_ok and "remote" in loc:
        return True, "remote"
    if not loc:
        body = description.lower()[:3000]
        if any(a in body for a in aliases):
            return True, f"mentions {wanted}"
    return False, ""


def detect_visa(text: str) -> str:
    if not text:
        return "Not stated"
    low = text.lower()
    for pat in VISA_NEGATIVE:
        if re.search(pat, low):
            return "No sponsorship"
    for pat in VISA_POSITIVE:
        if re.search(pat, text if "CPT" in pat else low):
            return "Sponsors"
    return "Not stated"


def score_job(job: Job, groups, seniority, keywords, location, remote_ok, need_visa) -> Job:
    reasons: list[str] = []
    title = f" {job.title.lower()} "
    body = job.description.lower()
    score = 0

    # Role match (35)
    if groups:
        hit = sum(1 for g in groups if any(_has(title, p) for p in g))
        part = 35 * hit / len(groups)
        if hit == 0:
            body_hit = sum(1 for g in groups if any(_has(body, p) for p in g))
            part = 15 * body_hit / len(groups)
        score += part
        if hit:
            reasons.append("role match")
    else:
        score += 20

    # Seniority (20)
    rules = SENIORITY.get(seniority, SENIORITY["Any level"])
    if not rules["include"] or any(_inc(title, w) for w in rules["include"]):
        score += 20
        if rules["include"]:
            reasons.append(seniority.lower())

    # Location (20)
    ok, why = location_match(job.location, job.description, location, remote_ok)
    if ok:
        score += 20
        if why:
            reasons.append(why)
    elif job.location:
        score -= 30          # known location, and it is somewhere else
    else:
        score += 8           # location unknown

    # Keywords (15)
    if keywords:
        found = [k for k in keywords if _has(title, k) or _has(body, k)]
        score += 15 * len(found) / len(keywords)
        if found:
            reasons.append("mentions " + ", ".join(found[:4]))
    else:
        score += 10

    # Freshness (10)
    if job.posted:
        days = (datetime.now(timezone.utc) - job.posted).days
        if days <= 7:
            score += 10
            reasons.append("posted this week")
        elif days <= 30:
            score += 6
        elif days <= 90:
            score += 3

    # Visa
    job.visa = detect_visa(job.description)
    if need_visa:
        if job.visa == "Sponsors":
            score += 10
        elif job.visa == "No sponsorship":
            score -= 40

    job.score = max(0, min(100, round(score)))
    job.reasons = reasons
    return job
