"""Managed local preview processes for generated projects."""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import socket
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

from . import bus, config, deploy_vars, plugins, secrets_guard, supabase_connect

_lock = threading.RLock()
_processes: dict[str, dict] = {}
_last: dict[str, dict] = {}
_revision = 0

# Every preview has its own private loopback port.  The old fixed 3001/5173
# model made unrelated applications collide and forced the studio to stop a
# preview merely because somebody opened another project.  Ports are stable
# per project where possible, but are always checked before use.
PREVIEW_PORT_FIRST = 3100
PREVIEW_PORT_LAST = 5099

# How long a preview may take to answer before it is shown as not started. It is watched a while
# longer after that, so a slow first compile still turns into a running preview on its own.
READY_SECONDS = 90
LATE_READY_SECONDS = 300

# The line each start writes into preview.log, and how much of the log one read hands the terminal.
RUN_MARK = "── preview: "
LOG_WINDOW = 200_000


def _port_candidates(project: str) -> list[int]:
    """A deterministic full pass through the project-preview port range."""
    count = PREVIEW_PORT_LAST - PREVIEW_PORT_FIRST + 1
    digest = hashlib.blake2s(project.encode("utf-8"), digest_size=4).digest()
    start = int.from_bytes(digest, "big") % count
    return [PREVIEW_PORT_FIRST + ((start + offset) % count) for offset in range(count)]


def _preview_port(project: str, package: dict, exclude: set[int] | None = None) -> int:
    """Allocate a free loopback port without touching another application's process."""
    del package  # every supported framework receives the chosen PORT below
    blocked = set(exclude or set())
    blocked.update(
        int(entry.get("port") or 0)
        for name, entry in _processes.items()
        if name != project and entry.get("process") and entry["process"].poll() is None
    )
    for port in _port_candidates(project):
        if port not in blocked and not _port_open(port):
            return port
    raise RuntimeError("No private preview port is available. Stop one of this Studio's previews and try again.")

# Preloaded into the preview process so a hardened app (X-Frame-Options, `frame-ancestors 'none'`)
# can still be shown in the Studio's iframe.
FRAME_HOOK = Path(__file__).resolve().with_name("preview_hooks") / "frame-headers.cjs"


def _metadata(project: str) -> Path:
    return config.record_dir(project) / "preview-runtime.json"


