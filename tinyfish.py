"""Small TinyFish REST client: Search, Fetch and Agent.

The API key is read from the TINYFISH_API_KEY environment variable
(or Streamlit secrets). It is never hardcoded or shown in the UI.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import requests

SEARCH_URL = "https://api.search.tinyfish.ai"
FETCH_URL = "https://api.fetch.tinyfish.ai"
AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run"


class TinyFishError(RuntimeError):
    pass


@dataclass
class Usage:
    """Counts every TinyFish call so the UI can show what TinyFish did."""

    searches: int = 0
    fetch_calls: int = 0
    urls_fetched: int = 0
    agent_runs: int = 0
    agent_steps: int = 0
    log: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def note(self, tool: str, message: str) -> None:
        self.log.append((tool, message))


class TinyFish:
    def __init__(self, api_key: str | None = None, usage: Usage | None = None):
        self.api_key = api_key or os.environ.get("TINYFISH_API_KEY", "")
        if not self.api_key:
            raise TinyFishError(
                "TINYFISH_API_KEY is not set. Add it to .streamlit/secrets.toml "
                "or export it in your terminal."
            )
        self.usage = usage or Usage()
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": self.api_key})

    # ---------- Search ----------
    def search(self, query: str, include_domains: str | None = None,
               page: int = 0, purpose: str | None = None) -> list[dict]:
        params = {"query": query, "location": "US", "language": "en", "page": page}
        if include_domains:
            params["include_domains"] = include_domains
        if purpose:
            params["purpose"] = purpose
        r = self.session.get(SEARCH_URL, params=params, timeout=20)
        self.usage.searches += 1
        if r.status_code != 200:
            raise TinyFishError(f"Search failed ({r.status_code}): {r.text[:200]}")
        return r.json().get("results", [])

    # ---------- Fetch ----------
    def fetch(self, urls: list[str], fmt: str = "markdown",
              purpose: str | None = None, timeout_ms: int = 60000,
              include_selectors: list[str] | None = None) -> dict[str, dict]:
        """Fetch up to 10 URLs. Returns {requested_url: result}."""
        out: dict[str, dict] = {}
        for i in range(0, len(urls), 10):
            batch = urls[i:i + 10]
            body = {"urls": batch, "format": fmt, "per_url_timeout_ms": timeout_ms}
            if purpose:
                body["purpose"] = purpose
            if include_selectors:
                body["include_selectors"] = include_selectors
            r = self.session.post(FETCH_URL, json=body, timeout=150)
            self.usage.fetch_calls += 1
            if r.status_code != 200:
                raise TinyFishError(f"Fetch failed ({r.status_code}): {r.text[:200]}")
            data = r.json()
            for res in data.get("results", []):
                out[res.get("url")] = res
                self.usage.urls_fetched += 1
        return out

    # ---------- Agent ----------
    def agent(self, url: str, goal: str, max_steps: int = 40,
              timeout_s: int = 240, use_profile: bool = False) -> dict:
        full = {
            "url": url,
            "goal": goal,
            "browser_profile": "lite",
            "api_integration": "internship-finder",
            "agent_config": {"max_steps": max_steps},
        }
        minimal = {"url": url, "goal": goal}
        if use_profile:  # saved browser profile = your signed-in cookies
            full["use_profile"] = minimal["use_profile"] = True
        data, last = None, ""
        for body in (full, minimal):  # retry with a bare request if the first is rejected
            try:
                r = self.session.post(AGENT_URL, json=body, timeout=timeout_s)
            except requests.RequestException as e:
                raise TinyFishError(f"Agent request failed: {type(e).__name__}")
            try:
                data = r.json()
            except ValueError:
                data = None
            if r.status_code < 400 or r.status_code >= 500:
                break
            err = (data or {}).get("error") or {}
            last = f"HTTP {r.status_code} {err.get('code', '')} {err.get('message', r.text[:160])}".strip()
        self.usage.agent_runs += 1
        if not isinstance(data, dict) or ("status" not in data and "error" in data):
            err = (data or {}).get("error") or {}
            raise TinyFishError(last or f"HTTP {r.status_code} {err.get('message', '')}".strip())
        self.usage.agent_steps += int(data.get("num_of_steps") or 0)
        if data.get("status") != "COMPLETED":
            msg = (data.get("error") or {}).get("message", "unknown error")
            raise TinyFishError(f"Agent run failed: {msg}")
        return data.get("result") or {}


_MD_ESCAPE = re.compile(r"\\([!#$%&'()*+,\-.:;<=>?@\[\]^_`{|}~])")


def parse_json_text(text: str):
    """Fetch returns JSON endpoints as markdown text; undo markdown escaping."""
    cleaned = _MD_ESCAPE.sub(r"\1", text.strip())
    # Some extractors wrap JSON in a code fence.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("\n") + 1:] if "\n" in cleaned else cleaned
    return json.loads(cleaned, strict=False)
