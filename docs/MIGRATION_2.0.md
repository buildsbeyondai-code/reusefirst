# Migrating from 1.x to 2.0

1. **Install bubblewrap** for builds: `sudo apt install bubblewrap`.
   - WSL2 works as is.
   - Ubuntu 24.04 outside WSL: allow unprivileged user namespaces for bwrap, or builds will be blocked.
   - Check the status bar: "Build sandbox verified". `GET /api/health` shows `sandbox_ok`.
2. **Update the plugin:** `claude plugin marketplace update reusefirst && claude plugin update reusefirst@reusefirst`.
   Then restart the 5057 server when no build is running. The next Claude Code session starts 2.0.
3. **Scripts calling the API** must send `X-ReqAn-Token` on every `/api/*` route except `/api/health`, including GETs:
   `TOKEN=$(cat ~/.local/state/req-analyzer/session.token)`.
   - Cross-origin callers are refused.
   - POSTs need `Content-Length`.
   - Use `Idempotency-Key` on `/api/build`.
4. **Status names changed.** `timed-out` → `timed_out`. New states: `created`, `validated`, `preparing`, `verifying`,
   `partially_completed`, `blocked`.
   - `succeeded` now requires the independent gates.
   - Old job files are read and mapped automatically.
5. **Reuse.**
   - Nothing is pre-ticked unless it passes the reuse policy.
   - The agent no longer clones; ReuseFirst does, into `upstream/<owner>__<repo>`.
   - `reuse` entries must end with a plain `https://github.com/owner/repo[/tree/ref/path]` URL.
6. **Limits.** `budget_usd` (0.5–50) and `max_minutes` (2–180) are now rejected when out of range, instead of being
   clamped.
7. **Analysis JSON is additive:**
   - `profile`, `packages`, `providers`, `decision`, `stale` and `confidence_mode`;
   - per-candidate `id`, `relevance`, `evidence`, `licence`, `compatibility`, `maintenance`, `security_risk`,
     `recommendation` and `auto_reuse_eligible`.

   `closeness` and `verdict` remain.
8. **Launched apps** now run in the sandbox with no network access. Apps that call external APIs at run time cannot
   reach them when launched from ReuseFirst; run them yourself with `./run.sh`.