def _read_metadata(project: str) -> dict:
    try:
        return json.loads(_metadata(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_metadata(project: str, entry: dict) -> None:
    """Persist runtime ownership without serialising the live process object."""
    payload = {k: v for k, v in entry.items() if k not in {"process"}}
    path = _metadata(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _listening_pids(port: int) -> list[int]:
    """Return only processes that own a LISTEN socket for ``port``.

    `taskkill /IM node.exe` is intentionally never used: it kills the Studio
    and every unrelated app.  A port guard may only target the PID that owns
    the requested listener.
    """
    if os.name == "nt":
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
            check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        pids: set[int] = set()
        for line in completed.stdout.splitlines():
            bits = line.split()
            if len(bits) < 5 or bits[3].upper() != "LISTENING":
                continue
            local = bits[1].rsplit(":", 1)
            if len(local) != 2 or local[1] != str(port):
                continue
            try:
                pids.add(int(bits[4]))
            except ValueError:
                continue
        return sorted(pids)

    # `lsof` is available on supported macOS/Linux developer installations.
    # If it is absent, return no PID rather than terminating an unknown process.
    try:
        completed = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                   capture_output=True, text=True, check=False)
    except OSError:
        return []
    result: set[int] = set()
    for value in completed.stdout.split():
        try:
            result.add(int(value))
        except ValueError:
            continue
    return sorted(result)


def _terminate_tree(pid: int) -> None:
    """Stop a specific listener and all of its children, never all Node apps."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def _state(project: str, status: str = "stopped", **extra) -> dict:
    return {"project": project, "status": status, "url": extra.get("url", ""),
            "previewUrl": extra.get("url", ""), "runtimeId": extra.get("runtimeId", ""),
            "serverId": extra.get("serverId", f"srv-{project}"),
            "revision": extra.get("revision", 0), "port": extra.get("port", 0),
            "publicUrl": "", "detail": extra.get("detail", "")}


def _without_status(saved: dict) -> dict:
    """Persisted metadata carries its own `status`, which `_state` takes positionally."""
    return {k: v for k, v in saved.items() if k != "status"}


def status(project: str) -> dict:
    with _lock:
        entry = _processes.get(project)
        if not entry:
            saved = _read_metadata(project)
            # A random process may reuse a saved port after the backend restarts.
            # A matching listener PID is the minimum proof that it is still this
            # project's preview; older metadata without it is intentionally stale.
            if (saved.get("port") and saved.get("listenerPid")
                    and int(saved["listenerPid"]) in _listening_pids(int(saved["port"]))):
                return _state(project, "running", **_without_status(saved))
            return _last.get(project) or _state(project)
        process = entry["process"]
        if process.poll() is not None:
            _processes.pop(project, None)
            saved = _read_metadata(project)
            if (saved.get("port") and saved.get("listenerPid")
                    and int(saved["listenerPid"]) in _listening_pids(int(saved["port"]))):
                return _state(project, "running", **_without_status(saved))
            reason = _last_error(project)
            state = _state(project, "failed", revision=entry["revision"],
                           detail=f"Preview exited with code {process.returncode}."
                                  + (f" {reason}" if reason else ""))
            _last[project] = state
            bus.runtime_state(project, "failed", revision=entry["revision"])
            return state
        return _state(project, entry["status"], **{k: v for k, v in entry.items()
                                                  if k not in {"process", "status"}})


def _node_program() -> str:
    """Use the installed Node binary, with the normal name as a safe fallback."""
    return shutil.which("node") or ("node.exe" if os.name == "nt" else "node")


def _node_module(root: Path, relative: str) -> Path | None:
    """Find a framework CLI inside this project's dependency tree only."""
    candidate = root / "node_modules" / relative
    return candidate if candidate.is_file() else None


def _framework(package: dict) -> str:
    """Which framework serves this app, as the preview starts it: a change means a new process."""
    dependencies = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
    if "next" in dependencies:
        return "next"
    if any(name.startswith("@remix-run/") for name in dependencies):
        return "remix"
    return "vite" if "vite" in dependencies else ""


def _preview_command(root: Path, package: dict, script: str, port: int) -> list[str]:
    """Start known frameworks directly so their checked private port always wins.

    Generated Next projects used to hard-code 3001 in their npm scripts. Vite
    and Remix receive PORT through their configs, while Next gets its CLI port
    here. Unknown stacks retain their own start script and receive PORT/HOST.
    """
    dependencies = {**(package.get("dependencies") or {}),
                    **(package.get("devDependencies") or {})}
    node = _node_program()
    if "next" in dependencies:
        cli = _node_module(root, "next/dist/bin/next")
        if cli:
            return [node, str(cli), "start" if script == "start" else "dev",
                    "--port", str(port), "--hostname", "127.0.0.1"]
    # Remix uses Vite during development but its production server is
    # `remix-serve`; retain those scripts so SSR continues to work. Its config
    # already honours the PORT environment variable supplied above.
    remix = any(name.startswith("@remix-run/") for name in dependencies)
    if "vite" in dependencies and not remix:
        cli = _node_module(root, "vite/bin/vite.js")
        if cli:
            mode = ["preview"] if script == "start" else []
            return [node, str(cli), *mode, "--host", "127.0.0.1",
                    "--port", str(port), "--strictPort"]
    return ["npm.cmd" if os.name == "nt" else "npm", "run", script]


def _script_for(root: Path, package: dict) -> str:
    """`start` once a production build exists, else `dev`."""
    scripts = package.get("scripts") or {}
    production_ready = (root / ".next" / "BUILD_ID").is_file() and bool(scripts.get("start"))
    return "start" if production_ready else "dev"


def _shown(root: Path, command: list[str]) -> str:
    """The launch command as somebody would type it in the project folder."""
    parts = []
    for index, part in enumerate(command):
        path = Path(part)
        program = Path(re.split(r"[\\/]", part)[-1]).stem.lower()
        if index == 0 and program in {"node", "npm"}:
            part = program
        elif path.is_absolute() and path.is_relative_to(root):
            part = path.relative_to(root).as_posix()
        parts.append(f'"{part}"' if " " in part else part)
    return " ".join(parts)


def log_tail(project: str, limit: int = 6000) -> str:
    """The end of the preview's own output: the latest start attempt and why it stopped."""
    try:
        with (config.record_dir(project) / "preview.log").open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - limit))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).strip()


