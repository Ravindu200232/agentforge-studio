"""The clickable prototype, drawn directly from approved wireframes and design."""
from __future__ import annotations

import json
import hashlib
import re
import shutil
import threading
from typing import Any

from server_modules import bus, llm, prompts, store
from server_modules.session import ProjectSession, RunCancelled, session_for

from . import design as design_stage
from . import prototype_brief
from .assets import normalize_inline_svg

PROTOTYPE_DIR = "prototype"
ROUTES = (PROTOTYPE_DIR, "routes.json")


def _uploaded_site_images(session: ProjectSession, root: Any) -> list[dict[str, str]]:
    """Stage customer images next to the static HTML while preserving media originals."""
    uploaded = []
    if not hasattr(session, "workspace"):
        return uploaded
    media = (session.workspace / "media").resolve()
    if not media.is_relative_to(session.workspace.resolve()):
        return uploaded
    for image in session.read_record("images.json", fallback=[]) or []:
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
    checkpoint = session.read_record(PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    # During an incremental draw routes.json intentionally exposes the pages
    # already ready for review. It is not build-ready until the checkpoint is
    # complete. Projects created before checkpoints remain compatible.
    if checkpoint and not checkpoint.get("complete"):
        return False
    return bool(routes(project))


def page_html(project: str, route: str = "/") -> str:
    session = session_for(project)
    wanted = str(route or "/")
    for row in routes(project):
        if str(row.get("route")) == wanted:
            path = session.record / PROTOTYPE_DIR / str(row.get("file") or "")
            if path.is_file():
                return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"no prototype page for {wanted}")


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


def _write_kit(session: ProjectSession, project: str, root: Any, made: dict[str, Any], routes_out: list[dict]) -> None:
    """The shared kit and what goes with it, into the prototype folder, announced as files in the chat."""
    files = {"assets/app.css": made["kit"]["assets/app.css"], "assets/app.js": made["kit"]["assets/app.js"],
             "assets/flow.js": made["flow_js"], "kit/shell.html": made["kit"]["shell.html"]}
    if made["ideas"]:
        files["kit/ideas.md"] = made["ideas"]
    files["demo-accounts.json"] = json.dumps({"sign_in": made["sign_in"], "accounts": made["accounts"]}, ensure_ascii=False, indent=2)
    if made["images"]:
        files["kit/images.json"] = json.dumps(made["images"], ensure_ascii=False, indent=2)
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        bus.file_written(project, f".agentforge/prototype/{name}", body, note="written", agent=bus.DESIGNER)


