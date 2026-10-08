"""The prototype: the approved wireframe app, copied and edited into a high-fidelity, animated React app.

The wireframe stays exactly as it was approved, so the customer can still look at it. When this stage starts it copies
the wireframe app to `.agentforge/prototype/app`, and the project's agent edits that copy with its own file tools
(`replace_text`, `write_file`), applying the design the customer chose. Code here only copies, stages the skill, says what
the design and the screens are, and leaves a built `bundle.html` for the preview; how the pages look and behave is the
agent's.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from server_modules import bus, config, prompts, store, web_app
from server_modules.session import ProjectSession, RunCancelled, session_for

from . import design as design_stage
from . import journey_walk
from . import visual_review

PROTOTYPE_DIR = "prototype"
ROUTES = (PROTOTYPE_DIR, "routes.json")
KIND = "prototype"
# What starting the prototype asks for. The same words are the first line of `prompts/prototype/generate.md`
# and `studio/app/page.jsx` sends the identical sentence.
APPROVAL_PROMPT = "Generate a high-fidelity, animated prototype."


class PrototypeIncomplete(RuntimeError):
    """The agent stopped with a resumable, high-fidelity prototype checkpoint."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("prototype generation is incomplete: " + ", ".join(missing))


def _read_record(session: Any, *parts: str, fallback=None):
    """Read optional session state without requiring it from focused callers.

    Production sessions persist incremental prototype state. Older focused
    callers may only provide a workspace and use the same drawing code for a
    one-shot render, where an absent checkpoint is simply a fresh run.
    """
    reader = getattr(session, "read_record", None)
    return reader(*parts, fallback=fallback) if callable(reader) else fallback


def _uploaded_site_images(session: ProjectSession, app: Path) -> list[dict[str, str]]:
    """Put the customer's images inside the app (`src/assets/uploads`) and leave the originals in `media/`."""
    uploaded = []
    if not hasattr(session, "workspace"):
        return uploaded
    media = (session.workspace / "media").resolve()
    if not media.is_relative_to(session.workspace.resolve()):
        return uploaded
    for image in _read_record(session, "images.json", fallback=[]) or []:
        relative = str(image.get("path") or "")
        source = (session.workspace / relative).resolve()
        if not relative.startswith("media/") or not source.is_relative_to(media) or not source.is_file():
            continue
        target = app / "src" / "assets" / "uploads" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        uploaded.append({"name": source.name, "usage": image.get("purpose") or "",
                         "source": relative, "file": f"src/assets/uploads/{source.name}"})
    return uploaded


def routes(project: str) -> list[dict[str, Any]]:
    saved = session_for(project).read_record(*ROUTES, fallback=None)
    return (saved or {}).get("routes") or []


def exists(project: str) -> bool:
    session = session_for(project)
    checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    # While the agent works, the app is not build-ready: it is only the finished, built prototype that is. Projects
    # created before checkpoints remain compatible.
    if checkpoint and not checkpoint.get("complete"):
        return False
    return bool(routes(project))


