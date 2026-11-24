"""Generate and edit static HTML wireframes from the approved specification."""
from __future__ import annotations

import html
import shutil
from pathlib import Path
from stat import S_ISREG
from typing import Any

from server_modules import bus, pointed, prompts, web_app
from server_modules.session import RunCancelled, session_for, start_fresh

from . import document
from .wireframe_review import Review

KIND = "wireframe"
MAX_REQUEST = 4000
# What starting the wireframes asks for: the default request in the Studio. The studio sends the same words.
APPROVAL_PROMPT = "Generate low-fidelity wireframes."
def app_path(project: str):
    return web_app.app_dir(session_for(project).workspace, KIND)


def built(project: str) -> bool:
    folder = html_path(project)
    return any(path.name != "index.html" and file_stamp(path) for path in folder.glob("*.html")) or web_app.built(app_path(project))


def file_stamp(path: Path) -> int:
    try:
        info = path.stat()
        return info.st_mtime_ns // 1_000_000 if info.st_size and S_ISREG(info.st_mode) else 0
    except OSError:
        return 0


def _relative(project: str) -> str:
    return app_path(project).relative_to(session_for(project).workspace).as_posix()


def _remember(session, **state: Any) -> None:
    """What the studio shows when there is no wireframe: the last error, if there was one."""
    try:
        session.write_record(KIND, "state.json", data=state)
    except RunCancelled:
        raise
    except OSError:
        pass


