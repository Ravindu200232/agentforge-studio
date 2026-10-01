"""Deploying the application: planned first, then carried out by the provider's own command line tool.

    Deploy pressed ──► plan (read-only, reads the project and the target's skill pages, may ask)
                          ▲                        │ the customer reads it in the chat
                          └──── revise ◄───────────┤ approve ──► carried out with a terminal
                                                   │             (git, gh, then the target's tool)
                                                   │                         │
                                                   │           the studio calls the live address itself;
                                                   │           what does not hold goes back to the agent
                                                   └ cancel

This is the chat's plan-first flow (`server_modules/changes.py`) with a deployment's own prompts. The
wording that tells the model what a complete deployment is, and how each target is done, lives in
`prompts/deployment/`: `plan.md`, `execute.md` and one skill page per target. This module keeps the
state, stages the skill pages where the agent can read them, measures what this computer has, and
checks the outcome without taking the agent's word for it.

The run's state and its events are files in the workspace (`.agentforge/deploy/`), written by the
agent as it works. Everything the studio's Deploy panel shows is read back from them, so a browser that
reconnects mid-deployment sees the run, not a blank panel.
"""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from server_modules import bus, changes, cli_signin, config, deploy_vars, prompts, reference_staging, store, supabase_connect
from server_modules.session import RunCancelled, session_for

DEPLOY_DIR = "deploy"
RUN = (DEPLOY_DIR, "run.json")
QUESTION = (DEPLOY_DIR, "question.json")
PLAN = (DEPLOY_DIR, "plan.json")
SKILLS_DIR = f"{config.RECORD_DIR}/{DEPLOY_DIR}/skills"

TERMINAL = {"LIVE", "FAILED", "ROLLED_BACK", "DESTROYED", "CANCELLED"}

# The stages the studio and the chat show for this flow (see `changes._execute_flow`).
STAGE_PLAN = "deploy_plan"
STAGE_RUN = "deploy"
# A deployment has many decisions the customer may make: account, names, layout, region, database, domain,
# cost, and every choice the target's and the stack's pages list. A guard against an endless interview only.
MAX_QUESTIONS = 20
# How many times a live address that does not hold is handed back to the agent before the run fails.
REPAIR_ROUNDS = 2
PROBE_SECONDS = 25

# Which skill pages each target reads, first the shared foundation, last the target's own. The pack
# decides what a target can do; this only says where to find it.
SKILLS_FOR = {
    "netlify": ["netlify"],
    "vercel": ["vercel"],
    "azure": ["azure"],
    "aws_ec2": ["aws", "aws-ec2"],
    "aws_ecs": ["aws", "aws-ecs"],
    "github": ["github"],
}
SKILL_FOR = {target: pages[-1] for target, pages in SKILLS_FOR.items()}
COMMON_SKILLS = ("core",)
REPAIR_SKILL = "deployment-repair"

# What a request that has not started carrying out yet looks like in the run record.
_STATE_OF = {"planning": "PLANNING", "asking": "NEEDS_INPUT", "proposed": "AWAITING_APPROVAL",
             "approved": "STARTING"}


# --- the targets --------------------------------------------------------------

def _catalogue() -> dict[str, dict[str, str]]:
    return {row["slug"]: row for row in prompts.catalogue("deployment")}


def label_of(target: str) -> str:
    """The name a customer knows the target by, from its own skill page's title."""
    page = _catalogue().get(SKILL_FOR.get(target, ""), {})
    return re.sub(r"^(Deploy|Publish) to ", "", page.get("title", ""), flags=re.I) or target


def targets() -> list[dict[str, str]]:
    """The targets this installation actually has skill pages for."""
    installed = set(_catalogue())
    return [{"id": target, "skill": SKILL_FOR[target], "label": label_of(target), "provider": pages[0]}
            for target, pages in SKILLS_FOR.items() if all(page in installed for page in pages)]


# --- the stack -----------------------------------------------------------------

DEFAULT_STACK = "nextjs-supabase"


def stack_of(project: str) -> str:
    """The stack the project was built on: what the build recorded, else what the project was created with."""
    built = session_for(project).read_record("build", "scaffold.json", fallback=None)
    found = str((built or {}).get("stack") or "") if isinstance(built, dict) else ""
    return found or str((store.get(project) or {}).get("stack") or "") or DEFAULT_STACK


