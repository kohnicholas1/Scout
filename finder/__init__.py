"""Internship finder pipeline: Search -> Fetch -> Agent -> rank."""

from __future__ import annotations

from .rank import Job, role_terms, score_job, title_relevant
from .sources import Prefs, discover, merge, read_boards, read_postings, run_agents
from .tinyfish import TinyFish, Usage

__all__ = ["Prefs", "Job", "Usage", "find_jobs"]


def find_jobs(prefs: Prefs, api_key: str | None = None, on_step=None):
    """Run the full pipeline. on_step(tool, message) is called as stages finish."""
    usage = Usage()
    tf = TinyFish(api_key, usage)
    groups = role_terms(prefs.role)

    def step(tool):
        if on_step and usage.log:
            on_step(*usage.log[-1])

    # 1. Search: discover postings, hiring companies and Workday sites
    found, boards, workday = discover(tf, prefs)
    step("Search")
    found = [j for j in found if title_relevant(j.title, groups, prefs.seniority, prefs.keywords)]

    # 2. Fetch: read whole job boards of the companies Search surfaced
    board_jobs = read_boards(tf, boards, prefs, groups)
    step("Fetch")

    # 3. Agent: operate Workday sites (discovered + user supplied)
    agent_jobs = []
    if prefs.use_agent:
        sites = list(dict.fromkeys(prefs.agent_urls + workday))
        agent_jobs = run_agents(tf, sites, prefs, groups)
        if sites:
            step("Agent")

    jobs = merge(board_jobs, found, agent_jobs)

    # Pre-rank, then open the best postings to read visa policy and skills
    for j in jobs:
        score_job(j, groups, prefs.seniority, prefs.keywords, prefs.location, prefs.remote_ok, prefs.need_visa)
    jobs.sort(key=lambda j: -j.score)
    read_postings(tf, jobs, limit=20)
    step("Fetch")

    for j in jobs:
        score_job(j, groups, prefs.seniority, prefs.keywords, prefs.location, prefs.remote_ok, prefs.need_visa)
    jobs.sort(key=lambda j: (-j.score, j.company))
    return jobs, usage