def _log_secrets(project: str) -> list[str]:
    """Credentials the app was started with: an app that prints its configuration must not show them."""
    hidden = list(deploy_vars.secret_values())
    supabase = supabase_connect.env_for(project)
    hidden += [value for key, value in supabase.items() if "KEY" in key or "DB_URL" in key]
    uri = deploy_vars.environment().get("MONGODB_URI", "")
    if uri:
        from urllib.parse import unquote, urlparse

        hidden += [uri, unquote(urlparse(uri).password or "")]
    return [value for value in hidden if value and len(value) >= 6]


def read_log(project: str, since: int = -1) -> dict:
    """What the running app printed from byte `since` on, for the terminal; -1 starts at the current run.

    Colour codes are kept (the terminal draws them); credentials are not. A read stops at the last whole line, so
    a character or a line is never split between two reads.
    """
    state = status(project)
    answer = {"status": state["status"], "url": state["url"], "port": state["port"], "detail": state["detail"],
              "cwd": str(config.workspace_for(project)), "text": "", "start": 0, "next": 0}
    path = config.record_dir(project) / "preview.log"
    try:
        size = path.stat().st_size
    except OSError:
        return answer
    with path.open("rb") as handle:
        if since < 0 or since > size:
            # The current run: from the last start's line, within the window. A log that shrank was replaced.
            base = max(0, size - LOG_WINDOW)
            handle.seek(base)
            window = handle.read()
            mark = window.rfind(RUN_MARK.encode("utf-8"))
            since = base + (window.rfind(b"\n", 0, mark) + 1 if mark >= 0 else 0)
            answer["start"] = since
        else:
            answer["start"] = since
        handle.seek(since)
        chunk = handle.read(LOG_WINDOW)
    # Half a line so far is read whole next time, unless that one line fills the window by itself.
    end = chunk.rfind(b"\n") + 1 or (len(chunk) if len(chunk) >= LOG_WINDOW else 0)
    text = chunk[:end].decode("utf-8", errors="replace")
    for value in _log_secrets(project):
        text = text.replace(value, "<hidden>")
    answer.update(text=secrets_guard.mask(text), next=since + end)
    return answer


def _last_error(project: str) -> str:
    """The last line of the preview's output that names an error, if one does."""
    for line in reversed(log_tail(project, 4000).splitlines()):
        line = line.strip()
        if re.search(r"\b(error|cannot|failed|missing|EADDRINUSE)\b", line, re.IGNORECASE):
            return line[:300]
    return ""


def _run_line(variables: dict, command: str, folder: str = ".") -> str:
    """One shell line that runs `command` in `folder` with `variables`, in the agent's own shell."""
    if os.name == "nt":
        move = "" if folder in ("", ".") else f"Set-Location '{folder}'; "
        return move + "".join(f"$env:{name}='{value}'; " for name, value in variables.items()) + command
    move = "" if folder in ("", ".") else f"cd '{folder}' && "
    return move + "".join(f"{name}='{value}' " for name, value in variables.items()) + command


