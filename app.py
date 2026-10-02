"""Scout: a TinyFish-powered internship finder.

Run:  streamlit run app.py
Needs TINYFISH_API_KEY in .streamlit/secrets.toml or the environment.
"""

from __future__ import annotations

import html
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from finder import Prefs, find_jobs
from finder.tinyfish import TinyFishError

st.set_page_config(page_title="Scout · Internship Finder", page_icon="🐟", layout="wide")

st.markdown(
    """
<style>
:root { --accent:#ff6a1a; --muted:#8a8f98; }
.block-container { padding-top: 2rem; max-width: 1100px; }
h1 { font-weight: 700; letter-spacing: -0.02em; }
.sub { color: var(--muted); margin-top: -0.6rem; margin-bottom: 1.2rem; }
.job-title { font-size: 1.05rem; font-weight: 600; margin: 0; }
.job-title a { color: inherit; text-decoration: none; }
.job-title a:hover { color: var(--accent); }
.job-meta { color: var(--muted); font-size: 0.88rem; margin: 2px 0 8px; }
.chip { display:inline-block; font-size:0.75rem; padding:2px 8px; border-radius:999px;
        border:1px solid rgba(128,128,128,.35); margin:0 4px 4px 0; }
.chip.good { border-color:#2e9e5b; color:#2e9e5b; }
.chip.bad  { border-color:#d64545; color:#d64545; }
.chip.tool { border-color:var(--accent); color:var(--accent); }
.score { font-size:1.6rem; font-weight:700; text-align:right; line-height:1; }
.score small { display:block; font-size:0.7rem; color:var(--muted); font-weight:500; }
</style>
""",
    unsafe_allow_html=True,
)


def api_key() -> str:
    try:
        return st.secrets.get("TINYFISH_API_KEY", "") or os.environ.get("TINYFISH_API_KEY", "")
    except Exception:
        return os.environ.get("TINYFISH_API_KEY", "")


def split(text: str) -> list[str]:
    return [x.strip().lower() for x in text.replace("\n", ",").split(",") if x.strip()]


# ---------------------------------------------------------------- Sidebar
with st.sidebar:
    st.subheader("What are you looking for?")
    role = st.text_input("Role", "Machine Learning Intern")
    location = st.text_input("Location", "New York")
    remote_ok = st.checkbox("Include remote roles", True)
    seniority = st.selectbox("Level", ["Internship", "New grad", "Any level"])
    keywords = st.text_input("Skills / keywords", "python, pytorch",
                             help="Comma separated. Matched against the full job description.")
    need_visa = st.checkbox("I need visa sponsorship", False,
                            help="Reads each posting's text and pushes down roles that say they won't sponsor.")
    with st.expander("More sources"):
        companies = st.text_input("Target companies", "",
                                  help="Comma separated, e.g. Stripe, Datadog. Scout searches their boards too.")
        use_agent = st.checkbox("Deep scan Workday sites with TinyFish Agent", True,
                                help="Workday career sites need a real browser. Uses a few cents of credit per site.")
        agent_urls = st.text_area("Extra careers pages for the Agent", "",
                                  placeholder="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite")
    min_score = st.slider("Minimum match", 0, 100, 50, step=5)
    go = st.button("Find openings", type="primary", width="stretch")

# ---------------------------------------------------------------- Header
st.title("Scout")
st.markdown('<p class="sub">Live internship openings from real careers pages, matched to you. '
            "Powered by TinyFish Search, Fetch and Agent.</p>", unsafe_allow_html=True)

if go:
    if not api_key():
        st.error("Add your TinyFish API key to `.streamlit/secrets.toml` as `TINYFISH_API_KEY` (see README).")
        st.stop()
    prefs = Prefs(
        role=role.strip(), location=location.strip(), seniority=seniority,
        keywords=split(keywords), remote_ok=remote_ok, need_visa=need_visa,
        companies=[c.strip() for c in companies.split(",") if c.strip()],
        agent_urls=[u.strip() for u in agent_urls.splitlines() if u.strip().startswith("http")],
        use_agent=use_agent,
    )
    with st.status("Scouting the live web...", expanded=True) as status:
        def on_step(tool, msg):
            st.write(f"**{tool}** · {msg}")
        try:
            jobs, usage = find_jobs(prefs, api_key(), on_step=on_step)
        except TinyFishError as e:
            status.update(label="Something went wrong", state="error")
            st.error(str(e))
            st.stop()
        status.update(label=f"Done · {len(jobs)} unique openings found", state="complete", expanded=False)
    st.session_state.update(jobs=jobs, usage=usage, prefs=prefs, at=datetime.now())

