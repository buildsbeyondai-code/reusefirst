# Improvement progress (2.0 program)

Start commit: 76d9cb2. Branch: improve/2.0-hardening. NOT merged or pushed. Status: **work in progress**.

## Done (code written; partially verified)
- Phase 1 audit: docs/AUDIT_BASELINE.md (22 findings, 8 reproduced).
- New modules: policy.py (GitHub URL parsing, SPDX rules, reuse eligibility), lifecycle.py (state machine),
  obs.py (redaction, metrics), sandbox.py + sbx_init.py (bwrap with every namespace unshared, allowlisting egress
  proxy, inbound forwarder, systemd-scope limits, self-test), gates.py (independent verification, CycloneDX SBOM,
  OSV), reuse.py (sandboxed pinned clones, REUSE_PROVENANCE.md).
- builder.py: strict number and URL validation; policy-based pre-selection; new BuildManager (state machine,
  sandboxed Claude, gates, transactional enhance with renameat2, orphan recovery, idempotency, sandboxed launch/stop).
- VERIFIED: sandbox self-test passes 12/12 isolation checks on this PC. A real `claude -p` ran inside the sandbox;
  egress was limited to api.anthropic.com, and mcp-proxy.anthropic.com was denied.

## Not done / blocking
- Test suite: 106 tests, 8 failures and 5 errors after the refactor (old tests expect 1.x behaviour: pre-tick of the
  top candidate, `succeeded` from a Claude exit, direct-host fake claude). Tests must be updated and the new tests written
  (test_security, test_sandbox, test_policy, test_lifecycle, test_gates, test_validation).
- server.py: auth on all routes, Origin/Sec-Fetch checks, Content-Length/timeout/concurrency limits, stop/diagnostics
  routes, Idempotency-Key passthrough.
- engine/sources: provider ids, evidence/compatibility/licence fields, README evidence, npm/crates providers,
  bounded cache, decision engine, retrieval benchmark.
- UI updates for the new states, gates and metrics; CI workflow; docs (SECURITY_MODEL, BUILD_LIFECYCLE, etc.).
- Version bump to 2.0.0, changelog, push and release: NOT done (must not ship with failing tests).
