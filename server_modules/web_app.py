"""Preview tooling for authored HTML prototypes and saved React previews.

The Studio publishes the prototype as one HTML file. Saved React projects
still use the Vite kit. Static wireframes are served from their own folder.

    <workspace>/.agentforge/wireframe/app/      the wireframe: source, and `bundle.html`, the page the studio shows
    <workspace>/.agentforge/prototype/app/      the prototype: a new app, written after reading the wireframes
    <state>/web-kit-custom/                     the packages, installed once and linked into new apps as `node_modules`

Vite and `vite-plugin-singlefile` inline scripts, styles and small images in `bundle.html`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from . import bus, config, html_prototype, prompts

SKILL = "custom-ui"
SKILL_SOURCE = config.PROMPTS / "skills" / SKILL
KIT_SOURCE = Path(__file__).resolve().parent / "web_kit"
RUNTIME = KIT_SOURCE / "runtime"
VITE_CONFIG = "agentforge.vite.config.mjs"
KINDS = ("wireframe", "prototype")
BUNDLE = "bundle.html"
BUILT = ".built"
# Only the policy of the page the studio frames: the app can run scripts and style itself and show any picture, but it can
# neither call out nor load anything else (but Google's fonts), so nothing it was written to do can reach the studio's own address.
PREVIEW_POLICY = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
                  "img-src * data: blob:; font-src * data:; media-src * data: blob:; connect-src 'none'; frame-src 'none'; "
                  "base-uri 'none'; form-action 'none'")
# A plain HTML wireframe has its own stylesheet and script beside its pages: they may be read from the same address, and nothing else.
HTML_POLICY = ("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' * data: blob:; "
               "font-src data:; connect-src 'none'; frame-src 'self'; base-uri 'none'; form-action 'none'")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_REPARSE_POINT = 0x400
_kit_lock = threading.Lock()
_build_locks: dict[str, threading.Lock] = {}
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class BuildFailed(RuntimeError):
    """The app does not bundle, and what the bundler said."""


# --- the packages ------------------------------------------------------------------------------------------------------------

def legacy_kit(app: Path) -> bool:
    """Older scaffolds include the component registry config and may still import its packages."""
    return (app / "components.json").is_file()


def kit_dir(legacy: bool = False) -> Path:
    return config.STATE / ("web-kit" if legacy else "web-kit-custom")


def _kit_source(legacy: bool) -> Path:
    return KIT_SOURCE / "legacy" if legacy else KIT_SOURCE


def _signature(legacy: bool = False) -> str:
    digest = hashlib.sha256()
    for name in ("package.json", "package-lock.json"):
        path = _kit_source(legacy) / name
        if path.is_file():
            digest.update(name.encode() + path.read_bytes())
    return digest.hexdigest()


def kit_ready(legacy: bool = False) -> bool:
    folder = kit_dir(legacy)
    marker = folder / ".installed"
    return (marker.is_file() and marker.read_text(encoding="utf-8").strip() == _signature(legacy)
            and (folder / "node_modules" / "vite" / "bin" / "vite.js").is_file())


def node_exe() -> str | None:
    return shutil.which("node") or shutil.which("node.exe")


def _npm() -> str | None:
    return shutil.which("npm") or shutil.which("npm.cmd")


def _run(args: list[str], cwd: Path, timeout: int, env: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        done = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, creationflags=_NO_WINDOW, env={**os.environ, **(env or {})})
    except subprocess.TimeoutExpired:
        return False, f"{Path(args[0]).name} did not finish in {timeout} seconds"
    except OSError as exc:
        return False, str(exc)
    return done.returncode == 0, _ANSI.sub("", (done.stdout or "") + (done.stderr or "")).strip()


def prepare_kit(legacy: bool = False) -> tuple[bool, str]:
    """Install the packages every app is built with, once. Safe to call every time: it does nothing when they are there."""
    with _kit_lock:
        folder = kit_dir(legacy)
        folder.mkdir(parents=True, exist_ok=True)
        config_file = folder / VITE_CONFIG
        vite_config = (RUNTIME / "vite.config.mjs").read_bytes()
        if not config_file.is_file() or config_file.read_bytes() != vite_config:
            config_file.write_bytes(vite_config)
        if kit_ready(legacy):
            return True, ""
        npm = _npm()
        if not npm or not node_exe():
            return False, "Node.js (node and npm) was not found, and the wireframe and the prototype are built with it"
        for name in ("package.json", "package-lock.json"):
            source = _kit_source(legacy) / name
            if source.is_file():
                shutil.copyfile(source, folder / name)
            else:
                (folder / name).unlink(missing_ok=True)
        command = [npm, "ci" if (folder / "package-lock.json").is_file() else "install",
                   "--no-audit", "--no-fund", "--loglevel=error"]
        ok, text = _run(command, folder, timeout=1500)
        if not ok and "ci" in command:
            # A lock that does not fit this computer's npm is not a reason to stop: install what the file names.
            command[1] = "install"
            ok, text = _run(command, folder, timeout=1500)
        if not ok or not (folder / "node_modules" / "vite" / "bin" / "vite.js").is_file():
            return False, text[-1500:] or "the packages could not be installed"
        (folder / ".installed").write_text(_signature(legacy), encoding="utf-8")
        return True, ""


# --- the skill and the app ---------------------------------------------------------------------------------------------------

def stage_skill(workspace: Path) -> str:
    """Put the skill where the project's agent can read it, and say where (relative to the workspace)."""
    relative = f"{config.RECORD_DIR}/skills/{SKILL}"
    target = workspace / relative
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SKILL_SOURCE / "SKILL.md", target / "SKILL.md")
    return relative


