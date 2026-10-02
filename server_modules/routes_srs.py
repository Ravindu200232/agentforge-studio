"""The `/srs/...` router.

The studio posts most specification work as a job — `{path, method, body}` — and
polls for it, so one router serves both the direct GETs and the queued POSTs.
Everything here is the SRS agent and the prototype agent's design stage; nothing
here decides anything itself.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from prototype_agent import design as design_stage
from prototype_agent import prototype as prototyper
from srs_agent import document, interview, plan

from . import config, store

Handler = Callable[[str, dict[str, Any]], Any]

_ROUTES: list[tuple[str, str, re.Pattern[str], Handler]] = []


def route(method: str, pattern: str) -> Callable[[Handler], Handler]:
    compiled = re.compile("^" + pattern + "$")

    def register(fn: Handler) -> Handler:
        _ROUTES.append((method.upper(), pattern, compiled, fn))
        return fn

    return register


def dispatch(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    clean = "/" + (path or "").strip("/")
    for verb, _raw, pattern, handler in _ROUTES:
        if verb != method.upper():
            continue
        match = pattern.match(clean)
        if match:
            project = match.group("project") if "project" in (pattern.groupindex or {}) else ""
            return handler(project, {**(body or {}), "_match": match})
    raise FileNotFoundError(f"no SRS route for {method} {clean}")


P = r"(?P<project>[A-Za-z0-9_-]+)"


# --- the project ------------------------------------------------------------

@route("POST", r"/projects")
def create_project(_project: str, body: dict) -> Any:
    idea = str(body.get("idea") or "").strip()
    if not idea:
        raise ValueError("describe what you want built")
    # The model picked beside the first input: the interview, the plan and the specification all run on the
    # saved model, so it is saved here, before any of them starts.
    chosen = str(body.get("model") or "").strip()
    level = str(body.get("thinking_level") or "").strip().lower()
    patch: dict[str, Any] = {}
    if chosen and chosen != config.setting("model"):
        patch["model"] = chosen
    if level in config.THINKING_LEVELS and level != config.thinking():
        patch["thinking_level"] = level
    if patch:
        config.save_settings(patch)
    record = store.create(idea=idea,
                          language=str(body.get("language") or ""),
                          stack=str(body.get("stack") or ""),
                          workspace_path=str(body.get("workspace_path") or ""))
    return {"project": {"id": record["id"], "name": record["name"],
                        "stack": record["stack"], "language": record["language"],
                        "status": record["status"]}}


@route("GET", rf"/projects/{P}")
def project_detail(project: str, _body: dict) -> Any:
    return document.detail(project)


@route("POST", rf"/projects/{P}/analyze")
def analyze(project: str, _body: dict) -> Any:
    """Read the idea and work out what to ask. The first question comes with it."""
    store.require(project)
    return interview.next_question(project)


# --- the interview ----------------------------------------------------------

@route("GET", rf"/projects/{P}/interview")
def interview_next(project: str, _body: dict) -> Any:
    return interview.next_question(project)


@route("POST", rf"/projects/{P}/interview/answer")
def interview_answer(project: str, body: dict) -> Any:
    return interview.record_answer(project, body)


# --- the plan ---------------------------------------------------------------

@route("GET", rf"/projects/{P}/plan")
def plan_current(project: str, _body: dict) -> Any:
    return plan.current(project)


@route("POST", rf"/projects/{P}/plan")
def plan_draft(project: str, body: dict) -> Any:
    return plan.draft(project,
                      revision=str(body.get("revision") or ""),
                      answers=body.get("answers") if isinstance(body.get("answers"), dict) else None)


@route("POST", rf"/projects/{P}/plan/approve")
def plan_approve(project: str, _body: dict) -> Any:
    return plan.approve(project)


# --- the specification ------------------------------------------------------

@route("POST", rf"/projects/{P}/generate-srs")
def generate_srs(project: str, _body: dict) -> Any:
    return document.generate(project)


@route("POST", rf"/projects/{P}/approve")
def approve_srs(project: str, body: dict) -> Any:
    return document.approve(project, str(body.get("prompt") or ""))


@route("GET", rf"/projects/{P}/diagrams")
def diagrams(project: str, _body: dict) -> Any:
    return document.diagrams(project)


@route("POST", rf"/projects/{P}/diagrams/redraw")
def redraw_diagrams(project: str, body: dict) -> Any:
    kinds = body.get("kinds")
    chosen = [str(kind) for kind in kinds] if isinstance(kinds, list) else None
    return document.redraw_diagrams(project, deep=bool(body.get("deep")), kinds=chosen)


@route("GET", rf"/projects/{P}/builder-handoff")
def builder_handoff(project: str, _body: dict) -> Any:
    return document.handoff(project)


@route("GET", rf"/projects/{P}/agent-handoff")
def agent_handoff(project: str, _body: dict) -> Any:
    return document.agent_handoff(project)


@route("POST", rf"/projects/{P}/customize")
def customize(project: str, body: dict) -> Any:
    """A change typed into the specification review, carried into the document."""
    request = str(body.get("prompt") or "").strip()
    if not request:
        raise ValueError("say what to change")
    from server_modules import bus, prompts
    from server_modules.session import session_for

    session = session_for(project)
    session.begin("srs-edit")
    try:
        bus.user_msg(project, request)
        result = session.run_task(prompts.load(
            "chat/update", message=request, stage="specification",
            artifacts="the specification, its diagrams and its wireframes",
            language=store.require(project).get("language", "English")))
        session.finish("Specification updated.")
        return {"ok": True, "text": result.get("text", ""),
                "srs": document.document(project)}
    except Exception:
        session.fail("the specification could not be changed")
        raise


@route("POST", rf"/projects/{P}/changes")
def record_change(project: str, body: dict) -> Any:
    """The audit trail of approved updates, kept beside the specification."""
    from server_modules.session import session_for

    session = session_for(project)
    log = session.read_record("changes.json", fallback=None) or {"changes": []}
    entry = {"change_id": body.get("change_id"), "summary": body.get("summary"),
             "source": body.get("source", "studio")}
    if not any(c.get("change_id") == entry["change_id"] for c in log["changes"]):
        log["changes"].append(entry)
        session.write_record("changes.json", data=log)
    return {"ok": True, "changes": log["changes"]}


# --- wireframes -------------------------------------------------------------

@route("GET", rf"/projects/{P}/wireframes")
def wireframes(project: str, _body: dict) -> Any:
    return document.wireframes(project)


@route("POST", rf"/projects/{P}/wireframes/html")
def draw_wireframe(project: str, body: dict) -> Any:
    """The Wireframe tab's own draw button.

    One focused call per screen, reading the handoff documents the specification
    stage wrote. Previously this asked the agent to "redraw following the skill",
    which is how seven pages came back as four-line stubs.
    """
    return document.redraw(project, str(body.get("route") or "").strip(),
                            quiet=bool(body.get("quiet")))


@route("POST", rf"/projects/{P}/wireframes/html/edit")
def edit_wireframe(project: str, body: dict) -> Any:
    return document.save_wireframe_html(project, str(body.get("route") or ""),
                                        str(body.get("html") or ""))


@route("POST", rf"/projects/{P}/wireframes/html/ai-edit")
def ai_edit_wireframe(project: str, body: dict) -> Any:
    """Make one direct, page-scoped AI change without entering plan mode."""
    return document.ai_edit_wireframe(project, str(body.get("route") or ""),
                                      str(body.get("prompt") or ""))


@route("POST", rf"/projects/{P}/wireframes/approve")
def approve_wireframes(project: str, body: dict) -> Any:
    return prototyper.generate_from_wireframes(project, str(body.get("prompt") or ""))


# --- the design contract ----------------------------------------------------

@route("GET", rf"/projects/{P}/design-spec")
def design_spec(project: str, _body: dict) -> Any:
    return design_stage.current(project)


@route("POST", rf"/projects/{P}/design-spec/draft")
def design_draft(project: str, body: dict) -> Any:
    spec = body.get("spec") if isinstance(body.get("spec"), dict) else None
    return design_stage.draft(project, direction=str(body.get("direction") or ""), spec=spec)


@route("POST", rf"/projects/{P}/design-spec/(?P<version>[^/]+)/approve")
def design_approve(project: str, body: dict) -> Any:
    match = body.get("_match")
    version = match.group("version") if match else None
    return design_stage.approve(project, version)


# --- integrations -----------------------------------------------------------

@route("GET", rf"/projects/{P}/integrations")
def integrations(project: str, _body: dict) -> Any:
    from server_modules.session import session_for
    saved = session_for(project).read_record("integrations.json", fallback=None)
    doc = document.document(project).get("srs_document", {})
    return {"answers": (saved or {}).get("answers", {}),
            "questions": doc.get("integration_requirements") or []}


@route("POST", rf"/projects/{P}/integrations")
def save_integrations(project: str, body: dict) -> Any:
    from server_modules.session import session_for
    session = session_for(project)
    session.write_record("integrations.json", data={"answers": body.get("answers") or {}})
    return {"ok": True}


# --- attachments ------------------------------------------------------------

@route("POST", rf"/projects/{P}/inputs-json")
def upload_input(project: str, body: dict) -> Any:
    """One attachment, read into the project's own record."""
    import base64

    from server_modules.session import session_for

    session = session_for(project)
    rows = session.read_record("attachments.json", fallback=None) or []
    raw = base64.b64decode(str(body.get("data_base64") or ""), validate=False)
    mode = str(body.get("mode") or "text")
    try:
        text = raw.decode("utf-8") if mode in {"text", "document"} else ""
    except UnicodeDecodeError:
        text = ""

    entry = {
        "id": f"att_{len(rows) + 1}",
        "filename": str(body.get("filename") or "upload"),
        "mode": mode,
        "content_type": str(body.get("content_type") or ""),
        "purpose": str(body.get("purpose") or ""),
        "text": text[:20000],
        "bytes": len(raw),
    }
    stored = session.record_path("attachments", entry["filename"])
    stored.write_bytes(raw)
    entry["path"] = str(stored.relative_to(session.workspace).as_posix())
    rows.append(entry)
    session.write_record("attachments.json", data=rows)
    return {"ids": [entry["id"]], "attachment": entry}
