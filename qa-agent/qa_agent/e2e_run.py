"""The end-to-end suite, run once by the Studio itself.

The agent writes the journey tests and runs one spec file at a time while it writes or fixes them; the whole suite is the
Studio's to run, here, once per build - never again by itself. It ran again and again before: inside the build's last
phase (where the agent's ten-minute command limit killed it half-way, leaving a partial `results.json`), after every
screenshot-review fix, and once more in the Testing stage straight after a build that had just run it. Now:

- a build runs it once, after its phases, when the app's source is not what the last full run already tested (`current`);
- a Testing run reuses that run while the source is unchanged, unless the person asks for the journeys to run again;
- a fix the person asked for runs only the journeys it fixed (`grep`), and so does a screenshot-review round they said yes to.

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
TEMPLATE_RUNNER = (config.ROOT / "builder-agent" / "builder_agent" / "assets" / "templates" / "_testing" / "scripts"
                   / "with-server.mjs")
RUN_SECONDS = 45 * 60             # the whole suite, desktop and mobile; the agent's own commands stop at ten minutes
BUILD_SECONDS = 15 * 60
HEARTBEAT_SECONDS = 30
# The visual and accessibility checks are runs of their own (`qa:visual`, `qa:a11y`), not journeys. A journey that stalls
# once is tried once more (Playwright records it as flaky, and its last attempt decides), and two workers share the server.
PLAYWRIGHT_ARGS = ["--grep-invert", "@visual|@a11y", "--retries=1", "--workers=2"]
# What is not the app's source: what a build, a test run, a deployment or the Studio writes.
_SKIP_DIRS = {"node_modules", ".next", ".git", "test-results", "playwright-report", ".agentforge", ".lighthouseci", ".zap",
              ".vercel", ".netlify", "dist", "build", "coverage", "out", "__screenshots__", ".turbo", ".cache"}
_MAX_HASHED = 2_000_000


def fingerprint(workspace: Path) -> str:
    """What the app's source is now: its files, by path and content, without anything a build or a test run writes."""
    digest = hashlib.sha256()
    for root, dirs, names in os.walk(workspace):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(names):
            path = Path(root) / name
            try:
                if path.stat().st_size > _MAX_HASHED:
                    continue
                digest.update(path.relative_to(workspace).as_posix().encode("utf-8"))
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


def run(project: str, session: Any, grep: list[str] | None = None, reason: str = "build", force: bool = False) -> dict[str, Any]:
    """Run the end-to-end journeys: all of them, or only the tests `grep` names (journey ids or titles).

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
        command = [_node(), RUNNER, "--", "npx", "playwright", "test", *PLAYWRIGHT_ARGS]
        if pattern:
            command += ["--grep", pattern]
        shown = "node scripts/with-server.mjs -- npx playwright test " + " ".join(
            f'"{arg}"' if " " in arg or "|" in arg else arg for arg in PLAYWRIGHT_ARGS) + (f' --grep "{pattern}"' if pattern else "")
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


def _journey_tests(workspace: Path) -> list[dict[str, Any]]:
    """Every test's newest result across the kept runs (a re-run of one journey replaces only that journey's result)."""
    return build_evidence.newest_tests(workspace)
