"""Domain layer: reuse policy. Pure functions, no I/O.

- Structural GitHub URL parsing (never substring matching).
- Deterministic SPDX licence classification and reuse rights.
- Eligibility for *automatic* reuse pre-selection.
See docs/REUSE_POLICY.md.
"""
from __future__ import annotations

import math
import re
import time
from urllib.parse import urlsplit

_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_REPO = re.compile(r"[A-Za-z0-9._-]{1,100}")
_REF = re.compile(r"[A-Za-z0-9._/-]{1,200}")


class PolicyError(ValueError):
    pass


def parse_github_url(url: str) -> dict:
    """Return {owner, repo, ref, path, clone_url, html_url} or raise PolicyError.

    Accepts only https://github.com/<owner>/<repo>[.git][/tree/<ref>[/<path>]]: no userinfo, port, query or fragment."""
    if not isinstance(url, str) or len(url) > 400 or any(c.isspace() for c in url.strip()):
        raise PolicyError("not a single URL")
    u = urlsplit(url.strip())
    if u.scheme != "https" or u.hostname != "github.com" or u.netloc != "github.com":
        raise PolicyError("only https://github.com/ URLs are allowed")
    if u.query or u.fragment:
        raise PolicyError("GitHub URL must not have a query or fragment")
    parts = [p for p in u.path.split("/") if p != ""]
    if len(parts) < 2 or ".." in parts:
        raise PolicyError("GitHub URL must name owner/repo")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not _OWNER.fullmatch(owner) or not _REPO.fullmatch(repo) or repo in (".", ".."):
        raise PolicyError("invalid GitHub owner or repository name")
    ref = path = None
    rest = parts[2:]
    if rest:
        if rest[0] != "tree" or len(rest) < 2:
            raise PolicyError("only /tree/<ref>/<path> sub-paths are allowed")
        ref = rest[1]
        path = "/".join(rest[2:]) or None
        if not _REF.fullmatch(ref) or (path and not _REF.fullmatch(path)):
            raise PolicyError("invalid ref or path")
    base = f"https://github.com/{owner}/{repo}"
    return {"owner": owner, "repo": repo, "ref": ref, "path": path, "clone_url": base, "html_url": base}


def reuse_option_url(option: str) -> dict:
    """Reuse options look like 'GitHub · owner/repo · 58% · MIT · https://github.com/owner/repo'.
    The URL must be the LAST field, and the whole field must be the URL."""
    if not isinstance(option, str) or len(option) > 400:
        raise PolicyError("reuse entry must be a string of at most 400 characters")
    return parse_github_url(option.rsplit(" · ", 1)[-1].strip())


# ---------------------------------------------------------------- licences
# Deterministic, conservative classes. "allowed" = code may be copied into the new app with attribution.
PERMISSIVE = {"MIT", "MIT-0", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense", "Zlib",
              "BSL-1.0", "CC0-1.0", "Python-2.0", "PSF-2.0", "X11", "BlueOak-1.0.0"}
WEAK_COPYLEFT = {"MPL-2.0", "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0", "LGPL-3.0-only",
                 "LGPL-3.0-or-later", "EPL-2.0", "EPL-1.0", "CDDL-1.0"}
STRONG_COPYLEFT = {"GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later",
                   "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later", "EUPL-1.2", "OSL-3.0"}
NON_COMMERCIAL_OR_DATA = {"CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-4.0", "CC-BY-SA-4.0", "SSPL-1.0", "BUSL-1.1",
                          "Elastic-2.0", "Commons-Clause"}


def licence_class(spdx: str | None) -> dict:
    """{spdx, class, reuse, reason}. reuse: allowed | review | learn-only."""
    s = (spdx or "").strip()
    if not s or s.lower() == "none":
        return {"spdx": "none", "class": "none", "reuse": "learn-only",
                "reason": "no licence: all rights reserved, so code is never copied (read for ideas only)"}
    if s == "NOASSERTION":
        return {"spdx": s, "class": "unknown", "reuse": "review",
                "reason": "a licence file exists but is not a recognised SPDX licence: needs human review"}
    if s in PERMISSIVE:
        return {"spdx": s, "class": "permissive", "reuse": "allowed",
                "reason": "permissive: may be reused with the copyright notice and licence text kept"}
    if s in WEAK_COPYLEFT:
        return {"spdx": s, "class": "weak-copyleft", "reuse": "review",
                "reason": "weak copyleft: changes to its files stay under the same licence; human review before copying"}
    if s in STRONG_COPYLEFT:
        return {"spdx": s, "class": "strong-copyleft", "reuse": "review",
                "reason": "strong copyleft: the whole app would have to use a compatible licence; human review required"}
    if s in NON_COMMERCIAL_OR_DATA:
        return {"spdx": s, "class": "restricted", "reuse": "learn-only",
                "reason": "source-available, non-commercial or content licence: not for code reuse"}
    return {"spdx": s, "class": "unknown", "reuse": "review", "reason": "licence not in the policy table: human review"}


