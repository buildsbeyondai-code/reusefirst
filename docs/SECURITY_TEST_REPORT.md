# Security test report (2.0)

**Run:** 2026-11-06, WSL2 Ubuntu (kernel 6.18), bubblewrap 0.11.1, systemd user scopes available, Python 3.14.4.

**Command:** `python3 -m unittest discover -s tests` → **188 tests, OK, 29.5 s**. Static analysis:
- `ruff check .`: clean.
- `bandit -r plugins/req-analyzer/app -ll`: no Medium/High. 4 Medium false positives are annotated with reasons:
  two URL opens behind scheme guards, and two sandbox-internal `/tmp` mounts.

## Sandbox (tests/test_sandbox.py, real bubblewrap, harmless probes)
| Attack | Result |
|---|---|
| Read `~/.ssh`, `~/.aws`, `~/.claude/.credentials.json`, `~/.config/gh`, browser profiles, `.netrc`, `.git-credentials` | **blocked**: home is an empty tmpfs (probe `secrets_hidden`, glob of `~` returns `[]`) |
| Write outside the project folder | **blocked**: the host file was not created |
| Write to `/usr` | **blocked**: read-only |
| Inherit host secrets via the environment (GITHUB_TOKEN, SSH_AUTH_SOCK, AWS keys, D-Bus) | **blocked**: `--clearenv`, probe `env_clean` |
| Connect to a host service on 127.0.0.1 | **blocked**: separate network namespace |
| Direct connection to 1.1.1.1:443 | **blocked**: network unreachable |
| CONNECT to an unlisted host through the proxy | **403** |
| CONNECT to an allowlisted name that resolves to a private or loopback IP (SSRF / DNS rebinding) | **403 "non-public address"** |
| Plain-HTTP proxying, or CONNECT to port 22 | **403** |
| Docker socket | **absent** |
| Capabilities | CapEff = 0 |
| Fork a long-running child, then time out | **no orphan** after the kill (`pgrep '^sleep 301$'` empty) |
| Malicious `core.fsmonitor` in a generated repo's git config | **no effect on the host** (git runs sandboxed, fsmonitor disabled) |
| Tests that try the network or read home from inside the verifier | the network raises OSError and home is empty (`test_tests_cannot_reach_network_or_home`) |
| Sandbox missing (bwrap absent) | `self_test().ok == False`, `require()` raises, builds are **blocked** (fail closed) |

**Nested Bash sandbox (2.0.2, real Claude, small paid runs).** Claude ran inside the ReuseFirst sandbox with the
build's `--settings`:
- A Bash `open()` of a decoy secret that `filesystem.denyRead` covers raised **PermissionError**.
- `/proc/1/environ` was unreadable.
- `https://pypi.org/simple/pip/` returned 200 through the proxy chain, so installs still work.
- A redirect from the credential path was blocked by the permission layer before execution.
- The real credential was deliberately not read in the test. The auto-mode classifier also refused that probe, so
  the decoy proves the mechanism instead.

**Same-user check (2.0.2).** A WSL client connects with uid 1002 (this user) and a Windows `curl.exe` arrives as
uid 0 (WSL relay); both are accepted. A simulated other account is refused on `/api/session` and on a token-holding
`/api/builds`; `/api/health` stays public. Covered by `test_security.LocalUserTests`.

**Real Claude in the sandbox:** one `claude -p` call (no tools) succeeded through the egress proxy. The proxy log shows
`api.anthropic.com` allowed and `mcp-proxy.anthropic.com` denied. A full real build in the 2.0 sandbox is
**NOT VERIFIED**: it spends usage and needs the user's approval.

## Local API (tests/test_security.py)
| Attack | Result |
|---|---|
| Read builds, analyses, apps, a build, an analysis, diagnostics or outcomes without the token | 403 (7 routes) |
| POST analyze, inputs, reload, build, launch or stop without the token | 403 (6 routes) |
| Wrong token | 403 |
| `/api/session` from same-site / cross-site fetch metadata | 403; same-origin 200; strict mode 403 |
| Foreign `Origin` (other site, other port, `null`) or `Sec-Fetch-Site: cross-site` | 403; own origin 200 |
| Foreign `Host` (DNS rebinding) | 403 |
| `Content-Length: -1` (1.x hung a thread) | immediate 400 |
| Missing Content-Length / `Transfer-Encoding: chunked` | 411 / 400 |
| Body > 64 KiB | 413 |
| Stalled client | connection closed after the socket timeout |
| Concurrency cap reached | 503 |
| `top: true`, `top: "5"`, non-string requirement, keywords not a list | 400 |
| Path traversal in the build id (`..%2F..%2Fetc`), negative `since` | 404 |
| Token file permissions | 0600 |
| Diagnostics output | contains no token |

## Inputs and policy (tests/test_policy.py, tests/test_builder.py)
- **GitHub URL parser:** 18 hostile forms are rejected. Examples: `http:`, `github.com.evil.example`, userinfo,
  explicit port, query, fragment, `/blob/`, `..`, leading `-`, whitespace, newline, non-string, 500 chars.
- **URL fuzz:** 3,000 seeded random strings; anything accepted is exactly `https://github.com/<owner>/<repo>`.
- **Number property test:** 2,000 seeded values (NaN, ±inf, bool, None, containers, hex, Arabic-Indic digits, huge
  values, out of range). Only finite in-range values are accepted.
- **Build inputs** rejected:
  - NaN, inf and bool budgets; budgets out of range; `max_minutes` of 0 or inf; fractional ports;
  - substring-smuggled reuse URLs (regression A7), query/userinfo/http reuse URLs;
  - browser-blocked and reserved ports, bad field ids, nested values, folders outside the build root or inside
    protected folders, non-empty folders, symlinked apps.
- **State machine:** 500 random walks never reach SUCCEEDED without VERIFYING. Terminal states have no exits.
- **Licence:** a GPL clone is removed and a no-licence repository is never cloned. A registry/LICENSE disagreement
  becomes `review`.
- **Redaction:** Anthropic, GitHub, AWS and Slack keys, Bearer headers, `password=` values and private keys are
  removed. Secret-scan findings never echo the secret.

## Build engine (tests/test_builder.py, tests/test_enhance.py, fake Claude)
- An agent reporting success while the tests fail → **failed** (`tests` gate FAILED). Agent success with a hard-coded
  password → **failed** (`secrets` gate).
- Cancel during PREPARING → cancelled; Claude never starts.
- The restart orphan killer refuses a PID whose start time does not match.
- Idempotency key → the same job, with no second build.
- Failed enhancement → the app is untouched and staging is kept.
- A user edit during the build → BLOCKED, and the user's data is preserved byte for byte.
- A successful enhancement is applied atomically. The previous version is kept, and the baseline/regression gates
  are recorded.

## Mutation check (tools/mutate.py)
16/16 faults injected into these controls were caught by the tests: auth, origin, Content-Length, namespaces,
`--clearenv`, egress allowlist, private-IP block, URL parser, licence eligibility, number range, enhancement
manifest, gate decision, test-result parsing, state machine, licence-based clone removal and token redaction.

## Not tested / limitations
- No independent penetration test.
- Kernel or user-namespace escapes are not tested.
- Without strict mode, another local OS user can obtain the token via forged headers (documented; single-user
  target).
- Code generated during the build could read the read-only Claude credential (documented residual risk).
- Firefox and WebKit browser runs: NOT VERIFIED (Chromium only).
- GitHub Actions run: see docs/FINAL_AUDIT.md.
