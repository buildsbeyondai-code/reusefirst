# Quality gates

## Gates on every generated app (`gates.py`)
The agent never self-certifies. These run after Claude exits. Anything that executes project code runs in the
sandbox with **no network**.

| Gate | Mandatory | VERIFIED when |
|---|---|---|
| required_files | yes | README, docs/REQUIREMENTS, ARCHITECTURE, DECISIONS and the completion/enhance report exist |
| syntax | yes | every Python file parses (`ast`, no execution); JS/TS is reported NOT VERIFIED (no node) |
| secrets | yes | no private keys or Anthropic/GitHub/AWS/Slack/Google keys or hard-coded passwords (findings never echo the secret) |
| tests | yes | the app's own suite (pytest or unittest) is re-run: exit 0, ≥1 passed, 0 failed, no timeout. **No tests = FAILED** |
| regression (enhance) | yes | tests that passed before still pass, and no fewer pass |
| vulnerabilities | yes | OSV reports no known vulnerability for pinned dependencies (offline = NOT VERIFIED) |
| provenance | yes (if reuse) | REUSE_PROVENANCE.md exists and `upstream/` is not committed |
| launch | yes (server apps) | `run.sh` starts in the sandbox and answers HTTP < 500 on its port within 45 s |
| sbom | advisory | `docs/sbom.cdx.json` (CycloneDX 1.5) written; VERIFIED when all dependencies are pinned |
| static_analysis | advisory | the project's own ruff is clean (NOT VERIFIED if it has none) |
| git | advisory | working tree clean (only when git was requested) |

Result:
- any mandatory FAILED → **failed**;
- otherwise any mandatory NOT VERIFIED or BLOCKED → **partially_completed**;
- otherwise → **succeeded**.

ReuseFirst writes `docs/VERIFICATION_REPORT.md` into the app.

## Gates on ReuseFirst itself (CI, `.github/workflows/ci.yml`)
- ruff and bandit (medium+): no findings.
- Sandbox self-test passes.
- The full test suite on Python 3.11, 3.12 and 3.14.
- Coverage ≥ 85% (`--fail-under`).
- The labelled retrieval benchmark (v2 must not be worse than v1, `test_benchmark.py`).
- Packaging smoke test: version consistency, skill front matter, hook.
- CycloneDX SBOM and pip-audit of the dev toolchain.
- Mutation check of the high-risk controls (`tools/mutate.py`).

Targets the 9.8 programme asks for and their **measured** status are in docs/FINAL_AUDIT.md.