def _draw_with_agent(project: str, spec: dict[str, Any], direction: str) -> list[dict]:
    """Copy the approved wireframe app, then let the project's agent edit the copy into the prototype.

    Only what is the same for every prototype is code: the copy, the skill, the route map the build reads. The edits are the
    agent's, made with its own file tools, so every read and every file appears in the chat stream as it happens."""
    from srs_agent import document as srs_document
    from srs_agent import handoff as handoff_files
    from srs_agent import wireframe as wireframe_stage

    session = session_for(project)
    doc = srs_document.document(project).get("srs_document", {})
    pages = srs_document.screens(project)
    if not pages:
        raise ValueError("the specification names no screens to prototype")

    wire = web_app.app_dir(project, "wireframe")
    app = web_app.app_dir(project, KIND)
    app_rel = app.relative_to(session.workspace).as_posix()
    wire_rel = wire.relative_to(session.workspace).as_posix()
    root = session.record / PROTOTYPE_DIR
    root.mkdir(parents=True, exist_ok=True)
    record = f"{config.RECORD_DIR}/{PROTOTYPE_DIR}"

    # The route map the build reads: one row per screen, pointing at the app's route table.
    routes_out = [{"route": p["route"], "file": "app/src/App.tsx", "name": p.get("page_name") or p["route"],
                   "roles": p.get("allowed_roles") or [], "signed_in": bool(p.get("login_required"))} for p in pages]

    def write(name: str, body: str, note: str = "written") -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        bus.file_written(project, f"{record}/{name}", body, note=note, agent=bus.DESIGNER)

    # What the agent is told to read: the approved application and the approved design, read where earlier stages wrote them.
    handoff_app_md = session.record / srs_document.SRS_DIR / "handoff" / "app.md"
    app_md_path = f"{config.RECORD_DIR}/{srs_document.SRS_DIR}/handoff/app.md"
    if not handoff_app_md.is_file():
        app_md_path = f"{record}/input/app.md"
        write("input/app.md", handoff_files.app_md(doc))
    spec_path = f"{config.RECORD_DIR}/design/design-spec.json"
    if not (session.record / "design" / "design-spec.json").is_file():
        spec_path = f"{record}/input/design-spec.json"
        write("input/design-spec.json", json.dumps(spec, ensure_ascii=False, indent=2))
    customization = dict(design_stage.approved_customization(project) or {})
    inputs = [f"- `{app_md_path}` — app.md: what the customer asked for, in their own words, and the site map",
              f"- `{spec_path}` — the approved design tokens"]
    if customization.get("design_md_workspace_path"):
        inputs.append(f"- `{customization['design_md_workspace_path']}` — the selected theme's guidance "
                      f"({customization.get('design_md_path') or 'DESIGN.md'})")

    checkpoint_path = root / "generation.json"
    checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    # Resume is invoked without the original button prompt. Keep the exact
    # direction that owned the interrupted checkpoint so the fingerprint does
    # not change merely because the customer pressed Continue.
    effective_direction = direction.strip()
    if not effective_direction and checkpoint and not checkpoint.get("complete"):
        effective_direction = str(checkpoint.get("direction") or "").strip()
    headline = effective_direction if effective_direction.startswith(APPROVAL_PROMPT) \
        else "\n\n".join(part for part in (APPROVAL_PROMPT, effective_direction) if part)
    design_direction = ("### The customer's design direction (from Design Customize)\n\n"
                        + str(customization["customizer_prompt"]).strip()) if customization.get("customizer_prompt") else ""

    fingerprint = hashlib.sha256(json.dumps(
        {"routes": routes_out, "design": spec, "customization": customization,
         "wireframe": web_app.fingerprint(wire), "app_md": (session.workspace / app_md_path).read_text(encoding="utf-8"),
         "direction": effective_direction},
        ensure_ascii=False, sort_keys=True, default=str,
    ).encode("utf-8")).hexdigest()
    resuming = (checkpoint.get("fingerprint") == fingerprint and not checkpoint.get("complete")
                and (app / "index.html").is_file())
    if not resuming:
        # A changed design, route map or wireframe owns a fresh copy. A matching interrupted run keeps the pages it finished.
        web_app.copy_app(wire, app)
        (root / "routes.json").unlink(missing_ok=True)
    started_from = web_app.fingerprint(app)
    checkpoint_state = {"fingerprint": fingerprint, "complete": False,
                        "draw_complete": bool(resuming and checkpoint.get("draw_complete")),
                        "direction": effective_direction}
    checkpoint_path.write_text(json.dumps(checkpoint_state, ensure_ascii=False, indent=2), encoding="utf-8")

    def publish() -> None:
        write("routes.json", json.dumps({"routes": routes_out}, ensure_ascii=False, indent=2))

    # A stopped visual/journey review already has the finished, built app: carry on from there without editing it again.
    if resuming and checkpoint_state["draw_complete"] and web_app.built(project, KIND) and not web_app.stale(project, KIND):
        publish()
        return routes_out

    if not web_app.runtime_ready():
        bus.agent_msg(project, "Getting the UI toolkit ready. This happens once and can take a few minutes.",
                      title="Prototype toolkit", kind="narration", agent=bus.DESIGNER)
    ready, why = web_app.prepare_runtime()
    if not ready:
        raise RuntimeError("the UI toolkit could not be installed: " + why[-300:])
    skill = web_app.stage_skill(project)
    uploaded_images = _uploaded_site_images(session, app)

    resume = ""
    if resuming:
        resume = ("## Resuming an interrupted run\n\nThe app already has the edits an earlier run made: read it, keep what "
                  "is finished, and carry on with the pages that are still low fidelity.")
    request = prompts.load(
        "prototype/generate", request=headline, skill=skill, app=app_rel, wireframe=wire_rel,
        inputs="\n".join(inputs), design_direction=design_direction,
        routes=wireframe_stage.routes_text(pages), journeys=wireframe_stage.journeys_text(doc),
        uploads=(json.dumps(uploaded_images, ensure_ascii=False, indent=2) if uploaded_images
                 else "None — use fitting real photos, or draw the illustration in code."),
        resume=resume)

    result = session.run_task(request, audit=False, parallel_write_limit=4)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("plan"):
        (root / "plan.md").write_text(result["plan"], encoding="utf-8")
    if result.get("status") != "complete" and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)

    # An app the agent never touched is still the wireframe: stay resumable rather than hand it over as the prototype.
    if web_app.fingerprint(app) == started_from:
        checkpoint_state["draw_complete"] = False
        checkpoint_path.write_text(json.dumps(checkpoint_state, ensure_ascii=False, indent=2), encoding="utf-8")
        raise PrototypeIncomplete(["the agent did not change the wireframe app"])
    web_app.ensure_built(session, project, KIND, agent=bus.DESIGNER)
    publish()
    checkpoint_state["draw_complete"] = True
    checkpoint_path.write_text(json.dumps(checkpoint_state, ensure_ascii=False, indent=2), encoding="utf-8")
    return routes_out