def stack_info(stack: str) -> dict[str, Any]:
    """What the deployment pack says about a stack: its name, its skill page and which targets can host it."""
    known = prompts.data("deployment/stacks")
    return known.get(stack) or known.get(DEFAULT_STACK) or {}


def allowed_targets(stack: str) -> list[str]:
    """The targets that can host this stack, from the pack's own data."""
    wanted = stack_info(stack).get("targets", "all")
    every = [row["id"] for row in targets()]
    return every if wanted == "all" else [target for target in every if target in wanted]


# --- the run's own files -------------------------------------------------------

def run_state(project: str) -> dict[str, Any]:
    saved = session_for(project).read_record(*RUN, fallback=None)
    return saved if isinstance(saved, dict) else {}


def events(project: str, limit: int = 1000) -> list[dict[str, Any]]:
    session = session_for(project)
    path = session.record / DEPLOY_DIR / "events.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows[-limit:]


def pending_question(project: str) -> dict[str, Any] | None:
    saved = session_for(project).read_record(*QUESTION, fallback=None)
    return saved if isinstance(saved, dict) and saved.get("question") else None


def plan_of(project: str) -> dict[str, Any] | None:
    saved = session_for(project).read_record(*PLAN, fallback=None)
    return saved if isinstance(saved, dict) and saved.get("steps") else None


def _archive(project: str) -> None:
    """Keep the last run's record before a new one replaces it: a redeploy starts from what it made."""
    session = session_for(project)
    last = run_state(project)
    if last.get("run_id"):
        session.write_record(DEPLOY_DIR, "runs", f"{last['run_id']}.json", data=last)
        log = session.record / DEPLOY_DIR / "events.jsonl"
        if log.is_file():
            shutil.copyfile(log, session.record / DEPLOY_DIR / "runs" / f"{last['run_id']}.events.jsonl")


def past_runs(project: str, limit: int = 10) -> list[dict[str, Any]]:
    folder = session_for(project).record / DEPLOY_DIR / "runs"
    rows: list[dict[str, Any]] = []
    if folder.is_dir():
        for path in folder.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(row, dict) and row.get("run_id"):
                rows.append(row)
    rows.sort(key=lambda row: float(row.get("started_at") or 0), reverse=True)
    return rows[:limit]


def _fresh_run(project: str, change: dict) -> dict[str, Any]:
    session = session_for(project)
    run = {"run_id": change.get("run_id", ""), "change_id": change.get("id", ""), "project": project,
           "target": change.get("target", ""),
           "state": "PLANNING", "url": "", "started_at": time.time(), "finished_at": "",
           "repository": {}, "artifacts": [], "evidence": [], "checks": [],
           "security": {"secrets_in_repo": False, "notes": []}, "rollback": "", "error": ""}
    (session.record / DEPLOY_DIR).mkdir(parents=True, exist_ok=True)
    (session.record / DEPLOY_DIR / "events.jsonl").write_text("", encoding="utf-8")
    for name in ("question.json", "plan.json"):
        (session.record / DEPLOY_DIR / name).unlink(missing_ok=True)
    return run


def _restore_run(project: str, change: dict) -> dict[str, Any] | None:
    """The record and events of a run that was archived when another began, for taking it up again."""
    session = session_for(project)
    saved = session.read_record(DEPLOY_DIR, "runs", f"{change.get('run_id')}.json", fallback=None)
    if not isinstance(saved, dict) or not saved.get("run_id"):
        return None
    archived = session.record / DEPLOY_DIR / "runs" / f"{change.get('run_id')}.events.jsonl"
    log = session.record / DEPLOY_DIR / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    if archived.is_file():
        shutil.copyfile(archived, log)
    else:
        log.write_text("", encoding="utf-8")
    (session.record / DEPLOY_DIR / "question.json").unlink(missing_ok=True)
    return saved


