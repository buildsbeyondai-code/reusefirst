"""Shared test helpers: import path, fixture catalog, and a fake GitHub search API."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "plugins" / "req-analyzer" / "app"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(APP))
import tempfile  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="reqan-test-"))
os.environ["REQAN_STATE_DIR"] = str(TMP / "state")
os.environ["REQAN_APPS_DIR"] = str(TMP / "apps")
os.environ["REQAN_BUILD_ROOT"] = str(TMP)
os.environ["REQAN_UAISES"] = str(FIXTURES / "UAISES_TEST.md")
os.environ["REQAN_UI_STANDARD"] = str(FIXTURES / "UEUIS_TEST.md")
os.environ["REQAN_CLAUDE_BIN"] = str(Path(__file__).resolve().parent / "fake_claude.py")
os.environ["FAKE_CLAUDE_ARGV"] = str(TMP / "argv.jsonl")
os.environ["REQAN_NO_GH_CLI"] = "1"  # tests never read the developer's real GitHub token
os.environ.pop("GITHUB_TOKEN", None)
os.environ.pop("GH_TOKEN", None)

from reqanalyzer import engine, sources  # noqa: E402

REPOS = [
    {"full_name": "acme/stripe-invoices", "name": "stripe-invoices", "html_url": "https://github.com/acme/stripe-invoices",
     "description": "Self-hosted invoicing with recurring billing, PDF invoices and Stripe payments",
     "topics": ["invoice", "billing"], "stargazers_count": 1200, "pushed_at": "2026-10-01T00:00:00Z",
     "license": {"spdx_id": "MIT"}, "language": "Python", "archived": False},
    {"full_name": "acme/claude-invoice-plugin", "name": "claude-invoice-plugin", "html_url": "https://github.com/acme/claude-invoice-plugin",
     "description": "Invoice helper", "topics": ["claude-code-plugin"], "stargazers_count": 5, "pushed_at": None,
     "license": None, "language": None, "archived": True},
    {"full_name": "spam/whitepaper", "name": "whitepaper", "html_url": "https://github.com/spam/whitepaper",
     "description": ("invoice billing payment stripe recurring pdf self-hosted " * 2) + ("lorem ipsum " * 200) + " zebra",
     "topics": [], "stargazers_count": 3, "pushed_at": "2020-01-01T00:00:00Z", "license": None,
     "language": None, "archived": False},
]


class FakeGitHub:
    """Serves /search/repositories. mode: ok | ratelimit | error | empty."""

    def __init__(self, mode="ok"):
        self.mode = mode
        self.queries = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.queries.append(self.path)
                outer.auth = self.headers.get("Authorization")
                if outer.mode == "ratelimit":
                    self.send_response(403); self.end_headers(); return
                if outer.mode == "error":
                    self.send_response(500); self.end_headers(); return
                body = json.dumps({"items": [] if outer.mode == "empty" else REPOS}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def use_fixture_catalog(name="plugins"):
    os.environ["REQAN_PLUGINS_DIR"] = str(FIXTURES / name)
    engine.catalog(reload=True)


def use_github(fake):
    sources.GITHUB_API = fake.url
    sources._cache.clear()
    sources._token_tried = False
    sources._token = None
