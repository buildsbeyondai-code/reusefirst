# Security model (2.0)

## Assets
- The user's account, files and credentials: SSH keys, cloud keys, browser profiles, `~/.claude`, `gh` token.
- Local services on 127.0.0.1, such as SysPerf on 5056.
- The user's Claude usage (money) and their existing apps in `~/apps`.

## Threats and trust levels
| Source | Trust | Examples |
|---|---|---|
| The user (UI, skill) | trusted intent; inputs still validated | requirement, build inputs, reuse picks |
| ReuseFirst policy and code | trusted | sandbox, gates, licence rules |
| LLM-generated plans and code | **untrusted** | anything the build agent writes or runs |
| Retrieved content | **untrusted** | GitHub READMEs, repo code, plugin manifests, package metadata, web pages |
| Tool output | **untrusted** | test output, stream events (redacted before storage) |
| Other local OS users / processes | untrusted | may connect to 127.0.0.1:5057 |

Prompt injection is contained by **permissions, not wording**:
- Untrusted code and text only ever run or get read inside the sandbox.
- The agent cannot clone or fetch beyond the egress allowlist.
- Success is decided by ReuseFirst's own gates, not by the agent's report.

The build prompt also labels `upstream/` and fetched content as untrusted data. That is defence in depth only.

## Execution isolation (`sandbox.py`)
Every execution of untrusted code goes through bubblewrap. That covers the build agent, reuse clones, test re-runs,
linters, `git status` on generated repos, the launch check, and launched apps.
- **Namespaces:** `--unshare-all` (user, pid, ipc, uts, cgroup, mount, net), `--die-with-parent`, `--new-session`
  (no TIOCSTI), `--cap-drop ALL`, `--clearenv`.
- **Filesystem:** `/usr` and `/etc` are read-only, and `/bin` and `/lib*` mirror the host's symlinks. HOME, `/tmp` and
  `/run` are empty tmpfs. The host home is **never mounted**. Only the project folder is bound read-write, at its real
  path, or a staging copy is bound at the app's path. ReuseFirst's own package is read-only at `/opt/reusefirst`.
  There is no `/var/run/docker.sock`.
- **Network:** a private namespace with loopback only, so host services on 127.0.0.1 are unreachable. When a phase
  needs egress, `sbx_init.py` relays 127.0.0.1:3128 to a Unix socket served by the host-side `EgressProxy`. That proxy:
  - accepts only `CONNECT <host>:443`;
  - only for allowlisted hostnames;
  - only when the name resolves to a **public** IP (no SSRF to host or LAN through DNS);
  - logs every decision.

  Phases and their egress:

  | Phase | Allowed hosts |
  |---|---|
  | Build agent | `api.anthropic.com`, `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org` |
  | Reuse clone | `github.com`, `codeload.github.com` |
  | Verification and launched apps | none |

- **Resources:** a `systemd-run --user --scope` with MemoryMax, MemorySwapMax=0, TasksMax and CPUQuota, plus
  rlimits (no core dumps, 2 GiB file size, 4096 files).
  - Build: 4 GiB, 2048 tasks, 300% CPU. Tests: 4 GiB, 512 tasks. Apps: 1 GiB, 256 tasks.
  - The project size is capped at 6 GiB (`REQAN_MAX_PROJECT_MB`) by a watchdog.
  - Timeouts and cancel kill the whole process group. The pid namespace guarantees no survivors when the sandbox
    init exits.
- **The one deliberate secret:** the Claude credential file is bind-mounted **read-only** into the build agent's
  sandbox, and only there, because Claude Code cannot run without it.
  - Residual risk: code generated during the build could read it. It could send it only to the four allowlisted
    hosts, or write it into the project folder.
  - Mitigation: the secret-scan gate fails a build that leaves known token patterns in its files.
  - The credential is never mounted for clones, tests or launched apps.
- **Fail closed:** `self_test()` runs 13 harmless adversarial probes at start-up: secrets hidden, home
  empty/writable, host state hidden, `/usr` read-only, project writable, host loopback blocked, direct egress
  blocked, proxy denies unlisted hosts, environment cleared, no Docker socket, no capabilities, pid namespace.
  - If bwrap is missing or any probe fails, `/api/build` refuses: "builds are blocked because no verified sandbox
    is available".
  - There is **no** fallback to host execution and no override flag.

## Local API (`server.py`)
- Binds to 127.0.0.1 only. The `Host` header must be 127.0.0.1 or localhost (DNS rebinding).
- `Origin` must be this server, and `Sec-Fetch-Site: cross-site` is refused (CSRF from web pages).
- **Every `/api/*` route except `/api/health` and `/api/session` needs `X-ReqAn-Token`.** That covers analyses,
  builds, reports, apps, diagnostics and outcomes.
  - The token is 192-bit random and rotated on every server start.
  - It is written to `~/.local/state/req-analyzer/session.token` (0600) for the CLI and skill.
  - `/api/session` gives it to same-origin page scripts only. `REQAN_STRICT_TOKEN=1` disables it, and the UI then
    takes the token from a `#token=` link.
  - Residual risk: without strict mode, another local OS user could request `/api/session` with forged headers.
    ReuseFirst's target is a single-user WSL2 machine. Use strict mode on shared hosts.
- **HTTP:**
  - POST needs a non-negative Content-Length of at most 64 KiB (411/400/413). Transfer-Encoding is refused.
  - Body must be JSON (415). Sockets time out after 15 s, and at most 32 requests are in flight (503 beyond that).
  - Errors are generic: there are no tracebacks in responses.
- **Inputs:**
  - Money and time limits are finite, range-checked numbers; booleans, NaN and infinity are rejected.
  - Ports are integers in 1024–65535, excluding reserved and browser-blocked ports.
  - Reuse URLs go through a structural `https://github.com/<owner>/<repo>[/tree/<ref>/<path>]` parse (no userinfo,
    port, query, fragment or `..`).
  - Job and analysis IDs are matched by regex.
  - Output folders must be inside the build root and outside `~/.claude`, `~/.config`, `~/.ssh`, `~/.local` and the
    tool itself. The folder is re-checked after creation (symlink / TOCTOU). Symlinked apps are not offered for
    enhancement.

## Supply chain
- See `docs/REUSE_POLICY.md` for SPDX rules, pinned clones and provenance.
- Every build gets a CycloneDX 1.5 SBOM (`docs/sbom.cdx.json`) and an OSV known-vulnerability check.
- ReuseFirst itself has **no runtime dependencies** (stdlib only).
- CI pins actions to commit SHAs, uses `permissions: contents: read`, and checks out with
  `persist-credentials: false`. It needs no secrets.

## Logging and privacy
- Logs are JSON lines. `obs.redact()` removes private keys, Anthropic, GitHub, AWS, Slack and Google keys,
  `Authorization` headers and `password=`-style values from every log line, build event and stored stream line.
- `/api/diagnostics` (token-protected) redacts again.
- The GitHub token is never logged or returned.

## Out of scope / not verified
- No independent penetration test or production certification has been done.
- macOS and native Windows are unsupported. The server refuses to start, and the hook explains why.
- Kernel-level escapes from bubblewrap/user namespaces are outside what ReuseFirst can test.
