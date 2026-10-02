"""The event bus the studio listens to.

Every event shape here is one the studio's own reducer already understands
(`studio/lib/agent-session.js`). The bus retains a project's durable history so
a browser that reloads, or one that connects late, sees the same conversation
the live socket was showing.
"""
from __future__ import annotations

import itertools
import json
import threading
import time
import uuid
from typing import Any, Callable, Iterable

# The two roles the studio keeps separate sessions for. The prototype and design
# work is the designer's; everything else is the developer's.
DESIGNER = "designer"
DEVELOPER = "developer"
ROLES = (DESIGNER, DEVELOPER)

# One conversation per project, shown identically on every tab. Set False to go
# back to the studio's own split between the designer's chat and the developer's.
MIRROR_ROLES = True

_ids = itertools.count(1)
_lock = threading.RLock()
_history: dict[str, list[dict]] = {}
_runs: dict[str, dict[str, dict]] = {}
_listeners: list[Callable[[dict], None]] = []
_pending_decisions: dict[str, dict] = {}
_loaded: set[str] = set()
# A project may be deleted while a model call is still unwinding on a daemon
# worker.  Ignore every late event so it cannot recreate events.jsonl or make a
# deleted project reappear in a connected Studio window.
_discarded: set[str] = set()

# Events a browser needs to rebuild the screen. The rest — every token, every
# tool result — is live-only: keeping it would make the file enormous and the
# reload slow, and none of it is on screen a minute later.
DURABLE = {"log", "user_msg", "agent_msg", "phase", "step", "progress", "run_state", "agent_state", "file", "file_read", "memory", "runtime_state",
           "test_start", "test_result", "test_fixing", "prototype", "done", "error",
           "cancelled", "sync_state", "change"}


def _event_log(project: str):
    from . import config
    return config.record_dir(project) / "events.jsonl"


def _load(project: str) -> None:
    """Bring a project's own record of what happened back into memory.

    The conversation survives a restart in `context.json`; without this the chat
    beside it would not, and the customer would come back to a studio that had
    forgotten a three-hour build it had just finished.
    """
    if project in _loaded:
        return
    _loaded.add(project)
    path = _event_log(project)
    if not path.is_file():
        return
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return
    # `events.jsonl` is the durable conversation record. Loading every
    # durable row preserves the full chat after a restart instead of retaining
    # only the latest section of a long-lived project.
    _history.setdefault(project, [])[:0] = rows
    for row in rows:
        if row.get("type") == "run_state":
            _runs.setdefault(project, {})[row.get("agent") or DEVELOPER] = {
                "status": row.get("status", "stopped"), "run_id": row.get("run_id", "")}
    terminals = {}
    phases = {}
    for row in rows:
        role = row.get("agent") or DEVELOPER
        if row.get("type") in {"done", "error", "cancelled"}:
            terminals[role] = row
        elif row.get("type") == "phase":
            phases[(role, row.get("kind", "run"), row.get("key"))] = row
    for (role, _kind, _key), phase in phases.items():
        terminal = terminals.get(role)
        if (terminal and phase.get("status") in {"active", "running"}
                and terminal.get("at", 0) >= phase.get("at", 0)):
            closed = {**phase, "status": "complete" if terminal["type"] == "done" else "failed",
                      "at": int(time.time() * 1000), "event_id": uuid.uuid4().hex}
            _history[project].append(closed)
            _persist(closed)
    for role, state in _runs.get(project, {}).items():
        if state["status"] in {"running", "queued"}:
            recovered = {"type": "run_state", "project": project, "agent": role,
                         "status": "paused", "run_id": state.get("run_id", ""),
                         "at": int(time.time() * 1000), "event_id": uuid.uuid4().hex}
            _history[project].append(recovered)
            state["status"] = "paused"
            _persist(recovered)
            cleared = {"type": "agent_state", "project": project, "agent": role,
                       "state": "", "thinking": False, "at": recovered["at"] + 1,
                       "event_id": uuid.uuid4().hex}
            _history[project].append(cleared)
            _persist(cleared)
            active = {}
            for event in rows:
                if event.get("type") == "phase" and (event.get("agent") or DEVELOPER) == role:
                    active[(event.get("kind", "run"), event.get("key"))] = event
            for event in active.values():
                if event.get("status") in {"active", "running"}:
                    phase = {**event, "status": "paused", "detail": "Interrupted by server restart.",
                             "at": recovered["at"] + 2, "event_id": uuid.uuid4().hex}
                    _history[project].append(phase)
                    _persist(phase)


