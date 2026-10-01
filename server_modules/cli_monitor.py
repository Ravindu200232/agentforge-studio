"""Live monitors: the evidence a project's own command line tools can give, run on a click and streamed.

What can be asked of each provider (`vercel ls`, `aws logs tail`, `az webapp show`, `gh run list`) is data, in
`prompts/deployment/monitors.json`: per deployment type, a list of read-only commands. This module resolves the
values each command needs from the deployment's own record (`.agentforge/deploy/run.json`), runs one when asked
in the project's folder, and hands its output back as it is written, so the studio can show it live.

The database panel is the same thing in a second scope: `prompts/database/monitors.json` lists what the Supabase
command line tool and the project's own MongoDB driver can show, its values come from the project's database
connections (`database_context`), and each set names the credentials its tool is given in its environment.

Nothing here can run anything but that list: a command is chosen by its id, its arguments are the list's own,
and a value taken from the record goes in as one plain argument (never through a shell) and only when it looks
like a name, an id, an address or an ARN. What comes back is stripped of colour codes and of anything that looks
like a secret, including every value the customer saved for deployments and every credential a set was given.

The terminal's command box (`start_shell`) is the one exception: what the person types runs in the project folder,
through the shell, with the same output reading, stopping and masking.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import cli_signin, config, deploy_vars, prompts, secrets_guard

MAX_LINES = 4000
KEEP_SECONDS = 900
MAX_JOBS = 24
DEFAULT_TIMEOUT = 90
SHELL_TIMEOUT = 1800

# Where each scope's commands are listed.
CATALOGUES = {"deploy": "deployment/monitors", "database": "database/monitors"}
# A file a database command reads: a query of the pack's own, or one of the studio's scripts. Only by name.
QUERIES = config.PROMPTS / "database" / "queries"
SCRIPTS = Path(__file__).resolve().parent / "scripts"
_ASSET = re.compile(r"^(file|script)\.([a-z0-9-]+)$")

# A value taken from the record is used as a single argument, so it must be plain: a name, an id, an address, an ARN, a path such
# as an AWS log group (/app/name). It may start with `/` but never with `-`, which a tool would read as an option.
_SAFE = re.compile(r"^[A-Za-z0-9/][A-Za-z0-9._:/@=+,~%\-]*$")
_PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Settings a command may name. Never a secret.
_SETTINGS = {"aws_profile", "aws_region"}


def _catalogue(scope: str = "deploy") -> dict[str, Any]:
    if scope not in CATALOGUES:
        raise ValueError(f"there are no monitors for {scope!r}")
    return prompts.data(CATALOGUES[scope])


def _asset(expression: str) -> str | None:
    """`file.<name>` (a query in the pack) or `script.<name>` (a studio script): its path, if it is one of them."""
    match = _ASSET.match(expression)
    if not match:
        return None
    kind, name = match.groups()
    path = QUERIES / f"{name}.sql" if kind == "file" else SCRIPTS / f"{name}.mjs"
    return str(path) if path.is_file() else None


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
        if _ASSET.match(alternative):
            # The studio's own file, whole: its path may hold characters a record value may not.
            found = _asset(alternative)
            if found:
                return found
            continue
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
            "tool": _tool(command, group), "argv": [] if reason else argv, "reason": reason, "available": not reason,
            "shown": str(command.get("display") or "")}


def _display(item: dict) -> str:
    """The command as a person would type it, with a long query left as an ellipsis."""
    if item.get("shown"):
        return item["shown"]
    shown, previous = [], ""
    for argument in item.get("argv", []):
        shown.append('"…"' if previous == "--query" else argument)
        previous = argument
    return " ".join([item["tool"], *shown])


# --- what a project's databases are ------------------------------------------------------------

def mongodb_uri() -> str:
    """The MongoDB connection string a build, its preview and its deployment are given."""
    return str(deploy_vars.environment().get("MONGODB_URI") or "")


def uses_mongodb(project: str) -> bool:
    from . import store

    stack = str((store.get(project) or {}).get("stack") or "").lower()
    return "mongo" in stack or "mern" in stack or (config.workspace_for(project) / "node_modules" / "mongodb").is_dir()


def mongodb_database(uri: str) -> str:
    """The database a connection string names, or the one a driver falls back to."""
    path = urlparse(uri).path.strip("/") if uri else ""
    return unquote(path) or "test"


def database_context(project: str) -> dict[str, Any]:
    """What the database monitors fill their commands from: the project's connections, never a credential."""
    from . import supabase_connect

    context: dict[str, Any] = {"targets": []}
    linked = supabase_connect.status(project)
    if linked.get("connected"):
        context["supabase"] = {"ref": linked.get("ref", ""), "name": linked.get("name", ""), "url": linked.get("url", "")}
        context["targets"].append("supabase")
    uri = mongodb_uri()
    if uri and uses_mongodb(project):
        context["mongodb"] = {"database": mongodb_database(uri)}
        context["targets"].append("mongodb")
    return context


