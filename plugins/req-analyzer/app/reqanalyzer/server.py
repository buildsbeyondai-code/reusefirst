"""Presentation layer: local HTTP server (stdlib) for the web UI and JSON API.

Binds 127.0.0.1 only. POSTs must be application/json and carry a localhost Host
header, which blocks cross-site form posts and DNS-rebinding attacks.
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, builder, engine, history, obs, sandbox, sources

DEFAULT_PORT = int(os.environ.get("REQAN_PORT", "5057"))
MAX_BODY = 64 * 1024
STATIC = Path(__file__).parent / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
STARTED = time.time()
# Required on every /api/* route except /api/health and /api/session. Rotated on each start, and also written
# to a 0600 file so the CLI and the Claude skill can authenticate (local-user boundary = file permissions).
SESSION_TOKEN = builder.new_token()
STRICT_TOKEN = os.environ.get("REQAN_STRICT_TOKEN") == "1"  # /api/session disabled; the UI needs a #token= link
MAX_INFLIGHT = 32
REQUEST_TIMEOUT_S = 15
PUBLIC_API = {"/api/health", "/api/session"}
_inflight = threading.BoundedSemaphore(MAX_INFLIGHT)


ALLOWED_UIDS = {os.getuid(), 0}  # this user, and root (WSL's localhost relay for Windows browsers runs as root)


def peer_uid(client: tuple) -> int | None:
    """Owner uid of the connecting loopback socket (Linux /proc/net/tcp*), or None when it cannot be determined."""
    import socket as _s
    ip, port = client[0], client[1]
    try:
        v4 = _s.inet_aton(ip.removeprefix("::ffff:"))
    except OSError:
        v4 = None
    keys = set()
    if v4:
        keys.add(f"{int.from_bytes(v4, 'little'):08X}:{port:04X}")
        keys.add(f"0000000000000000FFFF0000{int.from_bytes(v4, 'little'):08X}:{port:04X}")
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(f).read_text().splitlines()[1:]
        except OSError:
            continue
        for ln in lines:
            p = ln.split()
            if len(p) > 7 and p[1].upper() in keys:
                return int(p[7])
    return None


def token_file() -> Path:
    return builder.STATE_DIR / "session.token"


def write_token_file() -> Path:
    f = token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(SESSION_TOKEN)
    os.chmod(f, 0o600)
    return f
_builds: builder.BuildManager | None = None
_history: history.History | None = None


def analyses() -> history.History:
    global _history
    if _history is None:
        _history = history.History()
    return _history


def builds() -> builder.BuildManager:
    global _builds
    if _builds is None:
        _builds = builder.BuildManager()
    return _builds
log = logging.getLogger("reqanalyzer")


class Handler(BaseHTTPRequestHandler):
    server_version = f"reusefirst/{__version__}"
    sys_version = ""
    timeout = REQUEST_TIMEOUT_S  # slow or stalled clients cannot hold a thread

    def log_message(self, fmt, *args):  # route access log through logging, without bodies
        log.info("%s %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------ helpers
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ALLOWED_HOSTS

    def _origin_ok(self) -> bool:
        """Browsers send Origin on POST and Sec-Fetch-Site on all fetches: refuse anything cross-site."""
        if (self.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        try:
            from urllib.parse import urlsplit
            u = urlsplit(origin)
        except ValueError:
            return False
        return u.scheme == "http" and (u.hostname or "") in ALLOWED_HOSTS and u.port == self.server.server_address[1]

    def _token_ok(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-ReqAn-Token") or "", SESSION_TOKEN)

    def _guard(self, path: str):
        """Common checks; returns an error tuple or None."""
        if not self._host_ok():
            return 403, "Host must be 127.0.0.1 or localhost"
        if path.startswith("/api/") and path != "/api/health" and peer_uid(self.client_address) not in ALLOWED_UIDS:
            obs.METRICS.inc("auth_denied_other_user")
            return 403, "requests from other local user accounts are refused"
        if not self._origin_ok():
            return 403, "cross-origin request refused"
        if path.startswith("/api/") and path not in PUBLIC_API and not self._token_ok():
            obs.METRICS.inc("auth_denied")
            return 403, "missing or invalid session token; reload the page"
        return None

    def handle_one_request(self):
        if not _inflight.acquire(blocking=False):
            try:
                self.raw_requestline = self.rfile.readline(65537)
                self.wfile.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.close_connection = True
            return
        try:
            super().handle_one_request()
        finally:
            _inflight.release()

    # ------------------------------------------------------------- routes
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        bad = self._guard(path)
        if bad:
            return self._json(bad[0], {"error": bad[1]})
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/app.js", "/app.css", "/theme.js"):
            ctype = "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8"
            return self._send(200, (STATIC / path[1:]).read_bytes(), ctype)
        if path == "/api/session":
            # Same-origin page scripts only (a cross-site page cannot read this: no CORS headers, and
            # Sec-Fetch-Site/Origin are checked above). Strict mode turns this off entirely.
            if STRICT_TOKEN or (self.headers.get("Sec-Fetch-Site") or "same-origin").lower() not in ("same-origin", "none"):
                return self._json(403, {"error": "token not available here; open the link printed by the plugin"})
            return self._json(200, {"token": SESSION_TOKEN, "claude_cli": bool(builder.claude_bin())})
        if path == "/api/builds":
            return self._json(200, {"builds": builds().list()})
        if path.startswith("/api/builds/"):
            job_id = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"[\w-]{1,64}", job_id):
                return self._json(404, {"error": "no such build"})
            from urllib.parse import parse_qs, urlsplit
            raw = (parse_qs(urlsplit(self.path).query).get("since") or ["0"])[0]
            since = int(raw) if raw.isdigit() and len(raw) < 9 else 0
            job = builds().get(job_id, since)
            return self._json(200, job) if job else self._json(404, {"error": "no such build"})
        if path == "/api/analyses":
            return self._json(200, {"analyses": analyses().list()})
        if path.startswith("/api/analyses/") and path.endswith("/report.md"):
            rec = analyses().get(path.split("/")[3])
            if not rec:
                return self._json(404, {"error": "no such analysis"})
            from . import decision
            return self._send(200, decision.report_markdown(rec).encode(), "text/markdown; charset=utf-8")
        if path.startswith("/api/analyses/"):
            rec = analyses().get(path.rsplit("/", 1)[-1])
            return self._json(200, rec) if rec else self._json(404, {"error": "no such analysis"})
        if path == "/api/apps":
            return self._json(200, {"apps": builder.existing_apps()})
        if path == "/api/outcomes":
            from . import decision
            return self._json(200, decision.outcome_summary(builder.STATE_DIR / "outcomes.jsonl"))
        if path == "/api/diagnostics":
            sb = sandbox.self_test()
            cat = engine.catalog()
            return self._json(200, obs.redact_obj({
                "version": __version__, "python": sys.version.split()[0], "platform": sys.platform,
                "uptime_s": round(time.time() - STARTED), "metrics": obs.METRICS.snapshot(),
                "sandbox": sb, "catalog": {"size": len(cat["plugins"]), "errors": cat["errors"]},
                "github_cache": sources.cache_info(), "builds": builds().list()[:10]}))
        if path == "/api/health":
            cat = engine.catalog()
            sb = sandbox.self_test()
            return self._json(200, {"ok": True, "version": __version__, "uptime_s": round(time.time() - STARTED),
                                    "catalog_size": len(cat["plugins"]), "catalog_errors": len(cat["errors"]),
                                    "sandbox_ok": sb["ok"] and bool(shutil.which("socat")),
                                    "sandbox_error": sb.get("error") or (None if shutil.which("socat") else
                                                                         "socat missing: sudo apt install socat"),
                                    "resource_control": sb.get("resource_control"),
                                    # UEUIS §8.11 status strip: what this tool can do right now
                                    "claude_cli": bool(builder.claude_bin()),
                                    "github_authenticated": bool(sources.github_token()),
                                    "standard_found": builder.UAISES.exists(),
                                    "ui_standard_found": builder.UI_STANDARD.exists(),
                                    "build_running": bool(builds().active())})
        return self._json(404, {"error": "not found"})

    do_HEAD = do_GET

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        bad = self._guard(path)
        if bad:
            return self._json(bad[0], {"error": bad[1]})
        m = re.fullmatch(r"/api/builds/([\w-]{1,64})/(cancel|launch|stop)", path)
        d = re.fullmatch(r"/api/analyses/([\w-]{1,64})/delete", path)
        if path not in ("/api/analyze", "/api/reload", "/api/inputs", "/api/build") and not m and not d:
            return self._json(404, {"error": "not found"})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"error": "Content-Type must be application/json"})
        if self.headers.get("Transfer-Encoding"):
            return self._json(400, {"error": "Transfer-Encoding is not supported; send Content-Length"})
        cl = self.headers.get("Content-Length")
        if cl is None or not cl.strip().isdigit():
            return self._json(400 if cl is not None else 411, {"error": "a non-negative Content-Length is required"})
        length = int(cl)
        if length > MAX_BODY:
            return self._json(413, {"error": f"body exceeds {MAX_BODY} bytes"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except ValueError as e:
            return self._json(400, {"error": f"invalid JSON: {e}"})

        if d:
            ok = analyses().delete(d.group(1))
            return self._json(200 if ok else 404, {"deleted": ok})
        if path in ("/api/build",) or m:
            try:
                if m and m.group(2) == "cancel":
                    ok = builds().cancel(m.group(1))
                    return self._json(200 if ok else 409, {"cancelled": ok})
                if m and m.group(2) == "stop":
                    ok = builds().stop(m.group(1))
                    return self._json(200 if ok else 409, {"stopped": ok})
                if m:
                    return self._json(200, builds().launch(m.group(1)))
                labels = body.get("labels") if isinstance(body.get("labels"), dict) else {}
                aid = body.get("analysis_id")
                aid = aid if isinstance(aid, str) and history.ID_RE.fullmatch(aid) else None
                job = builds().start(body.get("requirement"), body.get("answers"),
                                     {str(k)[:40]: str(v)[:120] for k, v in list(labels.items())[:60]},
                                     idem_key=self.headers.get("Idempotency-Key"), analysis_id=aid)
                return self._json(200 if job.get("duplicate") else 202, job)
            except builder.BuildError as e:
                return self._json(409 if "still running" in str(e) else 400, {"error": str(e)})
        if path == "/api/inputs":
            req = body.get("requirement")
            try:
                req, _ = engine.validate(req, [])
            except engine.InputError as e:
                return self._json(400, {"error": str(e)})
            target = body.get("target") or None
            if target is not None and not isinstance(target, str):
                return self._json(400, {"error": "target must be an app folder path"})
            if target:
                try:
                    builder.enhance_target(target)
                except builder.BuildError as e:
                    return self._json(400, {"error": str(e)})
            analysis = None
            try:
                analysis = engine.analyze(req, top=5, github=bool(body.get("github", True)))
            except Exception:  # reuse options are optional context; inputs still work without them
                log.exception("analysis for inputs failed")
            return self._json(200, builder.required_inputs(req, analysis, target))
        if path == "/api/reload":
            cat = engine.catalog(reload=True)
            return self._json(200, {"catalog_size": len(cat["plugins"]), "errors": cat["errors"]})
        top = body.get("top", 10)
        if isinstance(top, bool) or not isinstance(top, int):
            return self._json(400, {"error": "top must be an integer"})
        try:
            result = engine.analyze(body.get("requirement"), body.get("keywords"),
                                    top=top, github=bool(body.get("github", True)), semantic=body.get("semantic") is True)
        except (engine.InputError, TypeError, ValueError) as e:
            return self._json(400, {"error": str(e)})
        except Exception:  # unexpected: log with traceback, return a structured error, keep serving
            log.exception("analyze failed")
            return self._json(500, {"error": "internal error; see server log"})
        try:
            kws = body.get("keywords") if isinstance(body.get("keywords"), list) else []
            result["saved"] = analyses().save(result, [str(k)[:60] for k in kws[:20]], bool(body.get("github", True)))
        except OSError:  # saving history must never fail the analysis itself
            log.exception("could not save analysis history")
        return self._json(200, result)


def make_server(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reuse-First Builder (ReuseFirst) web UI")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    h = logging.StreamHandler()
    h.setFormatter(obs.JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    if not sys.platform.startswith("linux"):
        log.error("ReuseFirst needs Linux or WSL2 (process groups and the bubblewrap sandbox); this is %s", sys.platform)
        return 78
    try:
        srv = make_server(args.port)
    except OSError as e:
        log.error("cannot bind 127.0.0.1:%s: %s", args.port, e)
        return 76
    engine.catalog()  # warm the catalog so the first request is fast
    write_token_file()
    threading.Thread(target=sandbox.self_test, kwargs={"state_dir": builder.STATE_DIR}, daemon=True).start()
    log.info("listening on http://127.0.0.1:%s/ (token file %s)", args.port, token_file())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _builds:
            _builds.stop_all()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
