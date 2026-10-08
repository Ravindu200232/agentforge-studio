"""The wireframes: a low-fidelity React app the project's agent builds with Anthropic's web-artifacts-builder skill.

The agent reads the skill and `app.md` (what the customer asked for, and the site map) and writes one page per screen with its own file
tools, so every file it writes appears in the chat as it happens. Code here is only what it cannot do for itself: create the app
(the skill's first step), say which screens the specification names, and bundle the finished app into the one page the studio shows
(the skill's last step). What the pages look like, and how they hang together, is the agent's.

    <workspace>/.agentforge/wireframe/app/     the app: `src/pages/<page>.tsx` for every screen, and `bundle.html`
"""
from __future__ import annotations

from typing import Any

from server_modules import bus, prompts, web_app
from server_modules.session import RunCancelled, session_for

from . import document

KIND = "wireframe"
MAX_REQUEST = 4000
# What starting the wireframes asks for: the first line of `prompts/wireframe/generate.md`. The studio sends the same words.
APPROVAL_PROMPT = "Generate low-fidelity wireframes."


def app_path(project: str):
    return web_app.app_dir(session_for(project).workspace, KIND)


def built(project: str) -> bool:
    return web_app.built(app_path(project))


def _relative(project: str) -> str:
    return app_path(project).relative_to(session_for(project).workspace).as_posix()


def routes_text(rows: list[dict[str, Any]]) -> str:
    """One line for every screen: the route, its name, who may open it and the page file it is written to."""
    lines = []
    for row in rows:
        who = ", ".join(row.get("roles") or []) if row.get("signedIn") else ""
        lines.append(f"- `{row['route']}` — {row['name']}" + (f" (signed in: {who or 'any role'})" if row.get("signedIn") else "")
                     + f" — `src/pages/{row['file']}.tsx`")
    return "\n".join(lines)


def _remember(session, **state: Any) -> None:
    """What the studio shows when there is no wireframe: the last error, if there was one."""
    try:
        session.write_record(KIND, "state.json", data=state)
    except RunCancelled:
        raise
    except OSError:
        pass


def generate(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """Make the wireframe app from the approved specification and leave its bundle ready to show.

    `fresh` starts the app again; without it, an app a stopped run left behind is carried on."""
    session = session_for(project)
    pages = document.screens(project)
    if not pages:
        raise ValueError("the specification names no screens to draw")
    if not (session.record / document.SRS_DIR / "handoff" / "app.md").is_file():
        raise ValueError("the SRS handoff is missing; the wireframes are drawn from its app.md")

    if not web_app.kit_ready():
        bus.agent_msg(project, "Getting the toolkit the wireframes are built with ready (React, Tailwind and shadcn/ui). "
                               "This happens once and can take a few minutes.", title="Wireframe toolkit", kind="narration",
                      agent=bus.DESIGNER)
    ready, why = web_app.prepare_kit()
    if not ready:
        raise RuntimeError("the toolkit the wireframes are built with could not be installed: " + why[-300:])

    app = app_path(project)
    carrying_on = not fresh and (app / "index.html").is_file()
    if not carrying_on:
        web_app.remove_app(app)
    title = str((document.document(project).get("srs_document", {}).get("app_summary") or {}).get("app_name") or project)
    rows = web_app.create_app(app, title, pages)
    skill = web_app.stage_skill(session.workspace)

    bus.phase(project, "wireframes", "Drawing the wireframes", detail=f"{len(rows)} page(s) from the approved specification.",
              agent=bus.DESIGNER)
    resume = (f"The app already has pages from a run that stopped: read what is in `{_relative(project)}/src/pages`, keep it, "
              "and write the pages that are still missing." if carrying_on else "")
    result = session.run_task(
        prompts.load("wireframe/generate", request=request or APPROVAL_PROMPT, skill=skill, app=_relative(project),
                     routes=routes_text(rows), resume=resume),
        audit=False, parallel_write_limit=4)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") not in (None, "complete") and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)

    web_app.build_for(session, project, KIND, agent=bus.DESIGNER)
    _remember(session, error="")
    bus.phase(project, "wireframes", "Drawing the wireframes", status="complete", agent=bus.DESIGNER)
    bus.wireframe_changed(project)
    return result


def run(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """A whole wireframe run: the session, the progress the studio shows, and what it says when it ends."""
    session = session_for(project)
    session.begin("wireframes", role=bus.DESIGNER)
    bus.sync_state(project, "running", "Drawing the wireframes", source="wireframe")
    try:
        generate(project, request, fresh=fresh)
        pages = document.wireframes(project)["pages"]
        ready = sum(bool(row["has_html"]) for row in pages)
        session.finish(f"The wireframes are ready: {ready} of {len(pages)} page(s).")
        bus.agent_msg(project, f"The wireframes are ready: {ready} of {len(pages)} page(s) in the Wireframe tab. Click through "
                               "them, and ask for any change.", title="Wireframes ready", agent=bus.DESIGNER)
        bus.sync_state(project, "clean", "Wireframes ready", source="wireframe")
        return {"ok": True, "project": project, "ready": ready, "total": len(pages)}
    except RunCancelled:
        session.stage = "idle"
        session.save_context()
        bus.phase(project, "wireframes", "Drawing the wireframes", status="paused", agent=bus.DESIGNER)
        bus.sync_state(project, "paused", "Wireframe generation stopped.", source="wireframe")
        raise
    except Exception as exc:  # noqa: BLE001
        _remember(session, error=str(exc)[:300])
        session.fail(str(exc))
        bus.phase(project, "wireframes", "Drawing the wireframes", status="failed", detail=str(exc)[:300], agent=bus.DESIGNER)
        bus.sync_state(project, "failed", str(exc)[:300], source="wireframe", error=str(exc)[:300])
        raise


def edit(project: str, prompt: str, route: str = "") -> dict[str, Any]:
    """One change to the wireframes, asked for in words (and about one page, when it was asked for from that page)."""
    request = " ".join(str(prompt or "").split())
    if not request:
        raise ValueError("describe the wireframe change first")
    if len(request) > MAX_REQUEST:
        raise ValueError(f"keep the wireframe request under {MAX_REQUEST:,} characters")
    if not (app_path(project) / "index.html").is_file():
        raise FileNotFoundError("there are no wireframes to change yet")
    session = session_for(project)
    if session.stage in ("srs", "wireframes"):
        raise ValueError("wait for the wireframe run to finish")
    session.begin("wireframe-edit", role=bus.DESIGNER)
    try:
        bus.user_msg(project, request, agent=bus.DESIGNER)
        session.run_direct(prompts.load("wireframe/edit", request=request, skill=web_app.stage_skill(session.workspace),
                                        app=_relative(project),
                                        where=(f"The change is on the page for `{route}`." if route else "")))
        web_app.build_for(session, project, KIND, agent=bus.DESIGNER)
        bus.wireframe_changed(project)
        session.finish("Wireframes updated.")
        return {"ok": True, "route": route}
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
