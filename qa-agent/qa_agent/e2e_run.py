"""The end-to-end suite, run once by the Studio itself.

The agent writes the journey tests and runs one spec file at a time while it writes or fixes them; the whole suite is the
Studio's to run, here, once per build - never again by itself. It ran again and again before: inside the build's last
phase (where the agent's ten-minute command limit killed it half-way, leaving a partial `results.json`), after every
screenshot-review fix, and once more in the Testing stage straight after a build that had just run it. Now:

- a build runs it once, after its phases, when the app's source is not what the last full run already tested (`current`);
- a Testing run reuses that run while the source is unchanged, unless the person asks for the journeys to run again;
- a fix the person asked for runs only the journeys it fixed (`grep`).

Before the journeys, every page is photographed (`pages`: `e2e/pages.spec.js`, the Studio's own spec) for the screen review,
which has what looks wrong fixed and photographs only those pages again: the journeys are never run to take pictures. After
the journeys, a change made for accessibility or security is checked with the runtime test (`runtime_check`: the build, then
every page opens) instead of the journeys, and the journeys' run stays the app's (`carry_over`).

The run is `node scripts/with-server.mjs -- npx playwright test`, so it gets its own server, port and isolated database
exactly as the agent's runs did, with the same environment the agent's commands get (`session.command_environment`).
The runner script is the Studio's: the template's copy is put in the project before the run, so a fix to it (Atlas's
database-name limit, a user that may not drop a database) reaches projects built before it.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from server_modules import bus, config, live
from server_modules.session import RunCancelled, command_environment

from . import build_evidence

RECORD = ".agentforge/qa/e2e-run.json"
RUNNER = "scripts/with-server.mjs"
TEMPLATES = config.ROOT / "builder-agent" / "builder_agent" / "assets" / "templates" / "_testing"
TEMPLATE_RUNNER = TEMPLATES / "scripts" / "with-server.mjs"
PAGES_SPEC = "e2e/pages.spec.js"
TEMPLATE_PAGES = TEMPLATES / "e2e" / "pages.spec.js"
RUNTIME_SPEC = "e2e/smoke.spec.js"
RUN_SECONDS = 45 * 60             # the whole suite, desktop and mobile; the agent's own commands stop at ten minutes
PAGES_SECONDS = 20 * 60
RUNTIME_SECONDS = 10 * 60
BUILD_SECONDS = 15 * 60
HEARTBEAT_SECONDS = 30
# The visual and accessibility checks are runs of their own (`qa:visual`, `qa:a11y`), and so are the page pictures (`pages`):
# none of them is a journey. A journey that stalls once is tried once more (Playwright records it as flaky, and its last
# attempt decides), and two workers share the server.
PLAYWRIGHT_ARGS = ["--grep-invert", "@visual|@a11y|@pages", "--retries=1", "--workers=2"]
# What is not the app's source: what a build, a test run, a deployment or the Studio writes.
_SKIP_DIRS = {"node_modules", ".next", ".git", "test-results", "playwright-report", ".agentforge", ".lighthouseci", ".zap",
              ".vercel", ".netlify", "dist", "build", "coverage", "out", "__screenshots__", ".turbo", ".cache"}
_SKIP_FILES = {PAGES_SPEC}           # the Studio's own, put in place before it runs: not the app's source
_MAX_HASHED = 2_000_000


def fingerprint(workspace: Path) -> str:
    """What the app's source is now: its files, by path and content, without anything a build or a test run writes."""
    digest = hashlib.sha256()
    for root, dirs, names in os.walk(workspace):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(names):
            path = Path(root) / name
            try:
                relative = path.relative_to(workspace).as_posix()
                if relative in _SKIP_FILES or path.stat().st_size > _MAX_HASHED:
                    continue
                digest.update(relative.encode("utf-8"))
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            except OSError:
                continue
    return digest.hexdigest()[:24]