def sync(change: dict) -> None:
    """Keep the run record in step with the request it belongs to (called whenever the request is saved)."""
    project = str(change.get("project") or "")
    session = session_for(project)
    run = run_state(project)
    if run.get("run_id") != change.get("run_id"):
        run = _restore_run(project, change) or _fresh_run(project, change)
    status = str(change.get("status") or "")
    if status in _STATE_OF:
        run["state"] = _STATE_OF[status]
        if status == "approved":
            run.update(error="", finished_at="")
    elif status in ("failed", "cancelled") and run.get("state") not in TERMINAL:
        run.update(state="FAILED" if status == "failed" else "CANCELLED", finished_at=time.time())
        if status == "failed":
            run["error"] = str(change.get("error") or run.get("error") or "")
    if change.get("plan"):
        session.write_record(*PLAN, data=change["plan"])
    session.write_record(*RUN, data=run)


# --- what the model reads ------------------------------------------------------

def _skill_slugs(project: str, target: str) -> list[str]:
    """The pages this deployment follows: the shared rules, the target, the stack, then repair."""
    stack_page = stack_info(stack_of(project)).get("skill")
    return [*COMMON_SKILLS, *SKILLS_FOR[target], *([stack_page] if stack_page else []), REPAIR_SKILL]


def stage_skills(project: str, target: str) -> list[str]:
    """Copy the skill pages this deployment follows into the project, where the agent can read them.

    The agent's file tools stop at the workspace's edge, and the pack lives beside the application: so the
    pages are copied in (fresh each time, so an edited page takes effect on the next run). Returns their
    paths relative to the workspace, the shared foundation first.
    """
    session = session_for(project)
    wanted = _skill_slugs(project, target)
    files = {f"{slug}/SKILL.md": prompts.skill("deployment", slug) for slug in wanted}
    return reference_staging.stage(session.workspace, SKILLS_DIR, files)


def _skill_lines(paths: list[str]) -> str:
    return reference_staging.as_bullets(paths)


def _run(command: list[str], cwd: Path | None = None, timeout: int = 20) -> str:
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (done.stdout or "").strip()


def _tool_lines(target: str) -> str:
    """Which command line tools are here and who each is signed in as: measured, not remembered."""
    keys = list(dict.fromkeys([SKILLS_FOR[target][0], "github"]))
    seen = cli_signin.SIGNINS.available(fresh=True)
    settings = config.settings()
    lines = []
    for key in keys:
        row = seen.get(key) or {}
        tool = cli_signin.PROVIDERS[key].tool
        if not row.get("installed"):
            lines.append(f"  - {row.get('title', key)} (`{tool}`): NOT installed. Install: `{row.get('install', '')}`")
            continue
        who = row.get("identity") or {}
        if not row.get("signed_in"):
            expired = " (its session has expired)" if who.get("expired") else ""
            lines.append(f"  - {row.get('title', key)} (`{tool}`): installed, NOT signed in{expired}")
            continue
        detail = [f"signed in as {who.get('account')}"]
        if who.get("subscription"):
            detail.append(f"subscription {who['subscription']} ({who.get('subscription_id', '')})")
        if who.get("aws_account"):
            detail.append(f"account {who['aws_account']}, profile `{who.get('profile', '')}`")
        if key == "aws" and settings.get("aws_region"):
            detail.append(f"region {settings['aws_region']}")
        if who.get("scopes"):
            detail.append("token permissions: " + ", ".join(who["scopes"]))
        if who.get("missing_scopes"):
            detail.append("MISSING permissions: " + ", ".join(who["missing_scopes"]))
        lines.append(f"  - {row.get('title', key)} (`{tool}`): " + "; ".join(detail))
    for name in ("git", "node", "npm"):
        found = shutil.which(name)             # npm is a script on Windows: run it by its resolved name
        version = _run([found, "--version"]) if found else ""
        lines.append(f"  - {name}: {version or 'NOT installed'}")
    return "\n".join(lines)


def _database_fact(project: str) -> str:
    """Whether this project's own Supabase project is linked, and what it's called."""
    row = supabase_connect.status(project)
    if not row.get("connected"):
        return ("none linked - this stack needs one. Tell the customer to pick a Supabase stack from "
                "the build setup bar if they have not, which connects one automatically")
    return (f"linked: {row.get('name') or row.get('ref')} ({row.get('url')}), reachable from the "
            f"internet already (handed to your commands as SUPABASE_URL, SUPABASE_ANON_KEY and "
            f"SUPABASE_SERVICE_ROLE_KEY; never print the keys)")


