# Build lifecycle (2.0)

`lifecycle.py` defines the states and legal transitions. Every transition is recorded in `job.transitions` with a
time and, when unsuccessful, a reason. `job.json` is rewritten atomically (temp file + `os.replace`).

```
CREATED → VALIDATED → QUEUED → PREPARING → RUNNING → VERIFYING → SUCCEEDED | PARTIALLY_COMPLETED
  any active state → FAILED | CANCELLED | INTERRUPTED | BLOCKED;  RUNNING/VERIFYING → TIMED_OUT
```

| State | Meaning |
|---|---|
| validated | Inputs passed validation; standards readable; sandbox verified |
| preparing | New app: folder created and re-checked. Enhance: verified backup, staging copy, baseline tests. Reuse sources cloned at pinned commits |
| running | Claude Code in the sandbox (the time limit applies here) |
| verifying | ReuseFirst's own gates (docs/QUALITY_GATES.md) |
| **succeeded** | Every mandatory gate VERIFIED (or N/A); for enhancements, also applied atomically |
| partially_completed | No mandatory gate failed, but at least one could not be verified (for example, OSV unreachable). An enhancement is **not** applied |
| failed | Claude failed (crash, spending cap) or a mandatory gate failed; `reasons` lists which |
| timed_out | The time limit was reached; the process tree was killed |
| cancelled | The user cancelled; honoured in every active state (also before Claude starts) |
| interrupted | The server restarted mid-build. Leftover processes are killed only if their recorded start time still matches the PID (no PID-reuse kills) |
| blocked | Enhancement verified, but the user's app changed during the build, so nothing was applied |

## Transactional enhancement
1. Re-check the target (symlink/TOCTOU).
2. Back it up with tar.gz, then **verify** the backup by re-reading every member and checking every app file is
   present.
3. Record a manifest (size + mtime) of the app's own files.
4. Copy to `~/apps/.reusefirst-staging/<app>-<job>`. The copy is mounted at the app's real path inside the sandbox,
   so venv shebangs and absolute paths keep working.
5. Run the existing tests on the staging copy (baseline).
6. Build, then verify. The `regression` gate requires that tests which passed before still pass, and that the number
   of passing tests did not drop.
7. Only if SUCCEEDED: compare the manifest. If the user changed the app meanwhile, the state is BLOCKED and nothing
   is applied. Otherwise:
   - journal the swap in `job.json`;
   - `renameat2(RENAME_EXCHANGE)` swaps staging and app atomically;
   - the previous version moves to `backups/<app>-before-<job>`.

   Recovery after a crash during the swap uses the journal and the staging inode.
8. On any other outcome the app is untouched, and the attempted version stays in staging for review.

## Concurrency, duplicates and resources
- One build runs at a time. A second start returns 409.
- `Idempotency-Key` on `POST /api/build` returns the original job for 10 minutes, so a double click or retry never
  starts a second build.
- Cost is reported as Claude's own figure (`cost_usd`, "model-reported estimate, not billing") along with `usage`
  tokens and turns. The `--max-budget-usd` cap is enforced by Claude Code.
- Outcomes (numbers only) are appended to `outcomes.jsonl` and summarised at `/api/outcomes`.

## Launch
Only SUCCEEDED builds can be launched.
1. `run.sh` runs in the sandbox with no network and 1 GiB / 256 tasks.
2. Only its port is forwarded to the host's 127.0.0.1.
3. A health check (HTTP < 500 within 30 s) must pass, otherwise the app is stopped and the error is shown.
4. Stop: `POST /api/builds/<id>/stop`. All apps are stopped when the server shuts down.