def _persist(event: dict) -> None:
    project = event.get("project")
    if not project or project in _discarded or event.get("type") not in DURABLE:
        return
    try:
        path = _event_log(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except (OSError, ValueError):
        # A lost line of history must never fail the run that produced it.
        pass


def subscribe(fn: Callable[[dict], None]) -> Callable[[], None]:
    with _lock:
        _listeners.append(fn)

    def cancel() -> None:
        with _lock:
            if fn in _listeners:
                _listeners.remove(fn)

    return cancel


def emit(event: dict, mirrored: bool = False) -> dict:
    """Stamp one event, keep it, and hand it to every listener.

    The studio keeps a separate chat per agent role and swaps which one is on
    screen as you move between tabs — Prototype and Design show the designer's,
    everything else the developer's. AgentForge is one conversation per project,
    so each event is filed under both roles and the stream reads the same from
    every tab instead of appearing to reset at each stage.
    """
    event = dict(event)
    event.setdefault("at", int(time.time() * 1000))
    event.setdefault("event_id", uuid.uuid4().hex)
    project = event.get("project")

    with _lock:
        if project and project in _discarded:
            return event

    if MIRROR_ROLES and not mirrored and project and event.get("agent") in ROLES:
        emit({**event,
              "agent": DEVELOPER if event["agent"] == DESIGNER else DESIGNER,
              "event_id": event["event_id"] + "-m"}, mirrored=True)

    with _lock:
        # Deletion can happen while the mirrored event above was being emitted.
        if project and project in _discarded:
            return event
        if project:
            _load(project)
            rows = _history.setdefault(project, [])
            rows.append(event)
            _persist(event)
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener(event)
        except Exception:  # noqa: BLE001 - one dead socket must not stop a run
            pass
    return event


_viewer_count: Callable[[], int] = lambda: 1


def set_viewer_count(fn: Callable[[], int]) -> None:
    """The feed server says how many studio windows are connected (see `viewers`)."""
    global _viewer_count
    _viewer_count = fn


def viewers() -> int:
    """How many studio windows are listening right now."""
    try:
        return int(_viewer_count())
    except Exception:  # noqa: BLE001 - a wrong answer here must not stop a run
        return 1


def transient(event: dict) -> dict:
    """Hand an event to every listener without keeping it.

    A frame of a live browser is worth having for a fraction of a second. Kept in
    the history, a few minutes of them would be tens of megabytes that the next
    reload has to carry, for a picture nobody can look at any more.
    """
    event = dict(event)
    event.setdefault("agent", DEVELOPER)
    event.setdefault("at", int(time.time() * 1000))
    event.setdefault("event_id", uuid.uuid4().hex)
    with _lock:
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener(event)
        except Exception:  # noqa: BLE001 - one dead socket must not stop a run
            pass
    return event


def history(project: str) -> list[dict]:
    with _lock:
        _load(project)
        return list(_history.get(project, []))


def latest_memory(project: str) -> dict:
    """The newest durable usage report for a project.

    Focused cloud tasks deliberately do not open the shared tool-agent chat.
    Their token accounting still arrives as durable ``memory`` events, so the
    session status endpoint can show the real context window after a restart
    instead of a misleading ``0 / 0``.
    """
    with _lock:
        _load(project)
        for event in reversed(_history.get(project, [])):
            if event.get("type") == "memory":
                return dict(event)
    return {}


def events_by_role(project: str) -> dict[str, list[dict]]:
    rows = history(project)
    return {role: [e for e in rows if (e.get("agent") or DEVELOPER) == role] for role in ROLES}


def forget(project: str) -> None:
    with _lock:
        _discarded.add(project)
        _history.pop(project, None)
        _runs.pop(project, None)
        _loaded.discard(project)
        for decision_id, question in list(_pending_decisions.items()):
            if question.get("project") == project:
                _pending_decisions.pop(decision_id, None)


# --- the shapes the studio reads -------------------------------------------

def log(project: str, level: str, text: str, agent: str = DEVELOPER) -> None:
    emit({"type": "log", "project": project, "agent": agent,
          "level": level, "text": text})


def user_msg(project: str, text: str, agent: str = DEVELOPER) -> None:
    emit({"type": "user_msg", "project": project, "agent": agent, "text": text})


def agent_msg(project: str, text: str, agent: str = DEVELOPER,
              title: str = "", kind: str = "", design: Any = None) -> None:
    event = {"type": "agent_msg", "project": project, "agent": agent, "text": text}
    if title:
        event["title"] = title
    if kind:
        event["kind"] = kind
    if design is not None:
        event["design"] = design
    emit(event)


def run_state(project: str, status: str, run_id: str = "", agent: str = DEVELOPER) -> None:
    """queued | running | completed | paused | failed."""
    with _lock:
        _runs.setdefault(project, {})[agent] = {"status": status, "run_id": run_id}
    emit({"type": "run_state", "project": project, "agent": agent,
          "status": status, "run_id": run_id})


def agent_state(project: str, state: str, thinking: bool = False, agent: str = DEVELOPER,
                detail: str = "") -> None:
    """What the agent is doing right now; `detail` says how far along (`12/35` while compacting)."""
    event = {"type": "agent_state", "project": project, "agent": agent, "state": state, "thinking": thinking}
    if detail:
        event["detail"] = detail
    emit(event)


def memory(project: str, model: str, used: int, context: int, tools: int,
           agent: str = DEVELOPER, turn_started_at: int = 0,
           turn_input_tokens: int = 0, turn_output_tokens: int = 0,
           context_scope: str = "conversation") -> None:
    rows = history(project)
    files = len({e.get("name") for e in rows if e.get("type") == "file"})
    emit({"type": "memory", "project": project, "agent": agent, "model": model,
          "used": used, "context": context, "tokens": used, "limit": context,
          "percent": round(100 * used / context) if context else 0,
          "tools": tools, "files": files,
          "requests": len([e for e in rows if e.get("type") == "agent_state" and e.get("state") == "thinking"]),
          "iterations": tools, "sent": max(0, turn_input_tokens),
          "received": max(0, turn_output_tokens),
          # The bottom-of-chat meter intentionally uses only exact provider
          # counts.  Context-window usage above remains its own metric.
          "turn_started_at": max(0, turn_started_at),
          "turn_tokens": max(0, turn_output_tokens),
          "context_scope": context_scope})


def progress(project: str, name: str, pct: float, agent: str = DEVELOPER) -> None:
    emit({"type": "progress", "project": project, "agent": agent,
          "step": name, "pct": pct})


def phase(project: str, key: str, title: str, status: str = "active",
          detail: str = "", number: int = 0, kind: str = "run",
          agent: str = DEVELOPER) -> None:
    emit({"type": "phase", "project": project, "agent": agent, "key": key,
          "title": title, "status": status, "detail": detail,
          "phase": number, "kind": kind})


def file_written(project: str, name: str, content: str, old: str | None = None,
                 note: str = "", agent: str = DEVELOPER) -> None:
    event = {"type": "file", "project": project, "agent": agent,
             "name": name, "content": content, "note": note}
    if old is not None:
        event["old_content"] = old
    emit(event)
    verb = "Patched" if "patch" in note.lower() or "edit" in note.lower() else "Written"
    log(project, "INFO", f"{verb} {name} ({len(content.splitlines())} lines)", agent=agent)


def file_read(project: str, name: str, content: str, agent: str = DEVELOPER) -> None:
    emit({"type": "file_read", "project": project, "agent": agent,
          "name": name, "content": content})


def stream_start(project: str, file: str, agent: str = DEVELOPER) -> None:
    emit({"type": "stream_start", "project": project, "agent": agent, "file": file})


def stream(project: str, token: str, agent: str = DEVELOPER) -> None:
    emit({"type": "stream", "project": project, "agent": agent, "token": token})


def stream_end(project: str, file: str, content: str, agent: str = DEVELOPER) -> None:
    emit({"type": "stream_end", "project": project, "agent": agent,
          "file": file, "content": content})


class StreamWriter:
    """One file's live stream, front to back — `start()`, `token()` per
    delta, `end()` once the true final content is known.

    A focused call like `llm.complete_html()` can run several rounds behind
    one write: a tool round before the real content, a repair attempt if the
    first draft fails validation. Each of those calls `on_stream_start()`
    again before it writes — `start()` clears whatever this writer still had
    buffered from the round before, so an earlier round's leftover, unflushed
    tail can never bleed into the round that actually became the file.

    Token events are batched rather than sent one per delta: `stream` is
    deliberately not `DURABLE` (see that set above), but it still occupies a
    slot in the bounded, in-memory event history on its way past, and a raw
    per-token firehose can be thousands of events for one twenty-thousand-
    character page. `token()` flushes at least every `min_interval` seconds
    or `min_chars` characters, whichever comes first — still well under
    human reading speed. `end()` flushes any remainder itself, so the last
    few characters (routinely under both thresholds) are never left sitting
    unsent.
    """

    def __init__(self, project: str, agent: str = DEVELOPER,
                min_interval: float = 0.08, min_chars: int = 24):
        self.project = project
        self.agent = agent
        self.min_interval = min_interval
        self.min_chars = min_chars
        self._buf = ""
        self._last = time.monotonic()

    def start(self, file: str) -> None:
        self._buf = ""
        self._last = time.monotonic()
        stream_start(self.project, file, agent=self.agent)

    def token(self, text: str) -> None:
        if not text:
            return
        self._buf += text
        now = time.monotonic()
        if len(self._buf) >= self.min_chars or (now - self._last) >= self.min_interval:
            self._flush()

    def _flush(self) -> None:
        if self._buf:
            stream(self.project, self._buf, agent=self.agent)
            self._buf = ""
            self._last = time.monotonic()

    def end(self, file: str, content: str) -> None:
        self._flush()
        stream_end(self.project, file, content, agent=self.agent)


def prototype_changed(project: str) -> None:
    emit({"type": "prototype", "project": project, "agent": DESIGNER})


def change(project: str, change: dict, agent: str = DEVELOPER) -> None:
    """A request typed into the chat, at the stage it has reached (see `changes.py`).

    Durable: the plan card in the chat is rebuilt from these after a reload.
    """
    emit({"type": "change", "project": project, "agent": agent, "change_id": change.get("id"),
          "revision": change.get("revision", 0), "status": change.get("status", ""),
          "request": change.get("request", ""), "plan": change.get("plan"),
          "error": change.get("error", ""), "summary": change.get("summary", ""),
          "version": change.get("version"), "flow": change.get("flow", ""), "target": change.get("target", "")})


def test_start(project: str) -> None:
    emit({"type": "test_start", "project": project, "agent": DEVELOPER})


def test_result(project: str, status: str, msg: str, detail: str = "") -> None:
    emit({"type": "test_result", "project": project, "agent": DEVELOPER,
          "status": status, "msg": msg, "detail": detail})


def test_done(project: str) -> None:
    emit({"type": "test_done", "project": project, "agent": DEVELOPER})


def runtime_state(project: str, status: str, url: str = "", server_id: str = "",
                  revision: int = 0) -> None:
    emit({"type": "runtime_state", "project": project, "status": status,
          "url": url, "serverId": server_id, "revision": revision})


def sync_state(project: str, status: str, detail: str = "", **extra: Any) -> None:
    emit({"type": "sync_state", "project": project, "status": status, "detail": detail, **extra})


def project_created(project: str) -> None:
    with _lock:
        # Project ids are random, but releasing a tombstone here keeps this
        # helper correct if an imported project intentionally reuses an id.
        _discarded.discard(project)
    emit({"type": "project", "project": project})


def done(project: str, text: str = "", agent: str = DEVELOPER) -> None:
    run_state(project, "completed", agent=agent)
    emit({"type": "done", "project": project, "agent": agent, "text": text})


def failed(project: str, text: str, agent: str = DEVELOPER) -> None:
    run_state(project, "failed", agent=agent)
    emit({"type": "error", "project": project, "agent": agent, "text": text})


def cancelled(project: str, text: str = "", agent: str = DEVELOPER) -> None:
    run_state(project, "paused", agent=agent)
    emit({"type": "cancelled", "project": project, "agent": agent, "text": text})


# --- questions the run stops on --------------------------------------------

def ask(project: str, kind: str, question: str, options: Iterable[str] = (),
        agent: str = DEVELOPER, **extra: Any) -> str:
    """Put a question on screen and remember it until it is answered.

    `kind` decides where the studio shows it: `question` in the chat stream,
    `prototype` in the preview, anything else in a dialog.
    """
    # Unique across restarts: a card still on screen from before one must never answer a newer question.
    decision_id = f"ask-{next(_ids)}-{uuid.uuid4().hex[:8]}"
    event = {"type": "approval", "project": project, "agent": agent,
             "id": decision_id, "kind": kind, "question": question,
             "options": list(options), **extra}
    with _lock:
        _pending_decisions[decision_id] = dict(event)
    emit(event)
    return decision_id


def pending_decisions() -> list[dict]:
    with _lock:
        return list(_pending_decisions.values())


def resolve(decision_id: str) -> dict | None:
    with _lock:
        question = _pending_decisions.pop(decision_id, None)
    if question:
        emit({"type": "approval_resolved", "project": question.get("project"),
              "agent": question.get("agent", DEVELOPER), "id": decision_id})
    return question


# --- a run that holds still for the customer's answer ------------------------

_waiters: dict[str, dict] = {}


def ask_and_wait(project: str, kind: str, question: str, options: Iterable[str] = (), agent: str = DEVELOPER,
                 cancelled: Callable[[], bool] = lambda: False, **extra: Any) -> str | None:
    """`ask`, then hold this run until the customer answers: their answer comes back ("" when they left it to the
    run), or None when the run was stopped first. Nothing is saved - a restart ends the run and its question together.
    """
    waiter = {"done": threading.Event(), "reply": "", "project": project}
    with _lock:                      # the card and its waiter exist together: no answer can arrive between them
        decision_id = ask(project, kind, question, options, agent, **extra)
        _waiters[decision_id] = waiter
    try:
        while not waiter["done"].wait(0.5):
            if cancelled():
                return None
        return waiter["reply"]
    finally:
        with _lock:
            _waiters.pop(decision_id, None)
        resolve(decision_id)         # a card nobody will answer any more goes from the screen


def deliver(decision_id: str, reply: str) -> bool:
    """The customer's answer to a question a run is holding still for. False when no run waits on that question."""
    with _lock:
        waiter = _waiters.get(decision_id)
    if not waiter:
        return False
    waiter["reply"] = reply
    waiter["done"].set()
    return True


def waiting_question(project: str) -> dict | None:
    """The question a run of this project is holding still for, as it is on screen."""
    with _lock:
        return next((dict(_pending_decisions[i]) for i, w in _waiters.items()
                     if w["project"] == project and i in _pending_decisions), None)


def run_status(project: str) -> dict[str, dict]:
    with _lock:
        return dict(_runs.get(project, {}))


def saved_stream(project: str) -> dict:
    """What `/stream/{project}` hands back: the chat and the log, replayed."""
    rows = history(project)
    logs = [{"level": e.get("level", "INFO"), "text": e.get("text", ""), "at": e.get("at")}
            for e in rows if e.get("type") == "log"]
    chat: list[dict] = []
    for event in rows:
        if event.get("type") == "user_msg":
            chat.append({"role": "user", "text": event.get("text", ""), "at": event.get("at")})
        elif event.get("type") == "agent_msg":
            chat.append({"role": "assistant", "text": event.get("text", ""),
                         "title": event.get("title", ""), "at": event.get("at")})
    return {"logs": logs, "chat": chat}
