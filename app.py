"""Internship Radar: a TinyFish-powered internship finder.

Run:  streamlit run app.py
Needs TINYFISH_API_KEY in .streamlit/secrets.toml or the environment.
"""

from __future__ import annotations

import hashlib
import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from finder import Prefs, Usage, find_jobs
from finder.tinyfish import TinyFishError

st.set_page_config(page_title="Internship Radar", page_icon="🐟", layout="wide",
                   initial_sidebar_state="collapsed")

# ---------------------------------------------------------------- Styles
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@500&display=swap');
:root {
  --bg:#faf6f0; --panel:#ffffff; --panel2:#f6f0e8; --line:#ece3d7;
  --text:#2d2621; --muted:#8c8177; --accent:#d9734e; --accent-soft:rgba(217,115,78,.12);
  --good:#5e8f6e; --bad:#c0605a; --sage:#a8bfa3; --shadow:0 1px 2px rgba(60,40,20,.04), 0 6px 20px rgba(60,40,20,.05);
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: var(--bg) !important; }
[data-testid="stAppViewContainer"] { background:
  radial-gradient(800px 380px at 90% -5%, rgba(232,180,150,.28), transparent 60%),
  radial-gradient(700px 360px at -10% 20%, rgba(168,191,163,.22), transparent 60%), var(--bg) !important; }
* { font-family: 'Inter', system-ui, sans-serif; }
.block-container { max-width: 1080px; padding-top: 3.2rem !important; padding-bottom: 4rem; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display:none; }
#MainMenu, footer { visibility: hidden; }

.eyebrow { font-family:'JetBrains Mono', monospace; font-size:.72rem; letter-spacing:.18em;
  color:var(--muted); text-transform:uppercase; display:flex; align-items:center; gap:.5rem; }
.eyebrow .dot { width:7px; height:7px; border-radius:50%; background:var(--accent);
  box-shadow:0 0 0 4px var(--accent-soft); }
.hero .h1 { font-family:'Instrument Serif', Georgia, serif !important; font-size:4rem !important; line-height:1; letter-spacing:-.01em; font-weight:400 !important;
  color:var(--text) !important; margin:.6rem 0 .5rem; padding:0 !important; }
.hero .h1 em { color:var(--accent) !important; font-style:italic; font-family:'Instrument Serif', Georgia, serif !important; }
.hero p { color:var(--muted); font-size:1.02rem; max-width:640px; margin:0 0 1.6rem; }

/* form panel */
[data-testid="stForm"] { background:var(--panel); border:1px solid var(--line) !important;
  border-radius:20px; padding:1.4rem 1.4rem .7rem; box-shadow:var(--shadow); }
label, [data-testid="stWidgetLabel"] p { color:var(--muted) !important; font-size:.8rem !important;
  font-weight:500 !important; }
input, textarea, [data-baseweb="select"] > div { background:var(--panel2) !important;
  border-color:var(--line) !important; color:var(--text) !important; border-radius:10px !important; }
[data-testid="stFormSubmitButton"] button, .stButton button[kind="primary"] {
  background:var(--accent) !important; border:none !important; color:#fff !important;
  font-weight:600 !important; border-radius:999px !important; height:2.8rem; letter-spacing:.01em;
  box-shadow:0 6px 16px rgba(217,115,78,.25); }
[data-testid="stFormSubmitButton"] button:hover { filter:brightness(1.08); }
[data-testid="stExpander"] { border:1px solid var(--line) !important; border-radius:12px !important;
  background:transparent !important; }

/* pipeline */
.pipe { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:1.4rem 0 .4rem; }
.step { position:relative; background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:14px 16px; box-shadow:var(--shadow); }
.step .arrow { position:absolute; right:-13px; top:50%; transform:translateY(-50%); color:#c4b8aa;
  font-size:.9rem; z-index:2; background:var(--bg); padding:0 1px; }
.step .big { color:var(--text); font-size:1.7rem; font-weight:700; letter-spacing:-.03em; margin:6px 0 2px; line-height:1.1; }
.step .big small { font-size:.75rem; color:var(--muted); font-weight:500; margin-left:6px; letter-spacing:0; }
.step .big.wait { color:var(--accent); animation:pulse 1.2s ease-in-out infinite; }
.step.run { border-color:rgba(217,115,78,.6); box-shadow:0 0 0 4px var(--accent-soft); }
@keyframes pulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }
.trail { font-family:'JetBrains Mono',monospace; font-size:.66rem; letter-spacing:.08em; text-transform:uppercase;
  color:var(--accent); margin:0 0 7px; }
.trail .sep { color:var(--muted); margin:0 6px; }
.step .n { font-family:'JetBrains Mono',monospace; font-size:.7rem; color:var(--accent); letter-spacing:.12em; }
.step .t { color:var(--text); font-weight:600; margin:4px 0 2px; }
.step .d { color:var(--muted); font-size:.82rem; line-height:1.4; }
.step.done { border-color:rgba(217,115,78,.35); }

/* stats */
.stats { display:flex; gap:10px; flex-wrap:wrap; margin:1.6rem 0 .3rem; }
.stat { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:10px 16px; min-width:130px; }
.stat b { display:block; color:var(--text); font-size:1.5rem; letter-spacing:-.02em; }
.stat span { color:var(--muted); font-size:.75rem; }
.fresh { color:var(--muted); font-size:.78rem; margin:.4rem 0 1rem; }

/* job cards */
.job { display:flex; gap:16px; align-items:center; background:var(--panel); border:1px solid var(--line);
  border-radius:18px; padding:16px 20px; margin-bottom:12px; box-shadow:var(--shadow);
  transition:border-color .15s, transform .15s, box-shadow .15s; }
.job:hover { border-color:rgba(217,115,78,.45); transform:translateY(-2px);
  box-shadow:0 2px 4px rgba(60,40,20,.05), 0 12px 28px rgba(60,40,20,.08); }
.logo { flex:0 0 46px; height:46px; border-radius:14px; display:flex; align-items:center; justify-content:center;
  font-family:'Instrument Serif', Georgia, serif; color:#3a2f28; font-size:1.45rem; }
.body { flex:1; min-width:0; }
.title { color:var(--text); font-weight:600; font-size:1rem; margin:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.meta { color:var(--muted); font-size:.84rem; margin:2px 0 8px; }
.chip { display:inline-block; font-size:.72rem; padding:2px 9px; border-radius:999px; margin:0 5px 4px 0;
  background:var(--panel2); border:1px solid var(--line); color:#6f655c; }
.chip.good { color:var(--good); border-color:rgba(94,143,110,.3); background:rgba(168,191,163,.22); }
.chip.bad  { color:var(--bad);  border-color:rgba(192,96,90,.3);  background:rgba(192,96,90,.08); }
.chip.src  { color:var(--accent); border-color:rgba(217,115,78,.35); background:var(--accent-soft); }
.side { display:flex; flex-direction:column; align-items:center; gap:8px; }
.ring { --p:50; width:54px; height:54px; border-radius:50%;
  background:conic-gradient(var(--accent) calc(var(--p)*1%), #f1e9de 0);
  display:flex; align-items:center; justify-content:center; }
.ring b { width:44px; height:44px; border-radius:50%; background:var(--panel); display:flex; align-items:center;
  justify-content:center; color:var(--text); font-size:.85rem; }
.apply { font-size:.78rem; font-weight:600; color:#fff !important; background:var(--accent); padding:5px 16px;
  border-radius:999px; text-decoration:none !important; }
.apply:hover { filter:brightness(1.1); }

/* tabs */
[data-baseweb="tab-list"] { gap:10px; border-bottom:1px solid var(--line); background:transparent !important; }
[data-baseweb="tab"] { color:var(--muted) !important; }
[aria-selected="true"][data-baseweb="tab"] { color:var(--text) !important; }
[data-baseweb="tab-highlight"] { background:var(--accent) !important; }
.how { background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:20px 22px; color:var(--text); box-shadow:var(--shadow); }
.how h4 { color:var(--text); margin:.2rem 0 .3rem; font-size:.98rem; }
.how p { margin:0 0 .9rem; font-size:.9rem; color:var(--muted); }
.log { font-family:'JetBrains Mono',monospace; font-size:.78rem; color:#5f564e; background:var(--panel2);
  border:1px solid var(--line); border-radius:10px; padding:12px 14px; line-height:1.7; }
.log i { color:var(--accent); font-style:normal; }
.foot { color:var(--muted); font-size:.75rem; text-align:center; margin-top:3rem; }
@media (max-width: 860px) { .pipe { grid-template-columns:1fr 1fr; } .step .arrow { display:none; } }
@media (max-width: 720px) { .pipe { grid-template-columns:1fr; } .hero .h1 { font-size:2.2rem !important; } }
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


def logo_color(name: str) -> str:
    palette = ["#f4d6c6", "#dfe8d6", "#e9dcef", "#f6e3b8", "#d6e4ee", "#f2d4d7", "#e4ddd0", "#d5e6e1"]
    return palette[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(palette)]


def esc(s) -> str:
    return html.escape(str(s or ""))


# ---------------------------------------------------------------- Hero + form
st.markdown(
    """
<div class="hero">
  <div class="eyebrow"><span class="dot"></span>TinyFish × CUB Columbia AI Club</div>
  <div class="h1">Internship <em>Radar</em></div>
  <p>Live openings pulled from real company careers pages, matched to what you want
  and ranked with reasons. No stale listings, no refreshing ten tabs.</p>
</div>
""",
    unsafe_allow_html=True,
)

with st.form("search_form", border=False):
    c1, c2, c3 = st.columns([2.2, 1.4, 1])
    role = c1.text_input("Role", "Machine Learning Intern")
    location = c2.text_input("Location", "New York")
    seniority = c3.selectbox("Level", ["Internship", "New grad", "Any level"])
    c4, c5, c6 = st.columns([2.2, 1.4, 1])
    keywords = c4.text_input("Skills", "python, pytorch", help="Comma separated. Matched against the full job description.")
    need_visa = c5.toggle("I need visa sponsorship", False,
                          help="Reads each posting and pushes down roles that say they won't sponsor.")
    remote_ok = c5.toggle("Include remote", True)
    min_score = c6.slider("Min match", 0, 100, 50, step=5)
    with st.expander("More sources"):
        e1, e2 = st.columns(2)
        companies = e1.text_input("Target companies", "", placeholder="Stripe, Datadog, Jane Street")
        agent_urls = e2.text_input("Extra careers page for the Agent", "",
                                   placeholder="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite")
        use_agent = st.toggle("Deep scan Workday sites with TinyFish Agent (a few cents per site)", True)
    go = st.form_submit_button("Scan the live web  →", type="primary", width="stretch")


# ---------------------------------------------------------------- Pipeline strip
STEPS = [
    ("01", "Search", "Finds live postings on Greenhouse, Lever, Ashby and Workday, and who is hiring."),
    ("02", "Fetch", "Reads each company's full job board, then opens top postings for visa policy and skills."),
    ("03", "Agent", "Operates Workday career sites in a real browser: types the search, waits, extracts."),
    ("04", "Score", "De-duplicates every source and ranks each opening on fit, with reasons."),
]


def pipeline(usage=None, running=None, matches=None):
    stats = usage.stats if usage else {}
    seen = {t for t, _ in usage.log} if usage else set()
    figures = {
        "Search": (stats.get("postings"), "postings found",
                   f"{stats.get('companies', 0)} companies · {stats.get('workday', 0)} Workday sites · "
                   f"{stats.get('searches', 0)} searches"),
        "Fetch": (stats.get("board_openings"), "openings read",
                  f"{stats.get('boards', 0)} full job boards · {stats.get('postings_read', 0)} postings opened"),
        "Agent": (stats.get("agent_listings"), "listings extracted",
                  f"{stats.get('agent_sites', 0)} Workday sites in a real browser"),
        "Score": (matches if matches is not None else stats.get("unique"), "matches" if matches is not None else "ranked",
                  f"{stats.get('unique', 0)} unique openings ranked · top match {stats.get('top', 0)}"),
    }
    cells = []
    for n, tool, desc in STEPS:
        num, label, detail = figures[tool]
        if tool in seen and num is not None:
            state, body = "done", (f'<div class="big">{num:,}<small>{label}</small></div>'
                                   f'<div class="d">{esc(detail)}</div>')
        elif running == tool:
            state, body = "run", f'<div class="big wait">···<small>working</small></div><div class="d">{desc}</div>'
        else:
            state, body = "", f'<div class="d">{desc}</div>'
        arrow = '<div class="arrow">→</div>' if n != "04" else ""
        brand = "RADAR" if tool == "Score" else "TINYFISH"
        cells.append(f'<div class="step {state}"><div class="n">{n} · {brand} {tool.upper()}'
                     f'</div><div class="t">{tool}</div>{body}{arrow}</div>')
    return f'<div class="pipe">{"".join(cells)}</div>'


pipe_slot = st.empty()
pipe_slot.markdown(pipeline(st.session_state.get("usage"), matches=st.session_state.get("matches")),
                   unsafe_allow_html=True)

if go:
    if not api_key():
        st.error("Add your TinyFish API key to `.streamlit/secrets.toml` as `TINYFISH_API_KEY` (see README).")
        st.stop()
    prefs = Prefs(
        role=role.strip(), location=location.strip(), seniority=seniority,
        keywords=split(keywords), remote_ok=remote_ok, need_visa=need_visa,
        companies=[c.strip() for c in companies.split(",") if c.strip()],
        agent_urls=[agent_urls.strip()] if agent_urls.strip().startswith("http") else [],
        use_agent=use_agent,
    )
    live = Usage()
    pipe_slot.markdown(pipeline(live, running="Search"), unsafe_allow_html=True)

    def on_step(tool, msg):
        tools = [t for t, _ in live.log]
        if tool == "Search":
            nxt = "Fetch"
        elif tool == "Fetch" and tools.count("Fetch") == 1:
            nxt = "Agent" if prefs.use_agent else "Score"
        elif tool == "Score":
            nxt = None
        else:
            nxt = "Score"
        pipe_slot.markdown(pipeline(live, running=nxt), unsafe_allow_html=True)

    with st.spinner("Scanning careers pages. This takes about a minute..."):
        try:
            jobs, usage = find_jobs(prefs, api_key(), on_step=on_step, usage=live)
        except TinyFishError as e:
            st.error(str(e))
            st.stop()
    st.session_state.update(jobs=jobs, usage=usage, prefs=prefs, at=datetime.now(ZoneInfo("America/New_York")), min_score=min_score)
    matches = len([j for j in jobs if j.score >= min_score and not (need_visa and j.visa == "No sponsorship")])
    st.session_state.matches = matches
    pipe_slot.markdown(pipeline(usage, matches=matches), unsafe_allow_html=True)

if "jobs" not in st.session_state:
    st.markdown('<div class="foot">Built with TinyFish Search, Fetch and Agent</div>', unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------- Results
jobs = st.session_state.jobs
usage = st.session_state.usage
prefs = st.session_state.prefs
floor = min_score
shown = [j for j in jobs if j.score >= floor]
if prefs.need_visa:
    shown = [j for j in shown if j.visa != "No sponsorship"]

companies_n = len({j.company for j in shown})
sponsor_n = sum(1 for j in shown if j.visa == "Sponsors")
st.markdown(
    f"""<div class="fresh">Live results · refreshed {st.session_state.at:%b %d, %I:%M %p} ET · scan again for the latest</div>""",
    unsafe_allow_html=True,
)

tab_list, tab_table, tab_how = st.tabs(["Matches", "Results table", "How it works"])

with tab_list:
    if not shown:
        st.info("No openings above your minimum match. Try lowering it or broadening the role.")
    cards = []
    for j in shown[:60]:
        initial = (j.company[:1] or "?").upper()
        meta = " · ".join(esc(x) for x in [j.company, j.location, j.posted_label] if x)
        chips = "".join(f'<span class="chip">{esc(r)}</span>' for r in j.reasons)
        if j.visa != "Not stated" or prefs.need_visa:
            cls = {"Sponsors": "good", "No sponsorship": "bad"}.get(j.visa, "")
            chips += f'<span class="chip {cls}">Visa: {esc(j.visa)}</span>'
        chips += f'<span class="chip">{esc(j.source)}</span>'
        trail = ["Search", "Fetch"] if j.tool == "Fetch" else ["Search", "Agent"] if j.tool == "Agent" else ["Search"]
        if j.read and "Fetch" not in trail:
            trail.append("Fetch")
        trail.append("Score")
        trail_html = '<span class="sep">→</span>'.join(f"<span>{t}</span>" for t in trail)
        cards.append(
            f'<div class="job"><div class="logo" style="background:{logo_color(j.company)}">{esc(initial)}</div>'
            f'<div class="body"><p class="title" title="{esc(j.title)}">{esc(j.title)}</p>'
            f'<div class="meta">{meta}</div><div class="trail">{trail_html}</div>{chips}</div>'
            f'<div class="side"><div class="ring" style="--p:{j.score}"><b>{j.score}</b></div>'
            f'<a class="apply" href="{esc(j.url)}" target="_blank">Apply</a></div></div>'
        )
    st.markdown("".join(cards), unsafe_allow_html=True)

with tab_table:
    df = pd.DataFrame([{
        "Company": j.company, "Role": j.title, "Location": j.location, "Link": j.url,
        "Match": j.score, "Posted": j.posted_label, "Visa": j.visa, "Found by": j.source,
    } for j in shown])
    st.dataframe(df, width="stretch", hide_index=True, height=520,
                 column_config={
                     "Link": st.column_config.LinkColumn("Link", display_text="Apply"),
                     "Match": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%d"),
                 })
    st.download_button("Download CSV", df.to_csv(index=False), "internship_radar.csv", "text/csv")

with tab_how:
    log_html = "<br>".join(f"<i>{esc(t)}</i> · {esc(m)}" for t, m in usage.log)
    st.markdown(
        f"""<div class="how">
<h4>1 · TinyFish Search finds where the openings are</h4>
<p>A batch of searches across Greenhouse, Lever, Ashby and Workday for your role and location surfaces live
postings and tells Radar which companies are hiring right now.</p>
<h4>2 · TinyFish Fetch reads the full job boards and postings</h4>
<p>For the companies Search found, Fetch reads each complete job board as structured data, so Radar sees every
opening, not just the few in search results. It then opens the top postings to check visa language, skills and location.</p>
<h4>3 · TinyFish Agent handles sites that need a real browser</h4>
<p>Workday career sites only show jobs after you type a search and wait. The Agent does that in a real browser
and returns the listings as JSON.</p>
<h4>4 · Radar ranks the results</h4>
<p>Openings are de-duplicated across sources, then scored on role, level, location, skills, freshness and visa
policy. Every card shows why it matched.</p>
<div class="log">{log_html}<br><br>{usage.searches} searches · {usage.fetch_calls} fetch calls ({usage.urls_fetched} pages) ·
{usage.agent_runs} agent runs ({usage.agent_steps} steps)</div>
</div>""",
        unsafe_allow_html=True,
    )

st.markdown('<div class="foot">Built with TinyFish Search, Fetch and Agent · '
            '<a href="https://github.com/kohnicholas1/Scout" style="color:inherit">source</a></div>',
            unsafe_allow_html=True)
