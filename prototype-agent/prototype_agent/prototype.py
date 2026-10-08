"""The prototype: a new high-fidelity React app, made by reading the approved wireframes.

The wireframes stay exactly as they were approved, so the customer can still look at them. When this stage starts it sets up a new app in
`.agentforge/prototype/app` (the skill's first step), and the project's agent reads Anthropic's web-artifacts-builder skill, the wireframes,
`app.md` and the approved design, plans the prototype, and writes it with its own file tools. Code here only sets the app up, says which
screens and which design there are, bundles the finished app into the one page the studio shows, and leaves what the build reads:
`routes.json` and, when the product has sign-in, `demo-accounts.json`. How the pages look and behave is the agent's.

When the app is bundled it is looked at: every screen is photographed and a model that can look at pictures says what is visibly wrong
(`visual_review.py`), and every journey of the specification is clicked through in a real browser, shown live (`journey_walk.py`).
What they find is given back to the agent to fix, and the app is bundled and looked at again.

    <workspace>/.agentforge/prototype/app/              the prototype: `src/pages/<page>.tsx` for every screen, and `bundle.html`
    <workspace>/.agentforge/prototype/routes.json       every screen and the page file it is drawn in
    <workspace>/.agentforge/prototype/demo-accounts.json  the fictitious sign-in accounts, which the build seeds
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from server_modules import bus, config, prompts, store, web_app
from server_modules.session import ProjectSession, RunCancelled, session_for

from . import demo, journey_walk, visual_review
from . import design as design_stage

PROTOTYPE_DIR = "prototype"
ROUTES = (PROTOTYPE_DIR, "routes.json")
KIND = "prototype"
# What starting the prototype asks for: the first line of `prompts/prototype/generate.md`. The studio sends the same words.
APPROVAL_PROMPT = "Generate a high-fidelity, animated prototype."


class PrototypeIncomplete(RuntimeError):
    """The agent stopped before it had changed the wireframe into a prototype; the run can be carried on."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__("prototype generation is incomplete: " + ", ".join(missing))


def _read_record(session: Any, *parts: str, fallback=None):
    """Read optional session state without requiring it from focused callers."""
    reader = getattr(session, "read_record", None)
    return reader(*parts, fallback=fallback) if callable(reader) else fallback


def _uploaded_site_images(session: ProjectSession, app: Path) -> list[dict[str, str]]:
    """Put the customer's images inside the app (`src/assets/uploads`), where the bundle can inline them; the originals stay in `media/`."""
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
        uploaded.append({"name": source.name, "usage": image.get("purpose") or "", "source": relative,
                         "file": f"src/assets/uploads/{source.name}"})
    return uploaded


def routes(project: str) -> list[dict[str, Any]]:
    saved = session_for(project).read_record(*ROUTES, fallback=None)
    return (saved or {}).get("routes") or []


def exists(project: str) -> bool:
    session = session_for(project)
    checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    # While the agent works, the app is not build-ready: only the finished, bundled prototype is. Projects created before
    # checkpoints remain compatible.
    if checkpoint and not checkpoint.get("complete"):
        return False
    return bool(routes(project))


def app_path(project: str) -> Path:
    return web_app.app_dir(session_for(project).workspace, KIND)


def _sign_in_text(accounts: list[dict], sign_in: str, rows: list[dict]) -> str:
    """What the agent is told about signing in: the accounts are in the app already, and so is the session that uses them."""
    if not sign_in or not accounts:
        return ""
    page = next((r for r in rows if r["route"] == sign_in), {"name": sign_in})
    lines = [f"The product has sign-in, and the app already has it working underneath: `src/demo.ts` holds one fictitious account for each "
             "role (the finished application is seeded with the same ones) and `useSession()` from `@/lib/session` signs them in. "
             f"Make the sign-in page, **{page['name']}** (`{sign_in}`), a real one:", "",
             "- a form that calls `signIn(email, password)`, with its error shown under it when it returns null;",
             "- a clearly labelled demo panel with one button for each account in `accounts` that calls `signInAs(roleKey)`;",
             "- after signing in, people land on their own first page (the session opens it); `signOut()` is the Sign out;",
             "- the signed-in navigation and account menu show `user.name` and show only what `user.canOpen` allows; "
             "the signed-out navigation shows Sign in."]
    return "\n".join(lines)