def start_brief(project: str, seen: str = "", part: str = "") -> dict:
    """How the Studio starts this app's preview, for an agent asked to make it start.

    The same command, port and variables `open_preview` uses, so what the agent proves on its
    own run is what the Studio's next start does. `seen` is what the failed preview reported,
    read before it was stopped to free its ports. `part` narrows it to one part of the app (a
    service, the gateway, the client) the Ports view showed as not listening: how that part alone
    is started, and what it printed.
    """
    root = config.workspace_for(project)
    manifest = root / "package.json"
    if not manifest.is_file():
        raise ValueError("this project has no package.json to start yet")
    package = json.loads(manifest.read_text(encoding="utf-8"))
    script = _script_for(root, package)
    state = status(project)
    if state["status"] in {"running", "starting"} and state.get("port"):
        port = int(state["port"])
    else:
        with _lock:
            port = _preview_port(project, package)
    command = _shown(root, _preview_command(root, package, script, port))
    variables = {"PORT": str(port), "HOST": "127.0.0.1", "BROWSER": "none"}
    missing = "" if (package.get("scripts") or {}).get(script) else f"package.json has no `{script}` script."
    brief = {"command": command, "run": _run_line(variables, command), "port": port,
             "url": f"http://127.0.0.1:{port}/", "script": script,
             "detail": missing or seen or str(state.get("detail") or "")
                       or "nothing beyond its output below.",
             "log": log_tail(project) or "(the preview wrote nothing)"}
    if not part:
        return brief
    entry = next((row for row in _declared(project)["ports"] if row.get("name") == part), None)
    if not entry:
        raise ValueError(f"this app has no part called {part!r}")
    own = [line for line in log_tail(project, 40_000).splitlines() if line.startswith(f"[{part}]")]
    part_env = {str(k): str(v) for k, v in (entry.get("env") or {}).items()}
    brief.update(part=part, part_kind=str(entry.get("kind") or "part"), part_port=int(entry.get("port") or 0),
                 part_cwd=str(entry.get("cwd") or "."), part_command=str(entry.get("command") or ""),
                 part_run=_run_line(part_env, str(entry.get("command") or ""), str(entry.get("cwd") or ".")),
                 part_log="\n".join(own[-80:]) or f"({part} printed nothing in the current run)")
    return brief


# --- the parts of a running app and their ports (the Ports view) ---------------------------------

PORTS_FILE = "ports.json"


def _ports_file(project: str) -> Path:
    return config.record_dir(project) / PORTS_FILE


def _declared(project: str) -> dict:
    """What the app's own runner wrote about its parts (`AGENTFORGE_PORTS_FILE`), or nothing."""
    try:
        data = json.loads(_ports_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ports": [], "runtime": "", "written_at": ""}
    rows = [row for row in data.get("ports") or [] if isinstance(row, dict) and row.get("name")]
    return {"ports": rows, "runtime": str(data.get("runtime") or ""), "written_at": str(data.get("written_at") or "")}


def _listeners() -> dict[int, int]:
    """Every local TCP port something listens on, and the process that does, from one look."""
    found: dict[int, int] = {}
    try:
        if os.name == "nt":
            completed = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10)
            for line in completed.stdout.splitlines():
                bits = line.split()
                if len(bits) >= 5 and bits[3].upper() == "LISTENING" and bits[1].rsplit(":", 1)[-1].isdigit():
                    found.setdefault(int(bits[1].rsplit(":", 1)[-1]), int(bits[4]) if bits[4].isdigit() else 0)
        else:
            completed = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True,
                                       check=False, timeout=10)
            for line in completed.stdout.splitlines()[1:]:
                bits = line.split()
                match = re.search(r":(\d+)$", bits[8]) if len(bits) > 8 else None
                if match and bits[1].isdigit():
                    found.setdefault(int(match.group(1)), int(bits[1]))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return found


