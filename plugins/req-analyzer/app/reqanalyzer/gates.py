"""Application layer: deterministic release gates run AFTER Claude finishes, independent of the generating agent.

Every gate returns VERIFIED, NOT_VERIFIED, FAILED, BLOCKED or N/A with evidence. Anything that executes project
code (tests, launch, git, linters) runs in the sandbox with no network. Pure file inspections run on the host
(reading files, never executing them). See docs/QUALITY_GATES.md.
"""
from __future__ import annotations

import ast
import json
import os
import re
import socket
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from . import sandbox
from .obs import redact

VERIFIED, NOT_VERIFIED, FAILED, BLOCKED, NA = "VERIFIED", "NOT_VERIFIED", "FAILED", "BLOCKED", "N/A"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "upstream", ".pytest_cache", "browser-profile",
             ".mypy_cache", ".ruff_cache", "dist", "build"}
WEB_TYPES = ("Web app (browser UI + local server)", "REST API service", "Mobile-friendly PWA")
OSV_URL = os.environ.get("REQAN_OSV_URL", "https://api.osv.dev/v1/querybatch")
TEST_TIMEOUT_S = 900


def gate(gid: str, name: str, mandatory: bool, status: str, detail: str = "", evidence: str = "") -> dict:
    return {"id": gid, "name": name, "mandatory": mandatory, "status": status, "detail": redact(detail)[:600],
            "evidence": redact(evidence)[-3000:]}


def project_files(root: Path, suffixes: tuple[str, ...] | None = None, max_files: int = 20000):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            if p.is_symlink():
                continue
            if suffixes is None or p.suffix in suffixes:
                n += 1
                if n > max_files:
                    return
                yield p


# -------------------------------------------------------------- file gates
REQUIRED_DOCS = ("README.md", "docs/REQUIREMENTS.md", "docs/ARCHITECTURE.md", "docs/DECISIONS.md")


def g_required_files(w: Path, enhance: bool) -> dict:
    need = list(REQUIRED_DOCS) + ["docs/ENHANCE_REPORT.md" if enhance else "docs/COMPLETION_REPORT.md"]
    missing = [f for f in need if not (w / f).is_file()]
    return gate("required_files", "Required documents present", True, FAILED if missing else VERIFIED,
                f"missing: {', '.join(missing)}" if missing else f"{len(need)} documents present")


def g_syntax(w: Path) -> dict:
    """Parses every Python file with ast (no execution). JS needs node, which may be absent."""
    bad, n = [], 0
    for p in project_files(w, (".py",)):
        n += 1
        try:
            ast.parse(p.read_bytes(), filename=str(p))
        except (SyntaxError, ValueError) as e:
            bad.append(f"{p.relative_to(w)}:{getattr(e, 'lineno', '?')}: {e.__class__.__name__}")
    js = sum(1 for _ in project_files(w, (".js", ".mjs", ".ts")))
    if bad:
        return gate("syntax", "Syntax valid", True, FAILED, f"{len(bad)} file(s) do not parse", "\n".join(bad[:20]))
    if n == 0 and js == 0:
        return gate("syntax", "Syntax valid", True, NOT_VERIFIED, "no Python or JavaScript source found")
    detail = f"{n} Python file(s) parse"
    if js:
        detail += f"; {js} JavaScript/TypeScript file(s) NOT VERIFIED (no node in the verifier)"
    return gate("syntax", "Syntax valid", True, VERIFIED, detail)


SECRET_RES = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("AWS key", re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("hard-coded password", re.compile(r"(?i)\b(password|passwd|secret|api_key)\s*=\s*['\"][^'\"\s]{8,}['\"]")),
]


def scan_secrets(w: Path) -> list[str]:
    hits = []
    for p in project_files(w):
        try:
            if p.stat().st_size > 1_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, rx in SECRET_RES:
            m = rx.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{p.relative_to(w)}:{line}: {name}")
    return hits


