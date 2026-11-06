"""Application layer for the Build tab.

1. required_inputs(): the full list of inputs needed to build the app. Standard fields always;
   Claude (headless, no tools) proposes defaults and app-specific questions.
2. BuildManager: runs ONE non-interactive Claude Code build at a time in a background worker
   (`claude -p --permission-mode dontAsk` with a fixed tool allowlist: anything else is refused, never asked),
   streams progress, enforces timeout and budget, persists job state, and supports cancel.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import tarfile
import threading
import time
import uuid
from pathlib import Path

STATE_DIR = Path(os.environ.get("REQAN_STATE_DIR",
                                Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "req-analyzer"))
APPS_DIR = Path(os.environ.get("REQAN_APPS_DIR", Path.home() / "apps"))
PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # plugins/req-analyzer
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "req-analyzer" / "config.json"


def standard_path(env: str, key: str, bundled: str) -> Path:
    """Where a standard is read from: the env var, else this PC's config file (for example the user's live
    OneDrive copy), else the copy bundled with the plugin."""
    if os.environ.get(env):
        return Path(os.environ[env])
    try:
        configured = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError, AttributeError):
        configured = None
    if configured:
        return Path(os.path.expanduser(str(configured)))
    return PLUGIN_ROOT / "standards" / bundled


# UAISES: the engineering standard every build follows. UEUIS: the UI standard (ISO 9241 / WCAG 2.2 based).
UAISES = standard_path("REQAN_UAISES", "uaises", "UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md")
UI_STANDARD = standard_path("REQAN_UI_STANDARD", "ui_standard", "UNIVERSAL_ENTERPRISE_UI_STANDARD.md")
UI_LEVELS = ["Enterprise (WCAG 2.2 AA, usability-checked)", "Core (WCAG 2.2 A)",
             "Regulated (Enterprise + domain law)"]
NO_UI_TYPES = ("REST API service", "CLI tool")
INPUTS_TIMEOUT_S = 240
MAX_EVENTS_KEPT = 400
RESERVED_PORTS = {5056, 5057}
# Ports Chromium/Edge/Firefox refuse to open (ERR_UNSAFE_PORT). A real build defaulted to 5060 (SIP) and the
# app was unreachable from every browser. Subset of Chromium's kRestrictedPorts at or above 1024.
BROWSER_UNSAFE_PORTS = {1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668,
                        6669, 6679, 6697, 10080}
BUILD_ROOT = Path(os.environ.get("REQAN_BUILD_ROOT", Path.home()))  # builds may only be created under here
PROJECT_ROOT = Path(__file__).resolve().parents[4]  # ~/req-analyzer: never build inside this tool

# Pre-approved tools for builds. With --permission-mode dontAsk everything else is denied without a prompt.
# No rm, no sudo, no package installs outside the project (pip/npm run inside the project's own venv/node_modules).
BUILD_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite", "WebSearch", "WebFetch",
    "Bash(python3:*)", "Bash(python:*)", "Bash(.venv/bin/*:*)", "Bash(pip:*)", "Bash(pip3:*)", "Bash(uv:*)",
    "Bash(pytest:*)", "Bash(npm:*)", "Bash(npx:*)", "Bash(node:*)", "Bash(make:*)",
    "Bash(git init:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git status:*)", "Bash(git diff:*)",
    "Bash(git log:*)", "Bash(git clone:*)", "Bash(git checkout:*)",
    "Bash(mkdir:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(cp:*)",
    "Bash(mv:*)", "Bash(touch:*)", "Bash(chmod:*)", "Bash(sed:*)", "Bash(grep:*)", "Bash(find:*)",
    "Bash(curl -s http://127.0.0.1:*)", "Bash(curl -s http://localhost:*)", "Bash(timeout:*)", "Bash(sleep:*)",
    "Bash(./run.sh:*)", "Bash(bash:*)", "Bash(sh:*)", "Bash(kill:*)", "Bash(ss:*)",
]
# Note: python3/bash can run arbitrary code as the user, so the real boundaries are: Claude Code confines file
# edits to the build folder, no rm/sudo/git push/arbitrary curl commands, the spending cap and the time limit.


def build_tools(out: Path) -> list[str]:
    """Static allowlist plus absolute-path forms (a real build was refused /abs/.venv/bin/pip and /abs/run.sh)."""
    return BUILD_TOOLS + ["Bash(tools/*:*)", "Bash(./tools/*:*)",
                          f"Bash({out}/.venv/bin/*:*)", f"Bash({out}/run.sh:*)", f"Bash({out}/tools/*:*)"]


# ------------------------------------------------------------- enhance mode
ENHANCE = "Enhance an existing app"
BACKUP_SKIP = {".venv", "venv", "node_modules", "upstream", "__pycache__", ".git", "browser-profile", ".pytest_cache"}


def existing_apps() -> list[dict]:
    """Apps under APPS_DIR that can be enhanced (a folder with CLAUDE.md, README.md or run.sh)."""
    out = []
    if APPS_DIR.is_dir():
        for d in sorted(APPS_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and any((d / f).exists() for f in ("CLAUDE.md", "README.md", "run.sh")):
                out.append({"name": d.name, "path": str(d.resolve())})
    return out


def enhance_target(path: str) -> Path:
    """Resolve and check a folder chosen for enhancement: it must be one of existing_apps()."""
    p = Path(os.path.expanduser(str(path or "").strip())).resolve()
    if str(p) not in {a["path"] for a in existing_apps()}:
        raise BuildError(f"{p} is not an existing app in {APPS_DIR}")
    return p


def app_context(target: Path, limit: int = 3000) -> str:
    """The existing app's own description (CLAUDE.md and the start of README.md) for the inputs prompt."""
    parts = []
    for name in ("CLAUDE.md", "README.md"):
        f = target / name
        if f.is_file():
            parts.append(f"--- {name} ---\n" + f.read_text(encoding="utf-8", errors="replace")[:limit])
    return "\n".join(parts)


