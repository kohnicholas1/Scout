# Snag: a TinyFish-powered internship finder

Snag pulls **live** internship and new grad openings from real company careers pages,
matches them to what you are looking for (role, location, level, skills, visa sponsorship),
and gives you a clean, ranked, de-duplicated list with direct apply links.

Built at the TinyFish × CUB Columbia AI Club workshop.

**Live app:** https://snag-internships.streamlit.app

## How TinyFish is used

| Step | TinyFish tool | What it does |
|---|---|---|
| 1. Discover | **Search** | Runs targeted searches across Greenhouse, Lever, Ashby and Workday for your role and location. Finds live postings and tells Snag which companies are hiring right now. |
| 2. Read boards | **Fetch** | Reads each discovered company's complete job board as structured JSON, so Snag sees every opening at that company, not just the ones that showed up in search. |
| 3. Read postings | **Fetch** | Opens the top postings and reads the full description to check visa sponsorship language, required skills and location. |
| 4. Operate portals | **Agent** | Workday careers sites only show jobs after you type a search and wait. The Agent does that in a real browser and returns the listings as JSON. |

Then Snag de-duplicates across sources (by job ID, then company + title + location),
scores every opening (role match, level, location, skills, freshness, visa policy)
and shows **why** each one matched.

## Features

- **LinkedIn**: reads LinkedIn's public job search with TinyFish Fetch (no sign-in needed)
- **My LinkedIn (owner only)**: the TinyFish Agent browses LinkedIn signed in as you using a saved
  Browser Context Profile, and **Apply with Agent** submits Easy Apply applications. It only submits
  when LinkedIn already has every answer; otherwise it stops and lists the questions.
- **Résumé match**: upload a PDF, DOCX or TXT résumé; skills are extracted in memory (never stored)

- Your own preferences: role, location, level (internship / new grad), skills, remote, visa
- Visa filter: flags postings that say they won't sponsor and highlights ones that mention sponsorship or CPT/OPT
- Ranked results with a match score and reasons
- Sources: Greenhouse, Lever, Ashby, Workday, plus any careers page you add for the Agent
- Table view and CSV export
- "How it works" tab that shows exactly what TinyFish did in each run

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your key in it
streamlit run app.py
```

Get a key at https://agent.tinyfish.ai/api-keys. The key is read from
`.streamlit/secrets.toml` (git-ignored) or the `TINYFISH_API_KEY` environment variable.
It is never committed or shown in the app.

To unlock **My LinkedIn**, also set `OWNER_CODE = "something only you know"` in secrets, and in the
TinyFish dashboard create a Browser Context Profile, sign in to LinkedIn there, and set it as default.

## Cost

Search and Fetch are free. Each Agent run on a Workday site takes roughly 5 to 15 steps
(a few cents). You can turn the Agent off under **More sources**.

## Project layout

```
app.py              Streamlit UI
finder/tinyfish.py  TinyFish REST client (Search, Fetch, Agent)
finder/sources.py   Discovery, board reading, posting reading, Agent runs, de-dup
finder/rank.py      Matching, visa detection and scoring
```