def ports(project: str) -> dict:
    """Every part of the app the preview starts, its port, and whether something listens there now.

    A runner that starts several parts (a gateway, services, a client) lists them itself; an app that is one server is
    the preview's own port. Parts listed by an earlier run are still shown when the app is stopped, as not started.
    """
    state = status(project)
    declared = _declared(project)
    listening = _listeners()
    main = int(state.get("port") or 0)
    current_runtime = str((_processes.get(project) or _read_metadata(project)).get("runtimeId") or "")
    rows = []
    for entry in declared["ports"]:
        port = int(entry.get("port") or 0)
        rows.append({"name": str(entry["name"]), "kind": str(entry.get("kind") or "part"), "port": port,
                     "cwd": str(entry.get("cwd") or "."), "command": str(entry.get("command") or ""),
                     "main": bool(port and port == main)})
    if not any(row["main"] for row in rows):
        rows.insert(0, {"name": "app", "kind": "app", "port": main, "cwd": ".", "command": "", "main": True})
    for row in rows:
        row["listening"] = bool(row["port"] and row["port"] in listening)
        row["pid"] = listening.get(row["port"]) if row["listening"] else None
        row["url"] = f"http://127.0.0.1:{row['port']}/" if row["port"] else ""
    return {"status": state["status"], "url": state["url"], "detail": state["detail"], "ports": rows,
            "written_at": declared["written_at"],
            "current": bool(declared["runtime"] and declared["runtime"] == current_runtime)}


def wait_part(project: str, part: str, since: float, seconds: float = 60) -> bool:
    """Whether `part`, as the run started after `since` lists it, comes to listen within `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            fresh = _ports_file(project).stat().st_mtime >= since
        except OSError:
            fresh = False
        if fresh and any(row["name"] == part and row["listening"] for row in ports(project)["ports"]):
            return True
        if status(project)["status"] in {"failed", "stopped"}:
            return False
        time.sleep(1.5)
    return False


def wait_settled(project: str, seconds: float = READY_SECONDS + 15) -> dict:
    """The preview's state once it is no longer starting, or after `seconds`."""
    deadline = time.monotonic() + seconds
    while True:
        state = status(project)
        if state["status"] != "starting" or time.monotonic() >= deadline:
            return state
        time.sleep(1)