def g_secrets(w: Path) -> dict:
    hits = scan_secrets(w)
    return gate("secrets", "No secrets in files", True, FAILED if hits else VERIFIED,
                f"{len(hits)} possible secret(s)" if hits else "no known secret patterns", "\n".join(hits[:20]))


# ------------------------------------------------------- dependencies / SBOM
def _req_lines(text: str) -> list[tuple[str, str | None]]:
    out = []
    for ln in text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln or ln.startswith("-"):
            continue
        m = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(==\s*([A-Za-z0-9.*+!-]+))?", ln)
        if m:
            out.append((m.group(1), m.group(3)))
    return out


def dependencies(w: Path) -> list[dict]:
    """Declared + installed dependencies. Installed versions (from .venv dist-info) win: they are what runs."""
    deps: dict[tuple[str, str], dict] = {}

    def add(eco, name, version, source):
        key = (eco, re.sub(r"[-_.]+", "-", name).lower())
        cur = deps.get(key)
        if not cur or (version and not cur.get("version")) or source == "installed":
            deps[key] = {"ecosystem": eco, "name": name, "version": version, "source": source}

    for f in sorted(w.glob("requirements*.txt")):
        for n, v in _req_lines(f.read_text(errors="ignore")):
            add("PyPI", n, v, f.name)
    pp = w / "pyproject.toml"
    if pp.is_file():
        try:
            for d in (tomllib.loads(pp.read_text(errors="ignore")).get("project") or {}).get("dependencies") or []:
                for n, v in _req_lines(str(d)):
                    add("PyPI", n, v, "pyproject.toml")
        except (tomllib.TOMLDecodeError, AttributeError):
            pass
    for meta in w.glob(".venv/lib/python*/site-packages/*.dist-info/METADATA"):
        try:
            head = meta.read_text(errors="ignore")[:2000]
        except OSError:
            continue
        n = re.search(r"^Name: (.+)$", head, re.M)
        v = re.search(r"^Version: (.+)$", head, re.M)
        if n and v and n.group(1).strip().lower() not in ("pip", "setuptools", "wheel"):
            add("PyPI", n.group(1).strip(), v.group(1).strip(), "installed")
    lock = w / "package-lock.json"
    pj = w / "package.json"
    if lock.is_file():
        try:
            for path, info in (json.loads(lock.read_text(errors="ignore")).get("packages") or {}).items():
                if path.startswith("node_modules/") and isinstance(info, dict) and info.get("version"):
                    add("npm", path.rsplit("node_modules/", 1)[-1], info["version"], "package-lock.json")
        except (ValueError, AttributeError):
            pass
    elif pj.is_file():
        try:
            j = json.loads(pj.read_text(errors="ignore"))
            for sect in ("dependencies", "devDependencies"):
                for n, v in (j.get(sect) or {}).items():
                    add("npm", n, v if re.fullmatch(r"\d+\.\d+\.\d+", str(v)) else None, "package.json")
        except (ValueError, AttributeError):
            pass
    return sorted(deps.values(), key=lambda d: (d["ecosystem"], d["name"].lower()))


def cyclonedx(name: str, deps: list[dict]) -> dict:
    def purl(d):
        eco = "pypi" if d["ecosystem"] == "PyPI" else "npm"
        return f"pkg:{eco}/{d['name'].lower() if eco == 'pypi' else d['name']}" + (f"@{d['version']}" if d["version"] else "")
    return {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
            "metadata": {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "tools": [{"vendor": "ReuseFirst", "name": "reusefirst-gates"}],
                         "component": {"type": "application", "name": name}},
            "components": [{"type": "library", "name": d["name"], **({"version": d["version"]} if d["version"] else {}),
                            "purl": purl(d), "properties": [{"name": "reusefirst:source", "value": d["source"]}]}
                           for d in deps]}


