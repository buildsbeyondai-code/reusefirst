---
description: Find existing Claude plugins and GitHub open-source projects close to a requirement (with % closeness) before building
argument-hint: <requirement text, or path to a requirements file>
allowed-tools: Bash(python3:*), Read
---

Requirement to analyse: $ARGUMENTS

1. If the argument is a path to an existing file, read it and use its contents as the requirement. If no requirement was given, ask for one.
2. Choose 3-8 precise domain keywords that capture what the requirement must DO (not generic words like "app"). Run:
   `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/app" python3 -m reqanalyzer.cli --markdown -k "<kw1>" -k "<kw2>" ... "<requirement>"`
   (quote the requirement safely; for long text write it to a temp file and use `--file`).
3. The tool's % is a lexical estimate. Review the top results yourself: open the 2-3 most promising links only if needed, and say which ones genuinely implement the requirement versus only sharing words.
4. Report, in this order:
   - **Verdict** (Reuse / Fork or extend / Borrow parts / Build new) with the single best candidate and why.
   - Table: top Claude plugins (closeness %, name, what it covers, gaps).
   - Table: top GitHub repositories (closeness %, name, stars, license, last update, gaps).
   - Any warnings the tool printed (rate limits, missing catalogs). Never invent repositories, stars or percentages that the tool did not return.
5. Mention the web UI: http://127.0.0.1:5057/
