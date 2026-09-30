"""What the studio asks for over the socket.

One dispatcher, shared by the WebSocket feed and the HTTP fallback routes the
studio uses when the socket is down. Every message runs on its own thread so the
feed stays live while the work happens, and every run reports through the bus.
"""
from __future__ import annotations

import threading
from typing import Any

from builder_agent import build as builder
from prototype_agent import prototype as prototyper
from qa_agent import verify as qa

from . import bus, changes, config, plugins, prompts, secrets_guard, store
from .session import RunCancelled, session_for


_active_lock = threading.RLock()
_active: dict[str, str] = {}


def _model_from(message: dict[str, Any]) -> str:
    """Whichever model the studio picked for this kind of work."""
    order = (("design_model", "model", "builder_model", "planner_model", "qa_model")
             if message.get("agent") == bus.DESIGNER else
             ("builder_model", "model", "planner_model", "design_model", "qa_model"))
    for key in order:
        chosen = str(message.get(key) or "").strip()
        if chosen:
            return chosen
    return str(config.setting("model") or "")


def _remember_model(message: dict[str, Any]) -> None:
    chosen = _model_from(message)
    level = str(message.get("thinking_level") or "").strip().lower()
    patch: dict[str, Any] = {}
    if chosen and chosen != config.setting("model"):
        patch["model"] = chosen
    if level in config.THINKING_LEVELS and level != config.thinking():
        patch["thinking_level"] = level
    if patch:
        config.save_settings(patch)


def _thinking_from(message: dict[str, Any]) -> str:
    """A message-level effort setting wins for its own chat turn."""
    chosen = str(message.get("thinking_level") or "").strip().lower()
    return chosen if chosen in config.THINKING_LEVELS else config.thinking()


def _in_background(name: str, project: str, agent: str, fn, *args: Any, **kwargs: Any) -> None:
    """Start exactly one mutating run per project.

    Double clicks, an HTTP fallback racing a reconnecting WebSocket, and a
    quick Resume after Start used to create two agents writing the same files.
    Claim before the thread starts so the second request gets a useful answer
    instead of a corrupt workspace.
    """
    with _active_lock:
        current = _active.get(project)
        if current:
            raise ValueError("this project is already working — wait for it to finish or stop it first")
        _active[project] = name
    bus.run_state(project, "queued", agent=agent)
    threading.Thread(target=_guarded, args=(name, fn, args, kwargs),
                     name=name, daemon=True).start()


def _guarded(name: str, fn, args: tuple, kwargs: dict) -> None:
    project = kwargs.pop("_project", "")
    try:
        fn(*args, **kwargs)
    except RunCancelled:
        if project:
            bus.cancelled(project, "Stopped.")
    except Exception as exc:  # noqa: BLE001 - the studio must see why, not hang
        if project:
            bus.failed(project, str(exc) or exc.__class__.__name__)
    finally:
        if project:
            with _active_lock:
                if _active.get(project) == name:
                    _active.pop(project, None)


def active_run(project: str) -> str:
    with _active_lock:
        return _active.get(project, "")


# --- the messages -----------------------------------------------------------

def agent_build(message: dict[str, Any]) -> dict[str, Any]:
    """Build — or, when `prototype_only`, draw the prototype first."""
    _remember_model(message)
    project = str(message.get("srs_id") or message.get("project") or "").strip()
    direction = str(message.get("prompt") or "").strip()

    if not project:
        record = store.create(idea=direction or "See the attached files.",
                              language=str(message.get("language") or ""),
                              stack=str(message.get("stack") or ""))
        project = record["id"]
    else:
        # A late WebSocket/fallback request can arrive after the customer
        # deleted an SRS or project.  Do not announce a ghost project (or let
        # a stale worker revive its workspace) when its record is gone.
        store.require(project)

    if message.get("stack"):
        store.update(project, stack=str(message["stack"]))

    # Start can select several providers before the workspace exists. Persist
    # all of them as soon as the project has an id.
    if "plugins" in message:
        plugins.configure_project(project, message.get("plugins") or [])

    # Always, not only for a project the server just created. The studio clears
    # its own project before every build (`s.reset(null)` in Home), and adopts
    # whatever this event names. Without it a run started from an approved SRS
    # leaves the studio on "no project open", filing every later event against a
    # project nothing is looking at — a build that works and a screen that never
    # moves.
    bus.project_created(project)

    if message.get("prototype_only"):
        _in_background(f"prototype:{project}", project, bus.DESIGNER, prototyper.generate, project, direction,
                       _project=project)
    else:
        _in_background(f"build:{project}", project, bus.DEVELOPER, builder.run, project, direction,
                       _project=project)
    return {"ok": True, "project": project}


def agent_update(message: dict[str, Any]) -> dict[str, Any]:
    """Something typed into the chat stream.

    A project with a specification plans it first: the plan is shown in the chat and nothing is
    changed until it is approved (`changes.py`). A project with nothing to change yet is answered
    where it stands.
    """
    _remember_model(message)
    project = str(message.get("project") or "").strip()
    request = str(message.get("prompt") or "").strip()
    if not project:
        raise ValueError("that message names no project")
    if not request:
        raise ValueError("say what to change")
    held = secrets_guard.refusal(request)
    if held:
        bus.agent_msg(project, held, title="Not sent")
        return {"ok": False, "detail": held}
    if changes.applies(project):
        return changes.submit(project, request, _model_from(message))
    return agent_update_direct(message)