def backup(target: Path, dest_dir: Path) -> Path:
    """Snapshot the app before an enhancement build changes it (no venvs, caches, clones or browser profiles)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{target.name}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"

    def keep(ti: tarfile.TarInfo):
        return None if BACKUP_SKIP & set(Path(ti.name).parts) else ti
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(target, arcname=target.name, filter=keep)
    return dest


def git_env() -> dict:
    """Builds commit without a configured git identity (WSL had none and the real build could not commit)."""
    env = dict(os.environ)
    name = os.environ.get("REQAN_GIT_NAME") or _git_config("user.name") or "Requirement Reuse Analyser"
    email = os.environ.get("REQAN_GIT_EMAIL") or _git_config("user.email") or "req-analyzer@localhost"
    env.update(GIT_AUTHOR_NAME=name, GIT_COMMITTER_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_EMAIL=email)
    return env


def _git_config(key: str) -> str:
    try:
        r = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""

SELECT_OPTIONS = {
    "app_type": ["Web app (browser UI + local server)", "REST API service", "CLI tool", "Desktop app",
                 "Claude Code plugin", "Mobile-friendly PWA"],
    "stack": ["Let Claude choose", "Python (stdlib / Flask)", "Python + FastAPI", "Node.js + TypeScript",
              "Static HTML/JS only"],
    "data_storage": ["None", "Local JSON files", "SQLite", "PostgreSQL"],
    "auth": ["None (local, single user)", "Simple password", "OAuth / SSO"],
    "ui_theme": ["Light + dark (follows system)", "Dark", "Light", "No UI"],
    "tests": ["Unit + integration + end-to-end (UAISES)", "Unit + integration"],
    "model": ["default", "opus", "sonnet"],
    "ui_level": UI_LEVELS,
    "risk": ["Low (personal tool)", "Medium (shared or handles personal data)", "High (money, security or production)"],
}


class BuildError(ValueError):
    pass


# UAISES §2 minimum: who, where, what (must-haves) and how it is verified (acceptance criteria).
REQUIRED_FIELDS = ("app_name", "output_dir", "users", "platforms", "journeys", "must_have", "acceptance")


def claude_bin() -> str | None:
    env = os.environ.get("REQAN_CLAUDE_BIN")
    if env:
        return env
    return shutil.which("claude") or next((str(p) for p in [Path.home() / ".local/bin/claude"] if p.exists()), None)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40].strip("-")
    return s or "new-app"


def free_port(start: int = 5070) -> int:
    for port in range(start, start + 200):
        if port in RESERVED_PORTS or port in BROWSER_UNSAFE_PORTS:
            continue
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


# ------------------------------------------------------------------ inputs
REUSE_PRESELECT_MIN = 30  # % closeness; below this a match is too weak to pre-tick


def reuse_candidates(analysis: dict | None) -> tuple[list[str], list[str]]:
    """Options look like 'GitHub · owner/repo · 58% · MIT · https://github.com/owner/repo'.
    The closest GitHub repo and the closest plugin are always pre-ticked; up to 3 / 2 more if >= 30%."""
    opts, picked = [], []
    for kind, rows, n in (("GitHub", (analysis or {}).get("github") or [], 3),
                          ("Claude plugin", (analysis or {}).get("claude_plugins") or [], 2)):
        for i, r in enumerate(rows[:6]):
            if not str(r.get("url", "")).startswith("https://github.com/"):
                continue
            lic = r.get("license", "see repo")
            opt = f"{kind} · {r['name']} · {r['closeness']}% · {lic} · {r['url']}"
            opts.append(opt)
            if i == 0 or (len([p for p in picked if p.startswith(kind)]) < n and r["closeness"] >= REUSE_PRESELECT_MIN):
                picked.append(opt)
    return opts, picked


def base_fields(requirement: str, analysis: dict | None) -> list[dict]:
    """Standard inputs, grouped by the UAISES section they satisfy (§2 requirements, §3 architecture,
    §7-§10 non-functional, §14 delivery, §17 Phase B risk)."""
    name = " ".join(re.findall(r"[A-Za-z0-9]+", requirement)[:4]).title() or "New App"
    slug = slugify(name)
    reuse_opts, reuse_default = reuse_candidates(analysis)

    def f(id, label, type, default="", group="Basics", help="", options=None, required=False, uaises=""):
        d = {"id": id, "label": label, "type": type, "default": default, "group": group, "help": help,
             "required": required, "source": "standard", "uaises": uaises}
        if options:
            d["options"] = options
        return d

    R, N, T, D = ("Requirements (UAISES §2)", "Non-functional targets (UAISES §2, §7-§10)",
                  "Architecture (UAISES §3)", "Delivery (UAISES §14, §18)")
    return [
        f("app_name", "App name", "text", name, required=True, uaises="§0"),
        f("output_dir", "Create in folder", "text", str(APPS_DIR / slug), required=True,
          help="Must be inside your home folder and empty or new."),
        f("app_type", "Kind of app", "select", SELECT_OPTIONS["app_type"][0], options=SELECT_OPTIONS["app_type"]),
        f("reuse", "Reuse these existing projects (closest first)", "checklist", reuse_default, options=reuse_opts,
          uaises="§12", help="Pre-ticked: the closest GitHub repos and Claude plugins from the analysis. The build clones "
          "them, checks license and fit, reuses the best as its base and borrows the rest. Untick to exclude."),
        f("risk", "Risk level", "select", SELECT_OPTIONS["risk"][0], options=SELECT_OPTIONS["risk"], uaises="§17 B",
          help="Scales how much testing and review the standard requires."),
        f("users", "Users and roles", "textarea", "Me, a single user on this PC", R, required=True, uaises="§2"),
        f("platforms", "Target platforms", "text", "Windows 11 browser, served from WSL2 (Ubuntu)", R, required=True, uaises="§2"),
        f("journeys", "Key user journeys (one per line)", "textarea", "", R, required=True, uaises="§2"),
        f("must_have", "MUST-have features (one per line)", "textarea", "", R, required=True, uaises="§2"),
        f("should_have", "SHOULD-have features (one per line)", "textarea", "", R, uaises="§2"),
        f("optional", "OPTIONAL features (one per line)", "textarea", "", R, uaises="§2"),
        f("out_of_scope", "Out of scope (no speculative extras)", "textarea", "", R, uaises="§2"),
        f("acceptance", "Acceptance criteria: Given / When / Then (one per line)", "textarea", "", R, required=True, uaises="§2"),
        f("integrations", "Integrations / external services (one per line)", "textarea", "None", R, uaises="§2, §7",
          help="Never paste secrets. Keys are read from environment variables named in the README."),
        f("nfr_performance", "Latency / throughput / startup", "text", "Pages respond in < 300 ms; starts in < 3 s", N, uaises="§2, §8"),
        f("nfr_resources", "Memory / CPU limits", "text", "< 150 MB RAM idle; no busy polling (PC has 7.8 GB RAM)", N, uaises="§8"),
        f("nfr_reliability", "Reliability and recovery", "text", "Survives restart without data loss; atomic writes; clear error states", N, uaises="§9"),
        f("nfr_security", "Security", "text", "Localhost only; input validation; no secrets in code or logs", N, uaises="§7"),
        f("nfr_accessibility", "Accessibility and UI states", "text",
          "WCAG 2.2 AA (UEUIS §7): full keyboard use, screen-reader names, 4.5:1 text contrast in every theme, "
          "reflow at 320 px, every UEUIS §6 state (loading, empty, error, offline, success)", N, uaises="§10"),
        f("offline", "Must work offline", "boolean", False, N, uaises="§2"),
        f("installation", "Installation / packaging", "text", "./run.sh from the project folder", N, uaises="§2, §14"),
        f("stack", "Technology stack", "select", SELECT_OPTIONS["stack"][0], T, options=SELECT_OPTIONS["stack"], uaises="§3, §12"),
        f("data_storage", "Data storage", "select", SELECT_OPTIONS["data_storage"][1], T, options=SELECT_OPTIONS["data_storage"], uaises="§13"),
        f("auth", "Sign-in", "select", SELECT_OPTIONS["auth"][0], T, options=SELECT_OPTIONS["auth"], uaises="§7"),
        f("port", "Local port", "number", free_port(), T,
          help="5056 (SysPerf) and 5057 (this tool) are reserved; browser-blocked ports like 5060/5061 are refused."),
        f("ui_theme", "Look and feel", "select", SELECT_OPTIONS["ui_theme"][0], T, options=SELECT_OPTIONS["ui_theme"], uaises="§10"),
        f("ui_level", "UI standard conformance level (UEUIS)", "select", UI_LEVELS[0], T, options=UI_LEVELS,
          uaises="§10", help="Every UI is built to the Universal Enterprise UI Standard (ISO 9241-110/112/143/161/171/210, "
          "WCAG 2.2). Enterprise is the default for anything other people use."),
        f("tests", "Testing depth", "select", SELECT_OPTIONS["tests"][0], D, options=SELECT_OPTIONS["tests"], uaises="§6"),
        f("git", "Create a local git repo and commit", "boolean", True, D, uaises="§14"),
        f("model", "Claude model", "select", "default", "Run limits", options=SELECT_OPTIONS["model"]),
        f("budget_usd", "Spending cap (USD)", "number", 5, "Run limits", help="The build stops when this is reached."),
        f("max_minutes", "Time limit (minutes)", "number", 45, "Run limits"),
    ]


SUGGESTABLE = ("app_name", "app_type", "risk", "users", "platforms", "journeys", "must_have", "should_have", "optional",
               "out_of_scope", "acceptance", "integrations", "nfr_performance", "nfr_resources", "nfr_reliability",
               "nfr_security", "nfr_accessibility", "installation", "data_storage", "auth")

INPUTS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggested": {"type": "object", "properties": {k: {"type": "string"} for k in SUGGESTABLE}},
        "questions": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "label": {"type": "string"},
            "type": {"type": "string", "enum": ["text", "textarea", "select", "boolean", "number"]},
            "options": {"type": "array", "items": {"type": "string"}},
            "default": {"type": "string"}, "help": {"type": "string"}},
            "required": ["id", "label", "type", "default"]}},
    },
    "required": ["suggested", "questions"],
}


def uaises_text() -> str:
    try:
        return UAISES.read_text(encoding="utf-8")
    except OSError as e:
        raise BuildError(f"UAISES standard not readable at {UAISES}: {e}") from None


def ui_standard_text() -> str:
    try:
        return UI_STANDARD.read_text(encoding="utf-8")
    except OSError as e:
        raise BuildError(f"UI standard (UEUIS) not readable at {UI_STANDARD}: {e}") from None


def uaises_section(text: str, number: int) -> str:
    m = re.search(rf"^## {number}\. .*?(?=^## \d+\. |\Z)", text, re.S | re.M)
    return m.group(0).strip() if m else ""


def _inputs_prompt(requirement: str, analysis: dict | None, standard: str, context: str = "") -> str:
    tops = [f"- {r['name']} ({r['closeness']}%): {r['description'][:160]}"
            for r in ((analysis or {}).get("github") or [])[:3] + ((analysis or {}).get("claude_plugins") or [])[:2]]
    return f"""You prepare the requirements input form for building a software application. Every requirement must
