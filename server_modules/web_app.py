"""The React apps the wireframe and the prototype are made of.

Both are the same kind of thing: a small Vite + React + Tailwind + shadcn/ui app the project's agent writes with its own file tools,
following Anthropic's `web-artifacts-builder` skill (`prompts/skills/web-artifacts-builder/`). The skill's steps are done here, in code,
because they are the same for every app: the project is created (step 1) and the finished app is bundled into one HTML file (step 3).
What the pages look like is the agent's.

    <workspace>/.agentforge/wireframe/app/      the wireframe: source, and `bundle.html`, the page the studio shows
    <workspace>/.agentforge/prototype/app/      the prototype: a new app, written after reading the wireframes
    <state>/web-kit/                            the packages, installed once and linked into every app as `node_modules`

An app is bundled with Vite and `vite-plugin-singlefile` (the skill bundles with Parcel; Vite is what the app is built with, so it
bundles itself), which leaves every script, style and small image inlined in `bundle.html`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import threading
from pathlib import Path
from typing import Any, Callable

from . import bus, config, prompts

SKILL = "web-artifacts-builder"
SKILL_SOURCE = config.PROMPTS / "skills" / SKILL
# shadcn/ui's own skill (https://github.com/shadcn-ui/ui, `skills/shadcn`, unchanged) and the components of that repository the skill's
# archive does not have (`web_kit/components`, ported to Tailwind 3 and the single Radix packages the kit installs).
SHADCN = "shadcn"
SHADCN_SOURCE = config.PROMPTS / "skills" / SHADCN
KIT_SOURCE = Path(__file__).resolve().parent / "web_kit"
COMPONENTS_ARCHIVE = SKILL_SOURCE / "scripts" / "shadcn-components.tar.gz"
KINDS = ("wireframe", "prototype")
BUNDLE = "bundle.html"
BUILT = ".built"
# Only the policy of the page the studio frames: the app can run scripts and style itself and show any picture, but it can
# neither call out nor load anything else (but Google's fonts), so nothing it was written to do can reach the studio's own address.
PREVIEW_POLICY = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
                  "img-src * data: blob:; font-src * data:; media-src * data: blob:; connect-src 'none'; frame-src 'none'; "
                  "base-uri 'none'; form-action 'none'")
# A plain HTML wireframe has its own stylesheet and script beside its pages: they may be read from the same address, and nothing else.
HTML_POLICY = ("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src * data: blob:; "
               "font-src data:; connect-src 'none'; frame-src 'self'; base-uri 'none'; form-action 'none'")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_REPARSE_POINT = 0x400
_kit_lock = threading.Lock()
_build_locks: dict[str, threading.Lock] = {}
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class BuildFailed(RuntimeError):
    """The app does not bundle, and what the bundler said."""


# --- the packages ------------------------------------------------------------------------------------------------------------

def kit_dir() -> Path:
    return config.STATE / "web-kit"


def _signature() -> str:
    digest = hashlib.sha256()
    for name in ("package.json", "package-lock.json"):
        path = KIT_SOURCE / name
        if path.is_file():
            digest.update(name.encode() + path.read_bytes())
    return digest.hexdigest()


def kit_ready() -> bool:
    marker = kit_dir() / ".installed"
    return (marker.is_file() and marker.read_text(encoding="utf-8").strip() == _signature()
            and (kit_dir() / "node_modules" / "vite" / "bin" / "vite.js").is_file())


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


def prepare_kit() -> tuple[bool, str]:
    """Install the packages every app is built with, once. Safe to call every time: it does nothing when they are there."""
    with _kit_lock:
        if kit_ready():
            return True, ""
        npm = _npm()
        if not npm or not node_exe():
            return False, "Node.js (node and npm) was not found, and the wireframe and the prototype are built with it"
        folder = kit_dir()
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("package.json", "package-lock.json"):
            source = KIT_SOURCE / name
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
        (folder / ".installed").write_text(_signature(), encoding="utf-8")
        return True, ""


# --- the skill and the app ---------------------------------------------------------------------------------------------------

def stage_skill(workspace: Path) -> str:
    """Put the skill where the project's agent can read it, and say where (relative to the workspace)."""
    relative = f"{config.RECORD_DIR}/skills/{SKILL}"
    target = workspace / relative
    target.mkdir(parents=True, exist_ok=True)
    for name in ("SKILL.md", "LICENSE.txt"):
        shutil.copyfile(SKILL_SOURCE / name, target / name)
    return relative


def stage_shadcn(workspace: Path) -> str:
    """Put shadcn/ui's skill (its `SKILL.md`, the `rules/` and the references) where the project's agent can read it."""
    relative = f"{config.RECORD_DIR}/skills/{SHADCN}"
    target = workspace / relative
    for source in sorted(p for p in SHADCN_SOURCE.rglob("*") if p.is_file()):
        copy = target / source.relative_to(SHADCN_SOURCE)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, copy)
    return relative


