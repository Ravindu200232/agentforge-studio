"""Live monitors: the evidence a deployment's own command line tools can give, run on a click and streamed.

What can be asked of each provider (`vercel ls`, `aws logs tail`, `az webapp show`, `gh run list`) is data, in
`prompts/deployment/monitors.json`: per deployment type, a list of read-only commands. This module resolves the
values each command needs from the deployment's own record (`.agentforge/deploy/run.json`), runs one when asked
in the project's folder, and hands its output back as it is written, so the studio can show it live.

Nothing here can run anything but that list: a command is chosen by its id, its arguments are the list's own,
and a value taken from the record goes in as one plain argument (never through a shell) and only when it looks
like a name, an id, an address or an ARN. What comes back is stripped of colour codes and of anything that looks
like a secret, including every value the customer saved for deployments.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from . import cli_signin, config, deploy_vars, prompts, secrets_guard

MAX_LINES = 4000
KEEP_SECONDS = 900
MAX_JOBS = 24
DEFAULT_TIMEOUT = 90

# A value taken from the record is used as a single argument, so it must be plain: a name, an id, an address, an ARN, a path such
# as an AWS log group (/app/name). It may start with `/` but never with `-`, which a tool would read as an option.
_SAFE = re.compile(r"^[A-Za-z0-9/][A-Za-z0-9._:/@=+,~%\-]*$")
_PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Settings a command may name. Never a secret.
_SETTINGS = {"aws_profile", "aws_region"}


def _catalogue() -> dict[str, Any]:
    return prompts.data("deployment/monitors")


# --- what can be asked, for one deployment --------------------------------------------------------

def _dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return None
    return data


def _slug(url: str) -> str:
    """`owner/repo` from a GitHub address."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    return "/".join(parts[:2]).removesuffix(".git") if len(parts) >= 2 else ""


def _value(expression: str, run: dict) -> str | None:
    """One `{{...}}`: the first of its `|` alternatives that the record (or a setting) has, optionally turned into a slug."""
    for alternative in expression.split("|"):
        alternative, _, transform = alternative.strip().partition(":")
        if alternative.startswith("setting."):
            name = alternative[len("setting."):]
            found = config.setting(name) if name in _SETTINGS else None
        else:
            found = _dig(run, alternative)
        if isinstance(found, (str, int)) and str(found).strip():
            text = str(found).strip()
            if transform == "slug":
                text = _slug(text)
            if text and _SAFE.match(text):
                return text
    return None


def _fill(text: str, run: dict) -> tuple[str | None, str]:
    """A catalogue argument with its values filled in, or why it cannot be."""
    missing: list[str] = []

    def swap(match: re.Match[str]) -> str:
        found = _value(match.group(1), run)
        if found is None:
            missing.append(match.group(1).split("|")[0].split(":")[0])
            return ""
        return found

    filled = _PLACEHOLDER.sub(swap, text)
    return (None, "the deployment record has no " + ", ".join(missing)) if missing else (filled, "")


def _tool(command: dict, group: dict) -> str:
    return str(command.get("tool") or group.get("tool") or "")


def _resolve(command: dict, group: dict, run: dict) -> dict[str, Any]:
    argv, reason = [], ""
    for raw in [*command.get("argv", []), *group.get("common", [])]:
        filled, why = _fill(str(raw), run)
        if filled is None:
            reason = why
            break
        argv.append(filled)
    return {"id": command["id"], "label": command["label"], "group": command.get("group", ""),
            "follow": bool(command.get("follow")), "timeout": int(command.get("timeout") or DEFAULT_TIMEOUT),
            "tool": _tool(command, group), "argv": [] if reason else argv, "reason": reason, "available": not reason}


def _display(item: dict) -> str:
    """The command as a person would type it, with a long query left as an ellipsis."""
    shown, previous = [], ""
    for argument in item.get("argv", []):
        shown.append('"…"' if previous == "--query" else argument)
        previous = argument
    return " ".join([item["tool"], *shown])


def catalogue(project: str, run: dict | None = None) -> dict[str, Any]:
    """The monitors of this project's deployment type that can be run now: `{target, items}`."""
    from deploy_agent import deploy

    run = run if run is not None else deploy.run_state(project)
    target = str(run.get("target") or "")
    sets = _catalogue()["sets"]
    items: list[dict] = []
    seen: set[str] = set()
    for name in _catalogue()["targets"].get(target, []):
        group = sets.get(name) or {}
        for command in group.get("commands", []):
            item = _resolve(command, group, run)
            key = f"{item['tool']}:{item['id']}"
            if not item["available"] or key in seen:
                continue
            seen.add(key)
            item.update(set=name, cli=group.get("title", name), display=_display(item), installed=bool(cli_signin._where(item["tool"])))
            del item["argv"]
            items.append(item)
    return {"target": target, "items": items}


# --- running one ---------------------------------------------------------------------------------