follow the user's engineering standard (UAISES). Its requirements section is:

<uaises_section_2>
{uaises_section(standard, 2)}
</uaises_section_2>

Every user interface must also follow the user's UI standard (UEUIS: ISO 9241-110 interaction principles,
WCAG 2.2 AA accessibility, every UI state, light/dark theme parity, 320 px reflow). Write nfr_accessibility
as measurable UEUIS targets, and make journeys and acceptance criteria include the empty, error and loading states.

The user's requirement:
<requirement>
{requirement}
</requirement>
{f"""
This is an ENHANCEMENT of an existing app (not a new app). Describe only the change: journeys, must-haves and
acceptance criteria for the new behaviour, plus "existing features and tests keep working". The app today:
<existing_app>
{context}
</existing_app>
""" if context else ""}
Closest existing projects (context only):
{chr(10).join(tops) or "- none"}

Return JSON only:
- "suggested": default values for the standard fields, written to satisfy UAISES §2: users (roles), platforms,
  journeys, must_have / should_have / optional (strict MoSCoW split, no speculative features), out_of_scope,
  acceptance (one testable "Given ..., when ..., then ..." line per must-have), integrations, and measurable
  non-functional targets nfr_performance, nfr_resources, nfr_reliability, nfr_security, nfr_accessibility, installation.
  Lists are newline-separated. app_type must be one of {SELECT_OPTIONS['app_type']}; risk one of {SELECT_OPTIONS['risk']};
  data_storage one of {SELECT_OPTIONS['data_storage']}; auth one of {SELECT_OPTIONS['auth']}.
