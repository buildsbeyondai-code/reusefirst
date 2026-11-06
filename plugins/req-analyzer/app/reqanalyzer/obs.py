"""Cross-cutting: privacy-conscious structured logging, secret redaction and in-process metrics."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter

_SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{8,})"), "[REDACTED]"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[REDACTED]"),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED]"),
    (re.compile(r"\b(xox[abprs]-[A-Za-z0-9-]{10,})"), "[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "[REDACTED]"),
    (re.compile(r"(?i)(authorization:\s*(bearer|token|basic)\s+)[^\s\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token|access[_-]?key)(\s*[=:]\s*[\"']?)[^\s\"',;]{6,}"), r"\1\2[REDACTED]"),
]


def redact(text) -> str:
    s = text if isinstance(text, str) else str(text)
    for pat, rep in _SECRET_PATTERNS:
        s = pat.sub(rep, s)
    return s


def redact_obj(o):
    if isinstance(o, dict):
        return {k: ("[REDACTED]" if re.search(r"(?i)token|secret|password|authorization|credential", str(k))
                    and isinstance(v, str) else redact_obj(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact_obj(v) for v in o]
    if isinstance(o, str):
        return redact(o)
    return o


class JsonFormatter(logging.Formatter):
    def format(self, rec: logging.LogRecord) -> str:
        d = {"ts": round(rec.created, 3), "level": rec.levelname, "logger": rec.name, "msg": redact(rec.getMessage())}
        for k in ("event", "job", "state", "reason"):
            if hasattr(rec, k):
                d[k] = redact(str(getattr(rec, k)))
        if rec.exc_info:
            d["exc"] = redact(self.formatException(rec.exc_info))[-4000:]
        return json.dumps(d)


class Metrics:
    """Counters and last-seen values; exposed (redacted) through /api/diagnostics."""

    def __init__(self):
        self.lock = threading.Lock()
        self.counters: Counter = Counter()
        self.last: dict[str, object] = {}
        self.started = time.time()

    def inc(self, name: str, n: int = 1) -> None:
        with self.lock:
            self.counters[name] += n

    def set(self, name: str, value) -> None:
        with self.lock:
            self.last[name] = value

    def snapshot(self) -> dict:
        with self.lock:
            return {"since": self.started, "counters": dict(self.counters), "last": dict(self.last)}


METRICS = Metrics()