# Licences whose text is recognisable from the first lines of a LICENSE file (used after cloning).
_LICENSE_TEXT = [
    ("MIT", r"permission is hereby granted, free of charge"),
    ("Apache-2.0", r"apache license,?\s+version 2\.0"),
    ("BSD-3-Clause", r"neither the name of .* nor the names of its\s+contributors"),
    ("BSD-2-Clause", r"redistributions in binary form must reproduce"),
    ("ISC", r"permission to use, copy, modify, and(/or)? distribute this software for any"),
    ("Unlicense", r"this is free and unencumbered software released into the public domain"),
    ("AGPL-3.0", r"gnu affero general public license"),
    ("LGPL-3.0", r"gnu lesser general public license"),
    ("GPL-3.0", r"gnu general public license\s+version 3"),
    ("GPL-2.0", r"gnu general public license\s+version 2"),
    ("MPL-2.0", r"mozilla public license,?\s+(version|v\.?)\s*2\.0"),
]


def detect_licence_text(text: str) -> str | None:
    """SPDX id from a LICENSE file's text, or None. Order matters: AGPL/LGPL before GPL, BSD-3 before BSD-2."""
    t = re.sub(r"\s+", " ", (text or "")[:20000].lower())
    for spdx, pat in _LICENSE_TEXT:
        if re.search(pat, t):
            return spdx
    return None


def reconcile_licence(api_spdx: str | None, file_spdx: str | None) -> dict:
    """Combine the registry's SPDX id with the LICENSE file's detected id. Disagreement = human review."""
    a = (api_spdx or "").strip() or None
    a = None if a in ("none", "NOASSERTION") else a
    if a and file_spdx and a.split("-")[0] != file_spdx.split("-")[0]:
        c = licence_class(a)
        return {**c, "reuse": "review", "reason": f"registry says {a} but LICENSE text looks like {file_spdx}: human review"}
    return licence_class(a or file_spdx or ("NOASSERTION" if api_spdx == "NOASSERTION" else None))


# ------------------------------------------------------------- maintenance
def maintenance(pushed: str | None, archived: bool = False, now: float | None = None) -> dict:
    """active (< 1 year), stale (1-2 years), unmaintained (> 2 years), archived, unknown."""
    if archived:
        return {"state": "archived", "risk": "high", "age_days": None}
    if not pushed:
        return {"state": "unknown", "risk": "unknown", "age_days": None}
    try:
        t = time.mktime(time.strptime(pushed[:10], "%Y-%m-%d"))
    except ValueError:
        return {"state": "unknown", "risk": "unknown", "age_days": None}
    age = max(0, int(((now or time.time()) - t) // 86400))
    if age <= 365:
        return {"state": "active", "risk": "low", "age_days": age}
    if age <= 730:
        return {"state": "stale", "risk": "medium", "age_days": age}
    return {"state": "unmaintained", "risk": "high", "age_days": age}


# ------------------------------------------------- automatic pre-selection
AUTO_MIN_COVERAGE = 50     # % IDF-weighted concept coverage
AUTO_MIN_CONFIDENCE = 50   # % evidence confidence


def auto_reuse_eligible(c: dict) -> tuple[bool, list[str]]:
    """Whether a candidate may be PRE-TICKED for reuse. The user can still tick anything by hand (it is then
    cloned only if its licence allows code reuse). Returns (eligible, reasons-it-is-not)."""
    why = []
    try:
        parse_github_url(str(c.get("url", "")))
    except PolicyError:
        why.append("no valid GitHub URL")
    cov = c.get("coverage", 0)
    if not isinstance(cov, (int, float)) or not math.isfinite(cov) or cov < AUTO_MIN_COVERAGE:
        why.append(f"concept coverage below {AUTO_MIN_COVERAGE}%")
    lic = c.get("licence") or licence_class(c.get("license"))
    if lic.get("reuse") != "allowed":
        why.append(f"licence {lic.get('spdx')} is not cleared for automatic reuse ({lic.get('reuse')})")
    m = c.get("maintenance") or {}
    if m.get("state") in ("archived", "unmaintained"):
        why.append(f"repository is {m['state']}")
    if c.get("compatibility") == "fail":
        why.append("incompatible language or platform")
    conf = (c.get("evidence") or {}).get("confidence", 0)
    if conf < AUTO_MIN_CONFIDENCE:
        why.append(f"evidence confidence below {AUTO_MIN_CONFIDENCE}%")
    if c.get("fork"):
        why.append("is a fork (prefer the upstream project)")
    return (not why, why)