- "questions": 4-12 additional inputs SPECIFIC to this app that a builder needs and the standard fields do not
  cover (do NOT repeat: name, folder, port, theme, stack, storage, auth, tests, git, model, budget).
  Give each a sensible default so the user can submit without editing. ids are snake_case.
  Never ask for passwords, API keys or other secrets."""


STANDARD_TOPICS = {"port", "theme", "stack", "storage", "database", "auth", "login", "git", "budget", "model",
                   "tests", "testing", "name", "folder", "directory"}


def _clean_question(q: dict, taken: set[str]) -> dict | None:
    qid = re.sub(r"[^a-z0-9_]", "_", str(q.get("id", "")).lower())[:40].strip("_")
    if not qid or qid in taken or q.get("type") not in ("text", "textarea", "select", "boolean", "number"):
        return None
    if re.search(r"password|secret|api_?key|token", qid + str(q.get("label", "")).lower()):
        return None
    if STANDARD_TOPICS & set(qid.split("_")):  # already covered by a standard field
        return None
    taken.add(qid)
    out = {"id": qid, "label": str(q.get("label", qid))[:120], "type": q["type"], "group": "App-specific",
           "help": str(q.get("help", ""))[:200], "required": False, "source": "claude"}
    default = str(q.get("default", ""))[:2000]
    if q["type"] == "select":
        opts = [str(o)[:120] for o in (q.get("options") or [])][:12]
        if not opts:
            out["type"] = "text"
        else:
            if default not in opts:
                default = opts[0]
            out["options"] = opts
    if q["type"] == "boolean":
        out["default"] = default.strip().lower() in ("true", "yes", "1")
    elif q["type"] == "number":
        try:
            out["default"] = float(default) if "." in default else int(default)
        except ValueError:
            out["default"] = 0
    else:
        out["default"] = default
    return out


def run_claude_json(prompt: str, schema: dict, timeout: int = INPUTS_TIMEOUT_S) -> dict:
    exe = claude_bin()
    if not exe:
        raise BuildError("Claude Code CLI not found (install it or set REQAN_CLAUDE_BIN)")
    cmd = [exe, "-p", prompt, "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--json-schema", json.dumps(schema)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise BuildError(f"Claude did not answer within {timeout} s") from None
    try:
        out = json.loads(r.stdout)
    except ValueError:
        raise BuildError(f"Claude returned no JSON (exit {r.returncode}): {(r.stderr or r.stdout)[-300:]}") from None
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        raise BuildError(f"Claude error: {str(out.get('result') or out.get('subtype'))[:300]}")
    return out["structured_output"]


def enhance_fields(fields: list[dict], target: Path) -> list[dict]:
    """Turn the new-app inputs into enhancement inputs for an existing app."""
    by_id = {f["id"]: f for f in fields}
    by_id["app_name"].update(default=target.name, label="App")
    by_id["output_dir"].update(default=str(target), label="Enhance the app in folder",
                               help="An existing app in your apps folder. A backup is taken before the build changes it.")
    by_id["git"].update(default=False, label="Commit the change to git")
    mode = {"id": "build_mode", "label": "Build mode", "type": "select", "default": ENHANCE, "options": [ENHANCE],
            "group": "Basics", "help": "Adds the requirement to the existing app; its tests must keep passing.",
            "required": True, "source": "standard", "uaises": "§17"}
    return [mode] + [f for f in fields if f["id"] != "port"]


def required_inputs(requirement: str, analysis: dict | None = None, target: str | None = None) -> dict:
    fields = base_fields(requirement, analysis)
    tpath = enhance_target(target) if target else None
    if tpath:
        fields = enhance_fields(fields, tpath)
    by_id = {f["id"]: f for f in fields}
    ai_status, ai_error = "ok", None
    try:
        out = run_claude_json(_inputs_prompt(requirement, analysis, uaises_text(),
                                             app_context(tpath) if tpath else ""), INPUTS_SCHEMA)
        for k, v in (out.get("suggested") or {}).items():
            f = by_id.get(k)
            if k not in SUGGESTABLE or not f or not isinstance(v, str) or not v.strip():
                continue
            if f["type"] == "select" and v not in f["options"]:
                continue
            f["default"] = v.strip()[:4000]
            f["source"] = "claude"
        if tpath:  # the app and its folder are fixed when enhancing
            by_id["app_name"]["default"], by_id["output_dir"]["default"] = tpath.name, str(tpath)
        elif "app_name" in (out.get("suggested") or {}):
            by_id["output_dir"]["default"] = str(APPS_DIR / slugify(by_id["app_name"]["default"]))
        taken = set(by_id)
        for q in (out.get("questions") or [])[:12]:
            c = _clean_question(q, taken) if isinstance(q, dict) else None
            if c:
                fields.insert(len(fields) - 3, c)  # before "Run limits"
    except BuildError as e:
        ai_status, ai_error = "failed", str(e)
    return {"requirement": requirement, "fields": fields, "ai_status": ai_status, "ai_error": ai_error,
            "mode": "enhance" if tpath else "new", "standard": str(UAISES), "standard_found": UAISES.exists(),
            "ui_standard": str(UI_STANDARD), "ui_standard_found": UI_STANDARD.exists()}


# ------------------------------------------------------------------- build
def validate_spec(requirement: str, answers: dict) -> dict:
    if not isinstance(requirement, str) or not requirement.strip() or len(requirement) > 5000:
        raise BuildError("requirement must be 1-5000 characters")
    if not isinstance(answers, dict) or len(answers) > 60:
        raise BuildError("answers must be an object with at most 60 fields")
    clean = {}
    for k, v in answers.items():
        if not re.fullmatch(r"[a-z0-9_]{1,40}", str(k)):
            raise BuildError(f"bad field id: {k!r}")
        if isinstance(v, list):
            if len(v) > 20 or not all(isinstance(x, str) and len(x) <= 400 for x in v):
                raise BuildError(f"bad list for {k}")
        elif not isinstance(v, (str, int, float, bool)) or (isinstance(v, str) and len(v) > 4000):
            raise BuildError(f"bad value for {k}")
        clean[k] = v
    for req in REQUIRED_FIELDS:
        if not str(clean.get(req, "")).strip():
            raise BuildError(f"{req} is required")
    home = Path.home().resolve()
    root = BUILD_ROOT.resolve()
    out = Path(os.path.expanduser(str(clean["output_dir"]).strip())).resolve()
    if root not in out.parents:
        raise BuildError(f"output folder must be inside {root}")
    for forbidden in (home / ".claude", home / ".config", home / ".ssh", home / ".local", PROJECT_ROOT):
        if out == forbidden or forbidden in out.parents:
            raise BuildError(f"output folder may not be inside {forbidden}")
    if clean.get("build_mode", "") not in ("", ENHANCE):
        raise BuildError("unknown build mode")
    if clean.get("build_mode") == ENHANCE:
        out = enhance_target(str(out))  # must be an existing app, never an arbitrary folder
    elif out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise BuildError(f"output folder {out} already exists and is not empty")
    clean["output_dir"] = str(out)
    try:
        clean["budget_usd"] = max(0.5, min(float(clean.get("budget_usd", 5)), 50.0))
        clean["max_minutes"] = max(2, min(int(float(clean.get("max_minutes", 45))), 180))
    except ValueError:
        raise BuildError("budget_usd and max_minutes must be numbers") from None
    if "port" in clean:
        try:
            port = int(clean["port"])
        except (TypeError, ValueError):
            raise BuildError("port must be a number") from None
        if not 1024 <= port <= 65535 or port in RESERVED_PORTS or port in BROWSER_UNSAFE_PORTS:
            raise BuildError(f"port {port} is reserved or blocked by browsers; pick another (e.g. {free_port()})")
        clean["port"] = port
    reuse = clean.get("reuse") or []
    if isinstance(reuse, str):
        reuse = [reuse] if reuse else []
    for item in reuse:
        if not re.search(r"https://github\.com/[\w.-]+/[\w.-]+", item):
            raise BuildError(f"reuse entries must contain a https://github.com/ URL: {item[:80]!r}")
    clean["reuse"] = reuse
    if clean.get("ui_level", UI_LEVELS[0]) not in UI_LEVELS:
        raise BuildError("unknown UI conformance level")
    if clean.get("model", "default") not in SELECT_OPTIONS["model"]:
        raise BuildError("unknown model")
    return clean


def spec_markdown(requirement: str, a: dict, labels: dict[str, str]) -> str:
    title = "# Enhancement specification" if a.get("build_mode") == ENHANCE else "# Build specification"
    lines = [title, "", f"Generated by Requirement Reuse Analyser on {time.strftime('%Y-%m-%d %H:%M')}.", "",
             "## Original requirement", "", requirement.strip(), "", "## Inputs", ""]
    skip = {"output_dir", "budget_usd", "max_minutes", "model"}
    for k, v in a.items():
        if k in skip:
            continue
        label = labels.get(k, k)
        if isinstance(v, list):
            v = "\n".join(f"- {x}" for x in v) or "(none selected)"
        v = "yes" if v is True else "no" if v is False else str(v).strip() or "(not specified: choose a sensible default)"
        lines += [f"### {label}", "", v, ""]
    return "\n".join(lines)


def clone_url(url: str) -> str:
    m = re.match(r"(https://github\.com/[\w.-]+/[\w.-]+?)(?:\.git)?(?:/tree/[^/]+/(.*))?$", url.strip())
    return m.group(1) if m else url


def reuse_instructions(items: list[str]) -> str:
    if not items:
        return "No existing project was selected for reuse: build it new in this folder."
    lines = []
    for it in items:
        url = re.search(r"https://github\.com/\S+", it).group(0)
        sub = re.search(r"/tree/[^/]+/(.+)$", url)
        lines.append(f"- {it}\n  clone: git clone --depth 1 {clone_url(url)} upstream/{clone_url(url).rsplit('/', 1)[-1]}"
                     + (f" (plugin lives in subfolder {sub.group(1)})" if sub else ""))
    return f"""REUSE BEFORE BUILDING (UAISES §12). The user chose to reuse these closest existing projects:
{chr(10).join(lines)}
Step 1: clone each into upstream/ (shallow), read its README, LICENSE and code, and map it against the must-haves.
Step 2: pick the candidate that covers the most must-haves with a compatible license as the BASE (copy or adapt
its code into this project); borrow specific modules, skills, commands or patterns from the others. If the app is a
Claude Code plugin, reuse the selected plugins' skills/commands/hooks structure directly. Do not reuse code whose
license forbids it (no license = do not copy code, only learn from it).
Step 3: build only what is still missing.
Step 4: write docs/REUSE.md: for every candidate, what was reused (files/functions), license and attribution,
and what was built new; keep upstream/ out of git (.gitignore) and credit sources in README."""


def ui_instructions(a: dict) -> str:
    level = a.get("ui_level", UI_LEVELS[0])
    no_ui = a.get("app_type") in NO_UI_TYPES or a.get("ui_theme") == "No UI"
    head = f"""UI STANDARD (MANDATORY): docs/{UI_STANDARD.name} (UEUIS), conformance level: {level}."""
    if no_ui:
        return head + """
