"""Persistence: every completed analysis is saved as one JSON file with its timestamp.

Files live in <STATE_DIR>/analyses/<id>.json, where id = UTC timestamp + random suffix, so a
directory listing is already in time order. Only the newest MAX_KEEP files are kept.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from pathlib import Path

from . import builder

MAX_KEEP = 500
ID_RE = re.compile(r"\d{8}T\d{9}Z-[0-9a-f]{6}")


class History:
    def __init__(self, state_dir: Path | None = None):
        self.dir = (state_dir or builder.STATE_DIR) / "analyses"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def save(self, result: dict, keywords: list[str] | None = None, github: bool = True) -> dict:
        now = time.time()
        rid = time.strftime("%Y%m%dT%H%M%S", time.gmtime(now)) + f"{int(now * 1000) % 1000:03d}Z-" + secrets.token_hex(3)
        rec = {"id": rid, "created_at": now, "keywords": keywords or [], "github": github, "result": result}
        with self.lock:
            tmp = self.dir / f"{rid}.json.tmp"
            tmp.write_text(json.dumps(rec))
            tmp.replace(self.dir / f"{rid}.json")
            for old in sorted(self.dir.glob("*.json"))[:-MAX_KEEP]:
                old.unlink(missing_ok=True)
        return self._summary(rec)

    @staticmethod
    def _summary(rec: dict) -> dict:
        r = rec.get("result") or {}
        best = r.get("best") or {}
        return {"id": rec["id"], "created_at": rec["created_at"], "requirement": r.get("requirement", ""),
                "keywords": rec.get("keywords", []), "verdict": r.get("verdict", ""),
                "best_name": best.get("name"), "best_closeness": best.get("closeness")}

    def list(self, limit: int = 50) -> list[dict]:
        out = []
        for f in sorted(self.dir.glob("*.json"), reverse=True)[:limit]:
            try:
                out.append(self._summary(json.loads(f.read_text())))
            except (OSError, ValueError, KeyError):
                continue
        return out

    def get(self, rid: str) -> dict | None:
        if not ID_RE.fullmatch(rid or ""):
            return None
        try:
            return json.loads((self.dir / f"{rid}.json").read_text())
        except (OSError, ValueError):
            return None

    def delete(self, rid: str) -> bool:
        if not ID_RE.fullmatch(rid or ""):
            return False
        with self.lock:
            f = self.dir / f"{rid}.json"
            if not f.exists():
                return False
            f.unlink()
            return True
