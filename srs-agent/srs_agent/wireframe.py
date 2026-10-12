"""The wireframes: a low-fidelity React app the project's agent builds with Anthropic's web-artifacts-builder skill.

The agent reads the skill and `app.md` (what the customer asked for, and the site map) and writes one page per screen with its own file
tools, so every file it writes appears in the chat as it happens. Code here is only what it cannot do for itself: create the app
(the skill's first step), say which screens the specification names, and bundle the finished app into the one page the studio shows
(the skill's last step). What the pages look like, and how they hang together, is the agent's.

    <workspace>/.agentforge/wireframe/app/     the app: `src/pages/<page>.tsx` for every screen, and `bundle.html`
"""
from __future__ import annotations

import html
import shutil
from typing import Any

from server_modules import bus, pointed, prompts, web_app
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
    shadcn = web_app.stage_shadcn(session.workspace)

    bus.phase(project, "wireframes", "Drawing the wireframes", detail=f"{len(rows)} page(s) from the approved specification.",
              agent=bus.DESIGNER)
    resume = (f"The app already has pages from a run that stopped: read what is in `{_relative(project)}/src/pages`, keep it, "
              "and write the pages that are still missing." if carrying_on else "")
    result = session.run_task(
        prompts.load("wireframe/generate", request=request or APPROVAL_PROMPT, skill=skill, shadcn=shadcn, app=_relative(project),
                     routes=routes_text(rows), resume=resume),
        audit=False, parallel_write_limit=4)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") not in (None, "complete") and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)

    from prototype_agent import demo
    from server_modules import login_ui

    doc = document.document(project).get("srs_document", {})
    sign_in = demo.sign_in_route(doc)
    login_pages = [app / "src" / "pages" / f"{row['file']}.tsx" for row in rows
                   if row["route"] == sign_in]
    for _ in range(2):
        flagged = login_ui.issues(login_pages)
        if not flagged:
            break
        session.run_direct("Remove visible demo accounts, seeded emails/passwords and demo buttons from these wireframe "
                           "login pages. Leave a normal blank sign-in form and preserve navigation: " + ", ".join(flagged))
    if login_ui.issues(login_pages):
        raise ValueError("wireframe login page still shows demo account details")
    web_app.build_for(session, project, KIND, agent=bus.DESIGNER)
    _remember(session, error="")
    bus.phase(project, "wireframes", "Drawing the wireframes", status="complete", agent=bus.DESIGNER)
    bus.wireframe_changed(project)
    accounts = demo.draw_accounts(doc)
    message = demo.accounts_message(accounts, [{"route": r["route"], "name": r["name"]} for r in rows],
                                    sign_in) if accounts else ""
    if message:
        bus.agent_msg(project, message.replace("made for reviewing the prototype", "for the upcoming prototype and build"),
                      title="Demo accounts", agent=bus.DESIGNER)
    return result


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


def _gallery(folder, rows: list[dict[str, Any]], title: str) -> None:
    cards = []
    for row in rows:
        if not (folder / row["file"]).is_file():
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
    """Draw the same wireframes as plain HTML pages (one file per screen, one stylesheet, one script) beside the React app, to compare
    them. Nothing of the React app is touched."""
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
    title = str((document.document(project).get("srs_document", {}).get("app_summary") or {}).get("app_name") or project)
    routes = "\n".join(f"- `{row['route']}` — {row['name']}"
                       + (f" (signed in: {', '.join(row['roles']) or 'any role'})" if row["signedIn"] else "") + f" — `{row['file']}`"
                       for row in rows)
    bus.phase(project, "wireframes", "Drawing the HTML wireframes", detail=f"{len(rows)} page(s) from the approved specification.",
              agent=bus.DESIGNER)
    resume = (f"The folder already has pages from a run that stopped: read what is in `{relative}`, keep it, and write the pages that "
              "are still missing." if carrying_on else "")
    result = session.run_task(prompts.load("wireframe/html", request=request or "Generate low-fidelity wireframes as plain HTML.",
                                           app=relative, routes=routes, resume=resume), audit=False, parallel_write_limit=4)
    if session.cancelled:
        raise RunCancelled(project)
    if result.get("status") not in (None, "complete") and result.get("text"):
        bus.log(project, "WARN", f"The agent stopped early: {str(result['text'])[:300]}", agent=bus.DESIGNER)
    _gallery(folder, rows, title)
    missing = [row["route"] for row in rows if not (folder / row["file"]).is_file()]
    bus.phase(project, "wireframes", "Drawing the HTML wireframes", status="complete", agent=bus.DESIGNER)
    return {"ok": not missing, "written": len(rows) - len(missing), "total": len(rows), "missing": missing,
            "url": f"/__agentforge/api/web/{project}/{HTML_DIR}/index.html", "folder": relative}


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


def edit(project: str, prompt: str, route: str = "", elements: Any = None) -> dict[str, Any]:
    """One change to the wireframes, asked for in words (and about one page, when it was asked for from that page), with the things
    on the page they pointed at, when they did."""
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
        session.run_direct(prompts.load("wireframe/edit", request=request + pointed.describe(elements),
                                        skill=web_app.stage_skill(session.workspace),
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