def _driver_base(project: str) -> str:
    """The project's own MongoDB driver, else any built project's."""
    from . import mongo_check

    root = config.workspace_for(project)
    return str(root) if (root / "node_modules" / "mongodb" / "package.json").is_file() else mongo_check._driver_base()  # noqa: SLF001


def _set_environment(kind: str, project: str) -> tuple[dict[str, str], list[str]]:
    """What a set's tool is given beyond this computer's environment, and the values that must never be shown."""
    if kind == "supabase":
        from . import supabase_connect

        token = supabase_connect._env_with_token().get("SUPABASE_ACCESS_TOKEN", "")  # noqa: SLF001
        row = supabase_connect.record(project)
        hidden = [token, *(str(row.get(key) or "") for key in ("anon_key", "service_role_key", "db_password"))]
        return {"SUPABASE_ACCESS_TOKEN": token}, hidden
    if kind == "mongodb":
        uri = mongodb_uri()
        password = unquote(urlparse(uri).password or "") if uri else ""
        return {"CHECK_URI": uri, "DRIVER_BASE": _driver_base(project)}, [uri, password]
    return {}, []


def _context(project: str, scope: str) -> tuple[dict, list[str]]:
    """The record a scope's commands are filled from, and which of its catalogue's targets apply."""
    if scope == "database":
        context = database_context(project)
        return context, list(context["targets"])
    from deploy_agent import deploy

    run = deploy.run_state(project)
    return run, [str(run.get("target") or "")]


def catalogue(project: str, run: dict | None = None, scope: str = "deploy") -> dict[str, Any]:
    """The monitors of this project's deployment type (or its databases) that can be run now: `{target, items}`."""
    if run is None:
        run, targets = _context(project, scope)
    else:
        targets = list(run.get("targets") or []) if scope == "database" else [str(run.get("target") or "")]
    sets = _catalogue(scope)["sets"]
    items: list[dict] = []
    seen: set[str] = set()
    for target in targets:
        for name in _catalogue(scope)["targets"].get(target, []):
            group = sets.get(name) or {}
            for command in group.get("commands", []):
                item = _resolve(command, group, run)
                key = f"{item['tool']}:{item['id']}"
                if not item["available"] or key in seen:
                    continue
                seen.add(key)
                item.update(set=name, cli=group.get("title", name), display=_display(item), scope=scope,
                            installed=bool(cli_signin._where(item["tool"])))
                del item["argv"], item["shown"]
                items.append(item)
    return {"target": ",".join(t for t in targets if t), "items": items,
            **({"context": run} if scope == "database" else {})}


# --- running one ---------------------------------------------------------------------------------

class Job:
    def __init__(self, project: str, command: dict, argv: list[str], env: dict[str, str] | None = None,
                 hidden: list[str] | None = None):
        self.id = f"mon_{uuid.uuid4().hex[:10]}"
        self.project, self.command, self.argv = project, command, argv
        # What this one command is given beyond the computer's environment, and must never be shown.
        self.env = env or {}
        self.hidden = [value for value in (hidden or []) if value and len(value) >= 6]
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


def _mask(text: str, hidden: list[str] | None = None) -> str:
    """Colour codes out, and anything that looks like a secret, is one the customer saved for deployments, or is
    one this command was given."""
    clean = _ANSI.sub("", text.replace("\r", ""))
    for value in [*deploy_vars.secret_values(), *(hidden or [])]:
        if value:
            clean = clean.replace(value, "<hidden>")
    return secrets_guard.mask(clean)


def _kills_everything(command: str) -> bool:
    """Ending every Node process would end the Studio itself and every preview with it."""
    lowered = command.lower()
    return ("taskkill" in lowered and "/im" in lowered and "node" in lowered) \
        or bool(re.search(r"stop-process\s+(-name\s+)?node\b", lowered)) \
        or bool(re.search(r"\b(killall|pkill)\s+(-\w+\s+)*node\b", lowered))


def _shell_problem(command: str) -> str:
    from ollama_terminal.tools import _DENY_PATTERNS

    if _kills_everything(command):
        return "That would stop every Node process, the Studio included. Stop one process by its PID instead."
    lowered = command.lower()
    for pattern, message in _DENY_PATTERNS:
        if pattern.search(lowered):
            return message
    return ""


