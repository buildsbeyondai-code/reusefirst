"""Infrastructure: execution isolation for untrusted work (builds, reuse clones, verification gates, launched apps).

Boundary (see docs/SECURITY_MODEL.md):
- bubblewrap with every namespace unshared (user, pid, ipc, uts, cgroup, mount, NETWORK), all capabilities dropped,
  a cleared environment, and a new session (no TIOCSTI).
- Filesystem: /usr and /etc read-only; HOME is an empty tmpfs; /tmp and /run are tmpfs; ONLY the project folder
  (plus explicitly listed paths) is writable. No ~/.ssh, cloud credentials, browser profiles, Docker socket or other homes.
- Network: a private namespace with loopback only, so host localhost services are unreachable. Optional egress goes through
  a host-side CONNECT proxy that allows only listed hostnames on port 443 and only public IP addresses.
- Resources: a transient systemd user scope (MemoryMax, TasksMax, CPUQuota) when available, plus rlimits (core, file
  size, open files). Process-tree cleanup kills the whole process group on timeout and cancel.
If bubblewrap is missing or the self-test fails, callers must refuse to run untrusted work (fail closed).
"""
from __future__ import annotations

import ipaddress
import json
import os
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import sbx_init
from .obs import METRICS

INIT = Path(__file__).with_name("sbx_init.py")
PKG_MOUNT = "/opt/reusefirst"
SOCK_MOUNT = "/run/reusefirst"
EGRESS_PORT = 3128
HOME = str(Path.home())

# Default egress for each phase. Builds need the Claude API and package registries; clones need GitHub only;
# verification and launched apps get no network at all.
EGRESS_CLAUDE = frozenset({"api.anthropic.com"})
EGRESS_PACKAGES = frozenset({"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"})
EGRESS_GITHUB = frozenset({"github.com", "codeload.github.com"})


class SandboxUnavailable(RuntimeError):
    pass


def bwrap_bin() -> str | None:
    return os.environ.get("REQAN_BWRAP") or shutil.which("bwrap")


@dataclass
class Spec:
    workdir: Path
    mount_as: Path | None = None  # path at which workdir appears inside (enhance: staging copy at the app's path)
    egress: frozenset = frozenset()
    inbound_port: int | None = None
    ro_paths: tuple = ()          # extra read-only binds (same path inside)
    rw_paths: tuple = ()          # extra writable binds (same path inside)
    files_ro: tuple = ()          # (host file, path inside) read-only, e.g. the Claude credential
    env: dict = field(default_factory=dict)
    memory_mb: int = 4096
    tasks: int = 1024
    cpu_percent: int = 200
    allow_private_egress: bool = False  # tests only: lets the proxy reach a local fake server


def toolchain_paths() -> list[str]:
    """Read-only, non-secret tool caches mounted into every sandbox (e.g. Playwright's browsers, so browser tests run).
    REQAN_SANDBOX_TOOLCHAIN overrides the list (colon-separated); only existing paths are mounted."""
    raw = os.environ.get("REQAN_SANDBOX_TOOLCHAIN")
    paths = raw.split(":") if raw is not None else [str(Path.home() / ".cache" / "ms-playwright")]
    return [p for p in paths if p and os.path.isdir(p)]


def _system_binds() -> list[str]:
    args = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc"]
    for d in ("/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32"):
        if os.path.islink(d):
            args += ["--symlink", os.readlink(d), d]
        elif os.path.isdir(d):
            args += ["--ro-bind", d, d]
    return args


def _outside_usr(p: str) -> bool:
    return not (p.startswith("/usr/") or p.startswith("/bin/") or p.startswith("/lib"))