def _draw_with_agent(project: str, spec: dict[str, Any], direction: str) -> list[dict]:
    """Set up a new app, then let the project's agent read the wireframes, plan, and write the prototype into it.

    Only what is the same for every prototype is code: the new app, the skill, the route map and the demo accounts. The pages are the
    agent's, written with its own file tools, so every read and every file appears in the chat stream as it happens."""
    from srs_agent import document as srs_document
    from srs_agent import handoff as handoff_files
    from srs_agent import wireframe as wireframe_stage

    session = session_for(project)
    doc = srs_document.document(project).get("srs_document", {})
    pages = srs_document.screens(project)
    if not pages:
        raise ValueError("the specification names no screens to prototype")

    wire = wireframe_stage.app_path(project)
    app = app_path(project)
    app_rel = app.relative_to(session.workspace).as_posix()
    wire_rel = wire.relative_to(session.workspace).as_posix()
    root = session.record / PROTOTYPE_DIR
    root.mkdir(parents=True, exist_ok=True)
    record = f"{config.RECORD_DIR}/{PROTOTYPE_DIR}"

    files = web_app.page_files([str(p["route"]) for p in pages])
    routes_out = [{"route": p["route"], "file": f"app/src/pages/{files[str(p['route'])]}.tsx",
                   "name": p.get("page_name") or p["route"], "roles": p.get("allowed_roles") or [],
                   "signed_in": demo.signed_in_page(p)} for p in pages]
    sign_in = demo.sign_in_route(doc)
    accounts = demo.draw_accounts(doc)
    sign_up = demo.sign_up_of(doc, routes_out, accounts)

    def write(name: str, body: str, note: str = "written") -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        bus.file_written(project, f"{record}/{name}", body, note=note, agent=bus.DESIGNER)

    # What the agent is told to read: the approved application and the approved design, where earlier stages wrote them.
    app_md = session.record / srs_document.SRS_DIR / "handoff" / "app.md"
    app_md_path = f"{config.RECORD_DIR}/{srs_document.SRS_DIR}/handoff/app.md"
    if not app_md.is_file():
        app_md_path = f"{record}/input/app.md"
        write("input/app.md", handoff_files.app_md(doc))
    spec_path = f"{config.RECORD_DIR}/design/design-spec.json"
    if not (session.record / "design" / "design-spec.json").is_file():
        spec_path = f"{record}/input/design-spec.json"
        write("input/design-spec.json", json.dumps(spec, ensure_ascii=False, indent=2))
    customization = dict(design_stage.approved_customization(project) or {})
    inputs = [f"- `{app_md_path}` — app.md: what the customer asked for, in their own words, and the site map",
              f"- `{spec_path}` — the approved design: colours, type, space, shape and motion (put them in `src/index.css` and "
              "the Tailwind theme, and use them everywhere)"]
    if (session.record / srs_document.SRS_DIR / "user-journeys.json").is_file():
        inputs.insert(1, f"- `{config.RECORD_DIR}/{srs_document.SRS_DIR}/user-journeys.json` — the journeys: who does what, step by step, "
                         "on which screen; every one has to be possible to click through")
    if customization.get("design_md_workspace_path"):
        inputs.append(f"- `{customization['design_md_workspace_path']}` — the selected theme's guidance "
                      f"({customization.get('design_md_path') or 'DESIGN.md'})")

    checkpoint_path = root / "generation.json"
    checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    # Resume is invoked without the original button prompt. Keep the exact direction that owned the interrupted checkpoint so the
    # fingerprint does not change merely because the customer pressed Continue.
    effective_direction = direction.strip()
    if not effective_direction and checkpoint and not checkpoint.get("complete"):
        effective_direction = str(checkpoint.get("direction") or "").strip()
    headline = effective_direction if effective_direction.startswith(APPROVAL_PROMPT) \
        else "\n\n".join(part for part in (APPROVAL_PROMPT, effective_direction) if part)
    design_direction = ("### The customer's design direction (from Design Customize)\n\n"
                        + str(customization["customizer_prompt"]).strip()) if customization.get("customizer_prompt") else ""

    fingerprint = hashlib.sha256(json.dumps(
        {"routes": routes_out, "design": spec, "customization": customization, "wireframe": web_app.fingerprint(wire),
         "app_md": (session.workspace / app_md_path).read_text(encoding="utf-8"), "direction": effective_direction},
        ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    resuming = (checkpoint.get("fingerprint") == fingerprint and not checkpoint.get("complete")
                and (app / "index.html").is_file())
    if not resuming:
        # A changed design, route map or wireframe owns a new app. A matching interrupted run keeps the pages it wrote.
        web_app.remove_app(app)
        (root / "routes.json").unlink(missing_ok=True)
    web_app.create_app(app, str((doc.get("app_summary") or {}).get("app_name") or project), pages,
                       accounts=accounts, sign_in=sign_in, sign_up=sign_up)
    state = {"fingerprint": fingerprint, "complete": False, "direction": effective_direction}
    checkpoint_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    uploaded = _uploaded_site_images(session, app)
    skill = web_app.stage_skill(session.workspace)
    resume = ("## Resuming an interrupted run\n\nThe app already has the pages an earlier run wrote: read them, keep what is "
              "finished, and write only the pages that are still missing." if resuming else "")
    request = prompts.load(
        "prototype/generate", request=headline, skill=skill, app=app_rel, wireframe=wire_rel, inputs="\n".join(inputs),
        design_direction=design_direction,
        routes=wireframe_stage.routes_text([{"route": r["route"], "name": r["name"], "file": files[str(r["route"])],
                                             "roles": r["roles"], "signedIn": r["signed_in"]} for r in routes_out]),
        sign_in=_sign_in_text(accounts, sign_in, routes_out),
        uploads=(json.dumps(uploaded, ensure_ascii=False, indent=2) if uploaded
                 else "None — use fitting real photographs by their address, or draw the picture in code."),
        resume=resume)

    result = session.run_task(request, audit=False, parallel_write_limit=4)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("plan"):
        (root / "plan.md").write_text(result["plan"], encoding="utf-8")
    if result.get("status") != "complete" and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)

    # A screen with no page is not a prototype of it: stay resumable, with the pages that were written, rather than hand it over.
    written = app / "src" / "pages"
    missing = [str(r["route"]) for r in routes_out
               if not any((written / f"{files[str(r['route'])]}{ext}").is_file() for ext in (".tsx", ".jsx"))]
    if missing:
        raise PrototypeIncomplete(missing)
    web_app.build_for(session, project, KIND, agent=bus.DESIGNER)

    write("routes.json", json.dumps({"routes": routes_out}, ensure_ascii=False, indent=2))
    write("demo-accounts.json", json.dumps({"sign_in": sign_in, "accounts": accounts}, ensure_ascii=False, indent=2))
    return routes_out


def generate(project: str, direction: str = "") -> dict[str, Any]:
    """Make the prototype from the specification and the approved design."""
    return _generate(project, direction)


def generate_from_wireframes(project: str, direction: str = "") -> dict[str, Any]:
    """Make the prototype from the approved wireframe app."""
    return _generate(project, direction, from_wireframes=True)


def _generate(project: str, direction: str, *, from_wireframes: bool = False) -> dict[str, Any]:
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
        # A partially written or newly regenerated prototype must never enable a production build. Completion below is the only
        # place that turns this on. An explicit direction owns a fresh checkpoint even if Stop arrives before the worker reaches
        # ProjectSession.begin().
        store.update(project, build_available=False, status="prototype-generating")
        if direction.strip() and isinstance(getattr(session, "record", None), Path):
            pending = session.record / PROTOTYPE_DIR / "generation.json"
            pending.parent.mkdir(parents=True, exist_ok=True)
            (pending.parent / "routes.json").unlink(missing_ok=True)
            pending.write_text(json.dumps({"complete": False, "direction": direction.strip()}, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        session.begin("prototype", role=bus.DESIGNER)
        if from_wireframes:
            bus.sync_state(project, "running", "Making the prototype from the wireframes", source="prototype")
        spec = design_stage.approved_spec(project)
        if not spec:
            design_stage.draft(project, direction=direction)
            design_stage.approve(project)
            spec = design_stage.approved_spec(project)
        # The prototype is made from the wireframes: when they are not drawn yet they are drawn first.
        if not wireframe_stage.built(project):
            bus.agent_msg(project, "There are no wireframes to start from yet, so they are drawn first.", title="Wireframes first",
                          kind="narration", agent=bus.DESIGNER)
            wireframe_stage.generate(project)
        bus.phase(project, "prototype:draw", "Making the prototype", detail="Reading the wireframes, planning, then writing the prototype.")
        bus.agent_msg(project, "Reading the approved wireframes, planning, and writing a high-fidelity, animated prototype with "
                               "the design from Design Customize. The wireframes themselves stay as they were.",
                      title="Prototype generation", kind="narration", agent=bus.DESIGNER)
        drawn = _draw_with_agent(project, spec, direction)
        bus.phase(project, "prototype:draw", "Making the prototype", status="complete")
        if session.cancelled:
            raise RunCancelled(project)
        drawn = _look_at(project, session, drawn)

        checkpoint_path = session.record / PROTOTYPE_DIR / "generation.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
        checkpoint.update({"complete": True})
        checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")

        previous = store.require(project)
        if not previous.get("build_available"):
            store.update(project, prototype_only=True, status="prototyped", build_available=True)
        else:
            # Keep the persisted capability in sync with the completed prototype, so the Build App action stays enabled after reload.
            store.update(project, build_available=True)
        store.advance(project, "prototype")
        bus.prototype_changed(project)
        bus.agent_msg(project, f"The prototype is ready: {len(drawn)} screen{'s' if len(drawn) != 1 else ''} you can click through.",
                      title="Prototype ready", agent=bus.DESIGNER)
        # The demo accounts and what each role can open, at the end, in the chat: this is how the customer enters as each role.
        saved = _read_record(session, PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}
        accounts_text = demo.accounts_message(saved.get("accounts") or [], drawn, str(saved.get("sign_in") or ""))
        if accounts_text:
            bus.agent_msg(project, accounts_text, title="Demo accounts", agent=bus.DESIGNER)
        session.note(
            f"The prototype is built: a React app with {len(drawn)} screens under .agentforge/prototype/app, made from the approved "
            f"wireframes (which are unchanged in .agentforge/wireframe/app) and linked so the journeys can be clicked through. This is "
            f"what the customer approved the product on, and the build must match it. Routes: "
            + ", ".join(str(r.get("route")) for r in drawn)
            + (f"\n\n{accounts_text}\n\nThe build seeds these same fictitious accounts." if accounts_text else ""))
        session.finish(f"Prototype made: {len(drawn)} screens.")
        if from_wireframes:
            bus.sync_state(project, "clean", "Prototype ready", source="prototype")
        return {"routes": drawn, "complete": True}
    except PrototypeIncomplete as exc:
        bus.phase(project, "prototype:draw", "Making the prototype", status="paused", detail="Waiting to generate: " + ", ".join(exc.missing))
        store.update(project, build_available=False, status="prototype-incomplete")
        session.stage = "idle"
        session.save_context()
        if from_wireframes:
            bus.sync_state(project, "paused", "Prototype generation is incomplete and ready to continue.", source="prototype")
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
            bus.sync_state(project, "failed", str(exc)[:300], source="prototype", error=str(exc)[:300])
        raise


def _rebundler(project: str, session: Any):
    """What puts the app's changed files into the page the studio shows (and the browser looks at) again."""
    return lambda: web_app.build_for(session, project, KIND, agent=bus.DESIGNER)


def _look_at(project: str, session: Any, drawn: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Look at the finished prototype: its screens by their pictures, then its journeys clicked through live. Both skip themselves,
    saying why, when the model cannot see pictures or there is no browser; neither ever fails the prototype."""
    accounts = (_read_record(session, PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}).get("accounts") or []
    rebuild = _rebundler(project, session)
    visual_review.run(project, session, drawn, accounts, rebuild=rebuild)
    if session.cancelled:
        raise RunCancelled(project)
    journey_walk.run(project, session, routes(project) or drawn,
                     _read_record(session, PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}, rebuild=rebuild)
    if session.cancelled:
        raise RunCancelled(project)
    return routes(project) or drawn


def review(project: str, fix: bool = True, model: str = "") -> dict[str, Any]:
    """Look at every screen of the prototype that is already made, with a model that can look at pictures, and fix what it finds
    (`fix`: false only looks and reports)."""
    if not exists(project):
        raise ValueError("there is no prototype to look at yet")
    session = session_for(project)
    accounts = (_read_record(session, PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}).get("accounts") or []
    result = visual_review.run(project, session, routes(project), accounts, fix=fix, model=model, force=True,
                               rebuild=_rebundler(project, session))
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") == "done" and fix:
        bus.prototype_changed(project)          # the pages may have changed: the preview reloads them
    return result


def journeys(project: str, fix: bool = True, model: str = "") -> dict[str, Any]:
    """Click through the journeys of the prototype that is already made, in a real browser, shown live, with a picture at every step,
    and fix what cannot be done or looks wrong (`fix`: false only walks and reports)."""
    if not exists(project):
        raise ValueError("there is no prototype to click through yet")
    session = session_for(project)
    doc = _read_record(session, PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}
    result = journey_walk.run(project, session, routes(project), doc, fix=fix, model=model, force=True,
                              rebuild=_rebundler(project, session))
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") == "done" and fix and result.get("fixed_journeys"):
        bus.prototype_changed(project)          # the pages may have changed: the preview reloads them
    return result


def revise(project: str, request: str) -> dict[str, Any]:
    """Change the prototype from a message typed into the chat stream."""
    if not exists(project):
        raise ValueError("there is no prototype to change yet")

    session = session_for(project)
    session.begin("prototype-edit", role=bus.DESIGNER)
    try:
        bus.user_msg(project, request, agent=bus.DESIGNER)
        session.run_direct(prompts.load("prototype/revise", request=request, skill=web_app.stage_skill(session.workspace),
                                        app=app_path(project).relative_to(session.workspace).as_posix()))
        web_app.build_for(session, project, KIND, agent=bus.DESIGNER)
        bus.prototype_changed(project)
        session.finish("Prototype updated.")
        return {"routes": routes(project)}
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
