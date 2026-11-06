# Improvement progress (2.0 programme)

Start commit `76d9cb2` (1.13.0). Work branch `improve/2.0-hardening`, merged into `main` as 2.0.0.

| Phase | Status | Evidence |
|---|---|---|
| 1 Forensic audit | done | docs/AUDIT_BASELINE.md (22 findings; 8 reproduced live) |
| 2 P0 security | done | sandbox.py, server.py, policy.py, reuse.py; docs/SECURITY_MODEL.md, SECURITY_TEST_REPORT.md |
| 3 Discovery | done (lexical only) | engine.py, sources.py; docs/DISCOVERY_ENGINE.md; benchmark NDCG@10 0.740 → 0.763 |
| 4 Reuse-or-build decision | done | decision.py, `/api/analyses/<id>/report.md`, `/api/outcomes` |
| 5 Build engine | done | lifecycle.py, gates.py, builder.py; docs/BUILD_LIFECYCLE.md, QUALITY_GATES.md |
| 6 Standards and UX | done | decision panel, assessment chips, packages table, gates table, Stop, sandbox status; browser E2E pass |
| 7 Testing and CI | done locally | 188 tests, 90% coverage, mutation 16/16, fuzz; `.github/workflows/ci.yml` written (**not yet run on GitHub**) |
| 8 Install and platforms | done | hook and server refuse unsupported platforms clearly; MIGRATION_2.0.md; CHANGELOG.md |
| 9 Observability | done | obs.py (JSON logs, redaction, metrics), `/api/diagnostics` |
| 10 Product value | harness only | tools/value_benchmark.py; live runs PENDING (paid) |
| 12 Final audit | done | docs/FINAL_AUDIT.md: **7.6/10**, evidence-based |

## Blockers and pending items (need the user)
- Pushing `.github/workflows/ci.yml` needs the `workflow` scope on the gh token: `gh auth refresh -h github.com -s workflow`.
- A real end-to-end build in the sandbox, and the live A/B value benchmark, both spend Claude usage.