def bwrap_args(spec: Spec, sock_dir: Path, exe: str | None = None) -> list[str]:
    """The bubblewrap command line (without the command). Pure apart from reading the host's /bin layout."""
    work = str(Path(spec.workdir).resolve())
    inside = str(spec.mount_as) if spec.mount_as else work
    args = [bwrap_bin() or "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
            "--clearenv", "--hostname", "reusefirst-sandbox", *_system_binds(),
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", HOME,  # nosec B108 - fresh tmpfs inside the sandbox
            "--ro-bind", str(INIT.parent), PKG_MOUNT]
    py = os.path.realpath(sys.executable)
    tools = toolchain_paths()
    ro = list(spec.ro_paths) + tools
    if _outside_usr(py):
        ro.append(sys.base_prefix)
    if exe:
        real = os.path.realpath(exe)
        if _outside_usr(real):
            ro.append(os.path.dirname(real))
    seen = set()
    for p in ro:
        p = str(p)
        if p not in seen and os.path.exists(p):
            seen.add(p)
            args += ["--ro-bind", p, p]
    args += ["--bind", work, inside]
    for p in map(str, spec.rw_paths):
        args += ["--bind", p, p]
    for src, dst in spec.files_ro:
        if os.path.exists(src):
            args += ["--ro-bind", str(src), str(dst)]
    args += ["--bind", str(sock_dir), SOCK_MOUNT, "--chdir", inside]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": HOME, "LANG": "C.UTF-8", "TMPDIR": "/tmp",  # nosec B108 - sandbox-internal tmpfs
           "TERM": "dumb", "PYTHONDONTWRITEBYTECODE": "1"}
    pw = next((t for t in tools if t.rstrip("/").endswith("ms-playwright")), None)
    if pw:
        env["PLAYWRIGHT_BROWSERS_PATH"] = pw
    if exe and _outside_usr(os.path.realpath(exe)):
        env["PATH"] = os.path.dirname(os.path.realpath(exe)) + ":" + env["PATH"]
    if spec.egress:
        proxy = f"http://127.0.0.1:{EGRESS_PORT}"
        env.update(HTTPS_PROXY=proxy, HTTP_PROXY=proxy, https_proxy=proxy, http_proxy=proxy,
                   NO_PROXY="localhost,127.0.0.1", no_proxy="localhost,127.0.0.1")
    env.update({k: str(v) for k, v in spec.env.items()})
    for k, v in env.items():
        args += ["--setenv", k, v]
    return args


def init_args(spec: Spec) -> list[str]:
    py = os.path.realpath(sys.executable)
    a = [py, "-I", f"{PKG_MOUNT}/sbx_init.py"]
    if spec.egress:
        a += ["--egress-sock", f"{SOCK_MOUNT}/egress.sock", "--egress-port", str(EGRESS_PORT)]
    if spec.inbound_port:
        a += ["--inbound-sock", f"{SOCK_MOUNT}/in.sock", "--inbound-port", str(spec.inbound_port)]
    return a + ["--"]


# ------------------------------------------------------------ resource control
_scope_ok: bool | None = None


def scope_available() -> bool:
    """True when `systemd-run --user --scope` can apply MemoryMax/TasksMax (cgroup v2 user delegation)."""
    global _scope_ok
    if _scope_ok is None:
        exe = shutil.which("systemd-run")
        if os.environ.get("REQAN_NO_SCOPE") == "1" or not exe:
            _scope_ok = False
        else:
            try:
                r = subprocess.run([exe, "--user", "--scope", "--quiet", "-p", "MemoryMax=64M", "-p", "TasksMax=16",
                                    "true"], capture_output=True, timeout=15, check=False)
                _scope_ok = r.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                _scope_ok = False
    return _scope_ok


def resource_prefix(spec: Spec) -> list[str]:
    if not scope_available():
        return []
    return [shutil.which("systemd-run") or "systemd-run", "--user", "--scope", "--quiet", "--collect",
            "-p", f"MemoryMax={spec.memory_mb}M", "-p", "MemorySwapMax=0", "-p", f"TasksMax={spec.tasks}",
            "-p", f"CPUQuota={spec.cpu_percent}%"]


