"""What the studio needs to know about a project between runs.

The workspace on disk is the truth about what a project contains; this file only
records the things a directory listing cannot say — when it was created, which
stage it reached, what the customer originally asked for.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from . import config

_lock = threading.RLock()

# The order the studio moves through. `stage` is always one of these.
STAGES = ("interview", "plan", "srs", "design", "prototype", "build", "test", "deploy", "done")


def _read() -> dict[str, dict]:
    try:
        data = json.loads(config.PROJECTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict[str, dict]) -> None:
    config.PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.PROJECTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                    encoding="utf-8")


def new_id() -> str:
    return f"prj_{uuid.uuid4().hex[:16]}"


def create(idea: str, language: str = "", stack: str = "", workspace_path: str = "") -> dict:
    saved = config.settings()
    selected_workspace = config.validate_workspace_choice(workspace_path) if workspace_path else None
    record = {
        "id": new_id(),
        "name": "",
        "idea": idea,
        "language": language or saved.get("language") or "English",
        "stack": stack or saved.get("stack") or "nextjs-supabase",
        "stage": "interview",
        "status": "planning",
        "created_at": time.time(),
        "updated_at": time.time(),
        "spec_only": True,
        "prototype_only": False,
        "build_available": False,
        "kept": False,
        **({"workspace_path": str(selected_workspace)} if selected_workspace else {}),
    }
    record["name"] = record["id"]
    with _lock:
        data = _read()
        data[record["id"]] = record
        _write(data)
    config.scaffold_workspace(record["id"])
    return record


def get(project_id: str) -> dict | None:
    with _lock:
        return _read().get(project_id)


def require(project_id: str) -> dict:
    found = get(project_id)
    if not found:
        raise KeyError(project_id)
    return found


def build_available(record: dict | None) -> bool:
    """Whether the project has reached a point where a full build can start.

    Older prototype-only projects predate the persisted build_available flag.
    A successful prototype run marks them `prototyped`, which is sufficient
    evidence to safely enable the build action on reload as well.
    """
    if not record:
        return False
    return bool(record.get("build_available") or (
        record.get("prototype_only") and record.get("status") == "prototyped"
    ))


def update(project_id: str, **patch: Any) -> dict:
    with _lock:
        data = _read()
        record = data.get(project_id)
        if not record:
            raise KeyError(project_id)
        record.update(patch)
        record["updated_at"] = time.time()
        data[project_id] = record
        _write(data)
        return record


def advance(project_id: str, stage: str) -> dict:
    """Move a project forward, never backward."""
    record = require(project_id)
    try:
        now, then = STAGES.index(stage), STAGES.index(record.get("stage", "interview"))
    except ValueError:
        return record
    return update(project_id, stage=stage) if now > then else record


def rename(project_id: str, name: str) -> dict:
    clean = str(name or "").strip()
    return update(project_id, name=clean or project_id)


def listing() -> list[dict]:
    """Every project the studio should show, newest first."""
    with _lock:
        rows = list(_read().values())
    rows.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
    return [{
        "name": row["id"],
        "title": row.get("name") or row["id"],
        "idea": row.get("idea", "")[:300],
        "stage": row.get("stage", "interview"),
        "stack": row.get("stack", ""),
        "status": row.get("status", "planning"),
        "created_at": row.get("created_at", 0),
        "updated_at": row.get("updated_at", 0),
        "spec_only": bool(row.get("spec_only")),
        "prototype_only": bool(row.get("prototype_only")),
        "build_available": build_available(row),
    } for row in rows]


def delete(project_id: str) -> None:
    with _lock:
        data = _read()
        data.pop(project_id, None)
        _write(data)


def exists(project_id: str) -> bool:
    return get(project_id) is not None
