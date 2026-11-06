"""SessionStart hook: start the web UI on 127.0.0.1:5057 if nothing is listening. Never blocks the session."""
import os
import socket
import subprocess
import sys
from pathlib import Path

PORT = int(os.environ.get("REQAN_PORT", "5057"))

# Unsupported environments fail clearly and never block the session (Linux/WSL2 with Python 3.11+ only).
if not sys.platform.startswith("linux") or sys.version_info < (3, 11):
    print(f"ReuseFirst: needs Linux or WSL2 with Python 3.11+ (found {sys.platform}, Python {sys.version.split()[0]}); "
          "the web UI was not started.", file=sys.stderr)
    sys.exit(0)
APP = Path(__file__).resolve().parent.parent / "app"

with socket.socket() as s:
    s.settimeout(0.5)
    if s.connect_ex(("127.0.0.1", PORT)) == 0:
        sys.exit(0)  # already running (systemd service or earlier session)

log_dir = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "req-analyzer"
log_dir.mkdir(parents=True, exist_ok=True)
with open(log_dir / "server.log", "ab") as log:
    subprocess.Popen([sys.executable, "-m", "reqanalyzer.server", "--port", str(PORT)], cwd=APP,
                     env={**os.environ, "PYTHONPATH": str(APP)}, stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True)
