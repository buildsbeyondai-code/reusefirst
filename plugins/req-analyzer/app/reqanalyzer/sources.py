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
from collections import OrderedDict
from pathlib import Path

from . import policy

USER_AGENT = "reusefirst/2.0 (+https://github.com/buildsbeyondai-code/reusefirst)"
GITHUB_API = os.environ.get("REQAN_GITHUB_API", "https://api.github.com")
NPM_API = os.environ.get("REQAN_NPM_API", "https://registry.npmjs.org")
CRATES_API = os.environ.get("REQAN_CRATES_API", "https://crates.io")
HTTP_TIMEOUT_S = 20
CACHE_TTL_S = 900  # search results are cached 15 min to stay inside the rate limits
CACHE_MAX = 256
README_MAX_BYTES = 20000


def safe_base(url: str) -> str:
    """Only https, or http to 127.0.0.1 (tests). Blocks file:, ftp: and other schemes (bandit B310)."""
    if url.startswith("https://") or url.startswith("http://127.0.0.1"):
        return url.rstrip("/")
    raise ValueError(f"refusing API base URL {url!r}: only https is allowed")
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
    seen: set[str] = set()       # provider-scoped ids
    seen_urls: set[str] = set()   # same repository listed twice = same plugin
    seen_names: set[str] = set()  # a URL-less entry with a known name cannot be told apart: treated as the same

    cache = base / "plugin-directory-cache-v2.json"
    if cache.exists():
        try:
            for l in json.loads(cache.read_text(encoding="utf-8"))["listings"]:
                repo = (l.get("source") or {}).get("repository") or {}
                url = repo.get("url", "")
                if url and repo.get("path"):
                    url = f"{url}/tree/HEAD/{repo['path']}"
                key = "plugin-directory:" + (f"{repo.get('url', '')}/{repo.get('path', '')}".lower() if repo.get("url")
                                             else l["name"].lower())
                if key in seen or (url and url.lower() in seen_urls):
                    continue
                seen.add(key)
                seen_names.add(l["name"].lower())
                if url:
                    seen_urls.add(url.lower())
                out.append({"id": key, "name": l["name"], "description": l.get("summary") or "", "url": url,
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
            if not str(p.get("name", "")):
                continue
            key = f"marketplace:{mname}/{str(p['name']).lower()}"
            src = p.get("source")
            url = p.get("homepage") or ""
            if not url and isinstance(src, dict):
                url = src.get("url") or (f"https://github.com/{src['repo']}" if src.get("repo") else "")
            if key in seen or (url and url.lower() in seen_urls) or (not url and str(p["name"]).lower() in seen_names):
                continue
            seen.add(key)
            seen_names.add(str(p["name"]).lower())
            if url:
                seen_urls.add(url.lower())
            out.append({"id": key, "name": p["name"], "description": p.get("description") or "", "url": url,
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
                    r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=20)
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


class TTLCache:
    """Bounded LRU with a TTL; entries remember when they were fetched."""

    def __init__(self, maxsize: int = CACHE_MAX, ttl: float = CACHE_TTL_S):
        self.maxsize, self.ttl = maxsize, ttl
        self.data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self.lock = threading.Lock()
        self.hits = self.misses = 0

    def get(self, key: str):
        with self.lock:
            hit = self.data.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                self.data.move_to_end(key)
                self.hits += 1
                return hit
            self.misses += 1
            return None

    def put(self, key: str, value) -> float:
        now = time.time()
        with self.lock:
            self.data[key] = (now, value)
            self.data.move_to_end(key)
            while len(self.data) > self.maxsize:
                self.data.popitem(last=False)
        return now

    def clear(self) -> None:
        with self.lock:
            self.data.clear()

    def __len__(self) -> int:
        return len(self.data)


_cache = TTLCache()
RATE: dict[str, object] = {}  # last seen GitHub rate-limit headers


def cache_info() -> dict:
    return {"entries": len(_cache), "max": _cache.maxsize, "ttl_s": _cache.ttl, "hits": _cache.hits,
            "misses": _cache.misses, "rate": dict(RATE)}


def _get_json(url: str, headers: dict, what: str, raw: bool = False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=HTTP_TIMEOUT_S) as r:  # nosec B310 - every base URL passes safe_base()
            if "api.github" in url or url.startswith(GITHUB_API):
                for h in ("X-RateLimit-Remaining", "X-RateLimit-Reset", "X-RateLimit-Resource"):
                    if r.headers.get(h):
                        RATE[h] = r.headers.get(h)
            return r.read(README_MAX_BYTES).decode("utf-8", "replace") if raw else json.load(r)
    except urllib.error.HTTPError as e:
        limited = e.code in (403, 429)
        e.close()
        raise GitHubError(f"{what}: HTTP {e.code}" +
                          (" - rate limited, retry in a minute or set GITHUB_TOKEN" if limited else ""), limited) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise GitHubError(f"{what}: unreachable: {e}") from None


def _gh_headers(accept: str = "application/vnd.github+json") -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    tok = github_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return headers


def search_repositories(q: str, per_page: int = 30) -> list[dict]:
    hit = _cache.get("gh:" + q)
    if hit:
        return hit[1]
    url = f"{safe_base(GITHUB_API)}/search/repositories?" + urllib.parse.urlencode({"q": q, "per_page": per_page})
    items = _get_json(url, _gh_headers(), f"GitHub search for query '{q}'").get("items", [])
    _cache.put("gh:" + q, items)
    return items


def cached_at(q: str) -> float | None:
    hit = _cache.get("gh:" + q)
    return hit[0] if hit else None


def fetch_readme(full_name: str) -> str | None:
    """README text (first 20 KB) as untrusted data; None when absent or unreachable."""
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}", full_name or ""):
        return None
    hit = _cache.get("readme:" + full_name)
    if hit:
        return hit[1]
    try:
        text = _get_json(f"{safe_base(GITHUB_API)}/repos/{full_name}/readme", _gh_headers("application/vnd.github.raw"),
                         f"README of {full_name}", raw=True)
    except GitHubError:
        text = None
    _cache.put("readme:" + full_name, text)
    return text


def search_npm(q: str, size: int = 20) -> list[dict]:
    hit = _cache.get("npm:" + q)
    if hit:
        return hit[1]
    url = f"{safe_base(NPM_API)}/-/v1/search?" + urllib.parse.urlencode({"text": q, "size": size})
    objs = _get_json(url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, f"npm search '{q}'").get("objects", [])
    out = []
    for o in objs:
        p = o.get("package") or {}
        if not p.get("name"):
            continue
        links = p.get("links") or {}
        repo = links.get("repository") or ""
        out.append({"id": f"npm:{p['name']}", "name": p["name"], "description": p.get("description") or "",
                    "url": links.get("npm") or f"https://www.npmjs.com/package/{p['name']}", "repository": repo,
                    "topics": p.get("keywords") or [], "version": p.get("version"), "updated": (p.get("date") or "")[:10],
                    "license": p.get("license") or "none", "ecosystem": "npm", "language": "JavaScript"})
    _cache.put("npm:" + q, out)
    return out


def search_crates(q: str, per_page: int = 20) -> list[dict]:
    hit = _cache.get("crates:" + q)
    if hit:
        return hit[1]
    url = f"{safe_base(CRATES_API)}/api/v1/crates?" + urllib.parse.urlencode({"q": q, "per_page": per_page})
    crates = _get_json(url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, f"crates.io search '{q}'").get("crates", [])
    out = [{"id": f"crates:{c['name']}", "name": c["name"], "description": c.get("description") or "",
            "url": f"https://crates.io/crates/{c['name']}", "repository": c.get("repository") or "",
            "topics": c.get("keywords") or [], "version": c.get("max_stable_version") or c.get("max_version"),
            "updated": (c.get("updated_at") or "")[:10], "license": None, "ecosystem": "crates.io", "language": "Rust",
            "downloads": int(c.get("downloads") or 0)}
           for c in crates if c.get("name")]
    _cache.put("crates:" + q, out)
    return out


def repo_record(it: dict) -> dict:
    topics = it.get("topics") or []
    spdx = ((it.get("license") or {}).get("spdx_id")) or "none"
    return {"id": f"github:{it['full_name'].lower()}", "name": it["full_name"], "fork": bool(it.get("fork")),
            "licence": policy.licence_class(spdx),
            "maintenance": policy.maintenance(it.get("pushed_at"), bool(it.get("archived"))), "description": it.get("description") or "", "url": it["html_url"],
            "topics": topics, "stars": int(it.get("stargazers_count") or 0),
            "updated": (it.get("pushed_at") or "")[:10],
            "license": ((it.get("license") or {}).get("spdx_id")) or "none",
            "language": it.get("language") or "", "archived": bool(it.get("archived")),
            "is_claude_plugin": bool(PLUGIN_TOPICS & set(topics))}