def open_preview(project: str) -> dict:
    global _revision
    root = config.workspace_for(project)
    manifest = root / "package.json"
    if not manifest.is_file():
        return _state(project, detail="The builder has not written package.json yet.")
    package = json.loads(manifest.read_text(encoding="utf-8"))
    scripts = package.get("scripts") or {}
    script = _script_for(root, package)
    if not scripts.get(script):
        state = _state(project, "failed", detail=f"package.json has no {script} script.")
        _last[project] = state
        return state
    with _lock:
        current = status(project)
        if current["status"] in {"running", "starting"}:
            # Already this project's preview: keep it, unless it is not really there (the
            # port no longer answers) or it was started before the production build existed
            # and is still the slow dev server.
            saved = _processes.get(project) or _read_metadata(project)
            current_port = int(current.get("port") or 0)
            # ... or the app is now served by another framework (Vite became Next.js): the old process would keep
            # serving the old app.
            relaunch = saved.get("framework") is not None and saved["framework"] != _framework(package)
            stale = not current_port or \
                (current["status"] == "running" and not _port_open(current_port)) \
                or (saved.get("script") and saved["script"] != script) or bool(relaunch)
            if not stale:
                return current
            stop(project)
        elif _processes.get(project):
            # A preview shown as failed because it never answered is still alive, and still holds
            # its ports (and its child processes theirs).
            stop(project)
        _last.pop(project, None)
        try:
            port = _preview_port(project, package)
        except RuntimeError as exc:
            state = _state(project, "failed", detail=str(exc))
            _last[project] = state
            bus.runtime_state(project, "failed", revision=_revision)
            bus.log(project, "WARN", str(exc))
            return state
        _revision = max(_revision + 1, int(time.time() * 1000))
        revision = _revision
        command = _preview_command(root, package, script, port)
        runtime_id = uuid.uuid4().hex
        log_path = config.record_dir(project) / "preview.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        enabled_path = config.record_dir(project) / "plugins.json"
        enabled = json.loads(enabled_path.read_text(encoding="utf-8")) if enabled_path.is_file() else []
        # The same variables the build ran and tested this app with (session.py's command_env): a
        # MongoDB-stack preview reads the database the build seeded, not a local fallback.
        environment = {**os.environ, **plugins.environment(enabled),
                       **supabase_connect.env_for(project), **deploy_vars.environment(),
                       "PORT": str(port), "HOST": "127.0.0.1", "BROWSER": "none",
                       # A runner that starts several parts says where each one is (the Ports view).
                       "AGENTFORGE_PORTS_FILE": str(_ports_file(project)),
                       "AGENTFORGE_PREVIEW_RUNTIME_ID": runtime_id}
        # The Studio frames this app. Let this machine's pages do that, whatever the app's
        # own headers say; only this preview process is affected (see preview_hooks).
        environment["NODE_OPTIONS"] = " ".join(
            part for part in (environment.get("NODE_OPTIONS", ""), f'--require "{FRAME_HOOK.as_posix()}"') if part)
        process = _launch(command, root, environment, log_path)
        url = f"http://127.0.0.1:{port}/"
        _processes[project] = {"process": process, "status": "starting", "url": url,
                               "port": port, "runtimeId": runtime_id, "script": script,
                               "framework": _framework(package),
                               "serverId": f"srv-{project}", "revision": revision}
        _write_metadata(project, _processes[project])
        bus.runtime_state(project, "starting", url, f"srv-{project}", revision)
    threading.Thread(target=_wait_ready,
                      args=(project, process, url, root, command, environment, log_path, script),
                      daemon=True).start()
    return status(project)


def reopen(project: str) -> dict:
    """Serve the project as it is now: what a finished build or change leaves on disk.

    A running production server keeps serving the build it started with, so a new build is
    only visible after the server is replaced.
    """
    stop(project)
    return open_preview(project)


def _launch(command: list[str], root: Path, environment: dict, log_path: Path) -> subprocess.Popen:
    log = log_path.open("ab")
    try:
        # Where this start begins in the log, for the terminal that shows the current run (read_log).
        log.write(f"\n{RUN_MARK}{_shown(root, command)} · PORT {environment.get('PORT', '')} · "
                  f"{time.strftime('%Y-%m-%d %H:%M:%S')} ──\n".encode("utf-8"))
        log.flush()
        return subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                env=environment)
    finally:
        log.close()


# `next dev` writes its webpack cache into `.next` continuously; force-killing it
# mid-write (switching projects, stopping the preview) can leave a numbered chunk
# half-written, which then 500s every request for it forever until `.next` is
# cleared. A genuinely missing package/app import never looks like this - only a
# webpack-internal, purely numeric chunk id does - so this pattern is specific
# enough to self-heal on rather than something a real app bug could trigger.
_CORRUPT_CACHE = re.compile(r"Cannot find module '\.[/\\]\d+\.js'|PackFileCacheStrategy\] Restoring pack failed")


def _cache_corrupted(log_path: Path) -> bool:
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 20_000))
            tail = handle.read()
    except OSError:
        return False
    return bool(_CORRUPT_CACHE.search(tail.decode("utf-8", errors="replace")))


