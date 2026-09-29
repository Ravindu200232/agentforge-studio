"""Managed local preview processes for generated projects."""
from __future__ import annotations

import json
import os
import socket
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

from . import bus, config, plugins, store

_lock = threading.RLock()
_processes: dict[str, dict] = {}
_last: dict[str, dict] = {}
_revision = 0

# A preview is deliberately single-tenant. Each stack has a stable local port;
# switching projects stops the previous preview rather than silently accepting
# a framework's random fallback port or an old process's environment.
PREVIEW_PORT = 3001  # the two Next.js-based stacks
VITE_PREVIEW_PORT = 5173  # remix-supabase, vite-supabase, vite-microservices-supabase


def _preview_port(project: str, package: dict) -> int:
    """Pick the port of the selected stack, not one shared port for every app."""
    stack = str((store.get(project) or {}).get("stack") or "")
    dependencies = {**(package.get("dependencies") or {}),
                    **(package.get("devDependencies") or {})}
    if stack in {"remix-supabase", "vite-supabase", "vite-microservices-supabase"} or (
            "next" not in dependencies and ("@remix-run/serve" in dependencies or "vite" in dependencies)):
        return VITE_PREVIEW_PORT
    return PREVIEW_PORT

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


def _free_port(port: int, timeout: float = 6) -> None:
    """Replace whichever process currently listens on the selected preview port."""
    for pid in _listening_pids(port):
        _terminate_tree(pid)
    deadline = time.monotonic() + timeout
    while _port_open(port) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _port_open(port):
        raise RuntimeError(f"Port {port} is still in use. Close the app using it and try again.")


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
            state = _state(project, "failed", revision=entry["revision"],
                           detail=f"Preview exited with code {process.returncode}.")
            _last[project] = state
            bus.runtime_state(project, "failed", revision=entry["revision"])
            return state
        return _state(project, entry["status"], **{k: v for k, v in entry.items()
                                                  if k not in {"process", "status"}})


def open_preview(project: str) -> dict:
    global _revision
    root = config.workspace_for(project)
    manifest = root / "package.json"
    if not manifest.is_file():
        return _state(project, detail="The builder has not written package.json yet.")
    package = json.loads(manifest.read_text(encoding="utf-8"))
    scripts = package.get("scripts") or {}
    production_ready = (root / ".next" / "BUILD_ID").is_file() and bool(scripts.get("start"))
    script = "start" if production_ready else "dev"
    if not scripts.get(script):
        return _state(project, detail=f"package.json has no {script} script.")
    port = _preview_port(project, package)
    with _lock:
        current = status(project)
        if current["status"] in {"running", "starting"}:
            # Already this project's preview: keep it, unless it is not really there (the
            # port no longer answers) or it was started before the production build existed
            # and is still the slow dev server.
            saved = _processes.get(project) or _read_metadata(project)
            stale = int(current.get("port") or 0) != port or \
                (current["status"] == "running" and not _port_open(int(current.get("port") or port))) \
                or (saved.get("script") and saved["script"] != script)
            if not stale:
                return current
            stop(project)
        _last.pop(project, None)
        # One preview at a time: opening this project ends other managed previews.
        for other in [name for name in _processes if name != project]:
            stop(other)
        try:
            _free_port(port)
        except RuntimeError as exc:
            state = _state(project, "failed", detail=str(exc))
            _last[project] = state
            bus.runtime_state(project, "failed", revision=_revision)
            bus.log(project, "WARN", str(exc))
            return state
        _revision = max(_revision + 1, int(time.time() * 1000))
        revision = _revision
        # PORT is supplied below.  Do not append a second `--port`: scaffolds
        # may already run their guard and framework command with the fixed port.
        command = ["npm.cmd" if os.name == "nt" else "npm", "run", script]
        runtime_id = uuid.uuid4().hex
        log_path = config.record_dir(project) / "preview.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("ab")
        try:
            enabled_path = config.record_dir(project) / "plugins.json"
            enabled = json.loads(enabled_path.read_text(encoding="utf-8")) if enabled_path.is_file() else []
            environment = {**os.environ, **plugins.environment(enabled),
                           "PORT": str(port), "BROWSER": "none"}
            # The Studio frames this app. Let this machine's pages do that, whatever the app's
            # own headers say; only this preview process is affected (see preview_hooks).
            environment["NODE_OPTIONS"] = " ".join(
                part for part in (environment.get("NODE_OPTIONS", ""), f'--require "{FRAME_HOOK.as_posix()}"') if part)
            process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                       env=environment)
        finally:
            log.close()
        url = f"http://127.0.0.1:{port}/"
        _processes[project] = {"process": process, "status": "starting", "url": url,
                               "port": port, "runtimeId": runtime_id, "script": script,
                               "serverId": f"srv-{project}", "revision": revision}
        _write_metadata(project, _processes[project])
        bus.runtime_state(project, "starting", url, f"srv-{project}", revision)
    threading.Thread(target=_wait_ready, args=(project, process, url), daemon=True).start()
    return status(project)


def reopen(project: str) -> dict:
    """Serve the project as it is now: what a finished build or change leaves on disk.

    A running production server keeps serving the build it started with, so a new build is
    only visible after the server is replaced.
    """
    stop(project)
    return open_preview(project)


def _wait_ready(project: str, process: subprocess.Popen, url: str) -> None:
    for _ in range(90):
        if process.poll() is not None:
            status(project)
            return
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    with _lock:
                        entry = _processes.get(project)
                        if entry and entry["process"] is process:
                            entry["status"] = "running"
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
        except Exception:
            time.sleep(1)
    bus.log(project, "WARN", "Preview did not become ready. Check .agentforge/preview.log.")


def stop(project: str) -> None:
    with _lock:
        entry = _processes.pop(project, None)
    saved = entry or _read_metadata(project)
    if entry and entry["process"].poll() is None:
        process = entry["process"]
        _terminate_tree(process.pid)
        bus.runtime_state(project, "stopped", revision=entry["revision"])
    else:
        port = int(saved.get("port") or 0)
        listener_pid = int(saved.get("listenerPid") or 0)
        # A persisted port by itself is not ownership proof.  It is safe to
        # terminate only the exact listener that this runtime recorded.
        if port and listener_pid and listener_pid in _listening_pids(port):
            _terminate_tree(listener_pid)
            bus.runtime_state(project, "stopped", revision=int(saved.get("revision") or 0))
    _last.pop(project, None)
    _metadata(project).write_text("{}", encoding="utf-8")
