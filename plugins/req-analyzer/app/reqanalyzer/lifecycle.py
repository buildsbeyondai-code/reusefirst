"""Domain layer: the build job state machine. See docs/BUILD_LIFECYCLE.md.

SUCCEEDED means every mandatory verification gate passed, never merely "Claude exited 0".
"""
from __future__ import annotations

CREATED, VALIDATED, QUEUED, PREPARING, RUNNING, VERIFYING = (
    "created", "validated", "queued", "preparing", "running", "verifying")
SUCCEEDED, PARTIALLY_COMPLETED, FAILED, CANCELLED, TIMED_OUT, INTERRUPTED, BLOCKED = (
    "succeeded", "partially_completed", "failed", "cancelled", "timed_out", "interrupted", "blocked")

ACTIVE = (CREATED, VALIDATED, QUEUED, PREPARING, RUNNING, VERIFYING)
TERMINAL = (SUCCEEDED, PARTIALLY_COMPLETED, FAILED, CANCELLED, TIMED_OUT, INTERRUPTED, BLOCKED)
_ABORT = {FAILED, CANCELLED, INTERRUPTED, BLOCKED}

TRANSITIONS: dict[str, set[str]] = {
    CREATED: {VALIDATED} | _ABORT,
    VALIDATED: {QUEUED} | _ABORT,
    QUEUED: {PREPARING} | _ABORT,
    PREPARING: {RUNNING} | _ABORT,
    RUNNING: {VERIFYING, TIMED_OUT} | _ABORT,
    VERIFYING: {SUCCEEDED, PARTIALLY_COMPLETED, TIMED_OUT} | _ABORT,
}
for _t in TERMINAL:
    TRANSITIONS[_t] = set()

# 1.x job files used these names.
LEGACY = {"timed-out": TIMED_OUT, "queued": QUEUED, "running": RUNNING}


class TransitionError(RuntimeError):
    pass


def can(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, set())


def advance(job: dict, dst: str, reason: str | None = None, now: float | None = None) -> dict:
    """Move job to dst or raise TransitionError. Records the transition history."""
    import time
    src = job.get("status", CREATED)
    if not can(src, dst):
        raise TransitionError(f"illegal transition {src} -> {dst}")
    job["status"] = dst
    job.setdefault("transitions", []).append({"from": src, "to": dst, "at": now or time.time(),
                                              **({"reason": reason} if reason else {})})
    if reason and dst in TERMINAL and dst != SUCCEEDED:
        job["error"] = reason
    return job


def normalise(status: str) -> str:
    return LEGACY.get(status, status)


def is_active(status: str) -> bool:
    return normalise(status) in ACTIVE