HTML_DIR = "wireframe-html"
_GALLERY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@ — HTML wireframes</title>
<style>
:root{--ink:#171717;--muted:#737373;--line:#e5e5e5;--bg:#fafafa}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--bg)}
header{padding:20px 24px;border-bottom:1px solid var(--line);background:#fff}h1{margin:0;font-size:18px}p{margin:4px 0 0;color:var(--muted)}
main{padding:24px;display:grid;gap:20px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
a.card{display:block;border:1px solid var(--line);background:#fff;color:inherit;text-decoration:none;overflow:hidden}
a.card:hover{border-color:var(--ink)}.thumb{height:210px;overflow:hidden;border-bottom:1px solid var(--line);position:relative;background:#fff}
.thumb iframe{width:1280px;height:900px;border:0;transform:scale(.22);transform-origin:0 0;pointer-events:none}
.meta{padding:10px 12px}.meta b{display:block;font-weight:600}.meta code{color:var(--muted);font-size:11px}.meta small{display:block;color:var(--muted)}
</style></head><body>
<header><h1>@@TITLE@@ — wireframes as plain HTML</h1><p>@@COUNT@@ pages. Click a page to open it and click through; links between the pages work.</p></header>
<main>
@@CARDS@@
</main></body></html>
"""


def html_path(project: str):
    """The plain HTML version of the wireframes: a folder of pages, one stylesheet and one script, which opens from the folder."""
    return session_for(project).record / HTML_DIR


def source_path(project: str):
    """Use the HTML source when the project has an HTML wireframe, or its saved React source."""
    folder = html_path(project)
    return folder if folder.is_dir() else app_path(project)


def html_routes(rows: list[dict[str, Any]]) -> str:
    return "\n".join(f"- `{row['route']}` — {row['name']}"
                     + (f" (signed in: {', '.join(row['roles']) or 'any role'})" if row["signedIn"] else "")
                     + f" — `{row['file']}`" for row in rows)


def _gallery(folder, rows: list[dict[str, Any]], title: str) -> None:
    cards = []
    for row in rows:
        if not file_stamp(folder / row["file"]):
            cards.append(f'<div class="card"><div class="meta"><b>{html.escape(row["name"])}</b><code>{html.escape(row["route"])}</code>'
                         f'<small>not drawn</small></div></div>')
            continue
        who = ", ".join(row.get("roles") or []) if row.get("signedIn") else "public"
        cards.append(f'<a class="card" href="{html.escape(row["file"])}"><div class="thumb"><iframe src="{html.escape(row["file"])}" '
                     f'loading="lazy" tabindex="-1" title="{html.escape(row["name"])}"></iframe></div><div class="meta">'
                     f'<b>{html.escape(row["name"])}</b><code>{html.escape(row["route"])}</code><small>{html.escape(who)}</small></div></a>')
    page = (_GALLERY.replace("@@TITLE@@", html.escape(title)).replace("@@COUNT@@", str(len(rows)))
            .replace("@@CARDS@@", "\n".join(cards)))
    (folder / "index.html").write_text(page, encoding="utf-8")


def generate_html(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """Draw one plain HTML file per screen, with a shared stylesheet and script."""
    session = session_for(project)
    pages = document.screens(project)
    if not pages:
        raise ValueError("the specification names no screens to draw")
    if not (session.record / document.SRS_DIR / "handoff" / "app.md").is_file():
        raise ValueError("the SRS handoff is missing; the wireframes are drawn from its app.md")
    folder = html_path(project)
    carrying_on = not fresh and folder.is_dir()
    if not carrying_on:
        shutil.rmtree(folder, ignore_errors=True)
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    rows = web_app.route_rows(pages, ".html")
    relative = folder.relative_to(session.workspace).as_posix()
    doc = document.document(project).get("srs_document", {})
    title = str((doc.get("app_summary") or {}).get("app_name") or project)
    bus.phase(project, "wireframes", "Drawing the HTML wireframes", detail=f"{len(rows)} page(s) from the approved specification.",
              agent=bus.DESIGNER)
    resume = (f"The folder already has pages from a run that stopped: read what is in `{relative}`, keep it, and write the pages that "
              "are still missing." if carrying_on else "")
    start_fresh(session)
    ask = prompts.load("wireframe/html", request=request or "Generate low-fidelity wireframes as plain HTML.",
                       app=relative, routes=html_routes(rows), resume=resume)
    from prototype_agent import demo
    from server_modules import login_ui

    sign_in = demo.sign_in_route(doc)
    _gallery(folder, rows, title)
    with Review(project, session, folder, rows) as review:
        if not carrying_on or not any(file_stamp(folder / row["file"]) for row in rows):
            first = prompts.load("wireframe/html-first", page=html_routes(rows[:1]))
            result = session.run_task(ask + "\n\n" + first, audit=False, parallel_write_limit=4)
            if result.get("status") not in (None, "complete") and result.get("text"):
                bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)
        for index, row in enumerate(rows, 1):
            if session.cancelled:
                raise RunCancelled(project)
            page = folder / row["file"]
            bus.phase(project, "wireframes", row["name"], detail=f"Screen {index} of {len(rows)}", agent=bus.DESIGNER)
            if not file_stamp(page):
                session.run_unplanned(prompts.load("wireframe/html-page", app=relative, routes=html_routes(rows),
                                                    page=html_routes([row]), request=request or APPROVAL_PROMPT))
            if not file_stamp(page):
                continue
            _gallery(folder, rows, title)
            bus.wireframe_changed(project)
            if row["route"] == sign_in:
                for _ in range(2):
                    if not login_ui.issues([page]):
                        break
                    session.run_direct("Remove any visible demo account details and keep a blank sign-in form in "
                                       + page.relative_to(session.workspace).as_posix())
                if login_ui.issues([page]):
                    raise ValueError("wireframe login page still shows demo account details")
            review.page(row)
        review.save()
    _gallery(folder, rows, title)
    missing = [row["route"] for row in rows if not file_stamp(folder / row["file"])]
    _remember(session, error="")
    bus.phase(project, "wireframes", "Drawing the HTML wireframes", status="paused" if missing else "complete", agent=bus.DESIGNER)
    bus.wireframe_changed(project)
    accounts = demo.draw_accounts(doc)
    if accounts and not missing:
        route_list = [{"route": row["route"], "name": row["name"]} for row in rows]
        message = demo.accounts_message(accounts, route_list, sign_in)
        if message:
            bus.agent_msg(project, message.replace("made for reviewing the prototype", "for the upcoming prototype and build"),
                          title="Demo accounts", agent=bus.DESIGNER)
    return {"ok": not missing, "written": len(rows) - len(missing), "total": len(rows), "missing": missing,
            "url": f"/__agentforge/api/web/{project}/{HTML_DIR}/index.html", "folder": relative}


def generate(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    return generate_html(project, request, fresh=fresh)


def run_html(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """A whole HTML wireframe run: the session, what the studio shows, and what it says when it ends."""
    session = session_for(project)
    session.begin("wireframes", role=bus.DESIGNER)
    try:
        done = generate_html(project, request, fresh=fresh)
        session.finish(f"The HTML wireframes are ready: {done['written']} of {done['total']} page(s).")
        left = f" Not drawn: {', '.join(done['missing'][:8])}." if done["missing"] else ""
        bus.agent_msg(project, f"The HTML wireframes are ready: {done['written']} of {done['total']} page(s) in `{done['folder']}`. "
                               f"Open them at {done['url']} (or open `{done['folder']}/index.html` from the folder).{left}",
                      title="HTML wireframes ready", agent=bus.DESIGNER)
        return done
    except RunCancelled:
        session.stage = "idle"
        session.save_context()
        bus.phase(project, "wireframes", "Drawing the HTML wireframes", status="paused", agent=bus.DESIGNER)
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        bus.phase(project, "wireframes", "Drawing the HTML wireframes", status="failed", detail=str(exc)[:300], agent=bus.DESIGNER)
        raise


def run(project: str, request: str = "", fresh: bool = True) -> dict[str, Any]:
    """A whole wireframe run: the session, the progress the studio shows, and what it says when it ends."""
    session = session_for(project)
    session.begin("wireframes", role=bus.DESIGNER)
    bus.sync_state(project, "running", "Drawing the wireframes", source="wireframe")
    try:
        done = generate(project, request, fresh=fresh)
        ready, total = done["written"], done["total"]
        label = "Wireframes ready" if done["ok"] else "Wireframes paused"
        progress = f"{ready} of {total} HTML page(s) are ready in the Wireframe tab."
        session.finish(progress)
        bus.agent_msg(project, progress, title=label, agent=bus.DESIGNER)
        bus.sync_state(project, "clean" if done["ok"] else "paused", label, source="wireframe")
        return {"ok": done["ok"], "project": project, "ready": ready, "total": total, "missing": done["missing"]}
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


def edit(project: str, prompt: str, route: str = "", elements: Any = None,
         *, layout: tuple[str, str] | None = None) -> dict[str, Any]:
    """One change to the wireframes, asked for in words (and about one page, when it was asked for from that page), with the things
    on the page they pointed at, when they did."""
    request = " ".join(str(prompt or "").split())
    if not request:
        raise ValueError("describe the wireframe change first")
    if len(request) > MAX_REQUEST:
        raise ValueError(f"keep the wireframe request under {MAX_REQUEST:,} characters")
    session = session_for(project)
    if session.stage in ("srs", "wireframes"):
        raise ValueError("wait for the wireframe run to finish")
    app = source_path(project)
    html_mode = app == html_path(project)
    if not (built(project) if html_mode else (app / "index.html").is_file()):
        raise FileNotFoundError("there are no wireframes to change yet")
    session.begin("wireframe-edit", role=bus.DESIGNER)
    try:
        bus.user_msg(project, request, agent=bus.DESIGNER)
        where = f"The change is on the page for `{route}`." if route else ""
        if layout:
            source = "Find the component that renders this route in the existing wireframe."
            if html_mode:
                rows = web_app.route_rows(document.screens(project), ".html")
                page = next((row["file"] for row in rows if row["route"] == route), "")
                if not page or not file_stamp(app / page):
                    raise ValueError("open a drawn wireframe page before editing its layout")
                source = f"The wireframe source for this route is `{page}`."
            web_app.edit_layout(session, app, route, source, layout, bundle_preview=not html_mode)
        elif html_mode:
            rows = web_app.route_rows(document.screens(project), ".html")
            session.run_direct(prompts.load("wireframe/edit-html", request=request + pointed.describe(elements),
                                            app=app.relative_to(session.workspace).as_posix(), where=where,
                                            routes=html_routes(rows)))
            title = str((document.document(project).get("srs_document", {}).get("app_summary") or {}).get("app_name") or project)
            _gallery(app, rows, title)
        else:
            session.run_direct(prompts.load("wireframe/edit", request=request + pointed.describe(elements),
                                            skill=web_app.stage_skill(session.workspace), app=_relative(project), where=where))
            web_app.build_for(session, project, KIND, agent=bus.DESIGNER)
        bus.wireframe_changed(project)
        session.finish("Wireframes updated.")
        return {"ok": True, "route": route}
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise
