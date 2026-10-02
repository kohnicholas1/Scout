"""Snag: a TinyFish-powered internship finder.

Run:  streamlit run app.py
Secrets (.streamlit/secrets.toml or Streamlit Cloud → Settings → Secrets):
  TINYFISH_API_KEY = "..."      required
  OWNER_CODE = "..."            optional, unlocks "My LinkedIn" (signed-in browsing + Apply with Agent)
"""

from __future__ import annotations

import hashlib
import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from finder import Prefs, Usage, find_jobs, linkedin
from finder.resume import extract_text, find_skills
from finder.tinyfish import TinyFish, TinyFishError

st.set_page_config(page_title="Snag · internships, snagged for you", page_icon="🐟", layout="wide",
                   initial_sidebar_state="collapsed")


def secret(name: str) -> str:
    try:
        return st.secrets.get(name, "") or os.environ.get(name, "")
    except Exception:
        return os.environ.get(name, "")


def esc(s) -> str:
    return html.escape(str(s or ""))


def split(text: str) -> list[str]:
    return [x.strip().lower() for x in text.replace("\n", ",").split(",") if x.strip()]


def logo_color(name: str) -> str:
    palette = ["#ffe1d2", "#e2f3e8", "#ece6ff", "#fff1c9", "#dcefff", "#ffe0e6", "#efe9df", "#d9f3ef"]
    return palette[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(palette)]


# ======================================================================= styles
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@500&display=swap');
:root {
  --bg:#fbf8f4; --panel:#ffffff; --panel2:#f6f1ea; --line:#ece4d9; --text:#1f1b17; --muted:#857a70;
  --accent:#ff7a45; --accent2:#ffa56b; --accent-soft:rgba(255,122,69,.12); --good:#3f9a6b; --bad:#d0605a;
  --shadow:0 1px 2px rgba(60,40,20,.04), 0 10px 30px rgba(60,40,20,.06);
}
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] { background:var(--bg) !important; }
[data-testid="stAppViewContainer"] { background:
  radial-gradient(700px 420px at 92% 4%, rgba(255,190,150,.45), transparent 60%),
  radial-gradient(600px 380px at 62% 18%, rgba(205,195,255,.35), transparent 60%),
  radial-gradient(640px 400px at 2% 40%, rgba(190,235,212,.35), transparent 60%), var(--bg) !important; }
[data-testid="stHeader"] { background:transparent !important; }
* { font-family:'Inter', system-ui, sans-serif; }
.block-container { max-width:1160px; padding-top:1.2rem !important; padding-bottom:4rem; }
[data-testid="stSidebar"], [data-testid="collapsedControl"], #MainMenu, footer { display:none !important; }
a { color:inherit; }

