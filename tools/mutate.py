#!/usr/bin/env python3
"""Controlled-fault (mutation) check for the high-risk controls: each mutant breaks one safeguard; the named test
modules must FAIL for it. A surviving mutant means the tests would not notice that safeguard breaking.

  python3 tools/mutate.py            # runs every mutant on a scratch copy of the repo; prints killed/survived
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "plugins/req-analyzer/app/reqanalyzer/"

# (file, original, mutant, test modules that must catch it)
MUTANTS = [
    ("server.py", 'if path.startswith("/api/") and path not in PUBLIC_API and not self._token_ok():',
     'if False:', ["test_security"]),
    ("server.py", 'if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":', 'if False:', ["test_security"]),
    ("server.py", 'if cl is None or not cl.strip().isdigit():', 'if cl is None:', ["test_security"]),
    ("sandbox.py", '"--unshare-all", ', '', ["test_sandbox"]),
    # Equivalent mutant (documented): dropping "--tmpfs HOME" leaves HOME empty and writable anyway (bwrap's root is a
    # fresh tmpfs and the host home is never mounted), so the env-clearing control is mutated instead.
    ("sandbox.py", '"--clearenv", ', '', ["test_sandbox"]),
    ("sandbox.py", 'if port != 443 or not _host_allowed(host, self.allow):', 'if port != 443:', ["test_sandbox"]),
    ("sandbox.py", "if self.allow_private or ipaddress.ip_address(i[4][0]).is_global]", "]", ["test_sandbox"]),
    ("policy.py", 'if u.scheme != "https" or u.hostname != "github.com" or u.netloc != "github.com":',
     'if u.scheme != "https":', ["test_policy"]),
    ("policy.py", 'if lic.get("reuse") != "allowed":', 'if False:', ["test_policy", "test_builder"]),
    # Equivalent mutant (documented): without isfinite, NaN/inf are still rejected by the range check below it.
    ("builder.py", 'if not lo <= v <= hi:', 'if False:', ["test_builder", "test_policy"]),
    ("builder.py", 'if manifest(target) != before:', 'if False:', ["test_enhance"]),
    ("gates.py", 'if failed:\n        return L.FAILED', 'if False:\n        return L.FAILED', ["test_policy", "test_builder"]),
    ("gates.py", 'ok = r["code"] == 0 and not r["timed_out"] and counts["passed"] > 0 and counts["failed"] == 0',
     'ok = True', ["test_gates", "test_builder"]),
    ("lifecycle.py", "    RUNNING: {VERIFYING, TIMED_OUT} | _ABORT,", "    RUNNING: {VERIFYING, TIMED_OUT, SUCCEEDED} | _ABORT,",
     ["test_policy"]),
    ("reuse.py", 'if lic["reuse"] == "allowed":', 'if True:', ["test_policy"]),
    ("server.py", 'if path.startswith("/api/") and path != "/api/health" and peer_uid(self.client_address) not in ALLOWED_UIDS:',
     'if False:', ["test_security"]),
    ("builder.py", '"filesystem": {"denyRead": list(CREDENTIAL_PATHS)},', '"filesystem": {},', ["test_builder"]),
    ("builder.py", '"--settings", json.dumps(agent_settings()), ', '', ["test_builder"]),
    ("builder.py", 'exe = os.path.realpath(exe)  # ~/.local/bin/claude is a symlink', 'exe = exe  # ~/.local/bin/claude is a symlink',
     ["test_builder"]),
    ("semantic.py", 'if not c or not isinstance(it.get("fit"), int):', 'if not isinstance(it.get("fit"), int):', ["test_engine"]),
    ("gates.py", 'passed = total - failed - skipped', 'passed = total - failed', ["test_policy"]),
    ("obs.py", '(re.compile(r"\\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[REDACTED]"),', '',
     ["test_policy"]),
]


def main() -> int:
    killed = survived = 0
    for i, (f, old, new, mods) in enumerate(MUTANTS, 1):
        tmp = Path(tempfile.mkdtemp(prefix="mutant-"))
        shutil.copytree(ROOT, tmp / "repo", ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
        target = tmp / "repo" / PKG / f
        src = target.read_text()
        if src.count(old) != 1:
            print(f"#{i} {f}: original text not found exactly once (update the mutant)")
            return 2
        target.write_text(src.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "unittest", *mods], cwd=tmp / "repo" / "tests",
                           capture_output=True, text=True, timeout=900, check=False)
        caught = r.returncode != 0
        killed += caught
        survived += not caught
        print(f"#{i:2} {'KILLED  ' if caught else 'SURVIVED'} {f}: {old.strip()[:70]!r}")
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{killed}/{len(MUTANTS)} mutants killed, {survived} survived")
    return 0 if survived == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