def _draw_focused(project: str, spec: dict[str, Any], direction: str,
                  *, wireframe_source: dict[str, str] | None = None,
                  approved_execution_plan: str = "") -> list[dict]:
    """Generate each screen with its own output budget and an exact route map."""
    from srs_agent import document as srs_document

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
                   "roles": p.get("allowed_roles") or []} for p in pages]
    nav = [{"label": r["name"], "href": r["file"]} for r in routes_out]
    root = session.record / PROTOTYPE_DIR
    root.mkdir(parents=True, exist_ok=True)
    uploaded_images = _uploaded_site_images(session, root)
    context = {key: doc.get(key) for key in ("app_summary", "roles", "main_modules",
               "functional_requirements", "business_workflows", "validation_rules",
               "ui_ux_requirements", "database_design") if doc.get(key)}
    handoff = srs_document.handoff_docs(session) if wireframe_source is not None else {}
    customization = design_stage.approved_customization(project) if wireframe_source is not None else {}
    customization["uploaded_site_images"] = uploaded_images
    fingerprint_payload = {
        "routes": routes_out,
        "design": spec,
        "customization": customization,
    }
    # Structures are computed just below. Keep the payload declaration close to
    # the other input gathering, then finish the fingerprint once they exist.
    completed = 0
    progress_lock = threading.Lock()

    def say(text: str) -> None:
        bus.log(project, "INFO", text, agent=bus.DESIGNER)

    # Before any page: what makes them one product. Read the approved wireframe
    # structure, flow and images, then create the shared kit once.
    structures = {str(route): prototype_brief.structure(html) for route, html in (wireframe_source or {}).items()}
    fingerprint_payload["structures"] = structures
    fingerprint = hashlib.sha256(json.dumps(
        fingerprint_payload, ensure_ascii=False, sort_keys=True, default=str,
    ).encode("utf-8")).hexdigest()
    checkpoint_path = root / "generation.json"
    checkpoint = session.read_record(PROTOTYPE_DIR, "generation.json", fallback=None) or {}
    kit_paths = {
        "assets/app.css": root / "assets" / "app.css",
        "assets/app.js": root / "assets" / "app.js",
        "shell.html": root / "kit" / "shell.html",
    }
    can_resume = checkpoint.get("fingerprint") == fingerprint and all(path.is_file() for path in kit_paths.values())

    if not can_resume:
        # A changed design, route map or wireframe owns a fresh generated page
        # set. A matching interrupted run keeps its already completed work.
        for stale in root.glob("*.html"):
            stale.unlink(missing_ok=True)
        (root / "routes.json").unlink(missing_ok=True)
        checkpoint_path.unlink(missing_ok=True)

    bus.phase(project, "prototype:kit", "Designing the shared look",
              detail="Reading the approved wireframes, images and flow, then drawing the shared design system.")
    if can_resume:
        made = {
            "ideas": checkpoint.get("ideas") or "",
            "flow": checkpoint.get("flow") or {"journeys": [], "leads_to": {}},
            "sign_in": checkpoint.get("sign_in") or "",
            "accounts": checkpoint.get("accounts") or [],
            "images": checkpoint.get("images") or [],
            "kit": {name: path.read_text(encoding="utf-8") for name, path in kit_paths.items()},
            "flow_js": (root / "assets" / "flow.js").read_text(encoding="utf-8")
                       if (root / "assets" / "flow.js").is_file() else "",
        }
        say("Resuming the prototype from its saved design kit and completed pages.")
    else:
        bus.progress(project, "Preparing the shared prototype design", 2, agent=bus.DESIGNER)
        made = prototype_brief.prepare(doc, spec, customization, routes_out, structures, say)
        _write_kit(session, project, root, made, routes_out)
        checkpoint = {
            "fingerprint": fingerprint,
            "complete": False,
            "ideas": made["ideas"],
            "flow": made["flow"],
            "sign_in": made["sign_in"],
            "accounts": made["accounts"],
            "images": made["images"],
        }
        checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    premium_skill = prompts.skill("prototype", "premium-frontend")
    system = (prompts.load("prototype/system")
              + "\n\n## Premium frontend design skill\n\n"
              + premium_skill)

    def draw(item: tuple[dict, dict]) -> dict:
        nonlocal completed
        if session.cancelled:
            raise RunCancelled(project)
        page, row = item
        path = root / row["file"]
        if can_resume and path.is_file() and path.stat().st_size >= 1000:
            with progress_lock:
                completed += 1
                ready_routes.append(row)
                _publish_ready_routes()
                bus.progress(project, "Drawing prototype screens",
                             completed * 100 / len(pages), agent=bus.DESIGNER)
            return row
        bus.agent_msg(project, f"Drawing prototype screen {row['name']} ({row['route']}) from the approved wireframe and design.",
                      title="Prototype screen", kind="narration", agent=bus.DESIGNER)
        brief = {"page": page, "route_map": nav, "design": spec,
                 "product": context, "customer_direction": direction,
                 "flow": prototype_brief.page_flow(made["flow"], str(page["route"])),
                 "kit_shell": made["kit"]["shell.html"],
                 "kit": prototype_brief.kit_reference(made["kit"]),
                 "demo_accounts": made["accounts"],
                 "sample_photographs": made["images"],
                 "uploaded_site_images": uploaded_images,
                 "ideas_from_the_web": made["ideas"],
                 "requirements": [fr for fr in doc.get("functional_requirements", [])
                                  if set(fr.get("allowed_roles") or []) &
                                  set(page.get("allowed_roles") or [])][:12]}
        if wireframe_source is not None:
            brief.update({"approved_prototype_plan": approved_execution_plan,
                          # The source HTML often carries grey boxes and other
                          # low-fidelity styling. Give the page model only its
                          # stripped functional blueprint, so the approved
                          # design decides the finished visual UI.
                          "functional_blueprint": structures.get(str(page["route"]), ""),
                          "selected_design_md_path": customization.get("design_md_path", ""),
                          "customizer_prompt": customization.get("customizer_prompt", ""),
                          "customizer_selection": customization.get("customizer_spec", {})})
        user = json.dumps(brief, ensure_ascii=False)
        weight = len(page.get("sections") or []) + len(page.get("functions") or [])
        # Large screens used to demand 15–25k characters from the model even
        # when the approved wireframe was concise. Keep a useful floor while
        # bounding output so generation time follows the actual screen.
        minimum = max(2800, min(6500, weight * 650))
        html = llm.complete_html(system, user, minimum=minimum,
                                 label=f"prototype {row['route']}", attempts=1,
                                 think=False)
        if session.cancelled:
            raise RunCancelled(project)
        html = prototype_brief.ensure_assets(html)
        html = normalize_inline_svg(html, spec)
        path.write_text(html, encoding="utf-8")
        bus.file_written(project, f".agentforge/prototype/{row['file']}", html,
                         note="drawn", agent=bus.DESIGNER)
        with progress_lock:
            completed += 1
            ready_routes.append(row)
            _publish_ready_routes()
            bus.progress(project, "Drawing prototype screens",
                         completed * 100 / len(pages), agent=bus.DESIGNER)
        return row

    ready_routes: list[dict] = []

    def _publish_ready_routes() -> None:
        """Expose each completed page immediately while the rest keep drawing."""
        routes_text = json.dumps({"routes": ready_routes}, ensure_ascii=False, indent=2)
        (root / "routes.json").write_text(routes_text, encoding="utf-8")
        bus.file_written(project, ".agentforge/prototype/routes.json", routes_text,
                         note="updated", agent=bus.DESIGNER)

    # Screens share a route map and user journeys. Draw them one at a time so
    # each screen can apply the approved flow without competing context.
    results = llm.in_lanes(list(zip(pages, routes_out)), draw, lanes=1,
                           on_error=lambda item, exc: bus.log(project, "ERROR",
                               f"Could not draw {item[1]['route']}: {exc}", agent=bus.DESIGNER))
    drawn = [row for row in results if isinstance(row, dict)]
    if session.cancelled:
        raise RunCancelled(project)
    if len(drawn) != len(routes_out):
        raise ValueError(f"only {len(drawn)}/{len(routes_out)} prototype screens rendered")
    routes_text = json.dumps({"routes": drawn}, ensure_ascii=False, indent=2)
    (root / "routes.json").write_text(routes_text, encoding="utf-8")
    bus.file_written(project, ".agentforge/prototype/routes.json", routes_text,
                     note="written", agent=bus.DESIGNER)
    checkpoint["fingerprint"] = fingerprint
    checkpoint["complete"] = True
    checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    return drawn


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
        execution_plan = ("Read the handoff, route map and each approved wireframe's functional blueprint before drawing its screen. "
                          "Draw one screen at a time as a high-fidelity, real product UI. Preserve every button destination, "
                          "page navigation, image and user-flow step; reread the supplied inputs instead of guessing.")
        if source is not None:
            if direction.strip():
                execution_plan += " Customer direction: " + direction.strip()
        spec = design_stage.approved_spec(project)
        if not spec:
            design_stage.draft(project, direction=direction)
            design_stage.approve(project)
            spec = design_stage.approved_spec(project)
        bus.phase(project, "prototype:draw", "Drawing the prototype",
                  detail="Every screen in the specification, with the approved design.")
        bus.agent_msg(project, "Building the clickable prototype from the available approved wireframes, SRS handoff, and design.",
                      title="Prototype generation", kind="narration", agent=bus.DESIGNER)
        _draw_focused(project, spec, direction, wireframe_source=source,
                      approved_execution_plan=execution_plan)
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
        saved = session.read_record(PROTOTYPE_DIR, "demo-accounts.json", fallback=None) or {}
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
        session.stage = "idle"
        session.save_context()
        bus.cancelled(project, "Prototype generation stopped.", agent=bus.DESIGNER)
        if from_wireframes:
            bus.sync_state(project, "failed", "Prototype generation stopped.",
                           source="prototype", error="Prototype generation stopped.")
        raise
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
