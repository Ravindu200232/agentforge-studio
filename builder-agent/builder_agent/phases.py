"""The build as numbered phases, so the whole application gets built however big it is.

One conversation asked to build thirty pages, five services, the seed, the tests and the end-to-end journeys cuts the application down
once it sees how long it already is ("I must be honest about capacity"), and the run ends with a coherent subset. Here the Studio holds
the list of what the application consists of - the foundation, then the prototype's approved pages a few at a time, then the wiring and
the seed, the unit tests and the final checks - and gives the model one phase at a time, each small enough to be done in full.

What a phase delivers is checked, not taken on trust: a page is built when it has an entry in `.agentforge/build/progress.json` naming
files that exist. A phase that is not finished is asked for again; a page that is still not built when everything has run fails the
build with its name (`gate`), never a subset reported as the application. The state is kept on disk, so a build that was stopped carries
on from the phase it reached, with the plan it already made.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from server_modules import config, prompts

PAGES_PER_PHASE = 4
PROGRESS = ("build", "progress.json")
STATE = ("build", "phases.json")
MIN_BYTES = 1                      # a file a page names has to exist and not be empty


def routes_of(workspace: Path) -> list[dict[str, Any]]:
    """The pages the approved prototype has, in its own order: [{"route", "file", "name", "roles"}]."""
    try:
        data = json.loads((workspace / config.RECORD_DIR / "prototype" / "routes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows, seen = [], set()
    for row in (data.get("routes") if isinstance(data, dict) else None) or []:
        route = str(row.get("route") or "").strip() if isinstance(row, dict) else ""
        if not route or route in seen:
            continue
        seen.add(route)
        rows.append({"route": route, "file": str(row.get("file") or ""), "name": str(row.get("name") or route),
                     "roles": [str(r) for r in row.get("roles") or [] if str(r).strip()]})
    return rows


def section(request: str, number: int) -> str:
    """`## Phase N — …` of the build request, up to the next heading: the text the plan's own phases are written in."""
    found = re.search(rf"^## Phase {number}\b.*?(?=^## |\Z)", request or "", re.MULTILINE | re.DOTALL)
    return found.group(0).strip() if found else ""


def _span(rows: list[dict[str, Any]]) -> str:
    names = [row["name"] for row in rows]
    return ", ".join(names[:4]) + ("…" if len(names) > 4 else "")


