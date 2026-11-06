"""Integration adapters: Claude plugin catalogs (local files) and GitHub repository search (HTTPS).

Both return real data or an explicit error; nothing is synthesised on failure.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "req-analyzer/1.0"
GITHUB_API = os.environ.get("REQAN_GITHUB_API", "https://api.github.com")
HTTP_TIMEOUT_S = 20
CACHE_TTL_S = 900  # GitHub search results are cached 15 min to stay inside the rate limit.
PLUGIN_TOPICS = {"claude-code-plugin", "claude-plugin", "claude-code-plugins", "claude-skills", "claude-code-skills"}


def plugins_dir() -> Path:
    base = os.environ.get("REQAN_PLUGINS_DIR")
    if base:
        return Path(base)
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "plugins"


def load_claude_plugins(base: Path | None = None) -> tuple[list[dict], list[str]]:
    """Read the Claude Code plugin directory cache and every installed marketplace manifest."""
    base = base or plugins_dir()
    out: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()

    cache = base / "plugin-directory-cache-v2.json"
    if cache.exists():
        try:
            for l in json.loads(cache.read_text(encoding="utf-8"))["listings"]:
                repo = (l.get("source") or {}).get("repository") or {}
                url = repo.get("url", "")
                if url and repo.get("path"):
                    url = f"{url}/tree/HEAD/{repo['path']}"
                key = l["name"].lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"name": l["name"], "description": l.get("summary") or "", "url": url,
                            "source": "Claude plugin directory",
                            "reviewed": ((l.get("checks") or {}).get("review") or {}).get("state") == "done"})
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors.append(f"plugin directory cache unreadable: {e}")
    else:
        errors.append(f"plugin directory cache not found at {cache}")

    for mf in sorted((base / "marketplaces").glob("*/.claude-plugin/marketplace.json")):
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            errors.append(f"{mf}: {e}")
            continue
        mname = mf.parent.parent.name
        for p in m.get("plugins", []):
            key = str(p.get("name", "")).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            src = p.get("source")
            url = p.get("homepage") or ""
            if not url and isinstance(src, dict):
                url = src.get("url") or (f"https://github.com/{src['repo']}" if src.get("repo") else "")
            out.append({"name": p["name"], "description": p.get("description") or "", "url": url,
                        "source": f"marketplace: {mname}", "category": p.get("category", ""), "reviewed": None})
    return out, errors


# ---------------------------------------------------------------- GitHub
_token_lock = threading.Lock()
_token: str | None = None
_token_tried = False


def github_token() -> str | None:
    """GITHUB_TOKEN/GH_TOKEN, else the user's own `gh auth token` (Linux gh, then Windows gh via PowerShell).
    The token is only ever sent to api.github.com and is never logged or returned."""
    global _token, _token_tried
    with _token_lock:
        if _token_tried:
            return _token
        _token_tried = True
        _token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not _token and os.environ.get("REQAN_NO_GH_CLI") != "1":
            for cmd in (["gh", "auth", "token"], ["powershell.exe", "-NoProfile", "-Command", "gh auth token"]):
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                tok = r.stdout.strip()
                if r.returncode == 0 and re.fullmatch(r"[A-Za-z0-9_]{20,255}", tok):
                    _token = tok
                    break
        return _token


class GitHubError(Exception):
    def __init__(self, msg: str, rate_limited: bool = False):
        super().__init__(msg)
        self.rate_limited = rate_limited


_cache: dict[str, tuple[float, list]] = {}
_cache_lock = threading.Lock()


def search_repositories(q: str, per_page: int = 30) -> list[dict]:
    with _cache_lock:
        hit = _cache.get(q)
        if hit and time.time() - hit[0] < CACHE_TTL_S:
            return hit[1]
    url = f"{GITHUB_API}/search/repositories?" + urllib.parse.urlencode({"q": q, "per_page": per_page})
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    tok = github_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=HTTP_TIMEOUT_S) as r:
            items = json.load(r).get("items", [])
    except urllib.error.HTTPError as e:
        limited = e.code in (403, 429)
        raise GitHubError(f"GitHub HTTP {e.code} for query '{q}'" +
                          (" - rate limited, retry in a minute or set GITHUB_TOKEN" if limited else ""), limited) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise GitHubError(f"GitHub unreachable for query '{q}': {e}") from None
    with _cache_lock:
        _cache[q] = (time.time(), items)
    return items


def repo_record(it: dict) -> dict:
    topics = it.get("topics") or []
    return {"name": it["full_name"], "description": it.get("description") or "", "url": it["html_url"],
            "topics": topics, "stars": int(it.get("stargazers_count") or 0),
            "updated": (it.get("pushed_at") or "")[:10],
            "license": ((it.get("license") or {}).get("spdx_id")) or "none",
            "language": it.get("language") or "", "archived": bool(it.get("archived")),
            "is_claude_plugin": bool(PLUGIN_TOPICS & set(topics))}