def _shell() -> list[str]:
    if os.name == "nt":
        return [shutil.which("powershell") or "powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
    return [os.environ.get("SHELL") or "/bin/sh", "-c"]


def _project_environment(project: str) -> tuple[dict[str, str], list[str]]:
    """What the project's own commands run with: the variables its build and preview get."""
    from . import plugins, supabase_connect

    enabled_path = config.record_dir(project) / "plugins.json"
    try:
        enabled = json.loads(enabled_path.read_text(encoding="utf-8")) if enabled_path.is_file() else []
    except ValueError:
        enabled = []
    supabase = supabase_connect.env_for(project)
    env = {**plugins.environment(enabled), **supabase, **deploy_vars.environment()}
    hidden = [value for key, value in supabase.items() if "KEY" in key or "DB_URL" in key]
    uri = env.get("MONGODB_URI", "")
    hidden += [uri, unquote(urlparse(uri).password or "")] if uri else []
    return env, hidden


class Monitors:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # -- starting and stopping

    def start(self, project: str, command_id: str, scope: str = "deploy") -> dict[str, Any]:
        run, targets = _context(project, scope)
        if not any(targets):
            raise ValueError("this project has no database connected yet" if scope == "database"
                             else "this project has no deployment to look at yet")
        command, group = self._find(targets, command_id, scope)
        item = _resolve(command, group, run)
        if not item["available"]:
            raise ValueError(item["reason"])
        exe = cli_signin._where(item["tool"])
        if not exe:
            raise ValueError(f"the {item['tool']} command line tool is not installed on this computer")
        env, hidden = _set_environment(str(group.get("env") or ""), project)
        job = Job(project, item, [exe, *item["argv"]], env=env, hidden=hidden)
        return self._begin(job, project)

    def start_shell(self, project: str, command: str) -> dict[str, Any]:
        """What the person typed in the terminal, run in the project folder with the project's own variables."""
        text = str(command or "").strip()
        if not text:
            raise ValueError("type a command first")
        if len(text) > 4000:
            raise ValueError("that command is too long")
        problem = _shell_problem(text)
        if problem:
            raise ValueError(problem)
        env, hidden = _project_environment(project)
        item = {"id": f"shell-{uuid.uuid4().hex[:6]}", "label": text, "follow": True, "timeout": SHELL_TIMEOUT,
                "tool": "shell", "shown": text}
        # Windows PowerShell re-encodes what it relays in the console's old code page unless told otherwise.
        run = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; "
               + text) if os.name == "nt" else text
        job = Job(project, item, [*_shell(), run], env=env, hidden=hidden)
        return self._begin(job, project)

    def _begin(self, job: Job, project: str) -> dict[str, Any]:
        self._prune()
        # Looking at the same thing again replaces the earlier look at it.
        for other in list(self._jobs.values()):
            if other.project == project and other.command["id"] == job.command["id"] and other.status == "running":
                self._stop(other)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, str(config.workspace_for(project))), name=f"monitor:{job.id}",
                         daemon=True).start()
        return {"job": job.id, "display": _display(job.command), "follow": job.command["follow"],
                "timeout": job.command["timeout"]}

    @staticmethod
    def _find(targets: list[str], command_id: str, scope: str = "deploy") -> tuple[dict, dict]:
        sets = _catalogue(scope)["sets"]
        for target in targets:
            for name in _catalogue(scope)["targets"].get(target, []):
                group = sets.get(name) or {}
                for command in group.get("commands", []):
                    if command["id"] == command_id:
                        return command, group
        raise ValueError(f"there is no monitor called {command_id!r} for this "
                         + ("project's databases" if scope == "database" else "deployment"))

    def _run(self, job: Job, cwd: str) -> None:
        # The tools get this computer's environment, without what belongs to the assistant that may have started the
        # server (some tools print a hint to it, and its keys are not theirs to have).
        inherited = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC"))}
        env = {**inherited, "NO_COLOR": "1", "FORCE_COLOR": "0", "TERM": "dumb", "AWS_PAGER": "", "CI": "1",
               "PYTHONIOENCODING": "utf-8", "AZURE_CORE_NO_COLOR": "true", "AZURE_CORE_COLLECT_TELEMETRY": "false",
               "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_UPDATE_NOTIFIER": "1", **job.env}
        if not Path(cwd).is_dir():
            job.add("the project folder does not exist yet")
            self._finish(job, "failed", 1)
            return
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
            job.add(_mask(line.rstrip("\n"), job.hidden))
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