def _rlimits() -> None:  # runs in the child before exec
    for lim, val in ((resource.RLIMIT_CORE, 0), (resource.RLIMIT_FSIZE, 2 * 1024 ** 3), (resource.RLIMIT_NOFILE, 4096)):
        try:
            soft, hard = resource.getrlimit(lim)
            v = val if hard == resource.RLIM_INFINITY else min(val, hard)
            resource.setrlimit(lim, (v, hard))
        except (ValueError, OSError):
            pass


# ------------------------------------------------------------- egress proxy
def _host_allowed(host: str, allow: frozenset) -> bool:
    host = host.lower().rstrip(".")
    for d in allow:
        if d.startswith("*.") and host.endswith(d[1:]):
            return True
        if host == d:
            return True
    return False


class EgressProxy:
    """CONNECT-only proxy on a Unix socket. Allows host:443 for allowlisted names that resolve to public addresses."""

    def __init__(self, path: Path, allow: frozenset, allow_private: bool = False):
        self.allow, self.allow_private = allow, allow_private
        self.log: list[dict] = []
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(path))
        self.sock.listen(64)
        self.closed = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _record(self, host: str, port: int, allowed: bool, why: str = "") -> None:
        METRICS.inc("egress_allowed" if allowed else "egress_denied")
        with self.lock:
            if len(self.log) < 500:
                self.log.append({"host": host[:200], "port": port, "allowed": allowed, **({"why": why} if why else {})})

    def _loop(self) -> None:
        while not self.closed:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(c,), daemon=True).start()

    @staticmethod
    def _deny(c: socket.socket, code: int, msg: str) -> None:
        body = f"ReuseFirst sandbox: {msg}\n".encode()
        try:
            c.sendall(f"HTTP/1.1 {code} Forbidden\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        except OSError:
            pass
        c.close()

    def _handle(self, c: socket.socket) -> None:
        c.settimeout(15)
        buf = b""
        try:
            while b"\r\n\r\n" not in buf and len(buf) < 8192:
                chunk = c.recv(4096)
                if not chunk:
                    c.close()
                    return
                buf += chunk
        except OSError:
            c.close()
            return
        line = buf.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = line.split()
        if len(parts) != 3 or parts[0] != "CONNECT" or ":" not in parts[1]:
            self._record(parts[1] if len(parts) > 1 else "?", 0, False, "only HTTPS CONNECT is allowed")
            return self._deny(c, 403, "only HTTPS (CONNECT) egress is allowed")
        host, _, port_s = parts[1].rpartition(":")
        host = host.strip("[]")
        try:
            port = int(port_s)
        except ValueError:
            port = 0
        if port != 443 or not _host_allowed(host, self.allow):
            self._record(host, port, False, "not in the allowlist")
            return self._deny(c, 403, f"egress to {host}:{port} is not allowed")
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as e:
            self._record(host, port, False, f"DNS: {e}")
            return self._deny(c, 502, f"cannot resolve {host}")
        addrs = [i[4] for i in infos if self.allow_private or ipaddress.ip_address(i[4][0]).is_global]
        if not addrs:
            self._record(host, port, False, "resolves to a non-public address")
            return self._deny(c, 403, f"{host} resolves to a non-public address")
        try:
            up = socket.create_connection(addrs[0][:2], timeout=15)
            up.settimeout(None)
        except OSError as e:
            self._record(host, port, False, f"connect: {e}")
            return self._deny(c, 502, f"cannot connect to {host}")
        self._record(host, port, True)
        rest = buf.split(b"\r\n\r\n", 1)[1]
        try:
            c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            if rest:
                up.sendall(rest)
        except OSError:
            c.close()
            up.close()
            return
        c.settimeout(None)
        sbx_init.pipe(c, up)

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class InboundForwarder:
    """Host 127.0.0.1:port -> Unix socket -> (inside the sandbox) 127.0.0.1:port. Lets the browser reach a launched app
    while the app itself has no network access to the host."""

    def __init__(self, port: int, sock_path: Path):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(64)
        threading.Thread(target=sbx_init.serve, args=(self.sock, sbx_init.unix_connector(str(sock_path))),
                         daemon=True).start()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ----------------------------------------------------------------- running
class Run:
    """One sandboxed process with its proxy/forwarder. Always call close()."""

    def __init__(self, spec: Spec, argv: list[str], stdout=None, stderr=None, exe: str | None = None):
        if not bwrap_bin():
            raise SandboxUnavailable("bubblewrap (bwrap) is not installed")
        self.spec = spec
        self.dir = Path(tempfile.mkdtemp(prefix="reusefirst-sbx-"))
        os.chmod(self.dir, 0o700)
        self.proxy = EgressProxy(self.dir / "egress.sock", spec.egress, spec.allow_private_egress) if spec.egress else None
        self.forwarder = None
        if spec.inbound_port:
            self.forwarder = InboundForwarder(spec.inbound_port, self.dir / "in.sock")
        cmd = resource_prefix(spec) + bwrap_args(spec, self.dir, exe or argv[0]) + ["--"] + init_args(spec) + argv
        self.cmd = cmd
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                         start_new_session=True, preexec_fn=_rlimits, text=True)
        except OSError:
            self.close()
            raise
        self.started = time.time()
        METRICS.inc("sandbox_runs")

    def egress_log(self) -> list[dict]:
        return list(self.proxy.log) if self.proxy else []

    def kill(self) -> None:
        kill_group(self.proc)

    def close(self) -> None:
        if getattr(self, "proc", None) and self.proc.poll() is None:
            kill_group(self.proc)
        for x in (self.proxy, self.forwarder):
            if x:
                x.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def kill_group(p: subprocess.Popen, grace_s: float = 10) -> None:
    """SIGTERM the whole process group, then SIGKILL after grace_s. Never leaves orphans of this group."""
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        p.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run(spec: Spec, argv: list[str], timeout_s: float, exe: str | None = None, max_output: int = 200_000) -> dict:
    """Run to completion. Returns {code, output, timed_out, egress, duration_s}."""
    r = Run(spec, argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, exe=exe)
    timed_out = False
    try:
        out, _ = r.proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        r.kill()
        out, _ = r.proc.communicate()
    finally:
        egress = r.egress_log()
        r.close()
    return {"code": r.proc.returncode, "output": (out or "")[-max_output:], "timed_out": timed_out,
            "egress": egress, "duration_s": round(time.time() - r.started, 2)}


