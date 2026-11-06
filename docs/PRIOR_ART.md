# Prior-art check for this tool itself (2026-11-02)

Run through the analyzer itself plus a web search and a README review.

| Candidate | Closeness | Overlap | Gap vs this requirement |
|---|---|---|---|
| saqlainartaz/precedent (MIT, 0★) | 58% | GitHub prior-art research for Claude Code; REUSE/USE/FORK/BUILD verdict | Not a plugin (clone + .env), GitHub only, no % score, no web UI |
| jacobpowaza/research-first-plugin (MIT, 3★) | 39% | Claude Code plugin; auto prior-art search on build prompts | GitHub only, no % score, no web UI |
| fahrellgiovanny/nothing-new-under-the-sun (MIT, 9★) | 45% | Build-vs-buy scouting skill | No % score, no plugin-catalog search, no UI |
| dadaleo/DevDetective (8★) | 51% (earlier run) | "Search GitHub before you build", reuse advice | Codex-oriented, GitHub only |
| antiagree (Claude plugin directory) | 28% | Looks for prior art while challenging a plan | General plan critic |
| awesome-repositories plugin | 29% | Finds open-source alternatives (MCP) | No requirement scoring, no Claude-plugin search |

Conclusion: nothing found covered Claude plugin catalogs and GitHub together with a % closeness and a web UI.
Precedent and research-first-plugin are the nearest (verdict band: fork/extend). We built a small stdlib tool rather than fork them,
because the missing parts (plugin-catalog search, scoring, UI) are the core of the requirement. Candidates' features are as stated in their READMEs; their code was not run (UNVERIFIED).
