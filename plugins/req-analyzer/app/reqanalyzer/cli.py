"""CLI used by the Claude plugin command. Prints JSON (default) or a Markdown table."""
from __future__ import annotations

import argparse
import json
import sys

from . import engine


def to_markdown(r: dict) -> str:
    lines = [f"**Verdict:** {r['verdict']}  (best: {r['best']['name']} at {r['best']['closeness']}%)" if r["best"]
             else f"**Verdict:** {r['verdict']}",
             f"Concepts: {', '.join(r['concepts'])}  |  GitHub: {r['github_status']}  |  "
             f"plugin catalog: {r['catalog_size']}", ""]
    for title, key in (("Claude plugins", "claude_plugins"), ("GitHub open source", "github")):
        lines += [f"### {title}", "| % | Name | Description | Missing concepts | Link |", "|---|---|---|---|---|"]
        for x in r[key]:
            extra = f" ★{x['stars']} {x['license']} {x['updated']}" if "stars" in x else ""
            desc = x["description"][:120].replace("|", "/").replace("\n", " ")
            lines.append(f"| {x['closeness']} | {x['name']}{extra} | {desc} | {', '.join(x['missing'])} | {x['url']} |")
        if not r[key]:
            lines.append("| - | none found | | | |")
        lines.append("")
    for e in r["errors"]:
        lines.append(f"> WARNING: {e}")
    lines.append(f"_{r['method']}_")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find existing Claude plugins / GitHub repos close to a requirement")
    ap.add_argument("requirement", nargs="?", help="requirement text (or use --file / stdin)")
    ap.add_argument("--file", help="read requirement from file")
    ap.add_argument("-k", "--keyword", action="append", default=[], help="extra keyword (repeatable)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--no-github", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    a = ap.parse_args(argv)
    text = a.requirement
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            text = f.read()
    elif not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    try:
        r = engine.analyze(text or "", a.keyword, top=a.top, github=not a.no_github)
    except engine.InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(to_markdown(r) if a.markdown else json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