# ---------------------------------------------------------------- self-test
PROBE = r"""
import json, os, socket, sys
H = os.environ["HOME"]; res = {}
secret = [os.path.join(H, p) for p in (".ssh", ".aws", ".gnupg", ".config/gh", ".claude/.credentials.json",
          ".mozilla", ".config/google-chrome", ".docker", ".kube", ".netrc", ".git-credentials")]
res["secrets_hidden"] = [p for p in secret if os.path.exists(p)] == []
allowed = set(json.loads(sys.argv[3]))  # top-level entries created only by read-only toolchain mounts
res["home_empty"] = os.path.isdir(H) and set(os.listdir(H)) <= allowed
try:
    open(os.path.join(H, ".probe"), "w").write("x"); os.remove(os.path.join(H, ".probe")); res["home_writable_tmpfs"] = True
except OSError:
    res["home_writable_tmpfs"] = False
res["host_state_hidden"] = not os.path.exists(sys.argv[1])
try:
    open("/usr/reusefirst-probe", "w"); res["system_readonly"] = False
except OSError:
    res["system_readonly"] = True
open("probe-written.txt", "w").write("ok"); res["workdir_writable"] = True
c = socket.socket(); c.settimeout(2); res["host_loopback_blocked"] = c.connect_ex(("127.0.0.1", int(sys.argv[2]))) != 0
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3); res["direct_egress_blocked"] = False
except OSError:
    res["direct_egress_blocked"] = True
try:
    s = socket.create_connection(("127.0.0.1", 3128), timeout=5)
    s.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n")
    res["proxy_denies_unlisted"] = b" 403 " in s.recv(200)
except OSError as e:
    res["proxy_denies_unlisted"] = False
res["env_clean"] = not any(k in os.environ for k in ("GITHUB_TOKEN", "GH_TOKEN", "ANTHROPIC_API_KEY", "SSH_AUTH_SOCK",
                                                     "AWS_SECRET_ACCESS_KEY", "DBUS_SESSION_BUS_ADDRESS"))
res["docker_socket_absent"] = not (os.path.exists("/var/run/docker.sock") or os.path.exists("/run/docker.sock"))
cap = [l for l in open("/proc/self/status") if l.startswith("CapEff")][0].split()[1]
res["no_capabilities"] = int(cap, 16) == 0
res["pid_namespace"] = len([p for p in os.listdir("/proc") if p.isdigit()]) < 10
print("PROBE" + json.dumps(res))
"""