/* nav */
.nav { display:flex; align-items:center; justify-content:space-between; padding:6px 0 10px; }
.brand { display:flex; align-items:center; gap:10px; font-weight:700; color:var(--text); font-size:1.02rem; letter-spacing:-.01em; }
.brand .mark { width:30px; height:30px; border-radius:9px; background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:grid; place-items:center; box-shadow:0 6px 14px rgba(255,122,69,.35); }
.brand .mark i { width:12px; height:12px; border:2.5px solid #fff; border-radius:50%; display:block; }
.navlinks { display:flex; gap:26px; align-items:center; font-size:.88rem; color:var(--muted); }
.navlinks a, .navlinks a:visited { text-decoration:none !important; color:var(--muted) !important; } .navlinks a:hover { color:var(--text) !important; }
.pill { font-size:.78rem; padding:6px 12px; border-radius:999px; background:#fff; border:1px solid var(--line);
  color:var(--text); display:inline-flex; gap:8px; align-items:center; box-shadow:var(--shadow); }
.pill .dot { width:7px; height:7px; border-radius:50%; background:#3fbf7f; box-shadow:0 0 0 4px rgba(63,191,127,.18); }

/* hero */
.hero { display:grid; grid-template-columns:1.25fr .95fr; gap:24px; align-items:center; min-height:560px; padding:10px 0 20px; }
.hero h1 { font-size:3.55rem !important; line-height:.98 !important; letter-spacing:-.045em !important; font-weight:800 !important;
  color:var(--text) !important; margin:18px 0 18px !important; padding:0 !important; }
.hero h1 em { font-family:'Instrument Serif', Georgia, serif !important; font-style:italic; font-weight:400;
  letter-spacing:-.01em; background:linear-gradient(120deg,var(--accent),#ff5f8a); -webkit-background-clip:text;
  background-clip:text; color:transparent !important; padding-right:.06em; }
.hero p.lead { color:var(--muted); font-size:1.12rem; line-height:1.55; max-width:480px; margin:0 0 26px; }
.ctas { display:flex; gap:12px; flex-wrap:wrap; }
.btn { display:inline-flex; align-items:center; gap:10px; padding:14px 22px; border-radius:999px; font-weight:600;
  font-size:.95rem; text-decoration:none !important; transition:transform .15s, box-shadow .15s; }
.btn.primary { background:var(--text); color:#fff !important; box-shadow:0 10px 24px rgba(31,27,23,.22); }
.btn.primary span { width:24px; height:24px; border-radius:50%; background:var(--accent); display:grid; place-items:center; }
.btn.ghost { background:#fff; color:var(--text) !important; border:1px solid var(--line); }
.btn:hover { transform:translateY(-2px); }
.mini-stats { display:flex; gap:28px; margin-top:34px; }
.mini-stats b { display:block; font-size:1.5rem; color:var(--text); letter-spacing:-.03em; }
.mini-stats span { font-size:.78rem; color:var(--muted); }

/* claw scene */
.scene { position:relative; height:540px; perspective:1100px; }
.cable { position:absolute; left:50%; top:10px; width:3px; height:70px; margin-left:-1.5px;
  background:linear-gradient(#c9c2b8,#9d958b); border-radius:2px; animation:bob 5s ease-in-out infinite; }
.rig { position:absolute; left:50%; top:60px; width:340px; margin-left:-170px; animation:bob 5s ease-in-out infinite; z-index:3; }
.rig svg { position:absolute; left:0; top:0; width:340px; height:300px; z-index:4; filter:drop-shadow(0 10px 14px rgba(60,40,20,.18)); }
.gcard { position:absolute; left:52px; top:104px; width:236px; height:150px; border-radius:20px; z-index:3; color:#fff;
  padding:18px 20px; transform:rotateX(14deg) rotateZ(-7deg); transform-origin:50% 0; animation:swing 5s ease-in-out infinite;
  background:linear-gradient(135deg,#ff8a50 0%,#ff6a3d 45%,#ff4f6d 100%);
  box-shadow:0 30px 50px rgba(255,100,70,.35), inset 0 1px 0 rgba(255,255,255,.45); overflow:hidden; }
.gcard:before { content:""; position:absolute; inset:0; background:linear-gradient(115deg,rgba(255,255,255,.45) 0%,
  rgba(255,255,255,0) 38%); pointer-events:none; }
.gcard .top { display:flex; justify-content:space-between; align-items:center; font-size:.7rem; letter-spacing:.14em;
  font-family:'JetBrains Mono', monospace; opacity:.92; }
.gcard .chip { width:34px; height:26px; border-radius:6px; background:linear-gradient(135deg,#ffe3b0,#f3b765); opacity:.95; }
.gcard .role { font-size:1.12rem; font-weight:700; margin-top:14px; letter-spacing:-.01em; }
.gcard .co { font-size:.82rem; opacity:.9; margin-top:2px; }
.gcard .match { background:rgba(255,255,255,.95); color:#ff5a48; font-weight:800; font-size:.72rem;
  padding:4px 10px; border-radius:999px; letter-spacing:0; font-family:'Inter',sans-serif; }
.pile { position:absolute; left:0; right:0; bottom:0; height:200px; z-index:1; }
.pcard { position:absolute; width:220px; height:130px; border-radius:18px; padding:14px 16px; background:#fff;
  border:1px solid var(--line); box-shadow:var(--shadow); font-size:.78rem; color:var(--muted); }
.pcard b { display:block; color:var(--text); font-size:.92rem; margin:22px 0 2px; }
.pcard .bar { height:6px; width:60%; border-radius:4px; background:var(--panel2); margin-top:10px; }
.pcard.p1 { left:2%;  bottom:12px; transform:rotate(-13deg); background:#f3efff; }
.pcard.p2 { left:34%; bottom:-6px; transform:rotate(4deg); z-index:2; }
.pcard.p3 { right:0;  bottom:20px; transform:rotate(14deg); background:#eaf7ef; }
.spark { position:absolute; color:var(--accent); font-size:20px; animation:twinkle 3s ease-in-out infinite; }
.spark.s1 { left:8%; top:120px; } .spark.s2 { right:6%; top:70px; animation-delay:1s; color:#9b8cff; }
.spark.s3 { right:16%; top:300px; animation-delay:2s; color:#3fbf7f; font-size:14px; }
@keyframes bob { 0%,100% { transform:translateY(0) } 50% { transform:translateY(-14px) } }
@keyframes swing { 0%,100% { transform:rotateX(14deg) rotateZ(-7deg) } 50% { transform:rotateX(10deg) rotateZ(-3deg) } }
@keyframes twinkle { 0%,100% { opacity:.25; transform:scale(.8) } 50% { opacity:1; transform:scale(1.1) } }

/* sources strip */
.strip { display:flex; align-items:center; gap:34px; justify-content:center; flex-wrap:wrap; padding:18px 0 8px;
  color:#a39889; font-weight:700; letter-spacing:-.01em; font-size:1.05rem; }
.strip small { font-weight:500; font-size:.72rem; font-family:'JetBrains Mono',monospace; letter-spacing:.14em; color:var(--muted); }

/* section heads */
.sec { margin:56px 0 18px; display:flex; justify-content:space-between; align-items:flex-end; gap:20px; flex-wrap:wrap; }
.sec .k { font-family:'JetBrains Mono',monospace; font-size:.72rem; letter-spacing:.16em; color:var(--accent); }
.sec h2 { font-size:2.4rem !important; letter-spacing:-.035em !important; font-weight:800 !important; margin:6px 0 0 !important;
  color:var(--text) !important; padding:0 !important; }
.sec h2 em { font-family:'Instrument Serif', Georgia, serif !important; font-weight:400; font-style:italic; color:var(--accent) !important; }
.sec p { color:var(--muted); max-width:380px; margin:0; font-size:.95rem; }

/* form */
[data-testid="stForm"] { background:rgba(255,255,255,.85); backdrop-filter:blur(8px); border:1px solid var(--line) !important;
  border-radius:24px; padding:1.5rem 1.5rem .8rem; box-shadow:var(--shadow); }
[data-testid="stWidgetLabel"] p { color:var(--muted) !important; font-size:.78rem !important; font-weight:600 !important;
  letter-spacing:.02em; }
[data-testid="stTextInputRootElement"], [data-testid="stSelectbox"] [role="group"] {
  background:var(--panel2) !important; border:1px solid var(--line) !important; border-radius:14px !important;
  box-shadow:none !important; overflow:hidden; transition:border-color .15s, box-shadow .15s; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stSelectbox"] [role="group"]:focus-within {
  border-color:var(--accent) !important; box-shadow:0 0 0 4px var(--accent-soft) !important; }
[data-testid="stTextInputRootElement"] *, [data-testid="stSelectbox"] [role="group"] * { background:transparent !important; }
input, textarea { color:var(--text) !important; -webkit-text-fill-color:var(--text) !important; caret-color:var(--accent) !important; }
input::placeholder { color:#b6ab9f !important; -webkit-text-fill-color:#b6ab9f !important; }
[data-testid="stSelectbox"] button svg { color:var(--muted) !important; }
[data-testid="stSelectboxVirtualDropdown"] { background:#fff !important; border:1px solid var(--line) !important;
  border-radius:14px !important; box-shadow:0 14px 34px rgba(60,40,20,.14) !important; padding:4px !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="listbox"] { background:transparent !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"] { background:transparent !important; color:var(--text) !important; border-radius:10px !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"] * { color:inherit !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"][data-focused="true"],
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover { background:var(--panel2) !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"][data-selected="true"] { color:var(--accent) !important; font-weight:600; }
[data-testid="stCheckbox"] label > div:first-of-type { background:#e8dfd4 !important; border:none !important; }
[data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type { background:var(--accent) !important; }
[data-testid="stCheckbox"] label > div:first-of-type > div { background:#fff !important; box-shadow:0 1px 3px rgba(60,40,20,.25) !important; }
[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p { color:var(--text) !important; font-size:.88rem !important; font-weight:500 !important; }
[data-testid="stSlider"] [style*="translate(-50%, -50%)"] { background:var(--accent) !important; border:3px solid #fff !important; box-shadow:0 1px 4px rgba(60,40,20,.3) !important; }
[data-testid="stSliderThumbValue"] p { color:var(--accent) !important; }
[data-testid="stExpander"] details { background:var(--panel2) !important; border:1px solid var(--line) !important; border-radius:16px !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * { color:var(--text) !important; background:transparent !important; }
[data-testid="stFileUploaderDropzone"] { background:var(--panel2) !important; border:1.5px dashed #dccfbf !important; border-radius:14px !important; }
[data-testid="stFileUploaderDropzone"] * { color:var(--muted) !important; }
[data-testid="stFileUploaderDropzone"] button { background:#fff !important; border:1px solid var(--line) !important; color:var(--text) !important; border-radius:999px !important; }
[data-testid="stTooltipIcon"] svg { color:#c7bcae !important; }
[data-testid="stFormSubmitButton"] button, .stButton button[kind="primary"] {
  background:linear-gradient(135deg,var(--accent),#ff5f6d) !important; border:none !important; color:#fff !important;
  font-weight:700 !important; border-radius:999px !important; height:3rem; font-size:1rem !important;
  box-shadow:0 12px 26px rgba(255,100,80,.32) !important; }
.stButton button[kind="secondary"] { background:#fff !important; color:var(--text) !important; border:1px solid var(--line) !important;
  border-radius:999px !important; font-weight:600 !important; }
[data-testid="stAlert"] { border-radius:14px !important; }

/* pipeline */
.pipe { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:22px 0 6px; }
.step { position:relative; background:#fff; border:1px solid var(--line); border-radius:18px; padding:16px 18px; box-shadow:var(--shadow); }
.step .n { font-family:'JetBrains Mono',monospace; font-size:.68rem; color:var(--accent); letter-spacing:.12em; }
.step .t { color:var(--text); font-weight:700; margin:6px 0 2px; }
.step .d { color:var(--muted); font-size:.82rem; line-height:1.45; }
.step .big { color:var(--text); font-size:1.8rem; font-weight:800; letter-spacing:-.04em; margin:6px 0 2px; line-height:1.1; }
.step .big small { font-size:.74rem; color:var(--muted); font-weight:500; margin-left:6px; letter-spacing:0; }
.step .big.wait { color:var(--accent); animation:pulse 1.2s ease-in-out infinite; }
.step.done { border-color:rgba(255,122,69,.35); }
.step.run { border-color:var(--accent); box-shadow:0 0 0 5px var(--accent-soft); }
.step .arrow { position:absolute; right:-14px; top:50%; transform:translateY(-50%); color:#cdbfb0; z-index:2; }
@keyframes pulse { 0%,100% { opacity:.35 } 50% { opacity:1 } }

/* results */
.fresh { color:var(--muted); font-size:.8rem; margin:14px 0 6px; }
[data-baseweb="tab-list"] { gap:8px; border-bottom:1px solid var(--line); background:transparent !important; }
[data-baseweb="tab"] { color:var(--muted) !important; background:transparent !important; }
[aria-selected="true"][data-baseweb="tab"] { color:var(--text) !important; }
[data-baseweb="tab-highlight"] { background:var(--accent) !important; }
.job { display:flex; gap:16px; align-items:center; background:#fff; border:1px solid var(--line); border-radius:20px;
  padding:16px 20px; margin-bottom:12px; box-shadow:var(--shadow); transition:transform .15s, box-shadow .15s, border-color .15s; }
.job:hover { transform:translateY(-2px); border-color:rgba(255,122,69,.45); box-shadow:0 14px 34px rgba(60,40,20,.10); }
.logo { flex:0 0 48px; height:48px; border-radius:14px; display:grid; place-items:center; overflow:hidden;
  font-family:'Instrument Serif', Georgia, serif; color:#3a2f28; font-size:1.5rem; border:1px solid rgba(0,0,0,.04); }
.logo img { width:100%; height:100%; object-fit:cover; }
.body { flex:1; min-width:0; }
.title { color:var(--text); font-weight:650; font-size:1.02rem; margin:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.meta { color:var(--muted); font-size:.84rem; margin:2px 0 6px; }
.trail { font-family:'JetBrains Mono',monospace; font-size:.64rem; letter-spacing:.1em; text-transform:uppercase; color:var(--accent); margin:0 0 7px; }
.trail .sep { color:#cdbfb0; margin:0 6px; }
.chip { display:inline-block; font-size:.72rem; padding:3px 10px; border-radius:999px; margin:0 5px 4px 0;
  background:var(--panel2); border:1px solid var(--line); color:#6f655c; }
.chip.good { color:var(--good); border-color:rgba(63,154,107,.3); background:#e9f6ee; }
.chip.bad { color:var(--bad); border-color:rgba(208,96,90,.3); background:#fbecea; }
.chip.li { color:#0a66c2; border-color:rgba(10,102,194,.25); background:#e8f1fb; }
.side { display:flex; flex-direction:column; align-items:center; gap:8px; }
.ring { --p:50; width:56px; height:56px; border-radius:50%; display:grid; place-items:center;
  background:conic-gradient(var(--accent) calc(var(--p)*1%), #f1e9de 0); }
.ring b { width:46px; height:46px; border-radius:50%; background:#fff; display:grid; place-items:center; color:var(--text); font-size:.86rem; }
.apply { font-size:.78rem; font-weight:700; color:#fff !important; background:var(--text); padding:6px 16px; border-radius:999px; text-decoration:none !important; }
.apply:hover { background:var(--accent); }
.how { background:#fff; border:1px solid var(--line); border-radius:20px; padding:22px 24px; box-shadow:var(--shadow); }
.how h4 { color:var(--text); margin:.2rem 0 .3rem; font-size:1rem; }
.how p { margin:0 0 1rem; font-size:.9rem; color:var(--muted); }
.log { font-family:'JetBrains Mono',monospace; font-size:.76rem; color:#5f564e; background:var(--panel2);
  border:1px solid var(--line); border-radius:12px; padding:12px 14px; line-height:1.75; }
.log i { color:var(--accent); font-style:normal; }
.me { background:linear-gradient(135deg,#eef5ff,#fff); border:1px solid #d6e5f7; border-radius:20px; padding:18px 20px; margin:6px 0 14px; }
.me h4 { margin:0 0 4px; color:var(--text); } .me p { margin:0; color:var(--muted); font-size:.88rem; }
.foot { color:var(--muted); font-size:.78rem; text-align:center; margin-top:3.5rem; }
@media (max-width: 900px) { .hero { grid-template-columns:1fr; } .scene { height:460px; } .hero h1 { font-size:3rem !important; }
  .pipe { grid-template-columns:1fr 1fr; } .step .arrow, .navlinks a { display:none; } }
</style>
""",
    unsafe_allow_html=True,
)

# ======================================================================= hero
CLAW_SVG = """
<svg viewBox="0 0 340 300" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="metal" x1="0" x2="1"><stop offset="0" stop-color="#d9d4cc"/><stop offset=".45" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#b9b1a6"/></linearGradient>
    <linearGradient id="metal2" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#f4f1ec"/><stop offset="1" stop-color="#bdb5aa"/></linearGradient>
  </defs>
  <rect x="140" y="0" width="60" height="22" rx="8" fill="url(#metal)"/>
  <rect x="118" y="18" width="104" height="44" rx="16" fill="url(#metal)" stroke="#cfc7bc"/>
  <circle cx="170" cy="40" r="8" fill="#ff7a45"/><circle cx="170" cy="40" r="3.5" fill="#fff"/>
  <path d="M128 52 C 70 70, 32 120, 40 178 C 44 205, 56 222, 72 232" fill="none" stroke="url(#metal2)" stroke-width="16" stroke-linecap="round"/>
  <path d="M212 52 C 270 70, 308 120, 300 178 C 296 205, 284 222, 268 232" fill="none" stroke="url(#metal2)" stroke-width="16" stroke-linecap="round"/>
  <path d="M72 232 l 22 -6" stroke="#b9b1a6" stroke-width="12" stroke-linecap="round"/>
  <path d="M268 232 l -22 -6" stroke="#b9b1a6" stroke-width="12" stroke-linecap="round"/>
  <circle cx="128" cy="54" r="9" fill="#e9e4dc" stroke="#c4bcb1"/><circle cx="212" cy="54" r="9" fill="#e9e4dc" stroke="#c4bcb1"/>
</svg>"""

st.markdown(
    f"""
<div class="nav">
  <div class="brand"><div class="mark"><i></i></div>Snag</div>
  <div class="navlinks"><a href="#how">How it works</a><a href="#search">Find roles</a>
    <span class="pill"><span class="dot"></span>Live · powered by TinyFish</span></div>
</div>
<div class="hero">
  <div>
    <span class="pill">✦ Greenhouse · Lever · Ashby · Workday · LinkedIn</span>
    <h1>We already snagged<br>the <em>best ones.</em></h1>
    <p class="lead">Tell us the role you want. We scan real company careers pages and LinkedIn live, read every
    posting, and hand you a shortlist ranked by how well each one fits you.</p>
    <div class="ctas">
      <a class="btn primary" href="#search">Find my internships <span>↓</span></a>
      <a class="btn ghost" href="#how">How it works</a>
    </div>
    <div class="mini-stats">
      <div><b>~1 min</b><span>per full scan</span></div>
      <div><b>700+</b><span>openings read per scan</span></div>
      <div><b>5</b><span>live job sources</span></div>
    </div>
  </div>
  <div class="scene">
    <div class="cable"></div>
    <div class="rig">
      {CLAW_SVG}
      <div class="gcard">
        <div class="top"><span>BEST MATCH</span><span class="match">98% match</span></div>
        <div class="role">Machine Learning Intern</div>
        <div class="co">Pinterest · New York</div>
      </div>
    </div>
    <div class="pile">
      <div class="pcard p1">Stripe<b>Data Science Intern</b>San Francisco<div class="bar"></div></div>
      <div class="pcard p2">Datadog<b>Research Science Intern</b>New York<div class="bar"></div></div>
      <div class="pcard p3">NVIDIA<b>AI Research Intern</b>Santa Clara<div class="bar"></div></div>
    </div>
    <span class="spark s1">✦</span><span class="spark s2">✦</span><span class="spark s3">✦</span>
  </div>
</div>
<div class="strip"><small>READS LIVE FROM</small>Greenhouse<span>Lever</span><span>Ashby</span><span>Workday</span><span>LinkedIn</span></div>
""",
    unsafe_allow_html=True,
)

# ======================================================================= form
st.markdown(
    """<div id="search"></div><div class="sec"><div><div class="k">01 · YOUR SEARCH</div>
<h2>Tell us what you <em>want.</em></h2></div>
<p>Everything is optional except the role. Add a résumé and we'll match on your real skills.</p></div>""",
    unsafe_allow_html=True,
)

owner_code = secret("OWNER_CODE")

with st.form("search_form", border=False):
    c1, c2, c3 = st.columns([2.2, 1.4, 1])
    role = c1.text_input("ROLE OR JOB TITLE", "Machine Learning Intern")
    location = c2.text_input("LOCATION", "New York")
    seniority = c3.selectbox("LEVEL", ["Internship", "New grad", "Any level"])
    c4, c5, c6 = st.columns([2.2, 1.4, 1])
    keywords = c4.text_input("SKILLS", "python, pytorch", help="Comma separated. Matched against the full job description.")
    need_visa = c5.toggle("I need visa sponsorship", False,
                          help="Reads each posting and pushes down roles that say they won't sponsor.")
    remote_ok = c5.toggle("Include remote", True)
    min_score = c6.slider("MIN MATCH", 0, 100, 50, step=5)
    r1, r2 = st.columns([2.2, 2.4])
    resume = r1.file_uploader("RÉSUMÉ (OPTIONAL)", type=["pdf", "docx", "txt"],
                              help="Read in memory to pull out your skills. Never stored.")
    with r2:
        with st.expander("More sources"):
            use_linkedin = st.toggle("Search LinkedIn jobs", True)
            use_agent = st.toggle("Deep scan Workday sites with the Agent (a few cents each)", True)
            companies = st.text_input("TARGET COMPANIES", "", placeholder="Stripe, Datadog, Jane Street")
            agent_urls = st.text_input("EXTRA CAREERS PAGE FOR THE AGENT", "",
                                       placeholder="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite")
        with st.expander("My LinkedIn · sign in and apply with Agent"):
            st.caption("Browses LinkedIn signed in as you, using the LinkedIn browser profile saved in your "
                       "TinyFish account, and lets the Agent apply with Easy Apply. Owner only.")
            code = st.text_input("OWNER CODE", "", type="password")
            linkedin_me = st.toggle("Use my LinkedIn", False)
    go = st.form_submit_button("Scan the live web  →", type="primary", width="stretch")

me_unlocked = bool(owner_code) and code == owner_code


# ======================================================================= pipeline
STEPS = [
    ("01", "Search", "Finds live postings on Greenhouse, Lever, Ashby and Workday, and who is hiring."),
    ("02", "Fetch", "Reads full company job boards and LinkedIn, then opens top postings for visa and skills."),
    ("03", "Agent", "Operates Workday sites and your LinkedIn in a real browser: types, waits, extracts."),
    ("04", "Score", "De-duplicates every source and ranks each opening on fit, with reasons."),
]


def pipeline(usage=None, running=None, matches=None):
    stats = usage.stats if usage else {}
    seen = {t for t, _ in usage.log} if usage else set()
    figures = {
        "Search": (stats.get("postings"), "postings found",
                   f"{stats.get('companies', 0)} companies · {stats.get('workday', 0)} Workday sites · {stats.get('searches', 0)} searches"),
        "Fetch": ((stats.get("board_openings") or 0) + (stats.get("linkedin") or 0), "openings read",
                  f"{stats.get('boards', 0)} job boards · {stats.get('linkedin', 0)} LinkedIn listings · {stats.get('postings_read', 0)} postings opened"),
        "Agent": (stats.get("agent_listings"), "listings extracted", f"{stats.get('agent_sites', 0)} sites in a real browser"),
        "Score": (matches if matches is not None else stats.get("unique"), "matches" if matches is not None else "ranked",
                  f"{stats.get('unique', 0)} unique openings ranked · top match {stats.get('top', 0)}"),
    }
    cells = []
    for n, tool, desc in STEPS:
        num, label, detail = figures[tool]
        if tool in seen and num is not None:
            body = f'<div class="big">{num:,}<small>{label}</small></div><div class="d">{esc(detail)}</div>'
            state = "done"
        elif running == tool:
            body, state = f'<div class="big wait">···<small>working</small></div><div class="d">{desc}</div>', "run"
        else:
            body, state = f'<div class="d">{desc}</div>', ""
        brand = "SNAG" if tool == "Score" else "TINYFISH"
        arrow = '<div class="arrow">→</div>' if n != "04" else ""
        cells.append(f'<div class="step {state}"><div class="n">{n} · {brand} {tool.upper()}</div>'
                     f'<div class="t">{tool}</div>{body}{arrow}</div>')
    return f'<div class="pipe">{"".join(cells)}</div>'


pipe_slot = st.empty()
pipe_slot.markdown(pipeline(st.session_state.get("usage"), matches=st.session_state.get("matches")), unsafe_allow_html=True)

if go:
    if not secret("TINYFISH_API_KEY"):
        st.error("Add your TinyFish API key to Streamlit secrets as `TINYFISH_API_KEY` (see README).")
        st.stop()
    if linkedin_me and not me_unlocked:
        st.warning("My LinkedIn needs the owner code, so this scan skips it.")
    kw = split(keywords)
    resume_skills = []
    if resume is not None:
        resume_skills = find_skills(extract_text(resume.name, resume.getvalue()))
        kw = list(dict.fromkeys(kw + resume_skills))
    prefs = Prefs(
        role=role.strip(), location=location.strip(), seniority=seniority, keywords=kw,
        remote_ok=remote_ok, need_visa=need_visa,
        companies=[c.strip() for c in companies.split(",") if c.strip()],
        agent_urls=[agent_urls.strip()] if agent_urls.strip().startswith("http") else [],
        use_agent=use_agent, use_linkedin=use_linkedin, linkedin_me=linkedin_me and me_unlocked,
    )
    live = Usage()
    pipe_slot.markdown(pipeline(live, running="Search"), unsafe_allow_html=True)

    def on_step(tool, msg):
        tools = [t for t, _ in live.log]
        if tool == "Search":
            nxt = "Fetch"
        elif tool == "Fetch" and tools.count("Fetch") <= 2 and "Agent" not in tools:
            nxt = "Agent" if (prefs.use_agent or prefs.linkedin_me) else "Score"
        elif tool == "Score":
            nxt = None
        else:
            nxt = "Score"
        pipe_slot.markdown(pipeline(live, running=nxt), unsafe_allow_html=True)

    with st.spinner("Scanning careers pages. This takes about a minute..."):
        try:
            jobs, usage = find_jobs(prefs, secret("TINYFISH_API_KEY"), on_step=on_step, usage=live)
        except TinyFishError as e:
            st.error(str(e))
            st.stop()
    matches = len([j for j in jobs if j.score >= min_score and not (need_visa and j.visa == "No sponsorship")])
    st.session_state.update(jobs=jobs, usage=usage, prefs=prefs, matches=matches, resume_skills=resume_skills,
                            at=datetime.now(ZoneInfo("America/New_York")), applied={})
    pipe_slot.markdown(pipeline(usage, matches=matches), unsafe_allow_html=True)

# ======================================================================= results
st.markdown('<div id="how"></div>', unsafe_allow_html=True)
if "jobs" not in st.session_state:
    st.markdown(
        """<div class="sec"><div><div class="k">02 · YOUR SHORTLIST</div><h2>Your next role starts <em>here.</em></h2></div>
<p>Press Scan. In about a minute your ranked shortlist shows up below, with a reason for every match.</p></div>""",
        unsafe_allow_html=True)
    st.markdown('<div class="foot">Built with TinyFish Search, Fetch and Agent · '
                '<a href="https://github.com/kohnicholas1/snag">source</a></div>', unsafe_allow_html=True)
    st.stop()

jobs = st.session_state.jobs
usage = st.session_state.usage
prefs = st.session_state.prefs
shown = [j for j in jobs if j.score >= min_score]
if prefs.need_visa:
    shown = [j for j in shown if j.visa != "No sponsorship"]

st.markdown(
    f"""<div class="sec"><div><div class="k">02 · YOUR SHORTLIST</div><h2>{len(shown)} roles worth a <em>closer look.</em></h2></div>
<p>Live results · refreshed {st.session_state.at:%b %d, %I:%M %p} ET. Scan again any time for the latest.</p></div>""",
    unsafe_allow_html=True,
)
if st.session_state.get("resume_skills"):
    st.markdown("From your résumé: " + "".join(f'<span class="chip good">{esc(s)}</span>'
                                               for s in st.session_state.resume_skills), unsafe_allow_html=True)

tab_list, tab_table, tab_apply, tab_how = st.tabs(["Matches", "Results table", "Apply with Agent", "How it works"])

with tab_list:
    if not shown:
        st.info("No openings above your minimum match. Try lowering it or broadening the role.")
    cards = []
    for j in shown[:60]:
        meta = " · ".join(esc(x) for x in [j.company, j.location, j.posted_label] if x)
        chips = "".join(f'<span class="chip">{esc(r)}</span>' for r in j.reasons)
        if j.visa != "Not stated" or prefs.need_visa:
            cls = {"Sponsors": "good", "No sponsorship": "bad"}.get(j.visa, "")
            chips += f'<span class="chip {cls}">Visa: {esc(j.visa)}</span>'
        chips += f'<span class="chip {"li" if "LinkedIn" in j.source else ""}">{esc(j.source)}</span>'
        trail = ["Search", "Fetch"] if j.tool == "Fetch" and "LinkedIn" not in j.source else \
            ["Fetch"] if j.tool == "Fetch" else ["Search", "Agent"] if j.tool == "Agent" else ["Search"]
        if j.read and "Fetch" not in trail:
            trail.append("Fetch")
        trail.append("Score")
        trail_html = '<span class="sep">→</span>'.join(f"<span>{t}</span>" for t in trail)
        logo = (f'<img src="{esc(j.logo)}" alt="">' if j.logo else esc((j.company[:1] or "?").upper()))
        cards.append(
            f'<div class="job"><div class="logo" style="background:{logo_color(j.company)}">{logo}</div>'
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
                 column_config={"Link": st.column_config.LinkColumn("Link", display_text="Apply"),
                                "Match": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%d")})
    st.download_button("Download CSV", df.to_csv(index=False), "snag_internships.csv", "text/csv")

with tab_apply:
    st.markdown(
        """<div class="me"><h4>Apply with Agent</h4><p>The TinyFish Agent opens the job on LinkedIn signed in as you
(using your saved LinkedIn cookies), goes through Easy Apply with the details LinkedIn already has, and submits.
If the form asks a new question, it stops and tells you instead of guessing.</p></div>""",
        unsafe_allow_html=True)
    li_jobs = [j for j in shown if "linkedin.com/jobs/view" in j.url]
    if not me_unlocked:
        st.info("Owner only. Open **My LinkedIn** in the search form and enter the owner code to unlock this.")
    elif not li_jobs:
        st.info("No LinkedIn roles in this shortlist yet. Keep **Search LinkedIn jobs** on, or turn on **Use my LinkedIn**.")
    else:
        confirm = st.checkbox("I understand the Agent will submit real applications from my LinkedIn account.")
        applied = st.session_state.setdefault("applied", {})
        for j in li_jobs[:15]:
            a, b, c = st.columns([5, 2, 1.4])
            a.markdown(f"**{esc(j.title)}**  \n{esc(j.company)} · {esc(j.location)} · match {j.score}")
            b.markdown(applied.get(j.url, ""))
            if c.button("Apply", key=f"apply_{j.key}", disabled=not confirm, type="primary"):
                with st.spinner(f"Agent is applying to {j.company}..."):
                    try:
                        res = linkedin.apply_easy(TinyFish(secret("TINYFISH_API_KEY")), j.url)
                        status = res.get("status", "unknown")
                        label = {"submitted": "✅ Submitted", "needs_answers": "✍️ Needs your answers",
                                 "no_easy_apply": "↗ No Easy Apply, use the link",
                                 "not_signed_in": "🔒 Not signed in"}.get(status, status)
                        qs = res.get("questions") or []
                        applied[j.url] = label + (": " + "; ".join(qs[:3]) if qs else "")
                    except TinyFishError as e:
                        applied[j.url] = f"⚠️ {e}"
                st.rerun()

with tab_how:
    log_html = "<br>".join(f"<i>{esc(t)}</i> · {esc(m)}" for t, m in usage.log)
    st.markdown(
        f"""<div class="how">
<h4>1 · TinyFish Search finds where the openings are</h4>
<p>Searches across Greenhouse, Lever, Ashby and Workday surface live postings and show which companies are hiring right now.</p>
<h4>2 · TinyFish Fetch reads job boards, LinkedIn and the postings</h4>
<p>Fetch reads each company's complete job board and LinkedIn's public job search, then opens the top postings to check
visa language, skills and location.</p>
<h4>3 · TinyFish Agent handles anything that needs a real browser</h4>
<p>Workday sites only show jobs after you type a search and wait, so the Agent does it in a real browser. In My LinkedIn
mode it browses LinkedIn signed in as you and can apply with Easy Apply.</p>
<h4>4 · Snag scores and explains</h4>
<p>Every source is de-duplicated, then each opening is scored on role, level, location, skills (including your résumé),
freshness and visa policy. Each card shows why it matched.</p>
<div class="log">{log_html}<br><br>{usage.searches} searches · {usage.fetch_calls} fetch calls ({usage.urls_fetched} pages) ·
{usage.agent_runs} agent runs ({usage.agent_steps} steps)</div></div>""",
        unsafe_allow_html=True,
    )

st.markdown('<div class="foot">Built with TinyFish Search, Fetch and Agent · '
            '<a href="https://github.com/kohnicholas1/snag">source</a></div>', unsafe_allow_html=True)