This app has no graphical UI, so apply UEUIS only to what users see: §3 plain-language messages and errors,
§11 feedback and recovery, §13 locale-aware output. Mark the other §20 UI gates N/A with that reason."""
    return head + """
Apply it to every screen: §1 the seven ISO 9241-110 interaction principles; §2 presentation; §3 plain language;
§4 forms (visible labels, error summary that keeps input, aria-invalid); §5 consistent controls (links navigate,
buttons act); §6 EVERY state (loading, empty, partial, error, offline, stale, permission, success, busy, overflow,
first run); §7 WCAG 2.2 AA (keyboard only, visible focus, skip link, landmarks, names/roles/states, 4.5:1 text and
3:1 UI contrast, 24 px targets, reflow at 320 px, 200% zoom, live regions, reduced motion); §8 design tokens and
designed light AND dark themes of equal quality that follow the system with a remembered user override, plus
forced-colours support, with light and dark VISIBLY different in the header and navigation too (§8.9); §8.2-§8.8 colour
roles, type scale, icons, standard formats and data formats; §8.11 rich patterns where data is live, scored or multi-step;
§8.13 the app's OWN visual identity (never copy another product's look); §8.14 the top-20 professional polish checklist (a light theme as rich as the dark one); §8.16 a named palette per theme with one solid primary (not generic blue); §8.17 enterprise restraint (NO gradients,
glows, gradient text, glass or coloured shadows; solid colours, compact header, underline tabs); §8.18 a remembered
"Descriptions" switch that hides explanatory text only; §8.19 focused pages (the main input gets the space, secondary
records such as history on their own tab or page, no unused optional inputs); §8.15 button restraint (one
primary action per view, text/icon buttons for the rest, no duplicates); §9 responsive and §9.1 laptop density (fits
1366x768 without wasted margins); §11 feedback within 100 ms, undo or named confirmation for destructive
actions; §12.3 no dark patterns; §17 UI tests: automated browser tests of every journey that also check
keyboard reachability, accessible names, contrast of the theme tokens and no horizontal scroll at 320 px.
Write docs/UI_STATES.md (state inventory per screen) and docs/ACCESSIBILITY.md (target level, how it was
tested, known issues). The completion report must include the UEUIS §20 UI gate table."""


def build_prompt(a: dict) -> str:
    reuse_line = reuse_instructions(a.get("reuse") or [])
    ui_line = ui_instructions(a)
    return f"""You are building a complete application NON-INTERACTIVELY. Nobody will answer questions: never ask,
