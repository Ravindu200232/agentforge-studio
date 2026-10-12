"""A uniform, minimal per-stage checkpoint: did the last run of a stage
finish, fail, or get cut off mid-run.

`changes.py` and `deploy_agent/deploy.py` each already know how to notice
they were interrupted and resume from where they stopped (`resume={"interrupted":
True}`), but that awareness is theirs alone — the SRS write, the wireframes,
the prototype and the build have none of it: a server restart mid-build
leaves nothing behind but a stage stuck showing "running" forever. Rather than
teach each of those stages its own version of the same idea, this hooks the
three points every stage already calls without exception —
`ProjectSession.begin()`/`finish()`/`fail()` — so every stage gets the same
evidence for free, in one place.

This is deliberately not fine-grained resume-from-the-last-step (that stays
each stage's own business, `changes.py`/`deploy.py` included); it is only the
answer to "did the thing that was running last time ever finish", which is
what lets a stage's own start-up notice a crash instead of silently starting
over as if nothing happened.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import config


def _path(project: str, stage: str) -> Path:
    return config.record_dir(project) / stage / "evidence.json"


def _write(project: str, stage: str, record: dict[str, Any]) -> None:
    path = _path(project, stage)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # evidence is a courtesy; never a reason to fail the stage itself


def last(project: str, stage: str) -> dict[str, Any] | None:
    """The stage's last recorded checkpoint, or `None` before it ever ran."""
    path = _path(project, stage)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def was_interrupted(project: str, stage: str) -> bool:
    """True when the stage's last checkpoint is still "running" — the process
    ended (crash, restart, kill) before `finish()`/`fail()` ever recorded an
    outcome. A stage's own `begin()` calls this just before overwriting the
    file, which is the only moment the previous, unfinished state is still
    there to read."""
    record = last(project, stage)
    return bool(record and record.get("status") == "running")


def begin(project: str, stage: str) -> None:
    _write(project, stage, {"status": "running", "started_at": time.time()})


def finish(project: str, stage: str, detail: str = "") -> None:
    _write(project, stage, {"status": "complete", "finished_at": time.time(),
                            "detail": str(detail or "")[:500]})


def fail(project: str, stage: str, error: str = "") -> None:
    _write(project, stage, {"status": "failed", "finished_at": time.time(),
                            "error": str(error or "")[:500]})
