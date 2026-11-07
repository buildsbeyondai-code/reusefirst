#!/usr/bin/env python3
"""Release evidence for the ReuseFirst plugin: version consistency + per-file SHA-256.

    python3 tools/release_manifest.py --check            # versions agree? (CI runs this via tests)
    python3 tools/release_manifest.py -o manifest.json   # write the manifest for a release
    python3 tools/release_manifest.py --verify manifest.json [--root DIR]
                                                          # does DIR (default: this repo's plugin)
                                                          # hold exactly those files?

The plugin is installed from the git repository, not from a built artifact, so
the release evidence is a manifest of every file under plugins/req-analyzer
with its SHA-256, the version and the commit. Attach it to the GitHub release
by hand (docs/RELEASING.md); this tool never uploads or publishes anything.
`--verify` lets anyone check an installed copy (for example the plugin cache
Claude Code keeps) against the manifest of the release they meant to install.

Exit codes: 0 ok, 1 mismatch, 2 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path("plugins/req-analyzer")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


def versions(root: Path = ROOT) -> dict[str, str | None]:
    """Version string declared by each source of truth (None = not found)."""
    out: dict[str, str | None] = {}
    init = (root / PLUGIN / "app/reqanalyzer/__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.M)
    out["app/reqanalyzer/__init__.py"] = m.group(1) if m else None
    plugin = json.loads((root / PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    out[".claude-plugin/plugin.json"] = plugin.get("version")
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    entry = next((p for p in market.get("plugins", []) if p.get("name") == plugin.get("name")), {})
    out[".claude-plugin/marketplace.json"] = entry.get("version")
    log = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[?(\d+\.\d+\.\d+[^\]\s]*)", log, re.M)
    out["CHANGELOG.md (newest entry)"] = m.group(1) if m else None
    return out


def check(root: Path = ROOT) -> list[str]:
    found = versions(root)
    problems = [f"{src}: no version found" for src, v in found.items() if v is None]
    distinct = {v for v in found.values() if v is not None}
    if len(distinct) > 1:
        problems.append("versions disagree: " + ", ".join(f"{s}={v}" for s, v in found.items()))
    return problems


def _files(plugin_dir: Path) -> list[Path]:
    try:
        r = subprocess.run(["git", "-C", str(plugin_dir), "ls-files", "-z", "."],
                           capture_output=True, check=True)
        rel = [Path(p) for p in r.stdout.decode().split("\0") if p]
        if rel:
            return sorted(rel, key=lambda p: p.as_posix())
    except (OSError, subprocess.CalledProcessError):
        pass                              # not a git checkout (e.g. an installed copy)
    return sorted((p.relative_to(plugin_dir) for p in plugin_dir.rglob("*")
                   if p.is_file() and not SKIP_PARTS & set(p.parts)), key=lambda p: p.as_posix())


def digest_tree(plugin_dir: Path) -> dict[str, str]:
    return {p.as_posix(): hashlib.sha256((plugin_dir / p).read_bytes()).hexdigest()
            for p in _files(plugin_dir)}


def _commit(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True)
        return r.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def manifest(root: Path = ROOT) -> dict:
    version = versions(root)[".claude-plugin/plugin.json"]
    return {"name": "reusefirst", "version": version, "commit": _commit(root),
            "root": PLUGIN.as_posix(), "files": digest_tree(root / PLUGIN)}


def verify(expected: dict, plugin_dir: Path) -> list[str]:
    want, have = expected.get("files") or {}, digest_tree(plugin_dir)
    if not want:
        return ["manifest lists no files"]
    problems = [f"missing: {p}" for p in sorted(set(want) - set(have))]
    problems += [f"changed: {p}" for p in sorted(set(want) & set(have)) if want[p] != have[p]]
    problems += [f"not in manifest: {p}" for p in sorted(set(have) - set(want))]
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="only check that versions agree")
    mode.add_argument("--verify", type=Path, metavar="MANIFEST", help="check files against a manifest")
    ap.add_argument("--root", type=Path, help="plugin folder for --verify (default: this repo's)")
    ap.add_argument("-o", "--output", type=Path, help="write the manifest here instead of stdout")
    args = ap.parse_args(argv)

    if args.verify:
        try:
            expected = json.loads(args.verify.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"error: cannot read {args.verify}: {exc}", file=sys.stderr)
            return 2
        target = args.root or ROOT / PLUGIN
        if not target.is_dir():
            print(f"error: {target} is not a folder", file=sys.stderr)
            return 2
        problems = verify(expected, target)
        label = f"{expected.get('name')} {expected.get('version')}"
        if problems:
            print(f"FAILED {label} at {target}:", *(f"  - {p}" for p in problems), sep="\n")
            return 1
        print(f"verified {label}: {len(expected['files'])} files match at {target}")
        return 0

    problems = check()
    if problems:
        print("FAILED:", *(f"  - {p}" for p in problems), sep="\n")
        return 1
    if args.check:
        print(f"versions agree: {versions()['.claude-plugin/plugin.json']}")
        return 0
    text = json.dumps(manifest(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