never wait for confirmation. When something is unspecified, choose a sensible, reversible default and record it in
docs/DECISIONS.md.

Read BUILD_SPEC.md (the user's inputs) and docs/UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md (apply it
proportionately where it says so). The standard is MANDATORY for this build: follow its §0 working contract, §2 requirements
traceability, §4 no-fake-data rule, §6 testing, §7 security, §17 workflow phases A-G, §18 release gates and §19 files.
{ui_line}
{reuse_line}

Deliver, in this folder only:
1. Working source code implementing every must-have feature, with real behaviour (no fake data or dead buttons).
2. Tests per the requested depth; RUN them and fix failures until they pass.
3. README.md (what it does, how to run, env vars), docs/REQUIREMENTS.md (acceptance criteria -> tests),
   docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/LEARNINGS.md, CLAUDE.md (short).
4. An executable ./run.sh that starts the app (web apps on 127.0.0.1:{a.get('port', 5070)}). Verify it starts and
   responds, then stop it (kill by PID). Install dependencies only into the project (.venv or node_modules).
5. {"Initialise git and commit the result with plain `git add` / `git commit` (the author identity is already set in the environment)." if a.get("git", True) else "Do not use git."}
6. Finally write docs/COMPLETION_REPORT.md using the standard's §22 completion report template with real evidence:
   a requirements-to-tests traceability table, the §18 gate table and the UEUIS §20 UI gate table (PASS / FAIL /
   N/A / UNVERIFIED; never turn UNVERIFIED into PASS), and print a short summary as your last message.

Constraints: stay inside this folder; never delete files outside it; never use sudo; never put secrets in files.
Budget: you have about {a['max_minutes']} minutes; prioritise a working, tested core over extras."""


def enhance_prompt(a: dict) -> str:
    reuse_line = reuse_instructions(a.get("reuse") or []).replace("build it new in this folder", "build the change here")
    return f"""You are ENHANCING an existing, working application NON-INTERACTIVELY. Nobody will answer questions: never ask,
never wait for confirmation. When something is unspecified, choose a sensible, reversible default and record it in
docs/DECISIONS.md.