def _variables_fact() -> str:
    """The names of the values the customer saved for deployments (never the values)."""
    saved = [row["name"] for row in deploy_vars.names()]
    return ", ".join(saved) if saved else "none saved"


def _git_fact(workspace: Path) -> str:
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd=workspace)
    if not top or Path(top).resolve() != workspace.resolve():
        return "not a git repository of its own yet"
    branch = _run(["git", "branch", "--show-current"], cwd=workspace) or "(no commits yet)"
    commits = _run(["git", "rev-list", "--count", "HEAD"], cwd=workspace) or "0"
    remotes = _run(["git", "remote", "-v"], cwd=workspace).splitlines()
    dirty = len(_run(["git", "status", "--short"], cwd=workspace).splitlines())
    return (f"a repository on branch {branch} with {commits} commit(s), {dirty} changed file(s), "
            f"remote: {remotes[0] if remotes else 'none'}")


def _tests_fact(project: str) -> str:
    from qa_agent import verify

    try:
        report = verify.report(project)
    except Exception:  # noqa: BLE001 - a missing record is a fact, not an error
        return "no test record"
    if report.get("complete"):
        return "verification passed: " + json.dumps(report.get("summary") or {}, ensure_ascii=False)[:400]
    return "not verified in this session: " + json.dumps(report.get("summary") or {}, ensure_ascii=False)[:300]


def machine_facts(project: str, target: str, workspace: Path) -> str:
    shell = "Windows PowerShell" if os.name == "nt" else "a POSIX shell (/bin/sh)"
    stack = stack_of(project)
    return prompts.load("deployment/machine", stack=f"{stack} ({stack_info(stack).get('name', stack)})",
                        tools=_tool_lines(target), database=_database_fact(project), variables=_variables_fact(),
                        shell=f"{shell} on {platform.system()}", git=_git_fact(workspace),
                        tests=_tests_fact(project)).strip()


def _previous_run(project: str) -> str:
    past = past_runs(project, limit=5)
    last = next((row for row in past if row.get("state") == "LIVE"), past[0] if past else None)
    if not last:
        return ""
    summary = {key: last.get(key) for key in ("target", "state", "url", "repository", "rollback", "error")
               if last.get(key)}
    return prompts.load("deployment/previous-run", summary=json.dumps(summary, ensure_ascii=False, indent=2))


def plan_prompt(project: str, change: dict, session: Any, history: str, previous_plan: str,
                questions_left: str, language: str) -> str:
    """The planning prompt for this deployment (the flow's half of `changes._propose`)."""
    target = str(change["target"])
    paths = stage_skills(project, target)
    return prompts.load(
        "deployment/plan", target=target, target_label=label_of(target), project=project,
        stack_label=stack_info(stack_of(project)).get("name", stack_of(project)),
        skills=_skill_lines(paths), machine=machine_facts(project, target, session.workspace),
        previous_run=_previous_run(project),
        artifacts=changes.project_map(session.workspace), history=history, language=language,
        previous_plan=previous_plan, questions_left=questions_left)


# --- what the model returns ----------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:40]


def _reads(project: str, since: int) -> set[str]:
    """The files the agent has opened since the request began, from the durable event log."""
    return reference_staging.reads_since(project, since)


