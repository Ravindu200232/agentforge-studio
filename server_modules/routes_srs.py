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
from srs_agent import wireframe as wireframer

from . import bus, config, permissions, privacy, store, web_app
from .session import session_for

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
    hidden = privacy.scrub(idea) if privacy.enabled() else privacy.Scrubbed(idea)       # NotSent (a ValueError) when it cannot run
    idea = hidden.text
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
    privacy.tell(record["id"], hidden.found)
    permissions.start_project(record["id"], str(body.get("permission_mode") or ""))
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
    return interview.record_answer(project, {**body, **{key: privacy.screen(project, str(body[key]))
                                                         for key in ("text", "custom") if body.get(key)}})


@route("POST", rf"/projects/{P}/interview/skip")
def interview_skip(project: str, _body: dict) -> Any:
    """No interview: the plan is written from the idea and the chosen stack, and says what it assumed."""
    return interview.skip(project)


# --- the plan ---------------------------------------------------------------

@route("GET", rf"/projects/{P}/plan")
def plan_current(project: str, _body: dict) -> Any:
    return plan.current(project)


@route("POST", rf"/projects/{P}/plan")
def plan_draft(project: str, body: dict) -> Any:
    answers = body.get("answers") if isinstance(body.get("answers"), dict) else None
    return plan.draft(project,
                      revision=privacy.screen(project, str(body.get("revision") or "")),
                      answers={q: privacy.screen(project, str(a)) for q, a in answers.items()} if answers else None)


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
    request = privacy.screen(project, request)
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
        document.reconcile(project, request, result.get("text", ""), session)
        session.finish("Specification updated.")
        return {"ok": True, "text": result.get("text", ""),
                "srs": document.document(project)}
    except Exception:
        session.fail("the specification could not be changed")
        raise


@route("GET", rf"/projects/{P}/plain-summary")
def plain_summary_read(project: str, _body: dict) -> Any:
    """The specification in plain words, as it was last written, and whether it still matches the specification."""
    from srs_agent import plain_summary

    return plain_summary.read(project)


@route("POST", rf"/projects/{P}/plain-summary")
def plain_summary_write(project: str, body: dict) -> Any:
    """Write it (a model does, once): when there is none, when the specification changed, or when asked again."""
    from srs_agent import plain_summary

    return plain_summary.write(project, again=bool(body.get("again")))


@route("GET", rf"/projects/{P}/decisions")
def decisions_listing(project: str, _body: dict) -> Any:
    """The specification's open decisions as questions, and the ones already settled."""
    from srs_agent import decisions

    return decisions.listing(project)


@route("POST", rf"/projects/{P}/decisions")
def decisions_prepare(project: str, _body: dict) -> Any:
    """The same, with the questions of any decision that has none yet written first (a model writes them once)."""
    from srs_agent import decisions

    return decisions.prepare(project)


@route("POST", rf"/projects/{P}/decisions/(?P<ident>[A-Za-z0-9_.-]+)")
def decisions_answer(project: str, body: dict) -> Any:
    """The customer's answer to one open decision: an option (its index) or their own words."""
    from srs_agent import decisions

    option = body.get("option")
    ident = body["_match"].group("ident")
    return decisions.answer(project, ident, privacy.screen(project, str(body.get("answer") or "")),
                            option=int(option) if isinstance(option, (int, float)) or str(option).isdigit() else None)


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


@route("POST", rf"/projects/{P}/wireframes/build")
def build_wireframes(project: str, body: dict) -> Any:
    """Draw the wireframes again, or carry on a run that was stopped (`resume`)."""
    return wireframer.run(project, privacy.screen(project, str(body.get("prompt") or "").strip()), fresh=not body.get("resume"))


@route("POST", rf"/projects/{P}/wireframes/html")
def build_html_wireframes(project: str, body: dict) -> Any:
    """The same wireframes as plain HTML pages in `.agentforge/wireframe-html` (to compare with the React app)."""
    return wireframer.run_html(project, privacy.screen(project, str(body.get("prompt") or "").strip()), fresh=not body.get("resume"))


@route("POST", rf"/projects/{P}/wireframes/edit")
def edit_wireframe(project: str, body: dict) -> Any:
    """One change to the wireframes, asked for in words (about one page when `route` is given, and about the `elements` pointed at)."""
    return wireframer.edit(project, privacy.screen(project, str(body.get("prompt") or "")), str(body.get("route") or ""),
                           body.get("elements"))


@route("POST", rf"/projects/{P}/prototype/edit")
def edit_prototype(project: str, body: dict) -> Any:
    """One change to the prototype, asked for in words (and about the `elements` pointed at)."""
    return prototyper.revise(project, privacy.screen(project, " ".join(str(body.get("prompt") or "").split())), body.get("elements"))


# What is still working on an app: its words are not swapped under it.
_WORKING = ("srs", "wireframes", "wireframe-edit", "prototype", "prototype-edit", "review", "build")


@route("POST", rf"/projects/{P}/app/text-edit")
def edit_app_text(project: str, body: dict) -> Any:
    """Retype some words on a page of the wireframes or the prototype: `old` becomes `new` in the app's source when `old` is
    written there in exactly one place, and the app is bundled again. Otherwise `{"ok": false, "reason"}` says why not, and the studio
    hands the change to the agent."""
    kind = str(body.get("kind") or "")
    if kind not in web_app.KINDS:
        raise ValueError("the words are on the wireframes or on the prototype")
    session = session_for(project)
    if session.stage in _WORKING:
        raise ValueError("wait for the agent to finish: it is still working on the app")
    app = web_app.app_dir(session.workspace, kind)
    if not web_app.built(app):
        raise FileNotFoundError(f"the {kind} is not drawn yet")
    done = web_app.edit_text(app, str(body.get("old") or ""), str(body.get("new") or ""))
    if not done.get("ok"):
        return done
    original = done.pop("original")
    made, log = web_app.bundle(app)
    if not made:
        (app / done["file"]).write_bytes(original.encode("utf-8"))
        web_app.bundle(app)                                      # the page the studio shows is the one it had
        return {"ok": False, "reason": "does not bundle", "detail": log[-300:]}
    (bus.prototype_changed if kind == "prototype" else bus.wireframe_changed)(project)
    return done


@route("POST", rf"/projects/{P}/wireframes/approve")
def approve_wireframes(project: str, body: dict) -> Any:
    return prototyper.generate_from_wireframes(project, privacy.screen(project, str(body.get("prompt") or "")))


# --- the design contract ----------------------------------------------------

@route("GET", rf"/projects/{P}/design-spec")
def design_spec(project: str, _body: dict) -> Any:
    return design_stage.current(project)


@route("POST", rf"/projects/{P}/design-spec/draft")
def design_draft(project: str, body: dict) -> Any:
    spec = body.get("spec") if isinstance(body.get("spec"), dict) else None
    return design_stage.draft(project, direction=privacy.screen(project, str(body.get("direction") or "")), spec=spec)


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