def _heal(project: str, process: subprocess.Popen, url: str, root: Path, command: list[str],
          environment: dict, log_path: Path, script: str) -> None:
    """One-shot recovery from a `.next` cache an earlier interrupted restart left corrupted."""
    with _lock:
        entry = _processes.get(project)
        if not entry or entry["process"] is not process:
            return  # a newer preview already replaced this one
    bus.log(project, "WARN",
            "The preview's build cache looked corrupted after an earlier interrupted restart "
            "(a stale numbered chunk) - clearing .next and starting the preview again.")
    _terminate_tree(process.pid)
    shutil.rmtree(root / ".next", ignore_errors=True)
    new_process = _launch(command, root, environment, log_path)
    with _lock:
        entry = _processes.get(project)
        if not entry or entry["process"] is not process:
            _terminate_tree(new_process.pid)
            return
        entry["process"] = new_process
        _write_metadata(project, entry)
    _wait_ready(project, new_process, url, root, command, environment, log_path, script, healed=True)


def _wait_ready(project: str, process: subprocess.Popen, url: str, root: Path, command: list[str],
                environment: dict, log_path: Path, script: str, healed: bool = False) -> None:
    # Self-healing only ever applies to `next dev`: `next start` only ever reads a
    # `.next` a prior `next build` already finished writing, so it cannot itself
    # get corrupted this way, and deleting it would just delete the real build.
    healable = not healed and script == "dev"
    for second in range(LATE_READY_SECONDS):
        if second == READY_SECONDS:
            _not_answering(project, process, url, log_path)
        if process.poll() is not None:
            if healable and _cache_corrupted(log_path):
                _heal(project, process, url, root, command, environment, log_path, script)
                return
            status(project)
            return
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    with _lock:
                        entry = _processes.get(project)
                        if entry and entry["process"] is process:
                            entry["status"] = "running"
                            entry.pop("detail", None)
                            # The npm shell is not necessarily the listener.
                            # Store the actual listener PID so a backend restart
                            # can distinguish this preview from an unrelated app
                            # that later reuses the same port.
                            listener_pids = _listening_pids(int(entry["port"]))
                            entry["listenerPid"] = listener_pids[0] if listener_pids else 0
                            _write_metadata(project, entry)
                            bus.runtime_state(project, "running", url,
                                              entry["serverId"], entry["revision"])
                    return
                if healable and _cache_corrupted(log_path):
                    _heal(project, process, url, root, command, environment, log_path, script)
                    return
        except Exception:
            pass
        time.sleep(1)


def _not_answering(project: str, process: subprocess.Popen, url: str, log_path: Path) -> None:
    """Show a preview that is up but silent as not started, so it can be retried or handed to the
    agent, instead of a spinner that never ends. `_wait_ready` keeps watching it."""
    with _lock:
        entry = _processes.get(project)
        if not entry or entry["process"] is not process or entry["status"] != "starting":
            return
        entry["status"] = "failed"
        entry["detail"] = f"The app did not answer on {url} within {READY_SECONDS} seconds."
        bus.runtime_state(project, "failed", revision=entry["revision"])
    bus.log(project, "WARN", f"{entry['detail']} Check {log_path.name}.")


def stop(project: str) -> dict:
    with _lock:
        entry = _processes.pop(project, None)
    saved = entry or _read_metadata(project)
    revision = int(saved.get("revision") or 0)
    server_id = str(saved.get("serverId") or f"srv-{project}")
    stopped = _state(project, "stopped", serverId=server_id, revision=revision)
    if entry and entry["process"].poll() is None:
        process = entry["process"]
        _terminate_tree(process.pid)
        bus.runtime_state(project, "stopped", server_id=server_id, revision=revision)
    else:
        port = int(saved.get("port") or 0)
        listener_pid = int(saved.get("listenerPid") or 0)
        # A persisted port by itself is not ownership proof.  It is safe to
        # terminate only the exact listener that this runtime recorded.
        if port and listener_pid and listener_pid in _listening_pids(port):
            _terminate_tree(listener_pid)
            bus.runtime_state(project, "stopped", server_id=server_id, revision=revision)
    _last[project] = stopped
    _metadata(project).write_text("{}", encoding="utf-8")
    return stopped