def validator(project: str, change: dict):
    """Checks one reply of the planner. What is wrong is the repair prompt, so it says how to fix it."""
    target = str(change["target"])
    since = int(change.get("created") or 0)
    required = [f"{SKILLS_DIR}/{slug}/SKILL.md" for slug in _skill_slugs(project, target)
                if slug != REPAIR_SKILL]

    def check(data: Any, may_ask: bool) -> dict:
        if not isinstance(data, dict):
            raise ValueError("return one JSON object")
        kind = str(data.get("kind") or "").strip()
        if kind == "question":
            return changes.check_question(data, may_ask)
        if kind != "plan":
            raise ValueError('"kind" must be "question" or "plan"')
        unread = reference_staging.unread(required, project, since)
        if unread:
            raise ValueError("read the skill pages before you plan, with read_file: "
                             + ", ".join(unread) + ". Then return the plan again.")
        title, summary = str(data.get("title") or "").strip(), str(data.get("summary") or "").strip()
        if not title or not summary:
            raise ValueError('a "plan" needs a "title" and a "summary"')
        impact = [{"stage": str(row.get("stage") or "").strip(), "affected": bool(row.get("affected")),
                   "why": str(row.get("why") or "").strip()}
                  for row in data.get("impact") or [] if isinstance(row, dict) and str(row.get("stage") or "").strip()]
        if not impact:
            raise ValueError('a "plan" needs "impact": every place the deployment touches, affected or not')
        steps, used = [], set()
        for row in data.get("steps") or []:
            if not isinstance(row, dict) or not str(row.get("title") or "").strip():
                continue
            base = _slug(row.get("id") or row.get("title")) or f"step_{len(steps) + 1}"
            name, number = base, 2
            while name in used:
                name, number = f"{base}_{number}", number + 1
            used.add(name)
            steps.append({"id": name, "stage": str(row.get("stage") or "").strip(),
                          "title": str(row.get("title")).strip(), "detail": str(row.get("detail") or "").strip(),
                          "commands": changes.texts(row.get("commands")), "files": changes.texts(row.get("files"))})
        if not steps:
            raise ValueError('a "plan" needs "steps": what is done, in order')
        verification = changes.texts(data.get("verification"))
        if not verification:
            raise ValueError('a "plan" needs "verification": the live checks that must pass before it is called live')
        rollback = changes.texts(data.get("rollback"))
        if not rollback:
            raise ValueError('a "plan" needs "rollback": how to go back, and how to remove it')
        return {"kind": "plan", "title": title, "summary": summary,
                "skills": [path for path in required if path in _reads(project, since)],
                "requirements": changes.texts(data.get("requirements")), "impact": impact, "steps": steps,
                "assumptions": changes.texts(data.get("assumptions")), "risks": changes.texts(data.get("risks")),
                "verification": verification, "rollback": rollback, "cost": changes.texts(data.get("cost"))}

    return check


def plan_markdown(plan: dict) -> str:
    """The approved plan as the text the executing agent is handed."""
    lines = [f"# {plan.get('title', '')}", "", str(plan.get("summary", ""))]
    if plan.get("requirements"):
        lines += ["", "## What it needs"] + [f"- {item}" for item in plan["requirements"]]
    lines += ["", "## Steps (each step's id is the stage its progress is reported under)"]
    for number, step in enumerate(plan.get("steps", []), 1):
        lines.append(f"{number}. `{step.get('id')}` [{step.get('stage', '')}] {step.get('title', '')}")
        if step.get("detail"):
            lines.append(f"   {step['detail']}")
        for command in step.get("commands", []):
            lines.append(f"   - `{command}`")
        for file in step.get("files", []):
            lines.append(f"   - file: {file}")
    for heading, key in (("Assumptions", "assumptions"), ("Risks", "risks"), ("Live checks", "verification"),
                         ("Rollback and removal", "rollback"), ("Cost", "cost")):
        if plan.get(key):
            lines += ["", f"## {heading}"] + [f"- {item}" for item in plan[key]]
    return "\n".join(lines)


# --- starting ------------------------------------------------------------------

def _require_cli(target: str) -> None:
    """Fail now, with a clear install command, rather than deep inside a
    `run_command` call the customer only sees as a cryptic mid-run error."""
    key = SKILLS_FOR[target][0]
    row = cli_signin.SIGNINS.available(only=key, fresh=True).get(key) or {}
    if not row.get("installed"):
        provider = cli_signin.PROVIDERS[key]
        raise ValueError(f"{provider.title} is not installed on this machine. "
                         f"Install it with `{row.get('install') or provider.install}` and try again.")


def start(project: str, target: str, model: str = "") -> dict[str, Any]:
    """Deploy pressed: plan it. Nothing is deployed until the customer approves what comes back."""
    known = {row["id"] for row in targets()}
    if target not in known:
        raise ValueError(f"no deployment skill is installed for {target!r}; "
                         f"available: {', '.join(sorted(known)) or 'none'}")
    stack = stack_of(project)
    if target not in allowed_targets(stack):
        info = stack_info(stack)
        raise ValueError(f"{info.get('name', stack)} cannot be deployed to {label_of(target)}: "
                         f"it {info.get('reason', 'is not supported there')}. "
                         f"Choose one of: {', '.join(label_of(t) for t in allowed_targets(stack))}.")
    _require_cli(target)
    session_for(project)
    _archive(project)
    run_id = f"dep_{uuid.uuid4().hex[:12]}"
    request = prompts.load("deployment/request", target_label=label_of(target)).strip()
    flow = {"flow": "deploy", "target": target, "run_id": run_id}
    result = changes.submit(project, request, model, echo=True, flow=flow)
    return {"ok": True, "project": project, "run_id": run_id, "change": result["change"]}


