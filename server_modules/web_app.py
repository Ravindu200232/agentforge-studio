"""The React (JSX) app the wireframe and the prototype are made of.

Both stages build a web-artifacts-builder app (React + TypeScript + Tailwind + shadcn/ui) with the
model's own file tools, and this module is only the mechanical part around that: where the app lives,
the skill staged where the model can read and run it, the one shared dependency store every app links
its `node_modules` to, the bundle build, the copy that turns the wireframe into the prototype, and the
files the preview serves. Nothing here decides what an app looks like.

    <workspace>/.agentforge/wireframe/app/   the wireframe (low fidelity)
    <workspace>/.agentforge/prototype/app/   a copy of it, edited into the high fidelity prototype
    <workspace>/.agentforge/skills/web-artifacts-builder/   the skill, staged for the model
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config

SKILL = "web-artifacts-builder"
SKILL_SOURCE = config.PROMPTS / "design" / "skills" / SKILL
BUNDLE = "bundle.html"
KINDS = ("wireframe", "prototype")
# What is rebuilt or linked, never copied from one app to the next.
_NOT_COPIED = ("node_modules", "dist", ".parcel-cache", BUNDLE)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_REPARSE_POINT = 0x400

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".map": "application/json",
}

# What the preview may do. It can run its own scripts and draw, but it cannot call out, submit a form
# anywhere, nest another page or change the base address: a button in a wireframe goes nowhere outside it.
PREVIEW_POLICY = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https:; font-src 'self' data:; media-src 'self' data: blob:; "
    "connect-src 'none'; form-action 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'"
)
_HEAD = re.compile(rb"<head[^>]*>", re.IGNORECASE)


def preview_page(html: bytes) -> bytes:
    """`bundle.html` as the preview serves it: the policy goes into its head here, at serving time, so it
    is the preview's rule and never something the agent wrote (or could leave out). A `<meta>` rather than
    a header because the desktop app's bridge carries only a content type."""
    meta = f'<meta http-equiv="Content-Security-Policy" content="{PREVIEW_POLICY}">'.encode("utf-8")
    found = _HEAD.search(html)
    return html[:found.end()] + meta + html[found.end():] if found else meta + html


# --- where things are ---------------------------------------------------------------------------

def runtime_dir() -> Path:
    """The one shared dependency store. Outside the user's synced folders on an installed app."""
    named = os.environ.get("AGENTFORGE_WEB_RUNTIME")
    if named:
        return Path(named).expanduser().resolve()
    if config.DATA:
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else config.DATA.parent / "Local") / "AgentForge" / "web-artifacts-runtime"
    return config.ROOT / "tools" / "web-artifacts-runtime"


