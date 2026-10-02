"""The clickable prototype, drawn directly from approved wireframes and design."""
from __future__ import annotations

import hashlib
import html as html_text
import json
import re
import shutil
from typing import Any

from server_modules import auth_guide, bus, config, prompts, store
from server_modules.session import ProjectSession, RunCancelled, session_for

from . import design as design_stage
from . import prototype_brief
from .assets import normalize_inline_svg

PROTOTYPE_DIR = "prototype"
ROUTES = (PROTOTYPE_DIR, "routes.json")


def _read_record(session: Any, *parts: str, fallback=None):
    """Read optional session state without requiring it from focused callers.

    Production sessions persist incremental prototype state. Older focused
    callers may only provide a workspace and use the same drawing code for a
    one-shot render, where an absent checkpoint is simply a fresh run.
    """
    reader = getattr(session, "read_record", None)
    return reader(*parts, fallback=fallback) if callable(reader) else fallback


def _uploaded_site_images(session: ProjectSession, root: Any) -> list[dict[str, str]]:
    """Stage customer images next to the static HTML while preserving media originals."""
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
        target = root / "assets" / "uploads" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        uploaded.append({"name": source.name, "usage": image.get("purpose") or "",
                         "source": relative, "prototype_url": f"assets/uploads/{source.name}"})
    return uploaded


def routes(project: str) -> list[dict[str, Any]]:
    saved = session_for(project).read_record(*ROUTES, fallback=None)
    return (saved or {}).get("routes") or []


def exists(project: str) -> bool:
    session = session_for(project)
    checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    # During an incremental draw routes.json intentionally exposes the pages
    # already ready for review. It is not build-ready until the checkpoint is
    # complete. Projects created before checkpoints remain compatible.
    if checkpoint and not checkpoint.get("complete"):
        return False
    return bool(routes(project))


def asset(project: str, name: str) -> tuple[bytes, str]:
    """One prototype asset, for the studio's preview iframe."""
    session = session_for(project)
    path = (session.record / PROTOTYPE_DIR / name).resolve()
    root = (session.record / PROTOTYPE_DIR).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError(name)
    kind = {".css": "text/css", ".js": "text/javascript", ".html": "text/html",
            ".json": "application/json", ".svg": "image/svg+xml",
            ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return path.read_bytes(), kind.get(path.suffix.lower(), "application/octet-stream")


def _fallback_page(row: dict, wireframe: str) -> str:
    """A page the agent did not write, kept clickable: its approved wireframe wired into the flow, else a titled empty page."""
    if wireframe.strip():
        return wireframe
    name = html_text.escape(str(row.get("name") or row["route"]))
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{name}</title>\n'
            f'</head>\n<body>\n<main><h1>{name}</h1></main>\n</body>\n</html>\n')