def app_dir(workspace: Path, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown kind of app: {kind}")
    return workspace / config.RECORD_DIR / kind / "app"


def page_files(routes: list[str], *, reserved: tuple[str, ...] = ()) -> dict[str, str]:
    """The page file (under `src/pages`, without its extension) of every route: `/` is `home`, `/orders/[id]` is `orders-id`."""
    out: dict[str, str] = {}
    used = set(reserved)
    for route in routes:
        parts = [re.sub(r"^\[(.+)\]$|^:", lambda m: m.group(1) or "", part) for part in str(route).strip("/").split("/") if part]
        stem = re.sub(r"[^a-z0-9]+", "-", "-".join(parts).lower()).strip("-") or "home"
        name, n = stem, 2
        while name in used:
            name, n = f"{stem}-{n}", n + 1
        used.add(name)
        out[str(route)] = name
    return out


def _ts(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def route_rows(pages: list[dict[str, Any]], extension: str = "") -> list[dict[str, Any]]:
    """Every screen of the specification and the file it is drawn in (`extension`: ".html" for a plain HTML page)."""
    files = page_files([str(p["route"]) for p in pages], reserved=("index",) if extension == ".html" else ())
    return [{"route": str(p["route"]), "name": str(p.get("page_name") or p.get("name") or p["route"]),
             "file": files[str(p["route"])] + extension,
             "roles": [str(r) for r in (p.get("allowed_roles") or p.get("roles") or [])],
             "signedIn": bool(p.get("login_required", p.get("signed_in", False)))} for p in pages]


def write_routes(app: Path, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`src/routes.ts`: every screen of the specification and the page file it is drawn in. Returns the rows."""
    rows = route_rows(pages)
    path = app / "src" / "routes.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// Written by the Studio from the specification. Do not edit: add or change pages in src/pages.\n"
                    "export type RouteDef = { route: string; name: string; file: string; roles: string[]; signedIn: boolean };\n"
                    f"export const routes: RouteDef[] = {_ts(rows)};\n", encoding="utf-8")
    return rows


def write_demo(app: Path, accounts: list[dict[str, Any]] | None = None, sign_in: str = "", sign_up: dict | None = None) -> None:
    """`src/demo.ts`: the fictitious sign-in accounts, one per role (none for a wireframe or a product without sign-in)."""
    rows = [{"role": a["role"], "roleKey": a["role_key"], "name": a["display_name"], "email": a["email"], "password": a["password"],
             "landsOn": a["lands_on"], "canOpen": [p["route"] for p in a.get("can_open") or []]} for a in accounts or []]
    up = {"route": sign_up["route"], "roleKey": sign_up["role_key"]} if sign_up and accounts else None
    path = app / "src" / "demo.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// Written by the Studio from the specification. Do not edit.\n"
                    "export type Account = { role: string; roleKey: string; name: string; email: string; password: string; "
                    "landsOn: string; canOpen: string[] };\n"
                    f"export const accounts: Account[] = {_ts(rows)};\n"
                    f"export const signInRoute: string = {json.dumps(sign_in or '')};\n"
                    f"export const signUp: {{ route: string; roleKey: string }} | null = {json.dumps(up)};\n", encoding="utf-8")


def create_app(app: Path, pages: list[dict[str, Any]], *, accounts: list[dict] | None = None,
               sign_in: str = "", sign_up: dict | None = None) -> list[dict[str, Any]]:
    """Provide preview runtime and project data while leaving the application source to the agent."""
    rows = write_routes(app, pages)
    write_demo(app, accounts, sign_in, sign_up)
    sync_kit_files(app)
    link_node_modules(app)
    return rows


# --- links and copies --------------------------------------------------------------------------------------------------------

def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & _REPARSE_POINT)
    except OSError:
        return False


def drop_link(path: Path) -> None:
    """Remove a link to the packages without touching what it points at."""
    if not _is_link(path):
        return
    try:
        path.unlink()
    except (OSError, PermissionError):
        os.rmdir(path)      # a Windows junction is a directory to the system


def link_node_modules(app: Path) -> None:
    link, target = app / "node_modules", kit_dir(legacy_kit(app)) / "node_modules"
    if _is_link(link):
        try:
            if link.resolve() == target.resolve():
                return
        except OSError:
            pass
        drop_link(link)
    if link.exists():
        return                              # a real folder: the app has packages of its own
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, creationflags=_NO_WINDOW)
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_app(app: Path) -> None:
    drop_link(app / "node_modules")
    shutil.rmtree(app, ignore_errors=True)


# --- bundling ----------------------------------------------------------------------------------------------------------------

def _source_files(app: Path):
    if app.name == "wireframe-html":
        yield from sorted(app.glob("*.html"))
        yield from sorted(file for file in (app / "assets").rglob("*") if file.is_file())
        return
    if (app / html_prototype.MANIFEST).is_file():
        yield from (file for file in html_prototype.sources(app) if file.is_file())
        return
    for item in sorted(app.iterdir()) if app.is_dir() else ():
        if item.is_file() and (item.name in {"index.html", "package.json", "tsconfig.json"}
                               or item.name.startswith(("tailwind.config.", "vite.config.", "postcss.config."))):
            yield item
    yield from sorted(p for p in (app / "src").rglob("*") if p.is_file()) if (app / "src").is_dir() else ()


def fingerprint(app: Path) -> str:
    """What the app's source says, to tell a bundle that is current from one the agent has edited since."""
    digest = hashlib.sha256()
    for path in _source_files(app):
        digest.update(path.relative_to(app).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def edit_layout(session, app: Path, route: str, source: str, layout: tuple[str, str],
                *, bundle_preview: bool = True) -> None:
    """Run a focused layout edit and require an authored source change before publishing."""
    operation, details = layout
    before = fingerprint(app)
    session.run_direct(prompts.load(f"shared/{operation}-element", app=app.relative_to(session.workspace).as_posix(),
                                    route=route, source=source, details=details), thinking_level="low")
    if fingerprint(app) == before:
        failure = {"move": "move the selected element", "resize": "resize the selected element",
                   "layout": "apply the position and size changes", "insert": "add the new element"}[operation]
        raise ValueError(f"the model could not {failure}")
    if bundle_preview:
        made, error = bundle(app)
        if not made:
            raise BuildFailed(error)


def built(app: Path) -> bool:
    return (app / BUNDLE).is_file() and (app / BUNDLE).stat().st_size > 0


def stale(app: Path) -> bool:
    marker = app / BUILT
    return not built(app) or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != fingerprint(app)


# What the Studio owns in every app and writes again each time it is bundled: the agent imports them and never edits them, so an app made
# before they changed gets the change too.
KIT_OWNED = ("src/lib/router.tsx", "src/lib/session.tsx")


def sync_kit_files(app: Path) -> None:
    for name in KIT_OWNED:
        source, target = RUNTIME / Path(name).name, app / name
        if source.is_file() and (not target.is_file() or target.read_bytes() != source.read_bytes()):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def bundle(app: Path) -> tuple[bool, str]:
    """Bundle the app into one HTML file. Returns (ok, what the bundler said)."""
    if (app / html_prototype.MANIFEST).is_file():
        with _build_locks.setdefault(str(app), threading.Lock()):
            preview = app / BUNDLE
            pending = preview.with_suffix(".tmp")
            try:
                html = html_prototype.compose(app)
                pending.write_text(html, encoding="utf-8")
                pending.replace(preview)
                (app / BUILT).write_text(fingerprint(app), encoding="utf-8")
            except (OSError, ValueError, KeyError) as exc:
                return False, str(exc)
            finally:
                pending.unlink(missing_ok=True)
        return True, "HTML preview published."
    legacy = legacy_kit(app)
    ok, text = prepare_kit(legacy)
    if not ok:
        return False, text
    link_node_modules(app)
    sync_kit_files(app)
    with _build_locks.setdefault(str(app), threading.Lock()):
        folder = kit_dir(legacy)
        command = [node_exe() or "node", str(folder / "node_modules" / "vite" / "bin" / "vite.js"), "build"]
        if not any((app / f"vite.config.{ext}").is_file() for ext in ("js", "mjs", "ts", "cjs", "mts", "cts")):
            command.extend(("--config", str(folder / VITE_CONFIG)))
        ok, text = _run(command, app, timeout=600, env={"NODE_ENV": "production", "FORCE_COLOR": "0"})
        page = app / "dist" / "index.html"
        if not ok or not page.is_file():
            return False, text[-3000:] or "the bundler produced no page"
        shutil.copyfile(page, app / BUNDLE)
        (app / BUILT).write_text(fingerprint(app), encoding="utf-8")
        shutil.rmtree(app / "dist", ignore_errors=True)
        return True, text[-1000:]


# --- retyping words on a page ------------------------------------------------------------------------------------------------

# Skip the legacy starter components and generated route, session and configuration files.
_NOT_WORDS = ("components/ui/", "lib/router.tsx", "lib/session.tsx", "routes.ts", "demo.ts", "vite-env.d.ts")


def _spelling(word: str) -> str:
    """A word as the source may write it: the characters that need escaping in JSX or in a string have more than one spelling."""
    out = []
    for char in word:
        if char == "&":
            out.append(r"(?:&amp;|&)")
        elif char == "'":
            out.append(r"(?:&apos;|&#39;|\\'|')")
        elif char == '"':
            out.append(r'(?:&quot;|\\"|")')
        elif char == "<":
            out.append(r"(?:&lt;|<)")
        elif char == ">":
            out.append(r"(?:&gt;|>)")
        else:
            out.append(re.escape(char))
    return "".join(out)


def _literal(text: str, quote: str) -> str:
    text = text.replace("\\", "\\\\").replace(quote, "\\" + quote).replace("\r", "").replace("\n", "\\n")
    return text.replace("${", "\\${") if quote == "`" else text


def _jsx_text(text: str) -> str:
    for char, escaped in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("{", "&#123;"), ("}", "&#125;")):
        text = text.replace(char, escaped)
    return " ".join(text.split())


def edit_text(app: Path, old: str, new: str) -> dict[str, Any]:
    """Change the words `old` on a page to `new` in the app's source, when they are written there in exactly one place.

    The words must be a whole piece of text (the text of one element, or one whole string), so that "Cart" is never found inside
    "Cartographer". Returns {"ok": True, "file", "line"}, or {"ok": False, "reason"}: "found in several places" when a swap could change
    the wrong one, "built in code" when no file writes them out that way (the app puts them together, or they are not text at all)."""
    old = " ".join(str(old or "").split())
    new = str(new or "").strip()
    if not old:
        return {"ok": False, "reason": "no words"}
    if not new:
        return {"ok": False, "reason": "the new words are empty"}
    pattern = re.compile(
        r"(?P<pre>^|[>\"'`}])(?P<space1>[ \t\r\n]*)(?P<text>" + r"[ \t\r\n]+".join(_spelling(word) for word in old.split())
        + r")(?P<space2>[ \t\r\n]*)(?P<post>$|[<\"'`{])", re.MULTILINE)
    found = []
    source = app / "src"
    candidates = [path for path in source.rglob("*") if path.is_file() and path.suffix in (".tsx", ".ts", ".jsx", ".js")]
    if (app / html_prototype.MANIFEST).is_file():
        candidates.extend([app / "index.html", *(app / "pages").glob("*.html")])
    elif app.name == "wireframe-html":
        candidates.extend(path for path in app.glob("*.html") if path.name != "index.html")
    for path in sorted(candidates):
        if not path.is_file() or any(part in path.relative_to(app).as_posix() for part in _NOT_WORDS):
            continue
        raw = path.read_bytes().decode("utf-8", errors="replace")
        for match in pattern.finditer(raw):
            pre, post = match.group("pre"), match.group("post")
            if path.suffix == ".html" and (pre != ">" or post != "<"):
                continue
            if pre in "\"'`" and pre:
                if post != pre:
                    continue                        # a quote that closes something else: these words are only part of a string
                kind = pre
            elif post in "\"'`" and post:
                continue
            else:
                kind = ""
            found.append((path, raw, match, kind))
    if not found:
        return {"ok": False, "reason": "built in code"}
    if len(found) > 1:
        return {"ok": False, "reason": "found in several places"}
    path, raw, match, kind = found[0]
    replacement = _literal(new, kind) if kind else _jsx_text(new)
    start, end = match.start("text"), match.end("text")
    path.write_bytes((raw[:start] + replacement + raw[end:]).encode("utf-8"))
    return {"ok": True, "file": path.relative_to(app).as_posix(), "line": raw.count("\n", 0, start) + 1, "original": raw}


_SELFTEST = re.compile(r'<pre id="af-selftest"[^>]*>(.*?)</pre>', re.DOTALL)
_EMPTY_ROOT = re.compile(r'<div id="root"[^>]*>\s*</div>')
_EMPTY_HTML_MOUNT = re.compile(r'<main\b[^>]*\bid="af-page"[^>]*>\s*</main>')


def check_pages(app: Path) -> list[tuple[str, str]] | None:
    """Open every screen of the bundled app in a browser that is already on the computer; the screens that crash, as (route, what
    went wrong). `[]` when none does; None when it could not be checked (no browser, or the page said nothing).

    A page can bundle and still crash the moment it is opened (a name it uses that is not there), which no bundler can see."""
    import html as htmllib
    import tempfile

    try:
        from ollama_terminal import screenshot

        browser = screenshot.working_browser()
        if not browser or not built(app):
            return None
        with tempfile.TemporaryDirectory(prefix="agentforge-check-") as folder:
            page = Path(folder) / "app.html"
            shutil.copyfile(app / BUNDLE, page)
            dom = screenshot.dump_dom(page, "?selftest=1#/", browser=browser)
    except Exception:  # noqa: BLE001 - a check that cannot run is not a reason to stop
        return None
    found = _SELFTEST.search(dom or "")
    if not found:
        if (app / html_prototype.MANIFEST).is_file() and _EMPTY_HTML_MOUNT.search(dom or ""):
            return [("/", "The HTML preview opened an empty screen. Check index.html, the route fragment and assets/prototype.js.")]
        if _EMPTY_ROOT.search(dom or ""):
            return [("/", "The React entry did not mount the app. Check src/main.tsx and the Router pages prop.")]
        return None
    try:
        return [(str(row["route"]), str(row["error"])[:300]) for row in json.loads(htmllib.unescape(found.group(1)))]
    except (ValueError, KeyError, TypeError):
        return None


def _crashing(rows: list[tuple[str, str]]) -> str:
    return ("These pages bundle, but crash when opened. Fix the affected source pages and their shared code:\n\n"
            + "\n".join(f"- `{route}`: {error}" for route, error in rows[:20]))


def ensure_built(app: Path, repair: Callable[[str], None] | None = None, rounds: int = 2) -> None:
    """Bundle the app and open its screens. When it does not bundle, or a screen crashes, give what was said to `repair` (the agent
    fixes the files) and try again. An app that does not bundle after the agent's tries is an error; a screen that still crashes is
    not: it shows what is wrong in its own place, and the rest of the app works.

    The two have their own tries: a repair of a crashing screen that breaks the bundle (one took out a page's opening tag) still
    gets its `rounds` repairs of the bundle, rather than ending with the tries a crash had used up."""
    crash_tries = build_tries = 0
    while True:
        ok, text = bundle(app)
        if ok:
            crashing = check_pages(app)
            if not crashing:
                return
            text = _crashing(crashing)
            if repair is None or crash_tries >= rounds:
                return
            crash_tries += 1
        else:
            if repair is None or build_tries >= rounds:
                raise BuildFailed(text)
            build_tries += 1
        repair(text)


def build_for(session, project: str, kind: str, agent: str = "") -> None:
    """Bundle the project's `kind` app; when the bundler complains, the project's agent fixes the files and it is bundled again.

    Raises `BuildFailed` when it still does not bundle after the agent has tried."""
    app = app_dir(session.workspace, kind)
    relative = app.relative_to(session.workspace).as_posix()

    def repair(error: str) -> None:
        bus.log(project, "WARN", f"The {kind} does not bundle yet; the agent is fixing it.", agent=agent or bus.DESIGNER)
        session.run_direct(prompts.load("shared/build-fix", app=relative, error=error))
        if session.cancelled:
            from .session import RunCancelled
            raise RunCancelled(project)

    bus.log(project, "INFO", f"Bundling the {kind} into one page.", agent=agent or bus.DESIGNER)
    ensure_built(app, repair)
    bus.log(project, "SUCCESS", f"The {kind} is bundled ({(app / BUNDLE).stat().st_size // 1024:,} KB).", agent=agent or bus.DESIGNER)


# --- what the studio asks for ------------------------------------------------------------------------------------------------

def page(app: Path) -> bytes:
    """The bundled app, for the studio's preview frame."""
    path = app / BUNDLE
    if not path.is_file():
        raise FileNotFoundError("the app is not bundled yet")
    return path.read_bytes()


_HEAD = re.compile(rb"<head[^>]*>", re.IGNORECASE)


def preview_page(html: bytes, policy: str = PREVIEW_POLICY) -> bytes:
    """The bundled page with its policy first in the head, so nothing the app is written to do can call out."""
    meta = b'<meta http-equiv="Content-Security-Policy" content="' + policy.encode("ascii") + b'">'
    found = _HEAD.search(html)
    return html[:found.end()] + meta + html[found.end():] if found else meta + html


def source_files(root: Path):
    """Every file under `root` that is the project's own: never the packages, a build or the bundle."""
    for folder, folders, names in os.walk(root):
        folders[:] = sorted(d for d in folders if d not in ("node_modules", "dist", ".parcel-cache"))
        for name in sorted(names):
            if name not in (BUNDLE, BUILT):
                yield Path(folder) / name
