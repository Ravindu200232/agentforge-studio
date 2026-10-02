"""A request typed into the chat is planned first, and carried out only once the plan is approved.

    request ──► plan (read-only, may ask a question) ──► the customer reads it in the chat
                    ▲                                        │ approve ──► carried out, with full
                    └──────── revise (their words) ◄─────────┘             access to the project
                                                              cancel ──► dropped

Nothing here decides what a request touches. The wording that tells the model to update the
specification, the wireframes, the prototype and the build when the request reaches them lives in
`prompts/changes/`, and the plan the model writes is what says which of them it does. This module
keeps the state, shows it, and runs the two halves.

State is one small file per request under `<project>/.agentforge/changes/`, so a plan waiting for
approval, or a question waiting for an answer, survives a restart. The plan card in the chat is
rebuilt from the durable `change` events.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import bus, config, deploy_vars, plugins, prompts, store, versions
from .session import RunCancelled, session_for

CHANGES = "changes"
# The planner may ask this many questions about one request before it has to decide and say what it
# assumed. A guard against an endless interview, not something the customer is shown.
MAX_QUESTIONS = 3
OPEN = ("planning", "asking", "proposed", "approved", "running")
BUSY = ("planning", "approved", "running")

# What a project's tree holds that is not its own work: dependencies, build output, and what a run
# writes about itself. Kept out of the map the planner reads and out of the "what changed" check.
_NOISE = {"node_modules", ".next", ".git", ".turbo", ".cache", "dist", "coverage", "test-results",
          "playwright-report", "__pycache__", ".lighthouseci", ".vercel"}
_RUN_LOG = {"events.jsonl", "context.json", "preview.log", "preview-runtime.json", CHANGES, versions.VERSIONS}
_MAP_LINES = 260
_SNAPSHOT_FILES = 20000

_lock = threading.RLock()
_threads: dict[str, threading.Thread] = {}

# A request can belong to a flow of its own: a deployment is planned, asked about, approved and revised
# exactly like a change typed in the chat, but its plan is written from other prompts and carried out
# by other code. The flow's module says how; everything else here is shared.
FLOWS = {"deploy": "deploy_agent.deploy"}


def _flow(change: dict | None) -> Any:
    """The module that plans and carries out this request's kind of work, or None for a chat change."""
    name = str((change or {}).get("flow") or "")
    if not name:
        return None
    if name not in FLOWS:
        raise ValueError(f"unknown request flow: {name}")
    import importlib

    return importlib.import_module(FLOWS[name])


def _now() -> int:
    return int(time.time() * 1000)


# --- the state of one request ------------------------------------------------

def _dir(project: str) -> Path:
    return config.record_dir(project) / CHANGES


def _path(project: str, change_id: str) -> Path:
    return _dir(project) / f"{change_id}.json"