def _draw_with_agent(project: str, spec: dict[str, Any], direction: str,
                     *, wireframe_source: dict[str, str] | None = None) -> list[dict]:
    """Let the project's agent read the wireframes, app.md and the design, plan silently and write the prototype — like the builder.

    Only what is the same for every prototype is code: the route map, the flow and the demo sign-in in `assets/flow.js`. Everything
    drawn is the agent's, written with its own file tools, so every read and every file appears in the chat stream as it happens.
    Nothing it writes is rejected or redrawn.
    """
    from srs_agent import document as srs_document
    from srs_agent import handoff as handoff_files

    session = session_for(project)
    doc = srs_document.document(project).get("srs_document", {})
    if wireframe_source is None:
        pages = [p for p in (doc.get("public_pages") or []) + (doc.get("protected_pages") or [])
                 if isinstance(p, dict) and p.get("route")]
    else:
        from srs_agent import plan as plan_stage
        pages = srs_document._wireframe_pages(doc, plan_stage.approved_plan(project))
    if not pages:
        raise ValueError("the specification names no screens to prototype")

    def filename(route: str) -> str:
        """Use a stable, readable filename derived directly from the route."""
        if route == "/":
            return "index.html"
        parts = []
        for part in str(route).strip("/").split("/"):
            # `/rooms/[id]` becomes `rooms-id.html`; do not expose a random
            # hash in the page list or make navigation depend on one.
            clean = part[1:-1] if part.startswith("[") and part.endswith("]") else part
            clean = re.sub(r"[^a-zA-Z0-9-]+", "-", clean).strip("-").lower()
            if clean:
                parts.append(clean)
        return ("-".join(parts) or "page") + ".html"

    routes_out = [{"route": p["route"], "file": filename(str(p["route"])),
                   "name": p.get("page_name") or p["route"],
                   "roles": p.get("allowed_roles") or [],
                   "signed_in": prototype_brief.signed_in_page(p)} for p in pages]
    root = session.record / PROTOTYPE_DIR
    root.mkdir(parents=True, exist_ok=True)
    record = f"{config.RECORD_DIR}/{PROTOTYPE_DIR}"
    uploaded_images = _uploaded_site_images(session, root)
    wireframe_source = wireframe_source or {}

    def write(name: str, body: str, note: str = "written") -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        bus.file_written(project, f"{record}/{name}", body, note=note, agent=bus.DESIGNER)

    # The three inputs, and only these. app.md and the design spec are read where earlier stages wrote them; a wireframe is
    # read as its structure, with its low-fidelity styling already gone, so the agent reads content rather than grey boxes.
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
    blueprints: dict[str, str] = {}
    for row in routes_out:
        html = wireframe_source.get(str(row["route"]), "")
        if html.strip():
            name = f"input/wireframes/{row['file']}"
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(prototype_brief.structure(html, limit=22000), encoding="utf-8")
            blueprints[str(row["route"])] = f"{record}/{name}"
    inputs = [f"- `{app_md_path}` — app.md, the approved application",
              f"- `{spec_path}` — the approved design tokens"]
    if customization.get("design_md_workspace_path"):
        inputs.append(f"- `{customization['design_md_workspace_path']}` — the selected theme's guidance "
                      f"({customization.get('design_md_path') or 'DESIGN.md'})")
    guide = auth_guide.staged_for(session.workspace, doc)
    if guide:
        inputs.append(f"- `{guide}` — how signing in, roles, each role's dashboard and the signed-in and signed-out "
                      "navigation work (its sections 1–4 and 6 are for the prototype)")
    inputs += [f"- `{path}` — the wireframe of `{route}`" for route, path in blueprints.items()]
    direction_text = "\n\n".join(part for part in (
        ("### The customer's design direction (from Design Customize)\n\n" + str(customization["customizer_prompt"]).strip())
        if customization.get("customizer_prompt") else "",
        ("### What the customer asked for on this prototype\n\n" + direction.strip()) if direction.strip() else "",
    ) if part)

    flow = prototype_brief.flow_of(doc, routes_out)
    sign_in = prototype_brief.sign_in_route(doc)
    accounts = prototype_brief.draw_accounts(doc, routes_out, flow, "")
    sign_up = prototype_brief.sign_up_of(doc, routes_out, accounts)

    fingerprint = hashlib.sha256(json.dumps(
        {"routes": routes_out, "design": spec, "customization": customization, "blueprints":
         {route: (root / path.removeprefix(record + "/")).read_text(encoding="utf-8") for route, path in blueprints.items()},
         "app_md": (session.workspace / app_md_path).read_text(encoding="utf-8"), "direction": direction},
        ensure_ascii=False, sort_keys=True, default=str,
    ).encode("utf-8")).hexdigest()
    checkpoint_path = root / "generation.json"
    checkpoint = _read_record(session, PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    resuming = checkpoint.get("fingerprint") == fingerprint and not checkpoint.get("complete")
    if not resuming:
        # A changed design, route map or wireframe owns a fresh page set. A matching interrupted run keeps its completed pages.
        for stale in root.glob("*.html"):
            stale.unlink(missing_ok=True)
        for stale in ("assets/app.css", "assets/app.js", "routes.json"):
            (root / stale).unlink(missing_ok=True)
    written = [row for row in routes_out if (root / row["file"]).is_file() and (root / row["file"]).stat().st_size >= 1000]
    checkpoint_path.write_text(json.dumps({"fingerprint": fingerprint, "complete": False, "sign_in": sign_in,
                                           "accounts": accounts, "flow": flow}, ensure_ascii=False, indent=2), encoding="utf-8")

    # The parts that are the same for every prototype: the route map, the flow and the demo sign-in.
    write("assets/flow.js", prototype_brief.flow_script(routes_out, flow, accounts, sign_in, sign_up))
    write("demo-accounts.json", json.dumps({"sign_in": sign_in, "accounts": accounts}, ensure_ascii=False, indent=2))

    def publish(done: set[str]) -> None:
        """routes.json lists the pages already written, so the preview shows each one as soon as it exists."""
        write("routes.json", json.dumps({"routes": [row for row in routes_out if row["file"] in done]},
                                        ensure_ascii=False, indent=2), note="updated")

    resume = ""
    if resuming and (written or (root / "assets" / "app.css").is_file()):
        resume = ("## Resuming an interrupted run\n\nThese files are already written and finished — keep them, do not read or "
                  "rewrite them, and write only the rest:\n\n"
                  + "\n".join(f"- `{record}/{name}`" for name in
                              [n for n in ("assets/app.css", "assets/app.js") if (root / n).is_file()]
                              + [row["file"] for row in written]))
    request = prompts.load(
        "prototype/generate", inputs="\n".join(inputs), design_direction=direction_text,
        routes=prototype_brief.routes_text(routes_out, blueprints), journeys=prototype_brief.journey_text(flow),
        sign_in=prototype_brief.sign_in_text(accounts, sign_in, routes_out, sign_up),
        uploads=(json.dumps(uploaded_images, ensure_ascii=False, indent=2) if uploaded_images
                 else "None — use the wireframes' images or fitting real photos."),
        resume=resume)

    # Every page the agent writes is exposed to the preview and counted at once, while it goes on to the next.
    pages_done: set[str] = {row["file"] for row in written}
    by_file = {f"{record}/{row['file']}": row for row in routes_out}

    def watch(event: dict) -> None:
        if event.get("project") != project or event.get("type") != "file" or event.get("agent") != bus.DESIGNER:
            return
        row = by_file.get(str(event.get("name") or ""))
        if not row or row["file"] in pages_done:
            return
        pages_done.add(row["file"])
        publish(pages_done)
        bus.progress(project, "Drawing prototype screens", len(pages_done) * 100 / len(routes_out), agent=bus.DESIGNER)

    publish(pages_done)
    stop_watching = bus.subscribe(watch)
    try:
        # Read everything, plan silently, then write — the builder's own run, without its audit pass.
        result = session.run_task(request, audit=False, parallel_write_limit=4)
    finally:
        stop_watching()
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("plan"):
        (root / "plan.md").write_text(result["plan"], encoding="utf-8")
    if result.get("status") != "complete" and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)

    # What the agent wrote is used as it is. Only the links to the shared files every page needs are added if one is missing,
    # and a page it never wrote keeps its wireframe so every link in the prototype still opens something.
    kept: list[str] = []
    for row in routes_out:
        path = root / row["file"]
        html = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not html.strip():
            html = _fallback_page(row, wireframe_source.get(str(row["route"]), ""))
            kept.append(str(row["route"]))
        finished = normalize_inline_svg(prototype_brief.ensure_assets(html), spec)
        if finished != (path.read_text(encoding="utf-8") if path.is_file() else None):
            write(row["file"], finished, note="patched")
    if len(kept) == len(routes_out):
        raise ValueError("the agent wrote no prototype page"
                         + (f": {str(result.get('text'))[:300]}" if result.get("text") else ""))
    if kept:
        bus.agent_msg(project, f"The agent did not write {', '.join(kept)}, so "
                               f"{'they open' if len(kept) != 1 else 'it opens'} as {'their' if len(kept) != 1 else 'its'} "
                               "approved wireframe (or a titled page) for now. Ask for it in the chat to have it drawn.",
                      title="Prototype screens", kind="narration", agent=bus.DESIGNER)
    for name in ("assets/app.css", "assets/app.js"):
        if not (root / name).is_file():
            write(name, "/* The agent wrote no shared " + ("stylesheet" if name.endswith("css") else "script") + ". */\n")
    write("routes.json", json.dumps({"routes": routes_out}, ensure_ascii=False, indent=2))
    checkpoint_path.write_text(json.dumps({"fingerprint": fingerprint, "complete": True, "sign_in": sign_in,
                                           "accounts": accounts, "flow": flow}, ensure_ascii=False, indent=2), encoding="utf-8")
    return routes_out