class Job:
    def __init__(self, project: str, command: dict, argv: list[str]):
        self.id = f"mon_{uuid.uuid4().hex[:10]}"
        self.project, self.command, self.argv = project, command, argv
        self.lines: list[str] = []
        self.total = 0                       # every line ever added, so a reader's position survives lines dropped
        self.status = "running"              # running | done | failed | stopped | timeout
        self.exit_code: int | None = None
        self.process: subprocess.Popen | None = None
        self.started = time.time()
        self.finished = 0.0
        self.lock = threading.Lock()

    @property
    def offset(self) -> int:
        """How many lines have been dropped from the front."""
        return self.total - len(self.lines)

    def add(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)
            self.total += 1
            if len(self.lines) > MAX_LINES:
                del self.lines[: len(self.lines) - MAX_LINES]


def _mask(text: str) -> str:
    """Colour codes out, and anything that looks like a secret, or is one the customer saved for deployments."""
    clean = _ANSI.sub("", text.replace("\r", ""))
    for value in deploy_vars.secret_values():
        clean = clean.replace(value, "<hidden>")
    return secrets_guard.mask(clean)


class Monitors:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # -- starting and stopping

    def start(self, project: str, command_id: str) -> dict[str, Any]:
        from deploy_agent import deploy

        run = deploy.run_state(project)
        target = str(run.get("target") or "")
        if not target:
            raise ValueError("this project has no deployment to look at yet")
        command, group = self._find(target, command_id)
        item = _resolve(command, group, run)
        if not item["available"]:
            raise ValueError(item["reason"])
        exe = cli_signin._where(item["tool"])
        if not exe:
            raise ValueError(f"the {item['tool']} command line tool is not installed on this computer")
        job = Job(project, item, [exe, *item["argv"]])
        self._prune()
        # Looking at the same thing again replaces the earlier look at it.
        for other in list(self._jobs.values()):
            if other.project == project and other.command["id"] == command_id and other.status == "running":
                self._stop(other)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, str(config.workspace_for(project))), name=f"monitor:{job.id}",
                         daemon=True).start()
        return {"job": job.id, "display": _display(item), "follow": item["follow"], "timeout": item["timeout"]}

    @staticmethod
    def _find(target: str, command_id: str) -> tuple[dict, dict]:
        sets = _catalogue()["sets"]
        for name in _catalogue()["targets"].get(target, []):
            group = sets.get(name) or {}
            for command in group.get("commands", []):
                if command["id"] == command_id:
                    return command, group
        raise ValueError(f"there is no monitor called {command_id!r} for this deployment")

    def _run(self, job: Job, cwd: str) -> None:
        # The tools get this computer's environment, without what belongs to the assistant that may have started the
        # server (some tools print a hint to it, and its keys are not theirs to have).
        inherited = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC"))}
        env = {**inherited, "NO_COLOR": "1", "FORCE_COLOR": "0", "TERM": "dumb", "AWS_PAGER": "", "CI": "1",
               "PYTHONIOENCODING": "utf-8", "AZURE_CORE_NO_COLOR": "true", "AZURE_CORE_COLLECT_TELEMETRY": "false",
               "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_UPDATE_NOTIFIER": "1"}
        timeout = int(job.command["timeout"])
        try:
            job.process = subprocess.Popen(job.argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                           env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            job.add(f"could not start: {exc}")
            self._finish(job, "failed", 1)
            return

        def watchdog() -> None:
            deadline = job.started + timeout
            while job.status == "running" and time.time() < deadline:
                time.sleep(0.5)
            if job.status == "running":
                job.status = "timeout"
                self._kill(job)

        threading.Thread(target=watchdog, daemon=True).start()
        assert job.process.stdout is not None
        for line in iter(job.process.stdout.readline, ""):
            job.add(_mask(line.rstrip("\n")))
        code = job.process.wait()
        if job.status == "running":
            self._finish(job, "done" if code == 0 else "failed", code)
        else:
            job.exit_code, job.finished = code, time.time()

    @staticmethod
    def _finish(job: Job, status: str, code: int | None) -> None:
        job.status, job.exit_code, job.finished = status, code, time.time()

    @staticmethod
    def _kill(job: Job) -> None:
        process = job.process
        if not process or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            process.terminate()

    def _stop(self, job: Job) -> None:
        if job.status == "running":
            job.status = "stopped"
        self._kill(job)

    def stop(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if job:
            self._stop(job)
        return {"ok": True}

    # -- reading

    def poll(self, job_id: str, since: int = 0) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            return {"status": "gone", "lines": [], "next": since}
        with job.lock:
            lines = job.lines[max(0, since - job.offset):]
            following = job.total
            dropped = max(0, job.offset - since)
        took = (job.finished or time.time()) - job.started
        return {"status": job.status, "exit_code": job.exit_code, "lines": lines, "next": following,
                "seconds": round(took, 1), "dropped": dropped}

    def _prune(self) -> None:
        now = time.time()
        with self._lock:
            for key, job in list(self._jobs.items()):
                if job.status != "running" and job.finished and now - job.finished > KEEP_SECONDS:
                    del self._jobs[key]
            while len(self._jobs) > MAX_JOBS:
                oldest = min(self._jobs.values(), key=lambda j: j.started)
                self._stop(oldest)
                del self._jobs[oldest.id]


MONITORS = Monitors()