Start by reading CLAUDE.md, docs/LEARNINGS.md, docs/DECISIONS.md and README.md, then docs/ENHANCE_SPEC.md (the user's
inputs for THIS change) and docs/UNIVERSAL_AI_SOFTWARE_ENGINEERING_STANDARD.md (MANDATORY: §0 working contract, §2
traceability, §4 no fake data, §6 testing, §7 security, §17 phases A-G, §18 gates). Before changing anything, run the
existing test suite and note the result; if tools/coverage.sh exists, run it too.
{ui_instructions(a)}
{reuse_line}

Rules for an enhancement:
- Extend the existing code and its conventions; do not rewrite or reorganise unrelated code. Existing features,
  routes and data must keep working. Never delete or overwrite user data (data/, *.sqlite3, browser profiles, .env).
- Every existing test must still pass at the end. Add tests for every new acceptance criterion. If the project has a
  coverage gate (tools/coverage.sh), keep it passing and add new modules to it at the same level.
- Never test against real third-party websites or accounts in a way that sends real data or submits anything: use
  local fakes. Do not start long-running servers on ports already in use; verify on a free port and stop it after.
- Update README.md, docs/DECISIONS.md, docs/LEARNINGS.md and docs/REQUIREMENTS.md (if present) for the change.
- {"Commit the change with plain `git add` / `git commit` (the author identity is set in the environment)." if a.get("git") else "Do not commit; leave the change uncommitted for the user to review."}
- Finally write docs/ENHANCE_REPORT.md using the standard's §22 completion report template with real evidence: what
  changed (files), requirements-to-tests traceability, the test and coverage results before and after, the §18 gate
  table and the UEUIS §20 UI gate table (PASS / FAIL / N/A / UNVERIFIED; never turn UNVERIFIED into PASS). Print a
  short summary as your last message.

