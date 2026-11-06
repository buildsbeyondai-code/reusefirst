"""Application layer: preparing third-party code for a build (PREPARING stage).

ReuseFirst, not the agent, clones each selected repository. The clone runs in the sandbox with GitHub-only egress, no
credentials and no hooks or submodules. It records the exact commit SHA, reconciles the registry licence with the
LICENSE text, and removes clones whose licence does not allow copying. Then it writes docs/REUSE_PROVENANCE.md.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from . import policy, sandbox

CLONE_TIMEOUT_S = 180


def clone_repo(url: dict, dest: Path, workdir: Path) -> dict:
    """Shallow clone into dest (inside workdir). Returns {ok, sha, error}. Replaceable in tests."""
    rel = dest.relative_to(workdir)
    cmd = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never",
           "-c", "protocol.ext.allow=never", "-c", "core.fsmonitor=false", "clone", "--depth", "1",
           "--no-recurse-submodules", "--single-branch"]
    if url.get("ref") and url["ref"] != "HEAD":
        cmd += ["--branch", url["ref"]]
    cmd += ["--", url["clone_url"] + ".git", str(rel)]
    r = sandbox.run(sandbox.Spec(workdir=workdir, egress=sandbox.EGRESS_GITHUB, memory_mb=1024, tasks=128),
                    cmd, timeout_s=CLONE_TIMEOUT_S)
    if r["code"] != 0:
        return {"ok": False, "sha": None, "error": (r["output"] or "clone failed")[-300:]}
    head = dest / ".git" / "HEAD"
    sha = None
    try:  # read the SHA from the files git wrote; never execute git in the clone on the host
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            refpath = dest / ".git" / ref[5:]
            if refpath.is_file():
                sha = refpath.read_text().strip()
            else:
                packed = (dest / ".git" / "packed-refs").read_text()
                m = re.search(rf"^([0-9a-f]{{40}}) {re.escape(ref[5:])}$", packed, re.M)
                sha = m.group(1) if m else None
        else:
            sha = ref
    except OSError:
        sha = None
    return {"ok": True, "sha": sha if sha and re.fullmatch(r"[0-9a-f]{40}", sha) else None, "error": None}


def licence_file_spdx(root: Path) -> str | None:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "LICENCE", "LICENSE-MIT"):
        f = root / name
        if f.is_file() and not f.is_symlink():
            return policy.detect_licence_text(f.read_text(encoding="utf-8", errors="ignore"))
    return None


def parse_option(opt: str) -> dict:
    parts = [p.strip() for p in opt.split(" · ")]
    return {"kind": parts[0] if len(parts) > 1 else "GitHub", "name": parts[1] if len(parts) > 2 else "",
            "licence": parts[3] if len(parts) >= 5 else None, "option": opt}


def prepare(workdir: Path, items: list[str], log=lambda msg: None) -> list[dict]:
    """Clone what may be reused, at a pinned commit. Returns provenance records."""
    out = []
    up = workdir / "upstream"
    for opt in items:
        meta = parse_option(opt)
        url = policy.reuse_option_url(opt)
        rec = {"name": meta["name"] or f"{url['owner']}/{url['repo']}", "kind": meta["kind"], "url": url["html_url"],
               "subpath": url["path"], "registry_licence": meta["licence"], "sha": None, "cloned": False,
               "local_path": None, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        pre = policy.licence_class(meta["licence"])
        if pre["reuse"] == "learn-only" and meta["licence"] not in (None, "see repo"):
            rec.update(licence=pre, decision="not cloned: " + pre["reason"])
            out.append(rec)
            log(f"Not cloning {rec['name']}: {pre['reason']}")
            continue
        dest = up / f"{url['owner']}__{url['repo']}"
        if dest.exists():
            shutil.rmtree(dest)
        up.mkdir(exist_ok=True)
        log(f"Cloning {url['html_url']} (sandboxed, GitHub-only network)")
        try:
            c = clone_repo(url, dest, workdir)
        except sandbox.SandboxUnavailable as e:
            c = {"ok": False, "sha": None, "error": str(e)}
        if not c["ok"]:
            rec.update(licence=pre, decision=f"clone failed: {c['error']}")
            out.append(rec)
            continue
        lic = policy.reconcile_licence(None if meta["licence"] in (None, "see repo") else meta["licence"],
                                       licence_file_spdx(dest))
        rec.update(sha=c["sha"], licence=lic)
        if lic["reuse"] == "allowed":
            rec.update(cloned=True, local_path=str(dest.relative_to(workdir)),
                       decision="cloned at the pinned commit; code may be reused with attribution")
        else:
            shutil.rmtree(dest, ignore_errors=True)
            rec["decision"] = f"clone removed: {lic['reason']}"
        log(f"{rec['name']}: {rec['decision']}")
        out.append(rec)
    gi = workdir / ".gitignore"
    text = gi.read_text() if gi.is_file() else ""
    if "upstream/" not in text:
        gi.write_text(text + ("" if text.endswith("\n") or not text else "\n") + "upstream/\n")
    (workdir / "docs").mkdir(exist_ok=True)
    (workdir / "docs" / "REUSE_PROVENANCE.md").write_text(provenance_markdown(out))
    return out


def provenance_markdown(recs: list[dict]) -> str:
    rows = []
    for r in recs:
        lic = r.get("licence") or {}
        rows.append(f"| {r['name']} | {r['url']}{'/tree/…/' + r['subpath'] if r.get('subpath') else ''} | "
                    f"`{r['sha'] or 'n/a'}` | {lic.get('spdx', '?')} ({lic.get('class', '?')}) | {lic.get('reuse', '?')} | "
                    f"{r['decision']} |")
    return f"""# Reuse provenance

Written by ReuseFirst (not by the build agent) before the build started. The licence rules are in ReuseFirst's
docs/REUSE_POLICY.md. Code from a repository may be copied only when "Reuse" is `allowed`, and its copyright
notice and licence text must then be kept. `review` and `learn-only` sources were NOT cloned. Human review is
required before using them.

| Source | URL | Pinned commit | Licence | Reuse | Decision |
|---|---|---|---|---|---|
{chr(10).join(rows) or '| (none) | | | | | |'}
"""
