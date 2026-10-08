"""The wireframe: a low-fidelity React app the project's agent builds with the web-artifacts-builder skill.

The agent does the building, with its own file tools, so every file it writes appears in the chat as it
happens. Code here is only what it cannot do for itself: stage the skill and the shared toolkit, tell it
which screens and journeys the specification names, and leave a built `bundle.html` for the preview.
What the pages look like, and how they hang together, is the agent's.

    <workspace>/.agentforge/wireframe/app/    the app (source, and the bundle the preview shows)
"""
from __future__ import annotations

from typing import Any

from server_modules import bus, journeys, prompts, web_app
from server_modules.session import RunCancelled, session_for

from . import document

KIND = "wireframe"
MAX_REQUEST = 4000


def _lines(values: Any) -> str:
    return ", ".join(str(v).strip() for v in (values or []) if str(v).strip())


def routes_text(pages: list[dict]) -> str:
    rows = []
    for page in pages:
        route = str(page.get("route") or "/")
        name = str(page.get("page_name") or route)
        detail = "; ".join(part for part in (
            ("sections: " + _lines(page.get("sections"))) if page.get("sections") else "",
            ("functions: " + _lines(page.get("functions"))) if page.get("functions") else "") if part)
        rows.append(f"- `{route}` — {name}" + (f" — {detail}" if detail else ""))
    return "\n".join(rows)


def journeys_text(doc: dict) -> str:
    flows = journeys.user_journeys_for(doc)
    return "\n".join(
        f"- {flow['workflow_name']}: " + " → ".join(f"{step['step'][:90]} [{step['route']}]" for step in flow["steps"])
        for flow in flows) or "(the specification lists no journeys)"


def _remember(session, **state: Any) -> None:
    """What the studio shows when the wireframe is not there: the last error, if any."""
    try:
        session.write_record("wireframe", "state.json", data=state)
    except RunCancelled:
        raise
    except OSError:
        pass


def generate(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """Build the wireframe app from the approved specification and leave its bundle ready to preview.

    `fresh` starts the app again; without it an app a stopped run left behind is carried on."""
    session = session_for(project)
    pages = document.screens(project)
    if not pages:
        raise ValueError("the specification names no screens to build")
    if not (session.record / document.SRS_DIR / "handoff" / "app.md").is_file():
        raise ValueError("the SRS handoff files are missing; the wireframe is built from the approved contract")
    doc = document.document(project).get("srs_document", {})

    if not web_app.runtime_ready():
        bus.agent_msg(project, "Getting the UI toolkit the wireframe is built with ready. This happens once and can take "
                               "a few minutes.", title="Wireframe toolkit", kind="narration", agent=bus.DESIGNER)
    ready, why = web_app.prepare_runtime()
    if not ready:
        raise RuntimeError("the UI toolkit could not be installed: " + why[-300:])

    app = web_app.app_dir(project, KIND)
    relative = app.relative_to(session.workspace).as_posix()
    carrying_on = not fresh and (app / "index.html").is_file()
    if not carrying_on:
        web_app.remove_app(app)
    skill = web_app.stage_skill(project)

    bus.phase(project, "wireframes", "Building the wireframes", detail=f"{len(pages)} page(s) from the approved specification.",
              agent=bus.DESIGNER)
    result = session.run_task(
        prompts.load("wireframe/generate", request=request or document.WIREFRAME_APPROVAL_PROMPT, skill=skill, app=relative,
                     routes=routes_text(pages), journeys=journeys_text(doc),
                     resume=(f"The app already exists in `{relative}` from a run that stopped: carry on with it instead of "
                             "creating it again, and add what is missing." if carrying_on else "")),
        audit=False, parallel_write_limit=4)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") not in (None, "complete") and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)

    web_app.ensure_built(session, project, KIND, agent=bus.DESIGNER)
    _remember(session, error="")
    bus.phase(project, "wireframes", "Building the wireframes", status="complete", agent=bus.DESIGNER)
    bus.wireframe_changed(project)
    return result


def run(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """A whole wireframe run: the session, the progress the studio shows, and what it says when it ends."""
    session = session_for(project)
    session.begin("wireframes", role=bus.DESIGNER)
    bus.sync_state(project, "running", "Building the wireframes", source="wireframe")
    try:
        generate(project, request, fresh=fresh)
        pages = document.wireframes(project)["pages"]
        ready = sum(bool(row["has_html"]) for row in pages)
        session.finish(f"The wireframe app is ready: {len(pages)} page(s).")
        bus.agent_msg(project, f"The wireframe is ready: {len(pages)} page(s) in the Wireframe tab. Click through them, "
                               "and ask for any change.", title="Wireframes ready", agent=bus.DESIGNER)
        bus.sync_state(project, "clean", "Wireframes ready", source="wireframe")
        return {"ok": True, "project": project, "ready": ready, "total": len(pages)}
    except RunCancelled:
        session.stage = "idle"
        session.save_context()
        bus.phase(project, "wireframes", "Building the wireframes", status="paused", agent=bus.DESIGNER)
        bus.sync_state(project, "paused", "Wireframe generation stopped.", source="wireframe")
        raise
    except Exception as exc:  # noqa: BLE001
        _remember(session, error=str(exc)[:300])
        session.fail(str(exc))
        bus.phase(project, "wireframes", "Building the wireframes", status="failed", detail=str(exc)[:300], agent=bus.DESIGNER)
        bus.sync_state(project, "failed", str(exc)[:300], source="wireframe", error=str(exc)[:300])
        raise


def edit(project: str, prompt: str, route: str = "", element: str = "") -> dict[str, Any]:
    """One change to the wireframe, asked for in words (and, when it was picked in the preview, about one element)."""
    request = " ".join(str(prompt or "").split())
    if not request:
        raise ValueError("describe the wireframe change first")
    if len(request) > MAX_REQUEST:
        raise ValueError(f"keep the wireframe request under {MAX_REQUEST:,} characters")
    if not (web_app.app_dir(project, KIND) / "index.html").is_file():
        raise FileNotFoundError("there is no wireframe to change yet")

    session = session_for(project)
    if session.stage in ("srs", "wireframes"):
        raise ValueError("wait for the wireframe run to finish")
    session.begin("wireframe-edit", role=bus.DESIGNER)
    try:
        bus.user_msg(project, request, agent=bus.DESIGNER)
        skill = web_app.stage_skill(project)
        session.run_direct(prompts.load(
            "wireframe/edit", request=request, skill=skill,
            app=web_app.app_dir(project, KIND).relative_to(session.workspace).as_posix(),
            where=(f"The change is on the page for `{route}`." if route else ""),
            element=(f"The element picked in the preview:\n\n{element[:2000]}" if element else "")))
        web_app.ensure_built(session, project, KIND, agent=bus.DESIGNER)
        bus.wireframe_changed(project)
        session.finish("Wireframe updated.")
        return {"ok": True, "route": route}
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