def app_dir(workspace: Path, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown kind of app: {kind}")
    return workspace / config.RECORD_DIR / kind / "app"


def page_files(routes: list[str]) -> dict[str, str]:
    """The page file (under `src/pages`, without its extension) of every route: `/` is `home`, `/orders/[id]` is `orders-id`."""
    out: dict[str, str] = {}
    used: set[str] = set()
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
    files = page_files([str(p["route"]) for p in pages])
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


def _extract_components(app: Path) -> None:
    """The skill's shadcn/ui components (`components/ui`, `lib/utils.ts`, `hooks`), into the app's `src`."""
    root = (app / "src").resolve()
    with tarfile.open(COMPONENTS_ARCHIVE) as archive:
        for member in archive.getmembers():
            target = (root / member.name).resolve()
            if not target.is_relative_to(root) or not (member.isfile() or member.isdir()):
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source:
                    target.write_bytes(source.read())


def _add_components(app: Path) -> None:
    """The shadcn/ui components the skill's archive lacks (`Field`, `InputGroup`, `Empty`, `Spinner`...), beside the others; one the
    agent already has is left as it is, except a copy with the one mistake an earlier kit had in it (`Slot.Root`, which is the name in
    the single Radix package; the kit's own is `Slot`)."""
    target = app / "src" / "components" / "ui"
    target.mkdir(parents=True, exist_ok=True)
    for source in sorted((KIT_SOURCE / "components").glob("*.tsx")):
        copy = target / source.name
        if not copy.exists() or "Slot.Root" in copy.read_text(encoding="utf-8", errors="replace"):
            shutil.copyfile(source, copy)


# A wireframe is black, white and grey. The Studio writes this palette into a wireframe's Tailwind config, so that no page can bring colour
# in whatever it says: every colour name Tailwind has (`red-500`, `green-600`, ...) is the same grey scale, and the shadcn `destructive`
# colour is a dark grey.
GREY_SCALE = {"50": "#fafafa", "100": "#f4f4f5", "200": "#e4e4e7", "300": "#d4d4d8", "400": "#a1a1aa", "500": "#71717a",
              "600": "#52525b", "700": "#3f3f46", "800": "#27272a", "900": "#18181b", "950": "#09090b"}
COLOUR_NAMES = ("slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow", "lime", "green", "emerald", "teal",
                "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia", "pink", "rose")
DESTRUCTIVE_GREY = "0 0% 25%"


def wireframe_tailwind(base: str) -> str:
    """The kit's Tailwind config with the greys-only palette on the end."""
    config = base.replace("module.exports = {", "const config = {", 1)
    return (config.rstrip() + "\n\n// Written by the Studio: a wireframe is black, white and grey, so every colour name is the same grey scale here and the\n"
            "// shadcn `destructive` colour is a dark grey. Do not edit.\n"
            f"const grey = {json.dumps(GREY_SCALE)};\n"
            "config.theme.colors = { transparent: \"transparent\", current: \"currentColor\", inherit: \"inherit\", "
            "white: \"#ffffff\", black: \"#000000\" };\n"
            f"for (const name of {json.dumps(list(COLOUR_NAMES))}) config.theme.colors[name] = grey;\n"
            "config.theme.extend.colors.destructive = { DEFAULT: \"#3f3f46\", foreground: \"#fafafa\" };\n"
            "module.exports = config;\n")


def lock_palette(app: Path) -> None:
    """Make a wireframe app grey: its Tailwind config is the kit's with the palette above, and its `--destructive` is a grey."""
    if app.parent.name != "wireframe":
        return
    source = KIT_SOURCE / "app" / "tailwind.config.cjs"
    config = app / "tailwind.config.cjs"
    if source.is_file():
        wanted = wireframe_tailwind(source.read_text(encoding="utf-8"))
        if not config.is_file() or config.read_text(encoding="utf-8") != wanted:
            config.write_text(wanted, encoding="utf-8")
    css = app / "src" / "index.css"
    if css.is_file():
        text = css.read_text(encoding="utf-8")
        grey = re.sub(r"(--destructive:\s*)[^;]+;", lambda m: m.group(1) + DESTRUCTIVE_GREY + ";", text)
        if grey != text:
            css.write_text(grey, encoding="utf-8")


def create_app(app: Path, title: str, pages: list[dict[str, Any]], *, accounts: list[dict] | None = None,
               sign_in: str = "", sign_up: dict | None = None) -> list[dict[str, Any]]:
    """Step 1 of the skill, in code: a project with React, TypeScript, Vite, Tailwind and the shadcn/ui components in it.

    Files that are already there are left alone (an app a stopped run left behind keeps what the agent wrote); the route table and
    the demo accounts are always written again from the specification."""
    app.mkdir(parents=True, exist_ok=True)
    for source in sorted(p for p in (KIT_SOURCE / "app").rglob("*") if p.is_file()):
        target = app / source.relative_to(KIT_SOURCE / "app")
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        target.write_text(text.replace("{{title}}", re.sub(r"[<>&\"]", "", title) or "App"), encoding="utf-8")
    if not (app / "src" / "components" / "ui").is_dir():
        _extract_components(app)
    _add_components(app)
    lock_palette(app)
    package = app / "package.json"
    if not package.exists():
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "app"
        package.write_text(json.dumps({"name": slug, "private": True, "version": "0.0.0", "type": "module"}, indent=2) + "\n",
                           encoding="utf-8")
    rows = write_routes(app, pages)
    write_demo(app, accounts, sign_in, sign_up)
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
    link, target = app / "node_modules", kit_dir() / "node_modules"
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
    for name in ("index.html", "package.json", "tailwind.config.cjs", "vite.config.ts"):
        if (app / name).is_file():
            yield app / name
    yield from sorted(p for p in (app / "src").rglob("*") if p.is_file()) if (app / "src").is_dir() else ()


def fingerprint(app: Path) -> str:
    """What the app's source says, to tell a bundle that is current from one the agent has edited since."""
    digest = hashlib.sha256()
    for path in _source_files(app):
        digest.update(path.relative_to(app).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def built(app: Path) -> bool:
    return (app / BUNDLE).is_file() and (app / BUNDLE).stat().st_size > 0


def stale(app: Path) -> bool:
    marker = app / BUILT
    return not built(app) or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != fingerprint(app)


# What the Studio owns in every app and writes again each time it is bundled: the agent imports them and never edits them, so an app made
# before they changed gets the change too.
KIT_OWNED = ("src/lib/router.tsx", "src/lib/session.tsx")


def sync_kit_files(app: Path) -> None:
    lock_palette(app)                       # a wireframe made before the palette was grey becomes grey when it is bundled again
    for name in KIT_OWNED:
        source, target = KIT_SOURCE / "app" / name, app / name
        if source.is_file() and (not target.is_file() or target.read_bytes() != source.read_bytes()):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def bundle(app: Path) -> tuple[bool, str]:
    """Step 3 of the skill: all of the app in one HTML file, `bundle.html`. Returns (ok, what the bundler said)."""
    ok, text = prepare_kit()
    if not ok:
        return False, text
    link_node_modules(app)
    sync_kit_files(app)
    with _build_locks.setdefault(str(app), threading.Lock()):
        ok, text = _run([node_exe() or "node", str(kit_dir() / "node_modules" / "vite" / "bin" / "vite.js"), "build"],
                        app, timeout=600, env={"NODE_ENV": "production", "FORCE_COLOR": "0"})
        page = app / "dist" / "index.html"
        if not ok or not page.is_file():
            return False, text[-3000:] or "the bundler produced no page"
        shutil.copyfile(page, app / BUNDLE)
        (app / BUILT).write_text(fingerprint(app), encoding="utf-8")
        shutil.rmtree(app / "dist", ignore_errors=True)
        return True, text[-1000:]


# --- retyping words on a page ------------------------------------------------------------------------------------------------

# What is not the page's own words: the toolkit's components, the route table, the demo accounts and what the Studio writes again.
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
    for path in sorted(p for p in source.rglob("*") if p.is_file() and p.suffix in (".tsx", ".ts", ".jsx", ".js")):
        relative = path.relative_to(source).as_posix()
        if any(part in relative for part in _NOT_WORDS):
            continue
        raw = path.read_bytes().decode("utf-8", errors="replace")
        for match in pattern.finditer(raw):
            pre, post = match.group("pre"), match.group("post")
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
        return None
    try:
        return [(str(row["route"]), str(row["error"])[:300]) for row in json.loads(htmllib.unescape(found.group(1)))]
    except (ValueError, KeyError, TypeError):
        return None


def _crashing(rows: list[tuple[str, str]]) -> str:
    return ("These pages bundle, but crash as soon as they are opened. Fix each one in its page file (`src/pages/<file>.tsx`), "
            "and in what it imports:\n\n" + "\n".join(f"- `{route}`: {error}" for route, error in rows[:20]))


def ensure_built(app: Path, repair: Callable[[str], None] | None = None, rounds: int = 2) -> None:
    """Bundle the app and open its screens. When it does not bundle, or a screen crashes, give what was said to `repair` (the agent
    fixes the files) and try again. An app that does not bundle after the agent's tries is an error; a screen that still crashes is
    not: it shows what is wrong in its own place, and the rest of the app works."""
    tries = 0
    while True:
        ok, text = bundle(app)
        if ok:
            crashing = check_pages(app)
            if not crashing:
                return
            text = _crashing(crashing)
        if repair is None or tries >= rounds:
            if not ok:
                raise BuildFailed(text)
            return
        tries += 1
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