def plan(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The phases of a build, in order: the foundation, the pages a few at a time, the wiring, the unit tests, the final checks."""
    phases: list[dict[str, Any]] = [{
        "id": "foundation", "kind": "foundation", "title": "Foundation: the data, sign-in and the shared layout",
        "detail": "Building what every page stands on: the data models, authentication and roles, the shared layout and components.",
        "routes": [], "status": "pending"}]
    for number, start in enumerate(range(0, len(routes), PAGES_PER_PHASE), start=1):
        rows = routes[start:start + PAGES_PER_PHASE]
        first, last = start + 1, start + len(rows)
        phases.append({
            "id": f"pages-{number}", "kind": "pages",
            "title": f"Pages {first}–{last} of {len(routes)}: {_span(rows)}" if len(rows) > 1 else f"Page {first} of {len(routes)}: {rows[0]['name']}",
            "detail": f"Building {'pages' if len(rows) > 1 else 'the page'} {first}–{last} of {len(routes)} ({_span(rows)}), "
                      "each with its server handlers and data." if len(rows) > 1 else
                      f"Building page {first} of {len(routes)} ({rows[0]['name']}), with its server handlers and data.",
            "routes": [row["route"] for row in rows], "status": "pending"})
    phases += [
        {"id": "wiring", "kind": "wiring", "title": "Connecting everything: the seed, the environment and the build",
         "detail": "Connecting the parts, writing the seed and the environment file, and making the application compile.",
         "routes": [], "status": "pending"},
        {"id": "tests", "kind": "tests", "title": "Unit tests",
         "detail": "Reading the finished application and writing its unit tests.", "routes": [], "status": "pending"},
        {"id": "checks", "kind": "checks", "title": "Final checks and the reports",
         "detail": "Running the end-to-end journeys and the final product checks, and writing the reports.",
         "routes": [], "status": "pending"}]
    return phases


def _listing(rows: list[dict[str, Any]]) -> str:
    return "\n".join(f"- `{row['route']}` — {row['name']} — prototype file `{row['file'] or '(none)'}`"
                     + (f" — roles: {', '.join(row['roles'])}" if row["roles"] else "") for row in rows)


def request_for(phase: dict[str, Any], number: int, total: int, routes: list[dict[str, Any]], request: str) -> str:
    """What the model is asked for in this phase."""
    kind = phase["kind"]
    if kind == "foundation":
        task = prompts.load("builder/phase-foundation").strip()
    elif kind == "pages":
        wanted = [row for row in routes if row["route"] in set(phase.get("routes") or [])]
        task = prompts.load("builder/phase-pages", routes=_listing(wanted)).strip()
    elif kind == "wiring":
        task = prompts.load("builder/phase-wiring", phase1=section(request, 1)).strip()
    elif kind == "tests":
        task = "## What this phase is: the unit tests\n\n" + (section(request, 2) or "Write the unit tests of the finished application.")
    else:
        task = "## What this phase is: the final checks\n\n" + (section(request, 3) or "Run the final product checks and write the reports.")
    return prompts.load("builder/phase", number=number, total=total, title=phase["title"], task=task).strip()


def repair_for(phase: dict[str, Any], number: int, total: int, problems: list[str]) -> str:
    return prompts.load("builder/phase-repair", number=number, total=total, title=phase["title"],
                        problems="\n".join(f"- {line}" for line in problems)).strip()


# --- what a phase delivered ---------------------------------------------------------------------------------------------

def recorded(workspace: Path) -> dict[str, list[str]]:
    """The pages the model says it built, and the files it says are theirs, from `.agentforge/build/progress.json`."""
    try:
        data = json.loads((workspace / config.RECORD_DIR).joinpath(*PROGRESS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = data.get("routes") if isinstance(data, dict) else None
    if not isinstance(rows, dict):
        return {}
    return {str(route): [str(f) for f in files if isinstance(f, str)] for route, files in rows.items() if isinstance(files, list)}


def _real(workspace: Path, name: str) -> bool:
    """Whether `name` is a file of the workspace that exists and is not empty."""
    try:
        path = (workspace / name).resolve()
        return path.is_relative_to(workspace.resolve()) and path.is_file() and path.stat().st_size >= MIN_BYTES
    except (OSError, ValueError):
        return False


def built(workspace: Path, route: str, notes: dict[str, list[str]] | None = None) -> bool:
    notes = recorded(workspace) if notes is None else notes
    return any(_real(workspace, name) for name in notes.get(route, []))


def missing(workspace: Path, routes: list[dict[str, Any]]) -> list[str]:
    """The pages of the prototype that are not built: no entry in the progress file, or none of its files is there."""
    notes = recorded(workspace)
    return [row["route"] for row in routes if not built(workspace, row["route"], notes)]


def summary(workspace: Path, phase: dict[str, Any]) -> str:
    """What a finished pages phase delivered, as the chat reads it: each page and the files that are its own."""
    if phase["kind"] != "pages":
        return ""
    notes = recorded(workspace)
    lines = []
    for route in phase.get("routes") or []:
        files = [name for name in notes.get(route, []) if _real(workspace, name)]
        if files:
            lines.append(f"`{route}` — " + ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else ""))
    return ("Built:\n" + "\n".join(f"- {line}" for line in lines)) if lines else ""


def problems(workspace: Path, phase: dict[str, Any]) -> list[str]:
    """What keeps a phase from being finished, in words the model can act on; nothing when it is."""
    if phase["kind"] == "foundation":
        return [] if (workspace / "package.json").is_file() else ["there is no package.json: the application has not been set up"]
    if phase["kind"] != "pages":
        return []
    notes = recorded(workspace)
    found = []
    for route in phase.get("routes") or []:
        if route not in notes or not notes[route]:
            found.append(f"`{route}` is not recorded in .agentforge/build/progress.json (a page is done when it has an entry with its files)")
        elif not built(workspace, route, notes):
            found.append(f"`{route}` is recorded, but none of the files it names exists: {', '.join(notes[route][:3])}")
    return found


# --- the state, so a stopped build carries on ---------------------------------------------------------------------------

def fingerprint(routes: list[dict[str, Any]], stack: str, direction: str = "") -> str:
    body = json.dumps([[row["route"], row["file"]] for row in routes]) + "|" + stack + "|" + direction.strip()
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def save_state(session: Any, state: dict[str, Any]) -> None:
    session.write_record(*STATE, data=state)


def resume_state(session: Any, finger: str) -> dict[str, Any] | None:
    """The state of an unfinished build of this very application (the same pages, stack and request) whose plan is still on disk."""
    saved = session.read_record(*STATE, fallback=None)
    if not isinstance(saved, dict) or saved.get("finished") or saved.get("fingerprint") != finger:
        return None
    plan_file = str(saved.get("plan_file") or "")
    items = saved.get("phases")
    if not plan_file or not isinstance(items, list) or not items or not (session.workspace / plan_file).is_file():
        return None
    for item in items:                                   # a phase that ended unfinished is asked for again
        if isinstance(item, dict) and item.get("status") != "done":
            item["status"] = "pending"
    return saved


def finish_state(session: Any) -> None:
    """The build ended well: the next one starts from a fresh plan."""
    saved = session.read_record(*STATE, fallback=None)
    if isinstance(saved, dict):
        saved["finished"] = True
        session.write_record(*STATE, data=saved)


def gate(session: Any) -> None:
    """A page of the prototype that is not built fails the build, by name: never a subset reported as the application."""
    saved = session.read_record(*STATE, fallback=None)
    if not isinstance(saved, dict) or saved.get("finished"):
        return
    routes = routes_of(session.workspace)
    left = missing(session.workspace, routes)
    if left:
        shown = ", ".join(left[:12]) + (f" and {len(left) - 12} more" if len(left) > 12 else "")
        raise ValueError(f"{len(left)} of the prototype's {len(routes)} pages were not built: {shown}. "
                         "Press Build again to carry on from where it stopped.")