Constraints: stay inside this folder; never delete files outside it; never use sudo; never put secrets in files.
Budget: you have about {a['max_minutes']} minutes; prioritise working, tested must-haves over extras."""


class BuildManager:
    def __init__(self, state_dir: Path = STATE_DIR):
        self.dir = state_dir / "builds"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self._load()

    # persistence: job.json is rewritten atomically
    def _save(self, job: dict) -> None:
        d = self.dir / job["id"]
        d.mkdir(exist_ok=True)
        tmp = d / "job.json.tmp"
        tmp.write_text(json.dumps(job, indent=1))
        tmp.replace(d / "job.json")

    def _load(self) -> None:
        for f in sorted(self.dir.glob("*/job.json")):
            try:
                job = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if job.get("status") in ("queued", "running"):
                job["status"] = "interrupted"
                job["error"] = "the analyzer server restarted while this build was running"
                job["finished_at"] = job.get("finished_at") or time.time()
                self._save(job)
            self.jobs[job["id"]] = job

    def list(self) -> list[dict]:
        with self.lock:
            return sorted(({k: v for k, v in j.items() if k != "events"} for j in self.jobs.values()),
                          key=lambda j: -j["created_at"])[:30]

    def get(self, job_id: str, since: int = 0) -> dict | None:
        with self.lock:
            j = self.jobs.get(job_id)
            if not j:
                return None
            return {**j, "events": j["events"][since:] if since <= len(j["events"]) else [], "event_count": len(j["events"])}

    def active(self) -> dict | None:
        with self.lock:
            return next((j for j in self.jobs.values() if j["status"] in ("queued", "running")), None)

    def start(self, requirement: str, answers: dict, labels: dict | None = None) -> dict:
        exe = claude_bin()
        if not exe:
            raise BuildError("Claude Code CLI not found (install it or set REQAN_CLAUDE_BIN)")
        a = validate_spec(requirement, answers)
        standard = uaises_text()  # mandatory: every build follows UAISES
        ui_standard = ui_standard_text()  # and every UI follows UEUIS
        with self.lock:
            busy = next((j for j in self.jobs.values() if j["status"] in ("queued", "running")), None)
            if busy:
                raise BuildError(f"build {busy['id']} ({busy['app_name']}) is still running; one build at a time")
            enhance = a.get("build_mode") == ENHANCE
            job = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], "app_name": str(a["app_name"])[:80],
                   "mode": "enhance" if enhance else "new", "output_dir": a["output_dir"], "status": "queued", "created_at": time.time(), "started_at": None,
                   "finished_at": None, "cost_usd": None, "result": None, "error": None, "denials": 0,
                   "port": a.get("port"), "events": []}
            self.jobs[job["id"]] = job
        out = Path(a["output_dir"])
        if enhance:
            job["backup"] = str(backup(out, self.dir.parent / "backups"))
        (out / "docs").mkdir(parents=True, exist_ok=True)
        (out / ("docs/ENHANCE_SPEC.md" if enhance else "BUILD_SPEC.md")).write_text(spec_markdown(requirement, a, labels or {}))
        (out / "docs" / UAISES.name).write_text(standard, encoding="utf-8")
        (out / "docs" / UI_STANDARD.name).write_text(ui_standard, encoding="utf-8")
        cmd = [exe, "-p", enhance_prompt(a) if enhance else build_prompt(a), "--output-format", "stream-json", "--verbose",
               "--permission-mode", "dontAsk", "--allowedTools", *build_tools(out),
               "--max-budget-usd", f"{a['budget_usd']:.2f}"]
        if a.get("model", "default") != "default":
            cmd += ["--model", a["model"]]
        self._save(job)
        threading.Thread(target=self._run, args=(job, cmd, out, a["max_minutes"] * 60), daemon=True).start()
        return {k: v for k, v in job.items() if k != "events"}

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            p = self.procs.get(job_id)
            j = self.jobs.get(job_id)
            if not p or not j or j["status"] != "running":
                return False
            j["cancel_requested"] = True
        _kill_group(p)
        return True

    # ---------------------------------------------------------- worker
    def _event(self, job: dict, kind: str, text: str) -> None:
        with self.lock:
            job["events"].append({"t": round(time.time() - (job["started_at"] or time.time()), 1), "kind": kind, "text": text[:600]})
            if len(job["events"]) > MAX_EVENTS_KEPT:
                del job["events"][1:len(job["events"]) - MAX_EVENTS_KEPT + 1]  # keep the first event

    def _run(self, job: dict, cmd: list[str], cwd: Path, timeout_s: int) -> None:
        log = open(self.dir / job["id"] / "stream.jsonl", "w")
        try:
            p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, env=git_env(),
                                 stderr=subprocess.STDOUT, text=True, start_new_session=True)
        except OSError as e:
            with self.lock:
                job.update(status="failed", error=f"could not start Claude Code: {e}", finished_at=time.time())
            self._save(job)
            log.close()
            return
        with self.lock:
            self.procs[job["id"]] = p
            job.update(status="running", started_at=time.time(), pid=p.pid)
        self._save(job)
        self._event(job, "info", f"Claude Code started in {cwd}")
        timer = threading.Timer(timeout_s, lambda: (job.__setitem__("timed_out", True), _kill_group(p)))
        timer.start()
        last_save = time.time()
        final = None
        try:
            for line in p.stdout:
                log.write(line)
                try:
                    ev = json.loads(line)
                except ValueError:
                    if line.strip():
                        self._event(job, "stderr", line.strip())
                    continue
                if ev.get("type") == "result":
                    final = ev
                for kind, text in summarize(ev):
                    self._event(job, kind, text)
                if time.time() - last_save > 5:
                    self._save(job)
                    last_save = time.time()
            p.wait()
        finally:
            timer.cancel()
            p.stdout.close()
            log.close()
        with self.lock:
            self.procs.pop(job["id"], None)
            job["finished_at"] = time.time()
            job["exit_code"] = p.returncode
            if final:
                job["cost_usd"] = final.get("total_cost_usd")
                job["result"] = final.get("result")
                job["denials"] = len(final.get("permission_denials") or [])
            if job.get("cancel_requested"):
                job["status"], job["error"] = "cancelled", "cancelled by user"
            elif job.get("timed_out"):
                job["status"], job["error"] = "timed-out", f"stopped after {timeout_s // 60} minutes"
            elif final and not final.get("is_error") and final.get("subtype") == "success" and p.returncode == 0:
                job["status"] = "succeeded"
            else:
                job["status"] = "failed"
                job["error"] = (final or {}).get("subtype") or f"Claude Code exited with code {p.returncode}"
                if final and "budget" in str(final.get("subtype", "")) + str(final.get("result", "")):
                    job["error"] = "spending cap reached: " + str(job["error"])
            report = cwd / "docs" / ("ENHANCE_REPORT.md" if job.get("mode") == "enhance" else "COMPLETION_REPORT.md")
            job["report"] = report.read_text(errors="replace")[:20000] if report.exists() else None
            job["has_run_sh"] = (cwd / "run.sh").exists()
            job["has_reuse_doc"] = (cwd / "docs" / "REUSE.md").exists()
            job["file_count"] = sum(1 for f in cwd.rglob("*") if f.is_file() and not _ignored(f, cwd))
        self._event(job, "info", f"Finished: {job['status']}")
        self._save(job)

    def launch(self, job_id: str) -> dict:
        with self.lock:
            j = self.jobs.get(job_id)
        if not j or j["status"] != "succeeded":
            raise BuildError("only a successful build can be launched")
        run = Path(j["output_dir"]) / "run.sh"
        if not run.exists():
            raise BuildError("this build has no run.sh")
        logf = open(self.dir / job_id / "app.log", "ab")
        p = subprocess.Popen(["bash", str(run)], cwd=run.parent, stdin=subprocess.DEVNULL, stdout=logf,
                             stderr=logf, start_new_session=True)
        logf.close()
        with self.lock:
            j["app_pid"] = p.pid
        self._save(j)
        return {"pid": p.pid, "url": f"http://127.0.0.1:{j['port']}/" if j.get("port") else None}


def _ignored(f: Path, root: Path) -> bool:
    parts = f.relative_to(root).parts
    return any(p in (".git", ".venv", "node_modules", "__pycache__", "upstream") for p in parts)  # upstream = cloned reuse sources


def _kill_group(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def summarize(ev: dict) -> list[tuple[str, str]]:
    """Turn one stream-json event into human-readable progress lines."""
    t = ev.get("type")
    out: list[tuple[str, str]] = []
    if t == "assistant":
        for c in (ev.get("message") or {}).get("content") or []:
            if c.get("type") == "text" and c.get("text", "").strip():
                out.append(("say", c["text"].strip()))
            elif c.get("type") == "tool_use":
                i = c.get("input") or {}
                detail = i.get("file_path") or i.get("command") or i.get("pattern") or i.get("query") or i.get("url") or ""
                if c.get("name") == "TodoWrite":
                    todos = i.get("todos") or []
                    detail = f"{sum(1 for x in todos if x.get('status') == 'completed')}/{len(todos)} tasks done"
                out.append(("tool", f"{c.get('name')}: {detail}"))
    elif t == "user":
        for c in (ev.get("message") or {}).get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error"):
                body = c.get("content")
                body = body if isinstance(body, str) else json.dumps(body)
                out.append(("error", body.strip()))
    elif t == "result":
        cost = ev.get("total_cost_usd")
        out.append(("done", f"{ev.get('subtype')} · {ev.get('num_turns')} turns" + (f" · ${cost:.2f}" if cost else "")))
    return out


def new_token() -> str:
    return secrets.token_urlsafe(24)
