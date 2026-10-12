"""The design contract.

One theme, one set of tokens, one direction — decided before a screen is drawn
and binding on everything after it. The theme catalogue is the prompt pack's
`design/themes/` directory, so adding a theme is adding a folder.
"""
from __future__ import annotations

import json
import time
from typing import Any

from server_modules import bus, config, prompts, reference_staging, store
from server_modules.session import ProjectSession, session_for

RECORD = ("design.json",)


def _blank() -> dict[str, Any]:
    return {"spec": None, "version": 0, "versions": [], "approved": False}


def state(session: ProjectSession) -> dict[str, Any]:
    saved = session.read_record(*RECORD, fallback=None)
    return saved if isinstance(saved, dict) else _blank()


def save(session: ProjectSession, data: dict[str, Any]) -> None:
    session.write_record(*RECORD, data=data)


def themes() -> list[dict[str, str]]:
    """Every theme in the pack, for the studio's design customizer."""
    return prompts.catalogue("design", kind="themes")


def current(project: str) -> dict[str, Any]:
    data = state(session_for(project))
    selection = (data.get("customizer") or {}).get("spec") or {}
    return {"spec": data.get("spec"), "version": data.get("version", 0),
            "versions": data.get("versions", []), "approved": bool(data.get("approved")),
            "customizer_approved": bool(data.get("approved") and
                                        selection.get("mode") in ("theme", "custom")),
            "themes": themes()}


def selected_design_md(spec: dict[str, Any] | None) -> tuple[str, str]:
    """The chosen theme's DESIGN.md, never an arbitrary path from the browser."""
    theme = (spec or {}).get("theme") or {}
    slug = theme.get("slug") if isinstance(theme, dict) else ""
    slug = str(slug or "")
    if not slug or not all(c.isalnum() or c in "_-" for c in slug):
        return "", ""
    path = config.PROMPTS / "design" / "themes" / slug / "DESIGN.md"
    if not path.is_file():
        path = config.PROMPTS / "design" / "themes" / slug / "SKILL.md"
    if not path.is_file():
        return "", ""
    return f"prompts/design/themes/{slug}/{path.name}", path.read_text(encoding="utf-8")


def approved_customization(project: str) -> dict[str, Any]:
    session = session_for(project)
    data = state(session)
    if not data.get("approved"):
        return {}
    chosen = data.get("customizer") or {}
    path, markdown = selected_design_md(chosen.get("spec"))
    workspace_path = ""
    if markdown:
        # The theme doc lives in this app's own prompts/, outside the project
        # workspace a read tool is rooted at — stage a copy inside it.
        workspace_path, = reference_staging.stage(session.workspace, "design", {"theme.md": markdown})
    return {"design_md_path": path, "design_md": markdown,
            "design_md_workspace_path": workspace_path,
            "customizer_prompt": chosen.get("prompt") or "",
            "customizer_spec": chosen.get("spec") or {}}


def draft(project: str, direction: str = "", spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write the design contract, from what the customer chose or asked for."""
    record = store.require(project)
    session = session_for(project)
    session.role = bus.DESIGNER
    data = state(session)

    if isinstance(spec, dict) and spec.get("tokens"):
        # The customizer already assembled a spec; keep it and let the
        # conversation know, rather than asking the model to invent a second one.
        chosen = spec
        session.ask_text(
            "The customer settled the design themselves in the customizer:\n\n"
            + json.dumps(chosen, ensure_ascii=False, indent=2)
            + "\n\nThis is the design contract for every screen from here. "
              "Acknowledge in one sentence. Use no tool.")
    else:
        bus.agent_state(project, "choosing the design", thinking=True, agent=bus.DESIGNER)
        catalogue = "\n".join(f"- `{row['slug']}` — {row['summary'] or row['title']}"
                              for row in themes())
        from srs_agent import plan as plan_stage
        approved = plan_stage.approved_plan(project)
        design_path, design_markdown = selected_design_md(spec)
        customer_direction = direction or record.get("idea", "")
        if spec:
            customer_direction += ("\n\nCustomizer selection:\n" +
                                   json.dumps(spec, ensure_ascii=False, indent=2))
        if design_markdown:
            staged, = reference_staging.stage(session.workspace, "design", {"theme.md": design_markdown})
            customer_direction += (f"\n\nA candidate theme's guidance ({design_path}) is staged at "
                                   f"`{staged}` — read it yourself with read_file before deciding.")
        chosen = session.ask_json(
            prompts.load("design/system") + "\n\n---\n\n" + prompts.load(
                "design/draft",
                direction=customer_direction,
                look_and_feel=str(approved.get("look_and_feel") or "(not stated)"),
                themes=catalogue or "(no themes installed)"))
        bus.agent_state(project, "", agent=bus.DESIGNER)

    if not isinstance(chosen, dict) or not chosen.get("tokens"):
        raise ValueError("a design spec needs a `tokens` block")

    data["version"] = data.get("version", 0) + 1
    data["versions"] = (data.get("versions") or []) + [
        {"version": data["version"], "at": time.time()}]
    data["spec"] = chosen
    data["customizer"] = {"spec": spec or {}, "prompt": direction}
    data["approved"] = False
    save(session, data)
    session.write_record("design", "design-spec.json", data=chosen)

    bus.agent_msg(project, f"Design v{data['version']}: {chosen.get('theme', 'custom')} — "
                           f"{chosen.get('why', '')}",
                  title="Design", agent=bus.DESIGNER, design=chosen)
    store.advance(project, "design")
    return current(project)


def approve(project: str, version: Any = None) -> dict[str, Any]:
    session = session_for(project)
    data = state(session)
    if not data.get("spec"):
        raise ValueError("there is no design spec to approve yet")
    if version not in (None, "", data.get("version")) and str(version) != str(data.get("version")):
        raise ValueError(f"design v{version} is not the current one (v{data.get('version')})")
    data["approved"] = True
    data["approved_at"] = time.time()
    save(session, data)
    bus.log(project, "SUCCESS", f"Design v{data['version']} approved.", agent=bus.DESIGNER)
    store.advance(project, "prototype")
    return current(project)


def approved_spec(project: str) -> dict[str, Any]:
    data = state(session_for(project))
    return data.get("spec") or {}