def _load(project: str, change_id: str) -> dict | None:
    try:
        return json.loads(_path(project, change_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(change: dict) -> None:
    change["updated"] = _now()
    path = _path(change["project"], change["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(change, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    try:
        flow = _flow(change)
        if flow is not None:
            flow.sync(change)               # the flow keeps its own record in step with this one
    except Exception:  # noqa: BLE001 - a record that cannot be written must not undo the request
        pass


def _set_active(project: str, change_id: str | None) -> None:
    target = _dir(project) / "active.json"
    if change_id is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"id": change_id}), encoding="utf-8")


def active(project: str) -> dict | None:
    """The request this project is in the middle of, if any."""
    try:
        found = json.loads((_dir(project) / "active.json").read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError):
        return None
    change = _load(project, str(found)) if found else None
    return change if change and change.get("status") in OPEN else None


def recent(project: str, limit: int = 30) -> list[dict]:
    """The project's requests, newest first."""
    folder = _dir(project)
    if not folder.is_dir():
        return []
    rows = []
    for path in sorted(folder.glob("chg-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        found = _load(project, path.stem)
        if found:
            rows.append(found)
    return rows


def _alive(change_id: str) -> bool:
    thread = _threads.get(change_id)
    return bool(thread and thread.is_alive())


def _language(project: str) -> str:
    return str((store.get(project) or {}).get("language") or "English")


def applies(project: str) -> bool:
    """Whether a typed change goes through propose->approve: a project with a
    specification is planned against it, unless the customer turned plan mode
    off for this project (a real per-project choice — a project that has
    never set it behaves exactly as it always has, plan mode on)."""
    from srs_agent import document as srs_document

    record = store.get(project)
    if record is not None and not record.get("plan_mode", True):
        return False
    return srs_document.has_document(project)


# --- what the model is shown -------------------------------------------------

def _size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "?"
    return f"{size} B" if size < 1024 else f"{size / 1024:.0f} KB"


def project_map(workspace: Path) -> str:
    """The project's folders and files, as one listing, so the planner knows what exists.

    The record folder is shown in depth (it is where every stage keeps its work); the application
    beside it two levels down. Nothing is interpreted: a folder that is not there is not listed.
    """
    record = workspace / config.RECORD_DIR
    lines: list[str] = []

    def walk(base: Path, depth: int, indent: str, skip: set[str]) -> None:
        try:
            entries = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for path in entries:
            if len(lines) >= _MAP_LINES:
                return
            if path.name in _NOISE or path.name in skip:
                continue
            if path.is_dir():
                lines.append(f"{indent}{path.name}/")
                if depth > 1:
                    walk(path, depth - 1, indent + "  ", set())
            else:
                lines.append(f"{indent}{path.name} ({_size(path)})")

    lines.append(f"{config.RECORD_DIR}/")
    walk(record, 4, "  ", _RUN_LOG)
    lines.append("application files:")
    walk(workspace, 2, "  ", {config.RECORD_DIR})
    if len(lines) >= _MAP_LINES:
        lines.append("  … (the listing is cut off here; use list_files to see more)")
    return "\n".join(lines)


def _snapshot(workspace: Path) -> dict[str, tuple[int, int]]:
    """Every project file's modification time and size, for telling what a run changed."""
    found: dict[str, tuple[int, int]] = {}
    record = config.RECORD_DIR

    def walk(base: Path, relative: str) -> None:
        try:
            with os.scandir(base) as entries:
                for entry in entries:
                    if len(found) >= _SNAPSHOT_FILES or entry.name in _NOISE:
                        continue
                    name = f"{relative}{entry.name}"
                    if relative == f"{record}/" and entry.name in _RUN_LOG:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        walk(Path(entry.path), name + "/")
                    else:
                        info = entry.stat(follow_symlinks=False)
                        found[name] = (info.st_mtime_ns, info.st_size)
        except OSError:
            return

    walk(workspace, "")
    return found


def _turns(change: dict) -> str:
    """What was said about this request after the request itself."""
    rows = change.get("history", [])[1:]
    if not rows:
        return ""
    label = {"user": "customer", "assistant": "you"}
    body = "\n".join(f"- {label.get(row.get('role'), row.get('role'))}: {row.get('text', '')}" for row in rows)
    return prompts.load("changes/history", turns=body)


def _excluding(plan: dict, excluded: set[str]) -> dict:
    """The plan with excluded stages' steps dropped and their impact rows marked not affected.

    Excluded work is simply never described to the executing agent — there is
    no instruction, and so no reason, for it to touch that stage's files.
    """
    if not excluded:
        return plan
    return {**plan,
            "steps": [step for step in plan.get("steps", []) if step.get("stage") not in excluded],
            "impact": [{**row, "affected": bool(row.get("affected")) and row.get("stage") not in excluded}
                      for row in plan.get("impact", [])]}


def plan_markdown(plan: dict) -> str:
    """The plan as the text the executing agent is handed."""
    lines = [f"# {plan.get('title', '')}", "", str(plan.get("summary", "")), "", "## What it touches"]
    for row in plan.get("impact", []):
        lines.append(f"- {row.get('stage')}: {'affected' if row.get('affected') else 'not affected'}"
                     f" — {row.get('why', '')}")
    lines += ["", "## Steps"]
    for number, step in enumerate(plan.get("steps", []), 1):
        lines.append(f"{number}. [{step.get('stage', '')}] {step.get('title', '')}")
        if step.get("detail"):
            lines.append(f"   {step['detail']}")
        for file in step.get("files", []):
            lines.append(f"   - {file}")
    for heading, key in (("Assumptions", "assumptions"), ("Risks", "risks"), ("How it will be checked", "verification")):
        if plan.get(key):
            lines += ["", f"## {heading}"] + [f"- {item}" for item in plan[key]]
    return "\n".join(lines)


# --- what the model returns ---------------------------------------------------

def _texts(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _check(data: Any, may_ask: bool) -> dict:
    """The reply as a clean answer, question or plan. What is wrong is the repair prompt."""
    if not isinstance(data, dict):
        raise ValueError("return one JSON object")
    kind = str(data.get("kind") or "").strip()
    if kind == "answer":
        answer = str(data.get("answer") or "").strip()
        if not answer:
            raise ValueError('an "answer" needs the answer text')
        return {"kind": "answer", "answer": answer}
    if kind == "question":
        if not may_ask:
            raise ValueError("no more questions may be asked: decide it and return a plan that states the assumption")
        question = str(data.get("question") or "").strip()
        if not question:
            raise ValueError('a "question" needs the question text')
        options = []
        for index, option in enumerate(data.get("options") or [], 1):
            label = str(option.get("label") if isinstance(option, dict) else option or "").strip()
            if label:
                options.append({"id": str(index), "label": label,
                                "hint": str(option.get("hint") or "").strip() if isinstance(option, dict) else ""})
        # The card already says "No answer: it will"; a model that repeats those words is not shown saying them twice.
        assumption = re.sub(r"^\s*no answer\s*[:,\-]?\s*(?:it will\s*)?", "", str(data.get("assumption") or ""),
                            flags=re.IGNORECASE).strip()
        asked = {"kind": "question", "question": question, "why": str(data.get("why") or "").strip(),
                 "options": options[:4], "assumption": assumption}
        # A question can ask for a value only the customer has: it names the variable it is saved as, and the
        # studio asks for it in a private box and keeps it out of the conversation (see `deploy_vars.accept`).
        variable = str(data.get("variable") or "").strip()
        if variable:
            deploy_vars.valid_name(variable)
            check = str(data.get("check") or "").strip()
            if check and check not in deploy_vars.CHECKS:
                allowed = ", ".join(deploy_vars.CHECKS) or "nothing right now"
                raise ValueError(f'"check" must be left out ({allowed} is offered)')
            asked.update(variable=variable, secret=bool(data.get("secret", True)), check=check)
        return asked
    if kind != "plan":
        raise ValueError('"kind" must be "answer", "question" or "plan"')
    title, summary = str(data.get("title") or "").strip(), str(data.get("summary") or "").strip()
    if not title or not summary:
        raise ValueError('a "plan" needs a "title" and a "summary"')
    impact = [{"stage": str(row.get("stage") or "").strip(), "affected": bool(row.get("affected")),
               "why": str(row.get("why") or "").strip()}
              for row in data.get("impact") or [] if isinstance(row, dict) and str(row.get("stage") or "").strip()]
    if not impact:
        raise ValueError('a "plan" needs "impact": one row per stage, affected or not')
    steps = [{"stage": str(row.get("stage") or "").strip(), "title": str(row.get("title") or "").strip(),
              "detail": str(row.get("detail") or "").strip(), "files": _texts(row.get("files"))}
             for row in data.get("steps") or [] if isinstance(row, dict) and str(row.get("title") or "").strip()]
    if not steps:
        raise ValueError('a "plan" needs "steps": what is done, in order')
    return {"kind": "plan", "title": title, "summary": summary, "impact": impact, "steps": steps,
            "assumptions": _texts(data.get("assumptions")), "risks": _texts(data.get("risks")),
            "verification": _texts(data.get("verification"))}


def texts(value: Any) -> list[str]:
    """A list of non-empty strings from whatever the model returned (for flows that write their own plans)."""
    return _texts(value)


def check_question(data: dict, may_ask: bool) -> dict:
    """A planner's question, cleaned; shared by every flow so a question is asked the same way everywhere."""
    return _check({**data, "kind": "question"}, may_ask)


# --- the way in ---------------------------------------------------------------

def submit(project: str, request: str, model: str = "", echo: bool = True, flow: dict | None = None,
           answering: bool = False) -> dict:
    """Something typed in the chat. It answers a question, revises the plan on screen, or starts a request.

    `flow` starts a request of another kind (a deployment): its keys are kept on the request, and a
    request already open is not answered or revised by it, so it is refused instead. `answering` says the
    text is the answer to the question on screen, already taken by whoever asked (see `answer`).
    """
    request = str(request or "").strip()
    if not request:
        raise ValueError("say what to change")
    waiting = active(project)
    if (not flow and not answering and waiting and waiting["status"] == "asking"
            and (waiting.get("question") or {}).get("variable")):
        # A value only the customer has is given in the question's own private box, never as a line of chat.
        held = prompts.load("deployment/use-the-box").strip()
        bus.agent_msg(project, held, title="Not sent")
        return {"ok": False, "detail": held}
    if not flow and waiting and waiting["status"] == "asking" and isinstance(waiting.get("resume"), dict):
        # The run itself asked this: the answer takes it up again where it stopped; nothing is planned again.
        if echo:
            bus.user_msg(project, request)
        return answer(project, waiting["id"], request, model)
    with _lock:
        change = active(project)
        if flow and change and change["status"] in OPEN:
            raise ValueError("another plan is still open in the chat: approve, revise or cancel it first")
        if change and change["status"] in BUSY and _alive(change["id"]):
            raise ValueError("the previous request is still being worked on: wait for it, or stop it first")
        if change and change["status"] in BUSY:
            # The server that was working on it is gone; whatever it had not finished is over.
            change.update(status="failed", error="interrupted by a restart")
            _save(change)
            _set_active(project, None)
            change = None
        if change and change["status"] in ("asking", "proposed"):
            role = "answer" if change["status"] == "asking" else "feedback"
            change["history"].append({"role": "user", "kind": role, "text": request})
        else:
            change = {"id": f"chg-{uuid.uuid4().hex[:10]}", "project": project, "request": request,
                      "status": "planning", "revision": 0, "asked": 0, "plan": None, "created": _now(),
                      "history": [{"role": "user", "kind": "request", "text": request}], **(flow or {})}
        change["status"] = "planning"
        _save(change)
        _set_active(project, change["id"])
    if echo:
        bus.user_msg(project, request)
    _spawn(project, change["id"], _propose, project, change["id"], model)
    return {"ok": True, "project": project, "change": change["id"]}


def decide(project: str, change_id: str, decision: str, feedback: str = "", model: str = "",
          excluded_stages: list[str] | None = None) -> dict:
    """The buttons on the plan card."""
    change = _load(project, change_id)
    if not change:
        raise KeyError(change_id)
    if decision == "approve":
        with _lock:
            if change["status"] != "proposed":
                return {"ok": False, "detail": "that plan is no longer waiting for approval"}
            excluded = [str(stage) for stage in (excluded_stages or []) if str(stage).strip()]
            change["status"] = "approved"
            change["excluded_stages"] = excluded
            if excluded:
                change["history"].append({"role": "user", "kind": "excluded_stages",
                                          "text": "Excluded from this run: " + ", ".join(excluded)})
            _save(change)
        bus.change(project, change)
        _spawn(project, change_id, _execute, project, change_id, model)
        return {"ok": True}
    if decision == "revise":
        if change["status"] != "proposed":
            return {"ok": False, "detail": "that plan is no longer waiting for approval"}
        return submit(project, feedback, model, echo=True)
    if decision == "retry":
        # A deployment that was interrupted or stopped goes on from where it stopped, on the plan the customer approved.
        with _lock:
            if _flow(change) is None or not change.get("plan") or change["status"] not in ("failed", "cancelled"):
                return {"ok": False, "detail": "there is nothing to resume"}
            if active(project):
                return {"ok": False, "detail": "another plan is still open in the chat: approve, revise or cancel it first"}
            change.update(status="approved", error="", resume={"interrupted": True})
            _save(change)
            _set_active(project, change_id)
        bus.change(project, change)
        _spawn(project, change_id, _execute, project, change_id, model)
        return {"ok": True}
    if decision == "cancel":
        with _lock:
            if change["status"] not in OPEN:
                return {"ok": True}
            change["status"] = "cancelled"
            _save(change)
            _set_active(project, None)
        bus.change(project, change)
        return {"ok": True}
    raise ValueError("decision must be approve, revise, retry or cancel")


def answer(project: str, change_id: str, reply: str, model: str = "") -> dict:
    """The customer's reply to a question the planner asked (or their choice to let it decide)."""
    change = _load(project, change_id)
    if not change or change["status"] != "asking":
        return {"ok": False, "detail": "that question is no longer waiting"}
    text = str(reply or "").strip() or prompts.load("changes/unanswered").strip()
    if isinstance(change.get("resume"), dict):
        with _lock:
            change["resume"]["answer"] = text
            change["history"].append({"role": "user", "kind": "answer", "text": text})
            change["status"] = "approved"
            _save(change)
        bus.change(project, change)
        _spawn(project, change_id, _execute, project, change_id, model)
        return {"ok": True}
    return submit(project, text, model, echo=False, answering=True)


def restore_questions() -> list[dict]:
    """Restore real questions and close stale workers after a server restart."""
    found: list[dict] = []
    with _lock:                       # several browsers (or one, twice) ask at once: the question comes back once
        waiting = {d.get("change_id") for d in bus.pending_decisions() if d.get("change_id")}
        for row in store.listing():
            project = str(row.get("name") or row.get("id") or "")
            change = active(project) if project else None
            # Threads do not survive a process restart. Leaving their durable
            # state as planning/approved/running makes the chat show an endless
            # active plan even though no worker exists to finish it.
            if change and change["status"] in BUSY and not _alive(change["id"]):
                change.update(status="failed", error="interrupted by a restart")
                _save(change)
                _set_active(project, None)
                bus.change(project, change)
                continue
            if change and change["status"] == "asking" and change["id"] not in waiting:
                found.append(_ask(project, change))
    return found


# --- the two halves -----------------------------------------------------------

def _spawn(project: str, change_id: str, fn: Any, *args: Any) -> None:
    def run() -> None:
        try:
            fn(*args)
        except RunCancelled:
            _mark(project, change_id, "cancelled")
            bus.cancelled(project, "Stopped.")
        except Exception as exc:  # noqa: BLE001 - the customer must see why, not a silence
            _mark(project, change_id, "failed", str(exc) or exc.__class__.__name__)
            bus.failed(project, str(exc) or exc.__class__.__name__)
        finally:
            _threads.pop(change_id, None)

    thread = threading.Thread(target=run, name=f"change:{change_id}", daemon=True)
    with _lock:
        _threads[change_id] = thread
    thread.start()


def _mark(project: str, change_id: str, status: str, error: str = "") -> None:
    change = _load(project, change_id)
    if not change or change["status"] not in OPEN:
        return
    change.update(status=status, error=error)
    _save(change)
    _set_active(project, None)
    if change.get("plan"):
        bus.change(project, change)


def _ask(project: str, change: dict) -> dict:
    question = change["question"]
    decision = bus.ask(project, "question", question["question"], options=question["options"],
                       agent=bus.DEVELOPER, why=question["why"], assumption=question["assumption"],
                       change_id=change["id"], variable=question.get("variable", ""),
                       secret=question.get("secret", False), check=question.get("check", ""))
    return next((d for d in bus.pending_decisions() if d["id"] == decision), {})


def _propose(project: str, change_id: str, model: str) -> None:
    change = _load(project, change_id)
    session = session_for(project)
    flow = _flow(change)
    session.begin(getattr(flow, "STAGE_PLAN", "plan"))
    try:
        left = int(getattr(flow, "MAX_QUESTIONS", MAX_QUESTIONS)) - int(change.get("asked", 0))
        previous = ""
        if change.get("plan") and any(row.get("kind") == "feedback" for row in change["history"]):
            previous = prompts.load("changes/previous-plan",
                                    plan=json.dumps(change["plan"], ensure_ascii=False, indent=2))
        questions_left = (prompts.load("changes/questions-left", count=left).strip() if left > 0
                          else prompts.load("changes/no-questions").strip())
        if flow is not None:
            prompt = flow.plan_prompt(project, change, session, history=_turns(change), previous_plan=previous,
                                      questions_left=questions_left, language=_language(project))
            validate = flow.validator(project, change)
        else:
            prompt = prompts.load(
                "changes/plan", request=change["request"], history=_turns(change),
                artifacts=project_map(session.workspace), language=_language(project),
                previous_plan=previous, questions_left=questions_left)
            validate = _check
        agent = session.agent(model)
        with session.lock:
            agent.set_mode("plan")
        try:
            reply = session.ask_json(prompt, validator=lambda data: validate(data, left > 0), model=model)
        finally:
            with session.lock:
                agent.set_mode("act")
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc) or exc.__class__.__name__)
        _mark(project, change_id, "failed", str(exc))
        return

    change = _load(project, change_id) or change
    if reply["kind"] == "answer":
        change.update(status="done", summary=reply["answer"])
        _save(change)
        _set_active(project, None)
        bus.agent_msg(project, reply["answer"], agent=bus.DEVELOPER)
        session.finish("Answered.")
    elif reply["kind"] == "question":
        change.update(status="asking", question=reply, asked=int(change.get("asked", 0)) + 1)
        change["history"].append({"role": "assistant", "kind": "question", "text": reply["question"]})
        _save(change)
        # `done` clears a question on screen, so the run ends first and the question is asked after it.
        session.finish("Waiting for your answer.")
        _ask(project, change)
    else:
        plan = {key: value for key, value in reply.items() if key != "kind"}
        change.update(status="proposed", plan=plan, revision=int(change.get("revision", 0)) + 1)
        change["history"].append({"role": "assistant", "kind": "plan", "text": plan["title"]})
        _save(change)
        bus.change(project, change)
        session.finish("Plan ready: review it in the chat.")


def _execute_flow(project: str, change: dict, flow: Any, model: str) -> None:
    """Carry out an approved request of another kind; the flow does the work and says how it ended.

    It ends as `complete`, as `failed`, or as `asking`: it stopped on a question only the customer can
    answer, and it is taken up again from where it stopped once they have.
    """
    change_id = change["id"]
    session = session_for(project)
    session.begin(getattr(flow, "STAGE_RUN", "change"), run_id=str(change.get("run_id") or ""))
    change.update(status="running", started=True)
    _save(change)
    bus.change(project, change)
    try:
        outcome = flow.execute(project, change, session, model)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc) or exc.__class__.__name__)
        _mark(project, change_id, "failed", str(exc))
        return
    change = _load(project, change_id) or change
    if outcome["status"] == "asking":
        question = outcome["question"]
        change.update(status="asking", question=question, asked=int(change.get("asked", 0)) + 1,
                      resume={"question": question["question"]})
        change["history"].append({"role": "assistant", "kind": "question", "text": question["question"]})
        _save(change)
        session.finish("Waiting for your answer.")
        _ask(project, change)
        return
    done = outcome["status"] == "complete"
    change.pop("resume", None)
    change.update(status="done" if done else "failed", summary=outcome["text"],
                  error="" if done else (outcome["text"] or "the request was blocked"))
    _save(change)
    _set_active(project, None)
    bus.change(project, change)
    if done:
        session.finish(outcome["text"] or "Done.")
    else:
        session.fail(change["error"])


