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
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, builder, engine, history, sources

DEFAULT_PORT = int(os.environ.get("REQAN_PORT", "5057"))
MAX_BODY = 64 * 1024
STATIC = Path(__file__).parent / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
STARTED = time.time()
SESSION_TOKEN = builder.new_token()  # required on build/launch/cancel: defence in depth on top of Host + JSON checks
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
    server_version = f"req-analyzer/{__version__}"

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

    # ------------------------------------------------------------- routes
    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "Host must be 127.0.0.1 or localhost"})
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/app.js", "/app.css", "/theme.js"):
            ctype = "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8"
            return self._send(200, (STATIC / path[1:]).read_bytes(), ctype)
        if path == "/api/session":
            return self._json(200, {"token": SESSION_TOKEN, "claude_cli": bool(builder.claude_bin())})
        if path == "/api/builds":
            return self._json(200, {"builds": builds().list()})
        if path.startswith("/api/builds/"):
            job_id = path.rsplit("/", 1)[-1]
            try:
                since = int((self.path.split("since=", 1) + ["0"])[1].split("&")[0])
            except ValueError:
                since = 0
            job = builds().get(job_id, since)
            return self._json(200, job) if job else self._json(404, {"error": "no such build"})
        if path == "/api/analyses":
            return self._json(200, {"analyses": analyses().list()})
        if path.startswith("/api/analyses/"):
            rec = analyses().get(path.rsplit("/", 1)[-1])
            return self._json(200, rec) if rec else self._json(404, {"error": "no such analysis"})
        if path == "/api/apps":
            return self._json(200, {"apps": builder.existing_apps()})
        if path == "/api/health":
            cat = engine.catalog()
            return self._json(200, {"ok": True, "version": __version__, "uptime_s": round(time.time() - STARTED),
                                    "catalog_size": len(cat["plugins"]), "catalog_errors": cat["errors"],
                                    # UEUIS §8.11 status strip: what this tool can do right now
                                    "claude_cli": bool(builder.claude_bin()),
                                    "github_authenticated": bool(sources.github_token()),
                                    "standard_found": builder.UAISES.exists(),
                                    "ui_standard_found": builder.UI_STANDARD.exists(),
                                    "build_running": bool(builds().active())})
        return self._json(404, {"error": "not found"})

    do_HEAD = do_GET

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "Host must be 127.0.0.1 or localhost"})
        path = self.path.split("?", 1)[0]
        m = re.fullmatch(r"/api/builds/([\w-]{1,64})/(cancel|launch)", path)
        d = re.fullmatch(r"/api/analyses/([\w-]{1,64})/delete", path)
        if path not in ("/api/analyze", "/api/reload", "/api/inputs", "/api/build") and not m and not d:
            return self._json(404, {"error": "not found"})
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._json(415, {"error": "Content-Type must be application/json"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if length > MAX_BODY:
            return self._json(413, {"error": f"body exceeds {MAX_BODY} bytes"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except ValueError as e:
            return self._json(400, {"error": f"invalid JSON: {e}"})

        if d:
            if not hmac.compare_digest(self.headers.get("X-ReqAn-Token") or "", SESSION_TOKEN):
                return self._json(403, {"error": "missing or invalid session token; reload the page"})
            ok = analyses().delete(d.group(1))
            return self._json(200 if ok else 404, {"deleted": ok})
        if path in ("/api/build",) or m:
            if not hmac.compare_digest(self.headers.get("X-ReqAn-Token") or "", SESSION_TOKEN):
                return self._json(403, {"error": "missing or invalid session token; reload the page"})
            try:
                if m and m.group(2) == "cancel":
                    ok = builds().cancel(m.group(1))
                    return self._json(200 if ok else 409, {"cancelled": ok})
                if m:
                    return self._json(200, builds().launch(m.group(1)))
                labels = body.get("labels") if isinstance(body.get("labels"), dict) else {}
                job = builds().start(body.get("requirement"), body.get("answers"),
                                     {str(k)[:40]: str(v)[:120] for k, v in list(labels.items())[:60]})
                return self._json(202, job)
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
        try:
            result = engine.analyze(body.get("requirement"), body.get("keywords"),
                                    top=body.get("top", 10), github=bool(body.get("github", True)))
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
    ap = argparse.ArgumentParser(description="Requirement reuse analyzer web UI")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        srv = make_server(args.port)
    except OSError as e:
        log.error("cannot bind 127.0.0.1:%s: %s", args.port, e)
        return 76
    engine.catalog()  # warm the catalog so the first request is fast
    log.info("listening on http://127.0.0.1:%s/", args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