# --- carrying it out -----------------------------------------------------------

class _Progress(threading.Thread):
    """While the agent works, turn its own event log into chat stages, as they are written."""

    def __init__(self, project: str, titles: dict[str, str]):
        super().__init__(daemon=True, name=f"deploy-progress:{project}")
        self.project, self.titles, self.seen = project, titles, 0
        self._stop_event = threading.Event()

    def publish(self) -> None:
        rows = events(self.project)
        for row in rows[self.seen:]:
            stage = str(row.get("stage") or "deploy")
            status = str(row.get("status") or "active")
            title = self.titles.get(stage) or stage.replace("_", " ").title()
            bus.phase(self.project, f"deploy:{stage}", title,
                      status={"complete": "complete", "failed": "failed"}.get(status, "active"),
                      detail=str(row.get("message") or ""), kind="deploy")
            percent = row.get("percent")
            if isinstance(percent, (int, float)):
                bus.progress(self.project, stage, float(percent))
        self.seen = len(rows)

    def run(self) -> None:
        while not self._stop_event.wait(2.0):
            try:
                self.publish()
            except Exception:  # noqa: BLE001 - progress is a courtesy; the run does not depend on it
                pass

    def finish(self) -> None:
        self._stop_event.set()
        self.join(timeout=5)
        try:
            self.publish()
        except Exception:  # noqa: BLE001
            pass


def _expected(status: int, expect: Any) -> bool:
    """Whether a status is what a check said to expect: `200`, `2xx`, `200-399`, or several of them."""
    text = str(expect if expect not in (None, "") else "200-399")
    for token in re.split(r"[|,\s/]+", text):
        token = token.strip().lower()
        if re.fullmatch(r"\d{3}", token) and status == int(token):
            return True
        if re.fullmatch(r"\dxx", token) and status // 100 == int(token[0]):
            return True
        span = re.fullmatch(r"(\d{3})-(\d{3})", token)
        if span and int(span.group(1)) <= status <= int(span.group(2)):
            return True
    return False


def _public_https(url: str) -> str:
    """Why a URL is not a public HTTPS address, or an empty string when it is."""
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        return "is not an https:// address"
    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith((".local", ".internal", ".localhost")):
        return "is not a public address"
    try:
        if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback:
            return "is not a public address"
    except ValueError:
        pass
    return ""


def probe(run: dict) -> tuple[list[str], list[dict[str, str]]]:
    """Call the run's public address and every check it recorded, from this side. Returns (failures, evidence)."""
    wanted = [{"name": "the public address", "url": run.get("url") or (run.get("repository") or {}).get("url"),
               "expect": "200-399"}]
    wanted += [row for row in run.get("checks") or [] if isinstance(row, dict) and row.get("url")]
    failures: list[str] = []
    evidence: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in wanted:
        url, expect = str(row.get("url") or ""), row.get("expect")
        if not url or (url, str(expect)) in seen:
            continue
        seen.add((url, str(expect)))
        name = str(row.get("name") or url)
        problem = _public_https(url)
        if problem:
            failures.append(f"{name}: {url} {problem}")
            continue
        started = time.monotonic()
        try:
            answer = httpx.get(url, follow_redirects=True, timeout=PROBE_SECONDS,
                               headers={"User-Agent": "agentforge-recheck"})
        except httpx.HTTPError as exc:
            failures.append(f"{name}: {url} did not answer ({exc.__class__.__name__}: {exc})")
            continue
        took = int((time.monotonic() - started) * 1000)
        held = _expected(answer.status_code, expect)
        evidence.append({"kind": "studio re-check",
                         "detail": f"GET {url} -> {answer.status_code} in {took} ms; expected {expect or '200-399'}: "
                                   f"{'held' if held else 'did not hold'}"})
        if not held:
            failures.append(f"{name}: GET {url} answered {answer.status_code}, expected {expect or '200-399'}")
    return failures, evidence


