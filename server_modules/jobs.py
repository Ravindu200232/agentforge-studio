"""Background jobs.

The studio never blocks a request on a model. It posts the work, gets a job id
back, and polls — which is what lets an interview answer, a specification and a
deployment all take as long as they actually take without a proxy timing them
out. This is the queue behind those three job endpoints.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any, Callable

from .session import RunCancelled

_lock = threading.RLock()
_jobs: dict[str, dict[str, Any]] = {}

# A finished job is kept long enough for a browser that reloaded to collect it.
KEEP_SECONDS = 3600


def _sweep() -> None:
    cutoff = time.time() - KEEP_SECONDS
    with _lock:
        for job_id in [k for k, v in _jobs.items()
                       if v["status"] != "running" and v.get("finished_at", 0) < cutoff]:
            _jobs.pop(job_id, None)


def start(work: Callable[[], Any], label: str = "", *, project: str = "",
          agent: str = "", on_cancel: Callable[[], None] | None = None) -> str:
    """Run `work` on its own thread and hand back the id to poll."""
    _sweep()
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    record = {"id": job_id, "label": label, "status": "running",
              "started_at": time.time(), "finished_at": 0.0,
              "result": None, "error": "", "http_status": 200,
              "project": project, "agent": agent,
              "cancel_event": threading.Event(), "on_cancel": on_cancel,
              "cancel_notified": False}
    with _lock:
        _jobs[job_id] = record

    def runner() -> None:
        try:
            if record["cancel_event"].is_set():
                raise RunCancelled(project)
            result = work()
            with _lock:
                if record["cancel_event"].is_set():
                    raise RunCancelled(project)
                record["result"] = result
                record["status"] = "done"
                record["http_status"] = 200
        except RunCancelled:
            _cancelled(record)
        except FileNotFoundError as exc:
            _cancelled(record) if record["cancel_event"].is_set() else _fail(record, 404, str(exc) or "not found")
        except KeyError as exc:
            _cancelled(record) if record["cancel_event"].is_set() else _fail(record, 404, f"{exc} was not found")
        except (ValueError, TypeError) as exc:
            _cancelled(record) if record["cancel_event"].is_set() else _fail(record, 400, str(exc))
        except Exception as exc:  # noqa: BLE001 - the browser needs a reason, not a hang
            if record["cancel_event"].is_set():
                _cancelled(record)
            else:
                _fail(record, 500, str(exc) or exc.__class__.__name__,
                      traceback.format_exc())
        finally:
            with _lock:
                if not record["finished_at"]:
                    record["finished_at"] = time.time()

    threading.Thread(target=runner, name=f"job:{label or job_id}", daemon=True).start()
    return job_id


def _cancelled(record: dict[str, Any]) -> None:
    callback = None
    with _lock:
        if record["status"] != "running":
            return
        record["status"] = "cancelled"
        record["result"] = {"cancelled": True, "stopped": True}
        record["error"] = ""
        record["http_status"] = 200
        record["finished_at"] = time.time()
        if not record["cancel_notified"]:
            record["cancel_notified"] = True
            callback = record.get("on_cancel")
    if callback:
        try:
            callback()
        except Exception:  # noqa: BLE001 - cancellation remains terminal even if its notification cannot be written
            pass


def cancel_project(project: str) -> int:
    """Cancel every queued or running job owned by a project."""
    matched: list[dict[str, Any]] = []
    with _lock:
        for record in _jobs.values():
            if record.get("project") == project and record["status"] == "running":
                record["cancel_event"].set()
                matched.append(record)
    # Mark queued jobs terminal immediately. A worker that is already inside a
    # cancellation-aware operation will observe the same event and unwind.
    for record in matched:
        _cancelled(record)
    return len(matched)


def _fail(record: dict[str, Any], status: int, message: str, detail: str = "") -> None:
    with _lock:
        record["status"] = "error"
        record["error"] = message
        record["http_status"] = status
        record["result"] = {"error": message, "detail": detail[-2000:] if detail else message}


def poll(job_id: str) -> dict[str, Any]:
    """What `GET /…/jobs/{id}` answers."""
    with _lock:
        record = _jobs.get(job_id)
        if not record:
            return {"status": "unknown", "error": "that job has expired", "job_id": job_id}
        elapsed = int((record.get("finished_at") or time.time()) - record["started_at"])
        return {
            "job_id": job_id,
            "status": record["status"],
            "elapsed": elapsed,
            "http_status": record["http_status"],
            "result": record["result"],
            "error": record["error"],
        }