def generate(project: str, direction: str = "") -> dict[str, Any]:
    """Make the prototype from the specification and the approved design."""
    return _generate(project, direction)


def generate_from_wireframes(project: str, direction: str = "") -> dict[str, Any]:
    """Make the prototype from the approved wireframe app."""
    return _generate(project, direction, from_wireframes=True)


def _generate(project: str, direction: str,
              *, from_wireframes: bool = False) -> dict[str, Any]:
    from srs_agent import document as srs_document
    from srs_agent import wireframe as wireframe_stage

    if not srs_document.has_document(project):
        raise ValueError("write the specification before drawing the prototype")

    session = session_for(project)
    if from_wireframes:
        if not design_stage.current(project).get("approved"):
            raise ValueError("approve the selected design in Design Customize first")
        if not srs_document.screens(project):
            raise ValueError("approve the SRS before generating the prototype")
    try:
        # A partially written or newly regenerated prototype must never enable
        # a production build. Completion below is the only place that turns
        # this on. An explicit direction owns a fresh checkpoint even if Stop
        # arrives before the worker reaches ProjectSession.begin().
        store.update(project, build_available=False, status="prototype-generating")
        if direction.strip() and isinstance(getattr(session, "record", None), Path):
            pending = session.record / PROTOTYPE_DIR / "generation.json"
            pending.parent.mkdir(parents=True, exist_ok=True)
            (pending.parent / "routes.json").unlink(missing_ok=True)
            pending.write_text(json.dumps({"complete": False, "draw_complete": False,
                                           "direction": direction.strip()},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
        session.begin("prototype", role=bus.DESIGNER)
        if from_wireframes:
            bus.sync_state(project, "running", "Making the prototype from the wireframe",
                           source="prototype")
        spec = design_stage.approved_spec(project)
        if not spec:
            design_stage.draft(project, direction=direction)
            design_stage.approve(project)
            spec = design_stage.approved_spec(project)
        # The prototype is always the wireframe, edited: when there is none yet it is built first.
        if not web_app.built(project, "wireframe"):
            bus.agent_msg(project, "There is no wireframe app to start from yet, so it is built first.",
                          title="Wireframe first", kind="narration", agent=bus.DESIGNER)
            wireframe_stage.generate(project)
        bus.phase(project, "prototype:draw", "Making the prototype",
                  detail="The wireframe app, copied and edited with the approved design.")
        bus.agent_msg(project, "Copying the approved wireframe and editing the copy into a high-fidelity, animated prototype "
                               "with the design from Design Customize. The wireframe itself stays as it was.",
                      title="Prototype generation", kind="narration", agent=bus.DESIGNER)
        _draw_with_agent(project, spec, direction)
        bus.phase(project, "prototype:draw", "Making the prototype", status="complete")
        if session.cancelled:
            raise RunCancelled(project)

        drawn = routes(project)
        if not drawn:
            raise ValueError("the prototype wrote no routes.json, so no screen is reviewable")

        # Every screen is photographed silently and looked at by the model, when it can look at pictures (a model that
        # cannot skips this, with a line in the chat saying so); what it finds is fixed before the prototype is handed over.
        visual_review.run(project, session, drawn)
        if session.cancelled:
            raise RunCancelled(project)
        drawn = routes(project) or drawn
        # Then the journeys are clicked through in a real browser, shown live like a build's end-to-end tests, with a picture
        # at every step; what cannot be done by clicking, or looks wrong, is fixed (see journey_walk.py).
        journey_walk.run(project, session, drawn)
        if session.cancelled:
            raise RunCancelled(project)
        drawn = routes(project) or drawn

        checkpoint_path = session.record / PROTOTYPE_DIR / "generation.json"
        checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
        checkpoint.update({"draw_complete": True, "complete": True})
        checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")

        previous = store.require(project)
        if not previous.get("build_available"):
            store.update(project, prototype_only=True, status="prototyped",
                         build_available=True)
        else:
            # Keep the persisted capability in sync with the completed
            # prototype, so the Build App action remains enabled after reload.
            store.update(project, build_available=True)
        store.advance(project, "prototype")
        bus.prototype_changed(project)
        bus.agent_msg(project, f"The prototype is ready: {len(drawn)} screen"
                               f"{'s' if len(drawn) != 1 else ''} you can click through.",
                      title="Prototype ready", agent=bus.DESIGNER)
        session.note(
            f"The prototype is built: a React app with {len(drawn)} screens under "
            f".agentforge/prototype/app, edited from the approved wireframe (which is unchanged in "
            f".agentforge/wireframe/app) and linked so the journeys can be clicked "
            f"through. This is what the customer approved the product on, and "
            f"the build must match it. Routes: "
            + ", ".join(str(r.get("route")) for r in drawn))
        session.finish(f"Prototype made: {len(drawn)} screens.")
        if from_wireframes:
            bus.sync_state(project, "clean", "Prototype ready", source="prototype")
        return {"routes": drawn, "complete": True}
    except PrototypeIncomplete as exc:
        bus.phase(project, "prototype:draw", "Making the prototype", status="paused",
                  detail="Waiting to generate: " + ", ".join(exc.missing))
        store.update(project, build_available=False, status="prototype-incomplete")
        session.stage = "idle"
        session.save_context()
        if from_wireframes:
            bus.sync_state(project, "paused", "Prototype generation is incomplete and ready to continue.",
                           source="prototype")
        bus.cancelled(project, "Prototype paused with the edits so far preserved.", agent=bus.DESIGNER)
        return {"routes": routes(project), "complete": False, "remaining": exc.missing}
    except RunCancelled:
        bus.phase(project, "prototype:draw", "Making the prototype", status="paused")
        store.update(project, build_available=False, status="prototype-incomplete")
        session.stage = "idle"
        session.save_context()
        if from_wireframes:
            bus.sync_state(project, "paused", "Prototype generation stopped.", source="prototype")
        raise
    except Exception as exc:  # noqa: BLE001
        bus.phase(project, "prototype:draw", "Making the prototype", status="failed", detail=str(exc)[:300])
        store.update(project, build_available=False, status="prototype-incomplete")
        session.fail(str(exc))
        if from_wireframes:
            bus.sync_state(project, "failed", str(exc)[:300], source="prototype",
                           error=str(exc)[:300])
        raise


def review(project: str, fix: bool = True, model: str = "") -> dict[str, Any]:
    """Look at every screen of the prototype that is already made, with a model that can look at pictures, and fix what it
    finds (`fix`: false only looks and reports)."""
    if not exists(project):
        raise ValueError("there is no prototype to look at yet")
    session = session_for(project)
    result = visual_review.run(project, session, routes(project), fix=fix, model=model, force=True)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") == "done" and fix:
        bus.prototype_changed(project)          # the app may have changed: the preview loads the new build
    return result


def journeys(project: str, fix: bool = True, model: str = "") -> dict[str, Any]:
    """Click through the journeys of the prototype that is already made, in a real browser, shown live, with a picture at every
    step, and fix what cannot be done or looks wrong (`fix`: false only walks and reports)."""
    if not exists(project):
        raise ValueError("there is no prototype to click through yet")
    session = session_for(project)
    result = journey_walk.run(project, session, routes(project), fix=fix, model=model, force=True)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") == "done" and fix and result.get("fixed_journeys"):
        bus.prototype_changed(project)          # the app may have changed: the preview loads the new build
    return result


def revise(project: str, request: str) -> dict[str, Any]:
    """Change the prototype from a message typed into the chat stream."""
    if not exists(project):
        raise ValueError("there is no prototype to change yet")

    session = session_for(project)
    session.begin("prototype-edit", role=bus.DESIGNER)
    try:
        bus.user_msg(project, request, agent=bus.DESIGNER)
        skill = web_app.stage_skill(project)
        session.run_direct(prompts.load(
            "prototype/revise", request=request, skill=skill,
            app=web_app.app_dir(project, KIND).relative_to(session.workspace).as_posix()))
        web_app.ensure_built(session, project, KIND, agent=bus.DESIGNER)
        bus.prototype_changed(project)
        session.finish("Prototype updated.")
        return {"routes": routes(project)}
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