def _record(project: str, change_fields: dict[str, Any]) -> dict[str, Any]:
    session = session_for(project)
    current = run_state(project)
    current.update(change_fields)
    session.write_record(*RUN, data=current)
    return current


def execute(project: str, change: dict, session: Any, model: str) -> dict[str, Any]:
    """The flow's half of `changes._execute_flow`: carry out the approved plan and check the result."""
    target, plan = str(change["target"]), change["plan"]
    resume = change.get("resume") if isinstance(change.get("resume"), dict) else None
    session.write_record(*QUESTION, data={})
    paths = stage_skills(project, target)
    titles = {step["id"]: step["title"] for step in plan.get("steps", [])}
    resumed = ""
    if resume:
        resumed = (prompts.load("deployment/resume-interrupted") if resume.get("interrupted")
                   else prompts.load("deployment/resume", question=resume.get("question", ""),
                                     answer=resume.get("answer", "")))
    request = prompts.load(
        "deployment/execute", request=change["request"], plan=plan_markdown(plan), target=target,
        target_label=label_of(target), project=project, run_id=str(change["run_id"]), skills=_skill_lines(paths),
        machine=machine_facts(project, target, session.workspace), artifacts=changes.project_map(session.workspace),
        language=str((store.get(project) or {}).get("language") or "English"), resume=resumed)

    progress = _Progress(project, titles)
    progress.seen = len(events(project)) if resume else 0

    def carry(text: str) -> dict[str, Any]:
        """One turn of the run. A turn that stopped for the customer without the question it stopped for is told
        so once, and asks it (or carries on) - rather than the deployment failing with nobody asked anything."""
        outcome = session.execute_approved(text, plan_markdown(plan), model)
        stopped = outcome["status"] == "blocked" or str(run_state(project).get("state") or "") == "NEEDS_INPUT"
        if pending_question(project) or not stopped:
            return outcome
        return session.execute_approved(text + "\n" + prompts.load("deployment/ask-now"), plan_markdown(plan), model)

    progress.start()
    try:
        result = carry(request)
        for attempt in range(REPAIR_ROUNDS + 1):
            question = pending_question(project)
            if result["status"] == "blocked" and question:
                asked = changes.check_question({"kind": "question", **question}, True)
                _record(project, {"state": "NEEDS_INPUT"})
                return {"status": "asking", "question": asked}
            run = run_state(project)
            state = str(run.get("state") or "")
            if state in ("FAILED", "ROLLED_BACK", "CANCELLED", "DESTROYED"):
                return _settle(project, session, target, failed=str(run.get("error") or result["text"]
                                                                    or f"the deployment finished as {state}"))
            if result["status"] == "blocked":
                return _settle(project, session, target, failed=result["text"] or "the deployment was blocked")
            if state != "LIVE":
                return _settle(project, session, target,
                               failed="The deployment did not record a verified terminal result and address.")
            failures, evidence = probe(run)
            _record(project, {"evidence": [*(run.get("evidence") or []), *evidence]})
            if not failures:
                return _live(project, session, target, result["text"])
            if attempt == REPAIR_ROUNDS:
                return _settle(project, session, target, failed="The live address did not hold after "
                               f"{REPAIR_ROUNDS} repair round(s): " + "; ".join(failures))
            _record(project, {"state": "REPAIRING"})
            again = request + prompts.load("deployment/verify-failed", failures="\n".join(f"- {row}" for row in failures))
            result = carry(again)
        return _settle(project, session, target, failed="The deployment could not be verified.")
    except RunCancelled:
        _record(project, {"state": "CANCELLED", "finished_at": time.time()})
        raise
    finally:
        progress.finish()


def _settle(project: str, session: Any, target: str, failed: str) -> dict[str, Any]:
    run = run_state(project)
    if run.get("state") not in ("ROLLED_BACK", "CANCELLED", "DESTROYED"):
        run["state"] = "FAILED"
    run.update(error=failed, finished_at=time.time())
    session.write_record(*RUN, data=run)
    return {"status": "failed", "text": failed}