def agent_update_direct(message: dict[str, Any]) -> dict[str, Any]:
    """A change applied at once, with no plan to approve: the feedback on a drawing, an answer to a
    question the run itself asked, a message to a project that has no specification yet."""
    _remember_model(message)
    project = str(message.get("project") or "").strip()
    request = str(message.get("prompt") or "").strip()
    if not project:
        raise ValueError("that message names no project")
    if not request:
        raise ValueError("say what to change")
    held = secrets_guard.refusal(request)
    if held:
        bus.agent_msg(project, held, title="Not sent")
        return {"ok": False, "detail": held}

    role = str(message.get("agent") or bus.DEVELOPER)
    if role == bus.DESIGNER and prototyper.exists(project):
        _in_background(f"prototype-edit:{project}", project, bus.DESIGNER, prototyper.revise, project, request,
                       _project=project)
    elif builder.built(project):
        _in_background(f"build-edit:{project}", project, bus.DEVELOPER, builder.update, project, request,
                       _project=project)
    else:
        _in_background(f"chat:{project}", project, role, _chat, project, request, role,
                       _model_from(message), _thinking_from(message), _project=project)
    return {"ok": True, "project": project}


def _chat(project: str, request: str, role: str, model: str = "", thinking_level: str = "") -> None:
    """A message to a project that has nothing built yet: answer it in place."""
    session = session_for(project)
    session.begin("chat", role=role)
    try:
        bus.user_msg(project, request, agent=role)
        record = store.get(project) or {}
        artifacts = _artifacts(project)
        result = session.run_task(prompts.load(
            "chat/update", message=request,
            stage=record.get("stage", "interview"),
            artifacts=artifacts,
            language=record.get("language", "English")), model=model, thinking_level=thinking_level)
        text = result.get("text", "").strip()
        if text:
            bus.agent_msg(project, text, agent=role)
        session.finish(text)
    except RunCancelled:
        raise
    except Exception:
        session.fail("that message could not be carried out")
        raise


def _artifacts(project: str) -> str:
    from srs_agent import document as srs_document

    have = []
    if srs_document.has_document(project):
        have.append("the specification, its diagrams and its wireframes")
    if prototyper.exists(project):
        have.append("the clickable prototype")
    if builder.built(project):
        have.append("the built application")
    if qa.report(project).get("complete"):
        have.append("a verification report")
    return ", ".join(have) or "nothing yet — only the idea and the interview"


def agent_resume(message: dict[str, Any]) -> dict[str, Any]:
    """Carry on from wherever the project actually stopped."""
    project = str(message.get("project") or "").strip()
    if not project:
        raise ValueError("that message names no project")
    record = store.require(project)
    stage = record.get("stage", "interview")

    if stage in ("build", "test") and builder.built(project):
        _in_background(f"test:{project}", project, bus.DEVELOPER, qa.run, project, "", _project=project)
    elif stage in ("prototype", "design") and not prototyper.exists(project):
        # An interrupted prototype is still a design job. Sending it straight
        # to the builder leaves the customer with neither a prototype nor a
        # usable recovery button. Resume the focused HTML generation first;
        # its checkpoint reuses completed kit/pages instead of starting over.
        _in_background(f"prototype:{project}", project, bus.DESIGNER, prototyper.generate_from_wireframes,
                       project, "", _project=project)
    elif stage in ("prototype", "design"):
        _in_background(f"build:{project}", project, bus.DEVELOPER, builder.run, project, "", _project=project)
    else:
        _in_background(f"build:{project}", project, bus.DEVELOPER, builder.run, project, "", _project=project)
    return {"ok": True, "project": project}


def feature(message: dict[str, Any]) -> dict[str, Any]:
    """A new capability asked for against a project that already exists."""
    return agent_update({**message, "agent": message.get("agent") or bus.DEVELOPER})


def element_edit(message: dict[str, Any]) -> dict[str, Any]:
    """A change aimed at one thing the customer pointed at on screen."""
    project = str(message.get("project") or "").strip()
    if not project:
        raise ValueError("that message names no project")
    target = str(message.get("selector") or message.get("element") or "").strip()
    route = str(message.get("route") or "").strip()
    request = str(message.get("prompt") or "").strip()
    where = " ".join(part for part in (f"on {route}" if route else "",
                                       f"({target})" if target else "") if part)
    return agent_update({**message, "prompt": f"{request}\n\nThey pointed at this {where}."})


def run_tests(message: dict[str, Any]) -> dict[str, Any]:
    project = str(message.get("project") or "").strip()
    if not project:
        raise ValueError("that message names no project")
    _in_background(f"test:{project}", project, bus.DEVELOPER, qa.run, project,
                   str(message.get("prompt") or ""), _project=project)
    return {"ok": True, "project": project}


HANDLERS = {
    "agent_build": agent_build,
    "agent_update": agent_update,
    "agent_resume": agent_resume,
    "feature": feature,
    "element_edit": element_edit,
    "run_tests": run_tests,
}


def handle(message: dict[str, Any]) -> dict[str, Any]:
    kind = str(message.get("type") or "")
    handler = HANDLERS.get(kind)
    if not handler:
        raise ValueError(f"the server has no handler for {kind!r}")
    return handler(message)


def cancel(project: str, _agent: str = "") -> dict[str, Any]:
    if not project:
        raise ValueError("choose a project to stop")
    store.require(project)
    session = session_for(project)
    active = active_run(project)
    was_running = bool(active or session.stage != "idle")
    session.cancel()
    if was_running:
        bus.log(project, "WARN", "Stop requested — ending the current step now.")
        return {"ok": True, "status": "stopping"}
    return {"ok": True, "status": "idle", "detail": "No active run to stop."}