def g_sbom(w: Path, name: str) -> tuple[dict, list[dict]]:
    deps = dependencies(w)
    (w / "docs").mkdir(exist_ok=True)
    (w / "docs" / "sbom.cdx.json").write_text(json.dumps(cyclonedx(name, deps), indent=1))
    unpinned = [d["name"] for d in deps if not d["version"]]
    st = VERIFIED if not unpinned else NOT_VERIFIED
    return gate("sbom", "Dependency inventory (CycloneDX SBOM) and pinning", False, st,
                f"{len(deps)} dependencies in docs/sbom.cdx.json" + (f"; unpinned: {', '.join(unpinned[:10])}" if unpinned else "; all pinned")), deps


def osv_check(deps: list[dict], timeout: float = 20) -> tuple[str, list[str]]:
    """Query OSV for known vulnerabilities. Sends only public package names and versions."""
    q = [d for d in deps if d["version"]]
    if not q:
        return VERIFIED, []
    body = json.dumps({"queries": [{"package": {"name": d["name"], "ecosystem": d["ecosystem"]}, "version": d["version"]}
                                   for d in q[:500]]}).encode()
    if not OSV_URL.startswith(("https://", "http://127.0.0.1")):
        return NOT_VERIFIED, ["OSV URL rejected"]
    try:
        req = urllib.request.Request(OSV_URL, data=body, headers={"Content-Type": "application/json",
                                                                  "User-Agent": "reusefirst-gates"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 - scheme checked above (https or 127.0.0.1)
            res = json.load(r).get("results") or []
    except (urllib.error.URLError, OSError, ValueError) as e:
        return NOT_VERIFIED, [f"OSV unreachable: {e}"]
    found = []
    for d, r in zip(q, res, strict=False):
        ids = [v.get("id") for v in (r or {}).get("vulns") or []]
        if ids:
            found.append(f"{d['name']}=={d['version']}: {', '.join(ids[:5])}")
    return (FAILED if found else VERIFIED), found


def g_vulns(deps: list[dict]) -> dict:
    st, found = osv_check(deps)
    detail = ("no known vulnerabilities (OSV)" if st == VERIFIED else
              f"{len(found)} vulnerable package(s)" if st == FAILED else "vulnerability database not reachable")
    return gate("vulnerabilities", "Known-vulnerability check (OSV)", True, st, detail, "\n".join(found[:30]))


def g_provenance(w: Path, reuse: list) -> dict:
    if not reuse:
        return gate("provenance", "Reuse provenance and licences", True, NA, "no external code selected")
    prov = w / "docs" / "REUSE_PROVENANCE.md"
    if not prov.is_file():
        return gate("provenance", "Reuse provenance and licences", True, FAILED, "docs/REUSE_PROVENANCE.md missing")
    gi = (w / ".gitignore").read_text(errors="ignore") if (w / ".gitignore").is_file() else ""
    if (w / "upstream").exists() and (w / ".git").exists() and "upstream" not in gi:
        return gate("provenance", "Reuse provenance and licences", True, FAILED,
                    "upstream/ clones are not in .gitignore (third-party code would be committed)")
    return gate("provenance", "Reuse provenance and licences", True, VERIFIED, "provenance recorded by ReuseFirst")


# -------------------------------------------------------------- sandboxed
def _python(w: Path) -> str:
    """Relative to the project, because the project may be mounted at another path inside the sandbox."""
    return "./.venv/bin/python" if (w / ".venv" / "bin" / "python").exists() else "/usr/bin/python3"


def test_command(w: Path) -> list[str] | None:
    py = _python(w)
    has_pytest = any(w.glob(".venv/lib/python*/site-packages/pytest"))
    tests_dir = next((d for d in ("tests", "test") if (w / d).is_dir()), None)
    if has_pytest and (tests_dir or (w / "pytest.ini").exists() or (w / "pyproject.toml").exists()):
        return [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if tests_dir and any((w / tests_dir).glob("test*.py")):
        return [py, "-m", "unittest", "discover", "-s", tests_dir]
    return None


def parse_test_output(out: str) -> dict:
    """Counts from unittest or pytest output. Skipped tests are NOT passed tests."""
    passed = failed = skipped = 0
    m = re.search(r"Ran (\d+) tests?", out)
    if m:
        total = int(m.group(1))
        tail = out[m.end():]
        for key in ("failures", "errors"):
            f = re.search(rf"(?<!expected )\b{key}=(\d+)", tail)
            failed += int(f.group(1)) if f else 0
        for key in ("skipped", "expected failures"):
            k = re.search(rf"\b{key}=(\d+)", tail)
            skipped += int(k.group(1)) if k else 0
        u = re.search(r"\bunexpected successes=(\d+)", tail)
        failed += int(u.group(1)) if u else 0
        passed = total - failed - skipped
    else:
        for n, kind in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", out):
            if kind == "passed":
                passed += int(n)
            elif kind in ("skipped", "xfailed"):
                skipped += int(n)
            else:
                failed += int(n)
    return {"passed": passed, "failed": failed, "skipped": skipped}


def run_tests(w: Path, timeout_s: int = TEST_TIMEOUT_S, inside: Path | None = None) -> dict:
    cmd = test_command(w)
    if not cmd:
        return {"status": "none", "detail": "no test suite found (tests/ with test*.py, or pytest)"}
    try:
        r = sandbox.run(sandbox.Spec(workdir=w, mount_as=inside, memory_mb=4096, tasks=512), cmd, timeout_s=timeout_s)
    except sandbox.SandboxUnavailable as e:
        return {"status": "blocked", "detail": str(e)}
    counts = parse_test_output(r["output"])
    ok = r["code"] == 0 and not r["timed_out"] and counts["passed"] > 0 and counts["failed"] == 0
    return {"status": "passed" if ok else "failed", "command": " ".join(cmd), "exit": r["code"],
            "timed_out": r["timed_out"], **counts, "output": r["output"][-3000:], "duration_s": r["duration_s"]}


def g_tests(w: Path, result: dict | None = None) -> tuple[dict, dict]:
    t = result or run_tests(w)
    if t["status"] == "none":
        return gate("tests", "Test suite passes (re-run independently)", True, FAILED, t["detail"]), t
    if t["status"] == "blocked":
        return gate("tests", "Test suite passes (re-run independently)", True, BLOCKED, t["detail"]), t
    detail = f"{t['passed']} passed, {t['failed']} failed, {t.get('skipped', 0)} skipped" + \
        (" (timed out)" if t.get("timed_out") else "") + \
        f" in {t['duration_s']} s: {t['command']}"
    return gate("tests", "Test suite passes (re-run independently)", True,
                VERIFIED if t["status"] == "passed" else FAILED, detail, t.get("output", "")), t


def g_lint(w: Path, inside: Path | None = None) -> dict:
    ruff = w / ".venv" / "bin" / "ruff"
    if not ruff.exists():
        return gate("static_analysis", "Static analysis (ruff)", False, NOT_VERIFIED, "ruff not installed in the project")
    try:
        r = sandbox.run(sandbox.Spec(workdir=w, mount_as=inside), ["./.venv/bin/ruff", "check", "--no-cache", "."],
                        timeout_s=180)
    except sandbox.SandboxUnavailable as e:
        return gate("static_analysis", "Static analysis (ruff)", False, BLOCKED, str(e))
    return gate("static_analysis", "Static analysis (ruff)", False, VERIFIED if r["code"] == 0 else FAILED,
                "ruff clean" if r["code"] == 0 else "ruff reported problems", r["output"])


def g_git(w: Path, wanted: bool, inside: Path | None = None) -> dict:
    if not wanted:
        return gate("git", "Committed to git", False, NA, "git not requested")
    if not (w / ".git").is_dir():
        return gate("git", "Committed to git", False, FAILED, "no git repository")
    try:  # git reads the repo's .git/config (fsmonitor, hooks): run it sandboxed
        r = sandbox.run(sandbox.Spec(workdir=w, mount_as=inside), ["/usr/bin/git", "-c", "core.fsmonitor=false", "status", "--porcelain"],
                        timeout_s=60)
    except sandbox.SandboxUnavailable as e:
        return gate("git", "Committed to git", False, BLOCKED, str(e))
    dirty = [ln for ln in r["output"].splitlines() if ln.strip()]
    return gate("git", "Committed to git", False, VERIFIED if r["code"] == 0 and not dirty else NOT_VERIFIED,
                "working tree clean" if not dirty else f"{len(dirty)} uncommitted change(s)", "\n".join(dirty[:20]))


def free_host_port(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def http_ok(port: int, deadline_s: float) -> tuple[bool, str]:
    end = time.time() + deadline_s
    last = "no response"
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
                s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                head = s.recv(64).decode("latin-1", "replace")
            m = re.match(r"HTTP/\d\.\d (\d{3})", head)
            if m:
                code = int(m.group(1))
                if code < 500:
                    return True, f"HTTP {code}"
                last = f"HTTP {code}"
        except OSError as e:
            last = str(e)
        time.sleep(0.5)
    return False, last


_PORT_PATTERNS = [
    re.compile(r"""environ\.get\(\s*["']([A-Z][A-Z0-9_]*PORT[A-Z0-9_]*)["']\s*,\s*["']?(\d{2,5})"""),
    re.compile(r"""getenv\(\s*["']([A-Z][A-Z0-9_]*PORT[A-Z0-9_]*)["']\s*,\s*["']?(\d{2,5})"""),
    re.compile(r"""\$\{([A-Z][A-Z0-9_]*PORT[A-Z0-9_]*):-(\d{2,5})\}"""),
    re.compile(r"""process\.env\.([A-Z][A-Z0-9_]*PORT[A-Z0-9_]*)\s*(?:\|\||\?\?)\s*["']?(\d{2,5})"""),
]


def detect_port(w: Path) -> tuple[str | None, int | None]:
    """(env var, default port) the app reads its port from, found in run.sh, then its source (read, never executed)."""
    files = [w / "run.sh"] + [p for p in project_files(w, (".py", ".js", ".mjs", ".ts", ".sh"), max_files=400)]
    for f in files:
        try:
            text = f.read_text(errors="ignore")[:200_000]
        except OSError:
            continue
        for rx in _PORT_PATTERNS:
            m = rx.search(text)
            if m:
                return m.group(1), int(m.group(2))
    return None, None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def g_launch(w: Path, port: int | None, app_type: str | None, inside: Path | None = None) -> dict:
    if app_type not in WEB_TYPES:
        return gate("launch", "App starts and serves (sandboxed)", False, NA, "not a server app")
    if not (w / "run.sh").is_file():
        return gate("launch", "App starts and serves (sandboxed)", True, FAILED, "run.sh missing")
    var, default = detect_port(w)
    port = port or default
    env = {}
    if var and (not port or not free_host_port(port)):
        port = free_port()  # the user's own copy may be running on the default port: check on a free one
        env = {var: str(port), "PORT": str(port)}
    if not port:
        return gate("launch", "App starts and serves (sandboxed)", True, NOT_VERIFIED,
                    "no port configured and none found in run.sh or the source")
    if not free_host_port(port):
        return gate("launch", "App starts and serves (sandboxed)", True, NOT_VERIFIED, f"port {port} is busy on the host")
    try:
        r = sandbox.Run(sandbox.Spec(workdir=w, mount_as=inside, inbound_port=port, memory_mb=1024, tasks=256, env=env),
                        ["/bin/bash", "./run.sh"], stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w"))
    except (sandbox.SandboxUnavailable, OSError) as e:
        return gate("launch", "App starts and serves (sandboxed)", True, BLOCKED, str(e))
    try:
        ok, why = http_ok(port, 45)
    finally:
        r.close()
    return gate("launch", "App starts and serves (sandboxed)", True, VERIFIED if ok else FAILED,
                f"GET / on 127.0.0.1:{port}: {why}" + (f" (port set with {var})" if env else ""))


# --------------------------------------------------------------- decision
def decide(gates: list[dict]) -> tuple[str, list[str]]:
    """(lifecycle status, reasons). SUCCEEDED only when every mandatory gate is VERIFIED or N/A."""
    from . import lifecycle as L
    failed = [g for g in gates if g["mandatory"] and g["status"] == FAILED]
    open_ = [g for g in gates if g["mandatory"] and g["status"] in (NOT_VERIFIED, BLOCKED)]
    if failed:
        return L.FAILED, [f"{g['name']}: {g['detail']}" for g in failed]
    if open_:
        return L.PARTIALLY_COMPLETED, [f"{g['name']} {g['status'].replace('_', ' ')}: {g['detail']}" for g in open_]
    return L.SUCCEEDED, []


def report_markdown(job: dict, gates: list[dict]) -> str:
    rows = "\n".join(f"| {g['name']} | {'yes' if g['mandatory'] else 'no'} | {g['status'].replace('_', ' ')} | "
                     f"{g['detail'].replace('|', '/')} |" for g in gates)
    return f"""# Independent verification report

Written by ReuseFirst after the build, not by the agent that wrote the code. Commands ran in the sandbox with no network.

- Job: `{job['id']}`
- Result: **{job['status'].replace('_', ' ').upper()}**
- Verified at: {time.strftime('%Y-%m-%d %H:%M:%S')}

| Gate | Mandatory | Status | Detail |
|---|---|---|---|
{rows}

Statuses: VERIFIED (checked and passed), NOT VERIFIED (could not be checked), FAILED, BLOCKED (check could not run), N/A.
"""


def run_all(w: Path, a: dict, job: dict, baseline: dict | None = None, inside: Path | None = None) -> tuple[list[dict], dict]:
    """All gates for a finished build. Returns (gates, test result)."""
    enhance = job.get("mode") == "enhance"
    gs = [g_required_files(w, enhance), g_syntax(w), g_secrets(w)]
    tg, tres = g_tests(w, run_tests(w, inside=inside))
    gs.append(tg)
    if tres.get("skipped"):
        gs.append(gate("skipped_tests", "No tests skipped", False, NOT_VERIFIED,
                       f"{tres['skipped']} test(s) were skipped in the verifier, so what they cover is not verified",
                       tres.get("output", "")))
    if enhance:
        gs.append(g_regression(baseline, tres))
    sb, deps = g_sbom(w, str(a.get("app_name", w.name)))
    gs += [sb, g_vulns(deps), g_provenance(w, a.get("reuse") or []), g_lint(w, inside),
           g_git(w, bool(a.get("git")), inside), g_launch(w, a.get("port"), a.get("app_type"), inside)]
    return gs, tres


def g_regression(baseline: dict | None, after: dict) -> dict:
    """Enhancements must not break tests that passed before."""
    if not baseline or baseline.get("status") in ("none", "blocked"):
        return gate("regression", "Existing tests still pass", True, NOT_VERIFIED,
                    "no baseline test run" if not baseline else baseline.get("detail", ""))
    if baseline["status"] == "passed" and after.get("status") != "passed":
        return gate("regression", "Existing tests still pass", True, FAILED,
                    f"before: {baseline['passed']} passed; after: {after.get('passed', 0)} passed, {after.get('failed', 0)} failed")
    if after.get("passed", 0) < baseline.get("passed", 0):
        return gate("regression", "Existing tests still pass", True, FAILED,
                    f"fewer passing tests than before ({after.get('passed', 0)} < {baseline['passed']})")
    return gate("regression", "Existing tests still pass", True, VERIFIED,
                f"before: {baseline['passed']} passed; after: {after.get('passed', 0)} passed")