def _live(project: str, session: Any, target: str, account: str) -> dict[str, Any]:
    run = run_state(project)
    url = str(run.get("url") or (run.get("repository") or {}).get("url") or "")
    run.update(url=url, error="", finished_at=time.time())
    session.write_record(*RUN, data=run)
    store.update(project, status="deployed")
    store.advance(project, "deploy")
    bus.agent_msg(project, f"Deployed to {label_of(target)}" + (f" — {url}" if url else ""), title="Deployment live")
    session.note(f"Deployed to {label_of(target)}" + (f" at {url}" if url else "")
                 + ". The run record is at .agentforge/deploy/run.json.")
    return {"status": "complete", "text": account or f"Deployed to {label_of(target)}."}


# --- what the panel reads -------------------------------------------------------

def _heal(project: str) -> None:
    """A run whose server went away is not still running: say so, rather than showing it as busy for ever."""
    change = changes.active(project)
    run = run_state(project)
    if run.get("state") in TERMINAL or not run.get("run_id"):
        return
    if change and change.get("flow") == "deploy" and change.get("run_id") == run.get("run_id"):
        if change["status"] in changes.BUSY and not changes.alive(change["id"]):
            changes.mark(project, change["id"], "failed", "interrupted by a restart")
        return
    run.update(state="FAILED", error="interrupted: the server stopped while it was working", finished_at=time.time())
    session_for(project).write_record(*RUN, data=run)


def answer(project: str, reply: str) -> dict[str, Any]:
    """The customer's answer to what the run asked (the same as answering in the chat)."""
    change = changes.active(project)
    if not change or change.get("flow") != "deploy" or change["status"] != "asking":
        raise ValueError("the deployment is not waiting on a question")
    return changes.answer(project, change["id"], reply)


def _retry_of(project: str) -> dict[str, Any] | None:
    """The stopped deployment that can be taken up again: the newest that carried its plan out and did not finish.

    A newer deployment that finished supersedes it, and a plan that never ran (or was refused) is not one to resume.
    """
    if changes.active(project):
        return None
    for change in changes.recent(project):
        if change.get("flow") != "deploy":
            continue
        if change["status"] == "done":
            return None
        if change.get("plan") and change.get("started") and change["status"] in ("failed", "cancelled"):
            saved = session_for(project).read_record(DEPLOY_DIR, "runs", f"{change.get('run_id')}.json", fallback=None)
            record = saved if isinstance(saved, dict) else run_state(project)
            return {"change": change["id"], "error": str((record or {}).get("error") or change.get("error") or "")}
    return None


def results(project: str) -> dict[str, Any]:
    """`GET /deploy-results/{project}` — the last run, as the panel reads it."""
    _heal(project)
    last = run_state(project)
    log = events(project)
    change = changes.active(project)
    mine = bool(change and change.get("flow") == "deploy")
    live = None
    if last and last.get("state") not in TERMINAL:
        live = {**last, "events": log, "message": (log[-1].get("message") if log else ""), "plan": plan_of(project)}
    return {
        "project": project,
        "last": last or None,
        "runs": [row for row in [last, *past_runs(project)] if row][:10],
        "events": log,
        "plan": plan_of(project),
        "live": live,
        "change": {"id": change["id"], "status": change["status"], "revision": change.get("revision", 0)} if mine else None,
        "retry": _retry_of(project),
        "targets": targets(),
        "stack": stack_of(project),
        "stack_name": stack_info(stack_of(project)).get("name", stack_of(project)),
        "allowed_targets": allowed_targets(stack_of(project)),
        "refusal": stack_info(stack_of(project)).get("reason", ""),
        "question": pending_question(project),
    }


def status() -> dict[str, Any]:
    return {"available": bool(targets()), "targets": targets()}


def cancel(project: str) -> dict[str, Any]:
    """Stop: a run being carried out is interrupted; a plan not yet approved is dropped."""
    change = changes.active(project)
    if change and change.get("flow") == "deploy":
        if change["status"] in changes.BUSY:
            session_for(project).cancel()
        else:
            changes.decide(project, change["id"], "cancel")
    else:
        session_for(project).cancel()
    current = run_state(project)
    if current and current.get("state") not in TERMINAL:
        current.update({"state": "CANCELLED", "finished_at": time.time()})
        session_for(project).write_record(*RUN, data=current)
    bus.cancelled(project, "Deployment cancelled.")
    return current