def record(workspace: Path) -> dict[str, Any]:
    try:
        saved = json.loads((workspace / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def _save(workspace: Path, data: dict[str, Any]) -> None:
    target = workspace / RECORD
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def current(workspace: Path) -> bool:
    """Whether the last full run tested the app's source as it is now (so running it again would prove nothing new)."""
    last = record(workspace).get("full") or {}
    return bool(last.get("fingerprint")) and last.get("exit_code") is not None and last["fingerprint"] == fingerprint(workspace)


def runnable(workspace: Path) -> bool:
    """Whether this project has end-to-end tests the Studio can run: a package.json, Playwright and a spec."""
    try:
        manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    deps = {**(manifest.get("dependencies") or {}), **(manifest.get("devDependencies") or {})}
    return "@playwright/test" in deps and (workspace / "e2e").is_dir() and any((workspace / "e2e").rglob("*.spec.*"))


def ensure_runner(project: str, workspace: Path) -> None:
    """Put the Studio's own `with-server.mjs` in the project when its copy is missing or older. The one replaced is kept beside
    the run's record, in case the agent had changed it for a reason."""
    if not TEMPLATE_RUNNER.is_file():
        return
    target = workspace / RUNNER
    wanted = TEMPLATE_RUNNER.read_bytes()
    try:
        have = target.read_bytes() if target.is_file() else b""
    except OSError:
        have = b""
    if have.replace(b"\r\n", b"\n") == wanted.replace(b"\r\n", b"\n"):
        return
    if have:
        kept = workspace / ".agentforge" / "qa" / "with-server.before.mjs"
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_bytes(have)
        bus.log(project, "INFO", f"The test runner {RUNNER} was brought up to date with the Studio's (the earlier copy is kept at "
                                 f".agentforge/qa/with-server.before.mjs).", agent=bus.DEVELOPER)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(wanted)


def ensure_pages_spec(workspace: Path) -> bool:
    """Put the Studio's own `e2e/pages.spec.js` in the project (it photographs every page). Whether it is there."""
    if not TEMPLATE_PAGES.is_file():
        return (workspace / PAGES_SPEC).is_file()
    target = workspace / PAGES_SPEC
    wanted = TEMPLATE_PAGES.read_bytes()
    try:
        if target.is_file() and target.read_bytes().replace(b"\r\n", b"\n") == wanted.replace(b"\r\n", b"\n"):
            return True
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wanted)
    except OSError:
        return False
    return True


def grep_for(titles: list[str]) -> str:
    """A Playwright --grep that matches these tests (journey ids like UJ-003, or whole titles) and nothing else."""
    parts = []
    for title in titles:
        text = str(title or "").strip()
        if text:
            parts.append(re.escape(text) if not re.fullmatch(r"UJ-\d{3,}", text, re.I) else rf"\b{text}\b")
    return "|".join(parts)


def _stop_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        try:
            os.killpg(process.pid, 15)
        except OSError:
            process.terminate()


def _execute(project: str, session: Any, command: list[str], env: dict[str, str], seconds: int, label: str) -> dict[str, Any]:
    """Run one command in the workspace until it ends, Stop is pressed or `seconds` pass. Returns exit code and output tail."""
    workspace = session.workspace
    started = time.monotonic()
    tail: list[str] = []
    lines: queue.Queue[str | None] = queue.Queue()
    process = subprocess.Popen(command, cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               text=True, encoding="utf-8", errors="replace", env=env,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")

    def read() -> None:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read, daemon=True, name=f"e2e-run:{project}").start()
    heartbeat = HEARTBEAT_SECONDS
    timed_out = stopped = False
    done_reading = False
    exited_at = 0.0
    while process.poll() is None or not done_reading:
        if process.poll() is not None:
            exited_at = exited_at or time.monotonic()
            if time.monotonic() - exited_at > 5:
                break                     # ended; a grandchild still holding the output open is not waited for
        try:
            line = lines.get(timeout=0.5)
            if line is None:
                done_reading = True
            elif not line.startswith("@@pw "):
                tail.append(line.rstrip())
                del tail[:-200]
        except queue.Empty:
            pass
        if process.poll() is not None:
            continue
        elapsed = time.monotonic() - started
        if getattr(session, "cancelled", False):
            stopped = True
            _stop_tree(process)
        elif elapsed > seconds:
            timed_out = True
            _stop_tree(process)
            tail.append(f"Stopped after {seconds // 60} minutes.")
        elif elapsed >= heartbeat:
            heartbeat += HEARTBEAT_SECONDS
            last = next((t for t in reversed(tail) if t.strip()), "")
            bus.log(project, "INFO", f"{label} still running ({int(elapsed)}s){': ' + last[:160] if last else ''}",
                    agent=bus.DEVELOPER)
    code = process.wait()
    if stopped:
        raise RunCancelled(project)
    return {"exit_code": code, "timed_out": timed_out, "output": "\n".join(tail[-60:]),
            "seconds": round(time.monotonic() - started, 1)}


def _node() -> str:
    return shutil.which("node") or "node"


def _npm() -> list[str]:
    found = shutil.which("npm.cmd" if os.name == "nt" else "npm") or shutil.which("npm") or "npm"
    return [found]


def _build_if_needed(project: str, session: Any, env: dict[str, str], now: str) -> dict[str, Any] | None:
    """`npm run build` when the app's source changed since the build the last run tested. None when nothing needed it,
    else the build's result (a failed build means no test run: there is nothing current to test)."""
    workspace = session.workspace
    saved = record(workspace)
    built = any((workspace / part).exists() for part in (".next/BUILD_ID", "build/server/index.js", "client/dist/index.html", "dist"))
    if saved.get("built_fingerprint") == now and built:
        return None
    try:
        scripts = json.loads((workspace / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError):
        scripts = {}
    if "build" not in scripts:
        return None
    bus.agent_msg(project, "npm run build", title=f"Building the app for the end-to-end run · up to {BUILD_SECONDS // 60} min",
                  kind="command", agent=bus.DEVELOPER)
    result = _execute(project, session, [*_npm(), "run", "build"], env, BUILD_SECONDS, "The build for the end-to-end run")
    if result["exit_code"] == 0:
        saved["built_fingerprint"] = now
        _save(workspace, saved)
    return result


def run(project: str, session: Any, grep: list[str] | None = None, reason: str = "build", force: bool = False,
        desktop: bool = False) -> dict[str, Any]:
    """Run the end-to-end journeys: all of them, or only the tests `grep` names (journey ids or titles); `desktop` runs them
    at desktop width only (a journey is proved on the desktop browser; phone width is looked at in the page pictures).

    A full run is skipped when the last one already tested this source (`force` runs it anyway: the person asked).
    Returns {"status": "passed" | "failed" | "skipped" | "build_failed" | "error", ...}; never raises but for Stop."""
    workspace = session.workspace
    if not runnable(workspace):
        return {"status": "skipped", "reason": "the project has no end-to-end tests to run"}
    pattern = grep_for(grep or [])
    if grep is not None and not pattern:
        return {"status": "skipped", "reason": "no tests named"}
    # The runner is put in place before the source is fingerprinted: replacing it afterwards made the very run that replaced
    # it look out of date, and the next call built and ran everything again.
    ensure_runner(project, workspace)
    now = fingerprint(workspace)
    if not pattern and not force and current(workspace):
        bus.agent_msg(project, "The end-to-end journeys already ran on the app exactly as it is now, so their results are used "
                               "as they are rather than run again.", title="End-to-end journeys", kind="narration",
                      agent=bus.DEVELOPER)
        return {"status": "reused", **(record(workspace).get("full") or {})}

    phase_title = "Running the end-to-end journeys" if not pattern else "Running the journeys again"
    bus.phase(project, "qa:e2e", phase_title, detail=("Every journey, once, on the app's own server and a fresh test database."
                                                     if not pattern else f"Only: {', '.join(grep or [])[:200]}"),
              agent=bus.DEVELOPER)
    try:
        env = command_environment(project, getattr(session, "stage", "") or "build")
        built = _build_if_needed(project, session, env, now)
        if built and built["exit_code"] != 0:
            text = (f"The app did not build (exit {built['exit_code']}), so the end-to-end journeys were not run on it.\n\n"
                    + built["output"][-3000:])
            bus.agent_msg(project, text, title="End-to-end journeys not run", kind="command_output", agent=bus.DEVELOPER)
            bus.phase(project, "qa:e2e", phase_title, status="failed", detail="the app did not build", agent=bus.DEVELOPER)
            return {"status": "build_failed", "exit_code": built["exit_code"], "output": built["output"]}
        args = [*PLAYWRIGHT_ARGS, *(["--project=desktop"] if desktop else [])]
        command = [_node(), RUNNER, "--", "npx", "playwright", "test", *args]
        if pattern:
            command += ["--grep", pattern]
        shown = "node scripts/with-server.mjs -- npx playwright test " + " ".join(
            f'"{arg}"' if " " in arg or "|" in arg else arg for arg in args) + (f' --grep "{pattern}"' if pattern else "")
        bus.agent_msg(project, shown, title=f"{phase_title} · up to {RUN_SECONDS // 60} min", kind="command", agent=bus.DEVELOPER)
        started_at = time.time()
        result = _execute(project, session, command, env, RUN_SECONDS, "The end-to-end run")
    except RunCancelled:
        live.finish(project)
        bus.phase(project, "qa:e2e", phase_title, status="paused", agent=bus.DEVELOPER)
        raise
    except Exception as exc:  # noqa: BLE001 - a run that could not start is said, never a reason to fail what called it
        live.finish(project)
        bus.phase(project, "qa:e2e", phase_title, status="failed", detail=str(exc)[:300], agent=bus.DEVELOPER)
        bus.log(project, "WARN", f"The end-to-end run could not start: {str(exc)[:300]}", agent=bus.DEVELOPER)
        return {"status": "error", "reason": str(exc)[:300]}
    live.finish(project)

    counts = _counts(workspace, started_at)
    entry = {"at": started_at, "reason": reason, "grep": grep or [], "exit_code": result["exit_code"],
             "timed_out": result["timed_out"], "seconds": result["seconds"], "fingerprint": now, **counts}
    saved = record(workspace)
    saved["last"] = entry
    if not pattern:
        saved["full"] = entry
    saved.setdefault("runs", []).append({k: entry[k] for k in ("at", "reason", "grep", "exit_code", "seconds")})
    saved["runs"] = saved["runs"][-20:]
    _save(workspace, saved)

    status = "passed" if result["exit_code"] == 0 and not counts.get("failed") else "failed"
    summary = (f"{counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed"
               + (f", {counts['flaky']} passed only on the retry" if counts.get("flaky") else "")
               + (f" in {int(result['seconds'])}s" if result["seconds"] else ""))
    if result["timed_out"]:
        summary += f"; stopped after {RUN_SECONDS // 60} minutes"
    elif not counts.get("total"):
        summary = f"no test result was recorded (exit {result['exit_code']})"
    bus.agent_msg(project, (summary + ".\n\n" + result["output"][-2500:]).strip(),
                  title=f"End-to-end journeys · exit {result['exit_code']}", kind="command_output", agent=bus.DEVELOPER)
    bus.phase(project, "qa:e2e", phase_title, status="complete" if status == "passed" else "failed", detail=summary,
              agent=bus.DEVELOPER)
    return {"status": status, **entry, "output": result["output"]}


def pages(project: str, session: Any, titles: list[str] | None = None) -> dict[str, Any]:
    """Photograph the app's pages - every one, or only the tests `titles` names - for the screen review: `e2e/pages.spec.js`
    under the Studio's runner, so with the same build, server and test database as the journeys, which are not run.

    Returns {"status": "done" | "failed" | "skipped" | "build_failed" | "error", "skipped_pages": [[title, why], ...], ...};
    never raises but for Stop."""
    workspace = session.workspace
    if not runnable(workspace):
        return {"status": "skipped", "reason": "the project has no end-to-end tests to run"}
    ensure_runner(project, workspace)
    if not ensure_pages_spec(workspace):
        return {"status": "skipped", "reason": f"{PAGES_SPEC} could not be put in the project"}
    pattern = grep_for(titles or [])
    if titles is not None and not pattern:
        return {"status": "skipped", "reason": "no pages named"}
    now = fingerprint(workspace)
    title = "Photographing every page" if not pattern else "Photographing the fixed pages again"
    bus.phase(project, "qa:pages", title, detail=("Every page at desktop and mobile width, signed in as a role that may open it."
                                                 if not pattern else f"Only: {', '.join(titles or [])[:200]}"),
              agent=bus.DEVELOPER)
    try:
        env = command_environment(project, getattr(session, "stage", "") or "build")
        built = _build_if_needed(project, session, env, now)
        if built and built["exit_code"] != 0:
            bus.agent_msg(project, f"The app did not build (exit {built['exit_code']}), so its pages were not photographed.\n\n"
                                   + built["output"][-3000:], title="Pages not photographed", kind="command_output",
                          agent=bus.DEVELOPER)
            bus.phase(project, "qa:pages", title, status="failed", detail="the app did not build", agent=bus.DEVELOPER)
            return {"status": "build_failed", "exit_code": built["exit_code"], "output": built["output"]}
        command = [_node(), RUNNER, "--", "npx", "playwright", "test", PAGES_SPEC, "--retries=0", "--workers=3"]
        if pattern:
            command += ["--grep", pattern]
        bus.agent_msg(project, f"node {RUNNER} -- npx playwright test {PAGES_SPEC} --retries=0 --workers=3"
                               + (f' --grep "{pattern}"' if pattern else ""),
                      title=f"{title} · up to {PAGES_SECONDS // 60} min", kind="command", agent=bus.DEVELOPER)
        started_at = time.time()
        result = _execute(project, session, command, env, PAGES_SECONDS, "Photographing the pages")
    except RunCancelled:
        live.finish(project)
        bus.phase(project, "qa:pages", title, status="paused", agent=bus.DEVELOPER)
        raise
    except Exception as exc:  # noqa: BLE001 - said, never a reason to fail what called it
        live.finish(project)
        bus.phase(project, "qa:pages", title, status="failed", detail=str(exc)[:300], agent=bus.DEVELOPER)
        return {"status": "error", "reason": str(exc)[:300]}
    live.finish(project)
    counts = _counts(workspace, started_at)
    skipped = _skipped(workspace, started_at)
    saved = record(workspace)
    saved["pages"] = {"at": started_at, "titles": titles or [], "exit_code": result["exit_code"], "fingerprint": now,
                      "seconds": result["seconds"], **counts, "skipped": len(skipped)}
    _save(workspace, saved)
    taken = counts.get("total", 0) - len(skipped)
    summary = (f"{taken} page picture(s) taken" + (f", {counts['failed']} of them on a page that reported an error"
                                                   if counts.get("failed") else "")
               + (f" in {int(result['seconds'])}s" if result["seconds"] else "") + ".")
    if skipped:
        summary += " Not photographed: " + "; ".join(f"{name} ({why})" for name, why in skipped[:12]) + "."
    if not counts.get("total"):
        summary = f"No page was photographed (exit {result['exit_code']}).\n\n" + result["output"][-2500:]
    bus.agent_msg(project, summary, title=title, kind="narration" if counts.get("total") else "command_output",
                  agent=bus.DEVELOPER)
    bus.phase(project, "qa:pages", title, status="complete" if taken else "failed", detail=summary[:300], agent=bus.DEVELOPER)
    return {"status": "done" if taken else "failed", **counts, "skipped_pages": skipped, "output": result["output"]}


def runtime_check(project: str, session: Any) -> dict[str, Any]:
    """The runtime test: the app builds, then every page opens (`e2e/smoke.spec.js`, desktop: each page anyone can open answers
    and shows its content, each protected page turns a signed-out visitor away). What a change made after the journeys
    (accessibility, security) is checked with, instead of the journeys. Returns {"status": "passed" | "failed", ...}."""
    workspace = session.workspace
    ensure_runner(project, workspace)
    now = fingerprint(workspace)
    title = "Runtime test"
    bus.phase(project, "qa:runtime", title, detail="The build, then every page opens.", agent=bus.DEVELOPER)
    try:
        env = command_environment(project, getattr(session, "stage", "") or "build")
        built = _build_if_needed(project, session, env, now)
        if built and built["exit_code"] != 0:
            bus.agent_msg(project, f"The app did not build (exit {built['exit_code']}).\n\n" + built["output"][-3000:],
                          title=f"{title} · the build failed", kind="command_output", agent=bus.DEVELOPER)
            bus.phase(project, "qa:runtime", title, status="failed", detail="the app did not build", agent=bus.DEVELOPER)
            return {"status": "failed", "stage": "build", "output": built["output"]}
        if not runnable(workspace) or not (workspace / RUNTIME_SPEC).is_file():
            bus.agent_msg(project, f"The app builds. There is no {RUNTIME_SPEC} to open its pages with, so the build is the "
                                   "runtime test.", title=title, kind="narration", agent=bus.DEVELOPER)
            bus.phase(project, "qa:runtime", title, status="complete", agent=bus.DEVELOPER)
            return {"status": "passed", "stage": "build"}
        command = [_node(), RUNNER, "--", "npx", "playwright", "test", RUNTIME_SPEC, "--project=desktop", "--retries=0"]
        bus.agent_msg(project, f"node {RUNNER} -- npx playwright test {RUNTIME_SPEC} --project=desktop --retries=0",
                      title=f"{title} · up to {RUNTIME_SECONDS // 60} min", kind="command", agent=bus.DEVELOPER)
        started_at = time.time()
        result = _execute(project, session, command, env, RUNTIME_SECONDS, "The runtime test")
    except RunCancelled:
        live.finish(project)
        bus.phase(project, "qa:runtime", title, status="paused", agent=bus.DEVELOPER)
        raise
    except Exception as exc:  # noqa: BLE001
        live.finish(project)
        bus.phase(project, "qa:runtime", title, status="failed", detail=str(exc)[:300], agent=bus.DEVELOPER)
        return {"status": "failed", "stage": "start", "output": str(exc)[:300]}
    live.finish(project)
    counts = _counts(workspace, started_at)
    status = "passed" if result["exit_code"] == 0 and counts.get("total") and not counts.get("failed") else "failed"
    saved = record(workspace)
    saved["runtime"] = {"at": started_at, "exit_code": result["exit_code"], "fingerprint": now, **counts}
    _save(workspace, saved)
    summary = (f"The app builds and {counts.get('passed', 0)} of {counts.get('total', 0)} page checks pass"
               if counts.get("total") else f"No page check was recorded (exit {result['exit_code']})")
    bus.agent_msg(project, (summary + ".\n\n" + (result["output"][-2500:] if status == "failed" else "")).strip(),
                  title=f"{title} · {'passed' if status == 'passed' else 'failed'}",
                  kind="narration" if status == "passed" else "command_output", agent=bus.DEVELOPER)
    bus.phase(project, "qa:runtime", title, status="complete" if status == "passed" else "failed", detail=summary,
              agent=bus.DEVELOPER)
    return {"status": status, "stage": "pages", **counts, "output": result["output"]}


def carry_over(workspace: Path, why: str) -> bool:
    """The journeys' last full run stays the app's after a change the runtime test passed (`runtime_check`): it is not run
    again for an accessibility or security fix. Whether there was a run to carry over."""
    saved = record(workspace)
    full = saved.get("full")
    if not isinstance(full, dict) or full.get("exit_code") is None:
        return False
    now = fingerprint(workspace)
    if full.get("fingerprint") == now:
        return True
    full.setdefault("carried_over", []).append({"at": time.time(), "from": full.get("fingerprint"), "why": why})
    full["carried_over"] = full["carried_over"][-10:]
    full["fingerprint"] = now
    saved["full"] = full
    _save(workspace, saved)
    return True


def _skipped(workspace: Path, since: float) -> list[list[str]]:
    """The tests this run skipped, with why (Playwright's `skip` annotation): [[title, why], ...]."""
    path = workspace / build_evidence.PLAYWRIGHT_JSON
    try:
        if path.stat().st_mtime < since - 2:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found: dict[str, str] = {}

    def walk(suite: dict[str, Any]) -> None:
        for spec in suite.get("specs") or []:
            for test in spec.get("tests") or []:
                if test.get("status") != "skipped":
                    continue
                notes = [a for a in test.get("annotations") or [] if isinstance(a, dict) and a.get("type") == "skip"]
                found.setdefault(str(spec.get("title") or ""), str((notes[0].get("description") if notes else "") or "skipped"))
        for child in suite.get("suites") or []:
            walk(child)

    for suite in data.get("suites") or []:
        if isinstance(suite, dict):
            walk(suite)
    return [[title, why] for title, why in found.items()]


def _counts(workspace: Path, since: float) -> dict[str, int]:
    """What this run's results.json says (nothing when the run left none, or only an older one)."""
    path = workspace / build_evidence.PLAYWRIGHT_JSON
    try:
        if path.stat().st_mtime < since - 2:
            return {"total": 0, "passed": 0, "failed": 0, "flaky": 0}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"total": 0, "passed": 0, "failed": 0, "flaky": 0}
    parsed = build_evidence._from_playwright_json(data, workspace) or {}  # noqa: SLF001
    return {key: int(parsed.get(key) or 0) for key in ("total", "passed", "failed", "flaky")}


def failures(workspace: Path) -> list[dict[str, str]]:
    """The journeys whose newest result failed, with the first line of why: what a fix the person asks for is given."""
    from server_modules import journeys

    derived = journeys.e2e_coverage(workspace, _journey_tests(workspace)) or {}
    out = []
    for row in derived.get("journeys") or []:
        if row.get("status") == "passed":
            continue
        reason = next((t.get("error") for t in row.get("tests") or [] if t.get("error")), "") or (
            "no test is named with this id" if not row.get("tests") else "the test failed")
        out.append({"id": str(row["id"]), "name": str(row.get("workflow_name") or ""), "why": str(reason)[:300],
                    "files": ", ".join(sorted({_spec_path(workspace, str(t.get("file") or ""))
                                               for t in row.get("tests") or [] if t.get("file")}))})
    return out


def _spec_path(workspace: Path, name: str) -> str:
    """Where a spec the results name only by its file name lives in the project (`e2e/journeys/UJ-001.spec.js`)."""
    found = sorted((workspace / "e2e").rglob(name)) if name and (workspace / "e2e").is_dir() else []
    return found[0].relative_to(workspace).as_posix() if found else f"e2e/{name}"


_FIX_ASKED = re.compile(r"\bfix\b.{0,40}\b(fail(?:ing|ed)?|broken)\b.{0,20}\bjourneys?\b|\bfix\b.{0,20}\bjourneys?\b.{0,20}\bfail",
                        re.I | re.S)


def fix_asked(text: str) -> bool:
    """Whether what was typed asks for the failed journeys to be fixed ("fix the failing journeys", the button's words)."""
    return bool(_FIX_ASKED.search(str(text or ""))) and len(str(text or "")) < 300


def fix_request(workspace: Path, said: str = "") -> tuple[str, list[str]]:
    """What a fix of the failed journeys is given (written here, from the results on disk), and their ids. ("", []) when
    every journey passed."""
    from server_modules import prompts

    failed = failures(workspace)
    if not failed:
        return "", []
    rows = "\n".join(f"- **{row['id']}** {row['name']}" + (f" — `{row['files']}`" if row["files"] else "")
                     + f": {row['why']}" for row in failed)
    request = prompts.load("testing/fix-journeys", journeys=rows).strip()
    extra = str(said or "").strip()
    if extra and not re.fullmatch(r"\s*fix (the )?fail(ing|ed) journeys\s*\.?\s*", extra, re.I):
        request += f"\n\nThe person also said: {extra}"
    return request, [row["id"] for row in failed]


def journey_ids(workspace: Path) -> list[dict[str, str]]:
    """The journeys of the contract, in order: [{"id", "name"}]."""
    from server_modules import journeys

    contract = journeys.read_journey_contract(workspace) or {}
    return [{"id": str(j["id"]), "name": str(j.get("workflow_name") or j["id"])} for j in contract.get("journeys") or []
            if isinstance(j, dict) and j.get("id")]


REQUIREMENT_SPECS = "e2e/requirements"


def requirement_specs(workspace: Path) -> list[dict[str, Any]]:
    """The requirement tests the build wrote for pages no journey goes through: [{"id": spec path, "name", "grep": ids}]."""
    folder = workspace / REQUIREMENT_SPECS
    out = []
    for spec in sorted(folder.glob("*.spec.*")) if folder.is_dir() else []:
        try:
            ids = sorted(set(re.findall(r"\bFR-\d+\b", spec.read_text(encoding="utf-8", errors="replace"))))
        except OSError:
            continue
        if ids:
            out.append({"id": spec.relative_to(workspace).as_posix(), "name": spec.name, "grep": ids})
    return out


def fix_spec_request(workspace: Path, spec: dict[str, Any]) -> str:
    """What the fix of a failed requirement test is given: the tests of `spec` whose newest desktop result failed."""
    from server_modules import prompts

    wanted = set(spec["grep"])
    failed = [t for t in build_evidence.newest_tests(workspace)
              if str(t.get("status")) == "failed" and "mobile" not in str(t.get("project") or "")
              and wanted & set(re.findall(r"\bFR-\d+\b", f"{t.get('suite') or ''} {t.get('title') or ''}"))]
    if not failed:
        return ""
    rows = "\n".join(f"- `{spec['id']}` — {t.get('title')}: {str(t.get('error') or 'the test failed')[:300]}" for t in failed)
    return prompts.load("testing/fix-journey", journey=rows).strip()


def fix_one_request(workspace: Path, journey_id: str) -> str:
    """What the fix of one failed journey is given: its name, spec file and why it failed. "" when it did not fail."""
    from server_modules import prompts

    row = next((r for r in failures(workspace) if r["id"] == journey_id), None)
    if row is None:
        return ""
    text = f"- **{row['id']}** {row['name']}" + (f" — `{row['files']}`" if row["files"] else "") + f": {row['why']}"
    return prompts.load("testing/fix-journey", journey=text).strip()


def record_full(workspace: Path, entry: dict[str, Any]) -> None:
    """A journey-by-journey pass over every journey is the app's run, as a full run is: what `current` and the runtime
    test's carry-over read."""
    saved = record(workspace)
    saved["full"] = {**entry, "fingerprint": fingerprint(workspace)}
    _save(workspace, saved)


def _journey_tests(workspace: Path) -> list[dict[str, Any]]:
    """Every test's newest result across the kept runs (a re-run of one journey replaces only that journey's result)."""
    return build_evidence.newest_tests(workspace)