def app_dir(project: str, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown app kind: {kind}")
    return config.record_dir(project) / kind / "app"


def bundle_path(project: str, kind: str) -> Path:
    return app_dir(project, kind) / BUNDLE


def built(project: str, kind: str) -> bool:
    file = bundle_path(project, kind)
    try:
        return file.is_file() and file.stat().st_size > 0
    except OSError:
        return False


def _source_files(app: Path):
    """The files that make the bundle: the app's own source, not what was built or linked from it."""
    for name in ("index.html", "package.json", "tailwind.config.js", "postcss.config.js", "tsconfig.json"):
        if (app / name).is_file():
            yield app / name
    src = app / "src"
    if src.is_dir():
        for folder, _dirs, names in os.walk(src):
            for name in names:
                yield Path(folder) / name


def fingerprint(app: Path) -> str:
    """Changes whenever any source file does (size and modified time); used to know a review is out of date."""
    import hashlib
    digest = hashlib.sha1()
    for file in sorted(_source_files(app)):
        try:
            info = file.stat()
        except OSError:
            continue
        digest.update(f"{file.relative_to(app).as_posix()}|{info.st_size}|{int(info.st_mtime)}\n".encode())
    return digest.hexdigest()


def stale(project: str, kind: str) -> bool:
    """True when the app has source but no bundle, or a bundle older than its newest source file."""
    app = app_dir(project, kind)
    if not (app / "index.html").is_file():
        return False
    bundle = app / BUNDLE
    if not bundle.is_file():
        return True
    try:
        newest = max((f.stat().st_mtime for f in _source_files(app)), default=0.0)
        return newest > bundle.stat().st_mtime
    except OSError:
        return True


# --- the shared dependency store ----------------------------------------------------------------

def node_exe() -> str:
    candidates = [os.environ.get("AGENTFORGE_NODE_BINARY"), shutil.which("node"), shutil.which("node.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return "node.exe" if os.name == "nt" else "node"


def _store_package() -> dict:
    return json.loads((SKILL_SOURCE / "scripts" / "runtime" / "package.json").read_text(encoding="utf-8"))


_STORE_FILES = ("package.json", "package-lock.json", ".npmrc")
_MARKER = ".agentforge-runtime"


def _store_signature() -> str:
    """The same signature lib.mjs writes into the store after an install (sha1 of the three files)."""
    import hashlib
    digest = hashlib.sha1()
    for name in _STORE_FILES:
        digest.update((SKILL_SOURCE / "scripts" / "runtime" / name).read_bytes())
    return digest.hexdigest()


def runtime_ready() -> bool:
    """The store was installed from this toolkit's files and every package is on disk."""
    store = runtime_dir() / "node_modules"
    try:
        if (store / _MARKER).read_text(encoding="utf-8").strip() != _store_signature():
            return False
    except OSError:
        return False
    package = _store_package()
    names = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    return all((store / name / "package.json").is_file() for name in names)


def _run(args: list[str], cwd: Path, timeout: int, env_extra: dict | None = None) -> tuple[bool, str]:
    env = {**os.environ, "AGENTFORGE_WEB_RUNTIME": str(runtime_dir()), **(env_extra or {})}
    try:
        done = subprocess.run([node_exe(), *args], cwd=str(cwd), env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired as error:
        out = (error.stdout or b"") if isinstance(error.stdout, bytes) else (error.stdout or "")
        return False, f"timed out after {timeout}s\n{out}"[-4000:]
    except OSError as error:
        return False, f"could not run node: {error}"
    text = ((done.stdout or "") + (done.stderr or "")).strip()
    return done.returncode == 0, text[-6000:]


def prepare_runtime() -> tuple[bool, str]:
    """Install the shared store the first time (npm, once). Returns at once when it is already there."""
    if runtime_ready():
        return True, "ready"
    script = SKILL_SOURCE / "scripts" / "init-artifact.mjs"
    return _run([str(script), "--prepare"], SKILL_SOURCE, timeout=1500)


# --- the skill, staged for the model ------------------------------------------------------------

def stage_skill(project: str) -> str:
    """Copy the skill into the workspace (the model's tools stop at its edge) and point its scripts at the store.

    A real file copy, not `reference_staging.stage` (text only): the scripts keep their line endings and
    the shadcn tarball stays binary. Returns the workspace-relative folder."""
    target = config.record_dir(project) / "skills" / SKILL
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(SKILL_SOURCE, target, ignore=shutil.ignore_patterns("__pycache__"))
    (target / "scripts" / "runtime.json").write_text(json.dumps({"runtime": str(runtime_dir())}), encoding="utf-8")
    return target.relative_to(config.workspace_for(project)).as_posix()


# --- build, copy, link --------------------------------------------------------------------------

def bundle(project: str, kind: str) -> tuple[bool, str]:
    """Build the app into one bundle.html. Returns (built, the tail of the build output)."""
    app = app_dir(project, kind)
    if not (app / "index.html").is_file():
        return False, f"there is no app at {app.relative_to(config.workspace_for(project)).as_posix()}"
    ready, why = prepare_runtime()
    if not ready:
        return False, why
    link_node_modules(app)
    script = SKILL_SOURCE / "scripts" / "bundle-artifact.mjs"
    ok, text = _run([str(script)], app, timeout=900)
    return (ok and built(project, kind)), text


class BuildFailed(RuntimeError):
    """The app would not build, even after the agent was asked to fix it once."""


def ensure_built(session, project: str, kind: str, agent: str = "") -> None:
    """Leave a current bundle behind: build it when it is missing or older than the source, and when the
    build fails give the agent the build output once to fix its own source. Never edits the app itself."""
    from . import bus, prompts

    app = app_dir(project, kind)
    if not (app / "index.html").is_file():
        raise BuildFailed("the agent did not create the app (there is no index.html)")
    if built(project, kind) and not stale(project, kind):
        return
    ok, log = bundle(project, kind)
    if not ok:
        bus.log(project, "WARN", "The app did not build yet; asking the agent to fix it.\n" + log[-500:],
                **({"agent": agent} if agent else {}))
        session.run_direct(prompts.load("shared/build-fix", app=app.relative_to(config.workspace_for(project)).as_posix(),
                                        log=log[-3500:]))
        ok, log = bundle(project, kind)
    if not ok:
        raise BuildFailed(log[-1200:] or "the app did not build")


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt" and os.path.lexists(path):
        return bool(getattr(os.lstat(path), "st_file_attributes", 0) & _REPARSE_POINT)
    return False


def drop_link(path: Path) -> None:
    """Remove a node_modules link without touching what it points at (the shared store)."""
    if not _is_link(path):
        return
    try:
        os.rmdir(path) if os.name == "nt" else os.unlink(path)
    except OSError:
        pass


def link_node_modules(app: Path) -> None:
    """Point the app's node_modules at the shared store (a junction on Windows, a symlink elsewhere)."""
    link, target = app / "node_modules", runtime_dir() / "node_modules"
    if _is_link(link):
        try:
            if link.resolve() == target.resolve():
                return
        except OSError:
            pass
        drop_link(link)
    elif link.exists():
        shutil.rmtree(link, ignore_errors=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True,
                       creationflags=_NO_WINDOW, check=False)
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_app(app: Path) -> None:
    """Delete an app folder; its node_modules link goes first so the shared store is never followed into."""
    drop_link(app / "node_modules")
    shutil.rmtree(app, ignore_errors=True)


def copy_app(source: Path, destination: Path) -> None:
    """The wireframe becomes the prototype's starting point: a copy of the source, never the build output.

    The destination is replaced; the wireframe is only ever read."""
    if not (source / "index.html").is_file():
        raise FileNotFoundError(f"there is no app to copy at {source}")
    remove_app(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*_NOT_COPIED))
    link_node_modules(destination)


# --- what the preview serves and edits -----------------------------------------------------------

def served_file(project: str, kind: str, name: str) -> Path | None:
    """`bundle.html`, or a built file under `dist/` it points at; nothing else in the app is reachable."""
    app = app_dir(project, kind)
    clean = (name or BUNDLE).replace("\\", "/").lstrip("/")
    for base in (app, app / "dist"):
        if base is app and clean != BUNDLE:
            continue
        try:
            file = (base / clean).resolve()
            file.relative_to(base.resolve())
        except (OSError, ValueError):
            continue
        if file.is_file():
            return file
    return None


def replace_text(project: str, kind: str, old: str, new: str) -> dict:
    """Swap one literal string in the app's source, when it appears exactly once.

    The quick path for retyping a label in the preview; anything else (text built in code, or found in
    several places) is answered with `where` so the caller can fall back to asking the model for the edit."""
    if not old or old == new:
        return {"ok": False, "reason": "nothing to change"}
    app = app_dir(project, kind)
    hits: list[Path] = []
    for file in _source_files(app):
        if file.suffix.lower() not in (".tsx", ".ts", ".jsx", ".js", ".html", ".css"):
            continue
        try:
            if old in file.read_text(encoding="utf-8"):
                hits.append(file)
        except (OSError, UnicodeDecodeError):
            continue
    where = [f.relative_to(app).as_posix() for f in hits]
    if len(hits) != 1:
        return {"ok": False, "reason": "not found in the source" if not hits else "found in several places", "where": where}
    text = hits[0].read_text(encoding="utf-8")
    if text.count(old) != 1:
        return {"ok": False, "reason": "found in several places", "where": where}
    hits[0].write_text(text.replace(old, new, 1), encoding="utf-8")
    return {"ok": True, "file": where[0]}
