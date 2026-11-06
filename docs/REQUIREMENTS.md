# Requirements and acceptance criteria

Users: the developer (single user, local machine) deciding build-vs-reuse. Platforms: WSL2/Linux backend; browser on Windows.

| ID | Priority | Given / When / Then | Test |
|---|---|---|---|
| R1 | Must | Given a free-text requirement, when analysed, then the closest Claude plugins from installed catalogs are listed with % closeness and uncovered concepts | test_engine.AnalyzeTests.test_ranks_real_match_first, e2e_browser |
| R2 | Must | Given network access, when analysed, then GitHub repos are listed with %, stars, license, last push, archived flag | test_engine.test_repo_record_fields, e2e_browser |
| R3 | Must | When the best match is ≥70/50/30/<30, the verdict is Reuse/Fork/Borrow/Build new | test_textscore.test_verdict_bands |
| R4 | Must | When GitHub is rate-limited, failing or unreachable, then the status and error are shown and no synthetic results appear; plugin results still show | GitHubFailureTests |
| R5 | Must | Web UI at http://127.0.0.1:5057/, separate from SysPerf on 5056, reachable from Windows | live health check via Windows curl.exe |
| R6 | Must | Usable from Claude Code as a plugin (one skill `reusefirst`: analyze, build, enhance, status) | `claude plugin validate`, install, CLI tests |
| R7 | Must | Invalid input (empty, >5000 chars, bad keywords, bad JSON, wrong content type, oversize body) is rejected with 4xx | ValidationTests, ServerTests.test_bad_requests |
| R8 | Must | Only localhost can drive the API (bind 127.0.0.1, Host check, JSON-only POST, CSP) | test_rejects_foreign_host, test_rejects_form_posts |
| R9 | Should | Analysis completes in <20 s with GitHub, <1 s without | measured: ~10 s cold, 0.04 s cached |
| R10 | Should | UI readable in light and dark, no horizontal scroll at 390 px, no console errors | e2e_browser |
| R12 | Must | Given a requirement, when "List required inputs" is clicked, then every input needed to build it is listed, grouped by UAISES section (§2 users, platforms, journeys, MoSCoW, Given/When/Then, integrations, NFRs; §3; §14), pre-filled by Claude plus app-specific questions; never asks for secrets | test_builder.InputsTests, live run (41 inputs, 35 pre-filled) |
| R13 | Must | Given Claude is unavailable, then the standard inputs still show with a visible failure message | test_claude_failure_falls_back_visibly |
| R14 | Must | When the form is submitted, then the app is built non-interactively (no questions) by headless Claude Code in dontAsk mode with a fixed allowlist, within the budget and time limits, and the run finishes with a completion report | LifecycleTests, e2e_build.py |
| R15 | Must | When submitted, the closest GitHub repos and Claude plugins (pre-ticked) are cloned and reused first; reuse is recorded in docs/REUSE.md | test_reuse_preselects_closest, test_prompt_contents |
| R16 | Must | Every build follows UAISES: the standard is copied into the app's docs/ and the build refuses to start without it; required §2 inputs must be filled | test_missing_standard_refuses, test_rejects |
| R17 | Must | One build at a time; progress streams live; cancel works; a server restart marks running builds "interrupted" | test_one_at_a_time_and_cancel, test_restart_marks_interrupted |
| R18 | Must | Build endpoints need the per-session token; output folder must be new/empty, inside home, not in ~/.claude, ~/.ssh, ~/.config, ~/.local or this tool | test_build_requires_token, SpecTests |
| R19 | Must | The analyzer's own UI meets UEUIS Enterprise (WCAG 2.2 AA): skip link first in tab order, visible focus, every control named, tabs work with arrows/Home/End, theme follows the system with a remembered Light/Dark override, theme tokens ≥4.5:1 text and ≥3:1 controls in every theme, no sideways page scroll at 320 px, error summary that keeps input and moves focus, loading/empty/error rows for every list, named confirmations for Delete and Cancel, reduced motion and forced colours respected | test_ui_standard, e2e_browser (UEUIS section) |
| R20 | Must | Every build follows UEUIS: the UI standard is copied into the app's docs/, the build refuses to start without it, the conformance level (Enterprise by default) is an input, apps with a UI must deliver docs/UI_STATES.md, docs/ACCESSIBILITY.md and the §20 UI gate table; apps without a UI apply only the parts users see | test_missing_ui_standard_refuses, test_prompt_contents, test_ui_standard_scales_to_apps_without_a_ui |
| R11 | Optional | Semantic (embedding/LLM) scoring | not implemented; Claude reviews top hits in the plugin flow (D2) |