def _execute(project: str, change_id: str, model: str) -> None:
    change = _load(project, change_id)
    flow = _flow(change)
    if flow is not None:
        return _execute_flow(project, change, flow, model)
    session = session_for(project)
    session.begin("change")
    excluded = set(change.get("excluded_stages") or [])
    plan_data = _excluding(change["plan"], excluded)
    if excluded and not plan_data.get("steps"):
        change.update(status="done", summary="Nothing left to build — every affected stage was excluded.")
        _save(change)
        _set_active(project, None)
        bus.change(project, change)
        session.finish(change["summary"])
        return
    change.update(status="running")
    _save(change)
    bus.change(project, change)
    try:
        number = versions.next_number(project)
        versions.preserve_results(project, number, session.workspace)          # what the tests said before this update
        before, counts_before = _snapshot(session.workspace), versions.test_counts(session.workspace)
        plan = plan_markdown(plan_data)
        records = "\n".join(f"- {name}" for name in versions.result_records(session.workspace)) or "(none yet)"
        request = prompts.load("changes/execute", request=change["request"], plan=plan,
                               artifacts=project_map(session.workspace), language=_language(project),
                               results=records, guides=_guides(project))
        result = session.execute_approved(request, plan, model)
        after = _snapshot(session.workspace)
        _announce(project, before, after)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc) or exc.__class__.__name__)
        _mark(project, change_id, "failed", str(exc))
        return
    done = result["status"] == "complete"
    change = _load(project, change_id) or change
    change.update(status="done" if done else "failed", summary=result["text"],
                  error="" if done else (result["text"] or "the change was blocked"))
    if done:
        try:
            change["version"] = versions.record(project, number, change, before, after, counts_before,
                                                versions.test_counts(session.workspace), result["text"])["number"]
        except OSError as exc:  # a version file that cannot be written must not undo an update that worked
            bus.log(project, "WARN", f"The version file could not be written: {exc}")
    _save(change)
    _set_active(project, None)
    bus.change(project, change)
    if done:
        plugins.consume_handoff(project)
        session.finish(result["text"] or "Change applied.")
    else:
        session.fail(change["error"])


def _guides(project: str = "") -> str:
    """The build and test guides, for a change that reaches application code."""
    try:
        from builder_agent import scaffold

        return scaffold.common_context(str((store.get(project) or {}).get("stack") or "") if project else "")
    except Exception:  # noqa: BLE001 - guidance is a help, not a requirement
        return ""


def _announce(project: str, before: dict, after: dict) -> None:
    """Tell the studio which stages' files a run changed, from the folders they are in."""
    changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
    if not changed:
        return
    record = f"{config.RECORD_DIR}/"
    if any(path.startswith(f"{record}prototype/") for path in changed):
        bus.prototype_changed(project)
    if any(path.startswith(f"{record}srs/") for path in changed):
        bus.sync_state(project, "clean", source="change")
    if any(not path.startswith(record) for path in changed):
        from builder_agent import build as builder

        if builder.built(project):
            builder.show_preview(project)


# What the flows' modules use of the state above.
alive = _alive
mark = _mark