def generate(project: str, direction: str = "") -> dict[str, Any]:
    """Draw every screen the specification names."""
    return _generate(project, direction)


def generate_from_wireframes(project: str, direction: str = "") -> dict[str, Any]:
    """Draw the prototype directly from approved HTML wireframes."""
    return _generate(project, direction, from_wireframes=True)


def _generate(project: str, direction: str,
              *, from_wireframes: bool = False) -> dict[str, Any]:
    from srs_agent import document as srs_document

    if not srs_document.has_document(project):
        raise ValueError("write the specification before drawing the prototype")

    session = session_for(project)
    source: dict[str, str] | None = None
    if from_wireframes:
        if not design_stage.current(project).get("approved"):
            raise ValueError("approve the selected design in Design Customize first")
        grid = srs_document.wireframes(project).get("pages") or []
        if not grid:
            raise ValueError("approve the SRS before generating the prototype")
        # Ready wireframes are approved visual blueprints. A missing page must
        # not block approval: that route is generated from the approved SRS and
        # handoff instead, while every available wireframe is still honoured.
        source = {str(p["route"]): srs_document.wireframe_html(project, str(p["route"]))
                  for p in grid if p.get("has_html")}
    session.begin("prototype", role=bus.DESIGNER)
    if from_wireframes:
        bus.sync_state(project, "running", "Drawing the approved prototype",
                       source="prototype")
    try:
        spec = design_stage.approved_spec(project)
        if not spec:
            design_stage.draft(project, direction=direction)
            design_stage.approve(project)
            spec = design_stage.approved_spec(project)
        bus.phase(project, "prototype:draw", "Drawing the prototype",
                  detail="Every screen, from the wireframes, app.md and the approved design.")
        bus.agent_msg(project, "Building the clickable prototype from the approved wireframes, app.md and Design Customize.",
                      title="Prototype generation", kind="narration", agent=bus.DESIGNER)
        _draw_with_agent(project, spec, direction, wireframe_source=source)
        bus.phase(project, "prototype:draw", "Drawing the prototype", status="complete")
        if session.cancelled:
            raise RunCancelled(project)

        drawn = routes(project)
        if not drawn:
            raise ValueError("the prototype wrote no routes.json, so no screen is reviewable")

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
        # The demo accounts and what each role can open, at the end, in the chat: this is how the customer enters as each role.
        saved = _read_record(session, PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}
        accounts_text = prototype_brief.accounts_message(saved.get("accounts") or [], drawn, str(saved.get("sign_in") or ""))
        if accounts_text:
            bus.agent_msg(project, accounts_text, title="Demo accounts", agent=bus.DESIGNER)
        session.note(
            f"The prototype is built: {len(drawn)} screens under "
            f".agentforge/prototype/, linked so the journeys can be clicked "
            f"through. This is what the customer approved the product on, and "
            f"the build must match it. Routes: "
            + ", ".join(str(r.get("route")) for r in drawn)
            + (f"\n\n{accounts_text}\n\nThe build seeds these same fictitious accounts." if accounts_text else ""))
        session.finish(f"Prototype drawn: {len(drawn)} screens.")
        if from_wireframes:
            bus.sync_state(project, "clean", "Prototype ready", source="prototype")
        return {"routes": drawn}
    except RunCancelled:
        bus.phase(project, "prototype:draw", "Drawing the prototype", status="paused")
        session.stage = "idle"
        session.save_context()
        if from_wireframes:
            bus.sync_state(project, "paused", "Prototype generation stopped.", source="prototype")
        raise
    except Exception as exc:  # noqa: BLE001
        bus.phase(project, "prototype:draw", "Drawing the prototype", status="failed", detail=str(exc)[:300])
        session.fail(str(exc))
        if from_wireframes:
            bus.sync_state(project, "failed", str(exc)[:300], source="prototype",
                           error=str(exc)[:300])
        raise


def revise(project: str, request: str) -> dict[str, Any]:
    """Change the prototype from a message typed into the chat stream."""
    if not exists(project):
        raise ValueError("there is no prototype to change yet")

    session = session_for(project)
    session.begin("prototype-edit", role=bus.DESIGNER)
    try:
        bus.user_msg(project, request, agent=bus.DESIGNER)
        session.run_direct(prompts.load("prototype/revise", request=request))
        bus.prototype_changed(project)
        session.finish("Prototype updated.")
        return {"routes": routes(project)}
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