_self_test: dict | None = None
_self_test_lock = threading.Lock()


def self_test(force: bool = False, state_dir: Path | None = None) -> dict:
    """Harmless adversarial checks of the boundary. Cached; builds are blocked unless ok is True."""
    global _self_test
    with _self_test_lock:
        if _self_test is not None and not force:
            return _self_test
        res = {"ok": False, "bwrap": bwrap_bin(), "resource_control": "systemd-scope" if scope_available() else "rlimit-only",
               "checks": {}, "error": None, "at": time.time()}
        if not res["bwrap"]:
            res["error"] = "bubblewrap (bwrap) is not installed: install it (sudo apt install bubblewrap)"
            _self_test = res
            return res
        work = Path(tempfile.mkdtemp(prefix="reusefirst-probe-"))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        sentinel_dir = Path(tempfile.mkdtemp(prefix="reusefirst-sentinel-", dir=state_dir))
        hidden = str(sentinel_dir / "host-only.txt")
        Path(hidden).write_text("must not be visible inside the sandbox")
        try:
            r = run(Spec(workdir=work, egress=frozenset({"allowed.invalid"}), memory_mb=512, tasks=64),
                    [os.path.realpath(sys.executable), "-I", "-c", PROBE, hidden, str(listener.getsockname()[1]),
                     json.dumps(sorted({Path(t).relative_to(HOME).parts[0] for t in toolchain_paths()
                                        if Path(t).is_relative_to(HOME)}))],
                    timeout_s=60)
            line = next((ln for ln in r["output"].splitlines() if ln.startswith("PROBE")), None)
            if not line:
                res["error"] = f"sandbox did not start (exit {r['code']}): {r['output'][-400:]}"
            else:
                res["checks"] = json.loads(line[5:])
                res["checks"]["workdir_writable"] = res["checks"].get("workdir_writable") and \
                    (work / "probe-written.txt").read_text() == "ok"
                res["ok"] = all(res["checks"].values())
                if not res["ok"]:
                    res["error"] = "isolation check failed: " + ", ".join(k for k, v in res["checks"].items() if not v)
        except (OSError, ValueError, SandboxUnavailable) as e:
            res["error"] = f"sandbox self-test error: {e}"
        finally:
            listener.close()
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(sentinel_dir, ignore_errors=True)
        METRICS.set("sandbox_ok", res["ok"])
        _self_test = res
        return res


def require() -> dict:
    """Raise SandboxUnavailable unless the boundary is verified. Never downgrades to host execution."""
    st = self_test()
    if not st["ok"]:
        raise SandboxUnavailable(st["error"] or "sandbox self-test failed")
    return st