if "jobs" not in st.session_state:
    st.info("Set your preferences on the left and press **Find openings**. "
            "A full scan takes about a minute.")
    st.stop()

jobs = st.session_state.jobs
usage = st.session_state.usage
prefs = st.session_state.prefs
shown = [j for j in jobs if j.score >= min_score]
if prefs.need_visa:
    hide_no = st.toggle("Hide roles that say they don't sponsor", True)
    if hide_no:
        shown = [j for j in shown if j.visa != "No sponsorship"]

# ---------------------------------------------------------------- Summary
c1, c2, c3, c4 = st.columns(4)
c1.metric("Matches", len(shown))
c2.metric("Openings scanned", len(jobs))
c3.metric("Companies", len({j.company for j in jobs}))
c4.metric("Mention sponsorship", sum(1 for j in shown if j.visa == "Sponsors"))
st.caption(f"Refreshed {st.session_state.at:%b %d, %I:%M %p}. Press Find openings again for the latest listings.")

tab_list, tab_table, tab_how = st.tabs(["Matches", "Table", "How it works"])

with tab_list:
    if not shown:
        st.warning("No openings above your minimum match. Try lowering it or broadening the role.")
    for j in shown[:60]:
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                meta = " · ".join(x for x in [j.company, j.location, j.posted_label] if x)
                chips = "".join(f'<span class="chip">{html.escape(r)}</span>' for r in j.reasons)
                visa_cls = {"Sponsors": "good", "No sponsorship": "bad"}.get(j.visa, "")
                if j.visa != "Not stated" or prefs.need_visa:
                    chips += f'<span class="chip {visa_cls}">Visa: {j.visa}</span>'
                chips += f'<span class="chip tool">{html.escape(j.source)}</span>'
                st.markdown(
                    f'<p class="job-title"><a href="{html.escape(j.url)}" target="_blank">'
                    f"{html.escape(j.title)}</a></p>"
                    f'<p class="job-meta">{html.escape(meta)}</p>{chips}',
                    unsafe_allow_html=True,
                )
            with right:
                st.markdown(f'<div class="score">{j.score}%<small>match</small></div>', unsafe_allow_html=True)
                st.link_button("Apply", j.url, width="stretch")

with tab_table:
    df = pd.DataFrame([{
        "Match": j.score, "Title": j.title, "Company": j.company, "Location": j.location,
        "Posted": j.posted_label, "Visa": j.visa, "Found by": j.source, "Apply": j.url,
    } for j in shown])
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"Apply": st.column_config.LinkColumn("Apply", display_text="Open")})
    st.download_button("Download CSV", df.to_csv(index=False), "scout_matches.csv", "text/csv")

with tab_how:
    st.markdown(
        """
**1. TinyFish Search finds where the openings are.** Scout runs a batch of searches across
Greenhouse, Lever, Ashby and Workday for your role and location. That surfaces live postings
and tells Scout which companies are hiring right now.

**2. TinyFish Fetch reads the full job boards.** For the companies Search found, Fetch reads
each company's complete job board as structured data, so Scout sees every opening, not just
the few that showed up in search. Fetch then opens the top postings and reads the full text,
which is how Scout checks visa sponsorship language, skills and location.

**3. TinyFish Agent handles sites that need a real browser.** Workday career sites only show
jobs after you type a search and wait for the page to load. The Agent does exactly that in a
real browser and returns the listings as JSON.

**4. Scout ranks the results.** Openings are de-duplicated across sources, then scored on role
match, level, location, your skills, freshness and visa policy. Each card shows why it matched.
"""
    )
    st.markdown("**This run**")
    for tool, msg in usage.log:
        st.write(f"- **{tool}** · {msg}")
    st.caption(f"{usage.searches} searches · {usage.fetch_calls} fetch calls ({usage.urls_fetched} pages) · "
               f"{usage.agent_runs} agent runs ({usage.agent_steps} steps)")
