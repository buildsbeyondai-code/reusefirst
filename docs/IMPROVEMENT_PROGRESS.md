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
| 7 Testing and CI | done | 221 tests, 92% coverage, mutation 22/22, fuzz; CI green on GitHub (Python 3.11/3.12/3.14 + mutation) |
| 8 Install and platforms | done | hook and server refuse unsupported platforms clearly; MIGRATION_2.0.md; CHANGELOG.md |
| 9 Observability | done | obs.py (JSON logs, redaction, metrics), `/api/diagnostics` |
| 10 Product value | harness only | tools/value_benchmark.py; live runs PENDING (paid) |
| 12 Final audit | done | docs/FINAL_AUDIT.md: **8.6/10** (2.1.1, after the first real builds), evidence-based |

| Real build | done | job finder unattended auto-apply: 4 attempts → SUCCEEDED and applied (docs/FINAL_AUDIT.md) |

## Pending (need the user's approval)
- The live A/B value benchmark (spends Claude usage), independent relevance labels, and an external security review.
