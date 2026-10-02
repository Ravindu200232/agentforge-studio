"""Before a build is planned: settle with the customer everything it will need from them.

The questions are the model's own, written for this project from its specification and from what the connected
accounts already have — nothing here knows what to ask. This module only gathers those facts, checks the model's
reply, and carries out the one part that must be exact: where the data lives (keep or create the project's
Supabase project, use or create the MongoDB cluster), from the structured `database` the model settles on.
"""
from __future__ import annotations

import json
import re
from typing import Any

from server_modules import auth_guide, changes, mongo_connect, prompts, store, supabase_connect

MAX_QUESTIONS = 20
_REGION = re.compile(r"^[A-Za-z0-9_-]{2,40}$")


def uses_mongodb(stack: str) -> bool:
    return "mongo" in stack or stack.startswith("mern")


def facts(project: str, stack: str, earlier: dict | None = None) -> dict[str, Any]:
    """What this project and the connected accounts already have. Never a key, a password or a connection string.

    The Supabase account is read through its command line tool, which takes seconds, so one setup reads it once
    (`earlier`); everything else is read again each turn, because an answer can change it.
    """
    found: dict[str, Any] = {}
    this = supabase_connect.status(project)
    account = ((earlier or {}).get("supabase") or {}).get("account")
    try:
        account = account or supabase_connect.account_facts()
    except Exception as exc:  # noqa: BLE001 - a fact that cannot be read is said, not fatal
        account = {"connected": False, "unreadable": str(exc)[:200]}
    # Which of the account's projects another AgentForge project of this customer's runs on: what pausing or
    # deleting one of them would take away.
    linked = supabase_connect.linked_projects()
    titles = {row.get("name"): row.get("title") for row in store.listing()}
    for row in (account or {}).get("projects") or []:
        if isinstance(row, dict) and linked.get(row.get("ref")) not in (None, project):
            row["used_by_agentforge_project"] = titles.get(linked[row["ref"]]) or linked[row["ref"]]
    found["supabase"] = {"this_project": {k: this.get(k, "") for k in ("ref", "name", "url")} if this.get("connected")
                         else None, "account": account}
    if uses_mongodb(stack):
        try:
            found["mongodb"] = mongo_connect.account_facts()
        except Exception as exc:  # noqa: BLE001
            found["mongodb"] = {"unreadable": str(exc)[:200]}
    return found


def database_shape(stack: str) -> str:
    supabase = ('{"use": "this" (keep this project\'s Supabase project) or "new", '
                '"organization": "<an organization id from the facts, for new>", '
                '"region": "<a Supabase region code, for new>", '
                '"make_room": {"action": "pause" or "delete", "project": "<the ref of the account\'s project to pause or '
                'delete first, so the new one fits>"} — only for "new", and only when the customer chose that for that very '
                'project; otherwise leave it out}')
    if not uses_mongodb(stack):
        return '{"supabase": ' + supabase + "}"
    return ('{"supabase": ' + supabase + ', "mongodb": {"use": "atlas" (the connected Atlas account\'s cluster, '
            'or a new free cluster there), "saved" (a connection string the customer gave), or "local" '
            '(this computer\'s MongoDB, for now), "region": "<an Atlas region name, when a new cluster is created>"}}')


def prompt(project: str, session: Any, stack: str, found: dict, state: dict, left: int) -> str:
    reading = ["the stack's build guide at `.agentforge/build/guides/`"]
    if (session.workspace / ".agentforge" / "PLUGIN.md").is_file():
        reading.append("`.agentforge/PLUGIN.md` (the integrations already chosen)")
    if (session.workspace / auth_guide.PATH).is_file():
        reading.append(f"`{auth_guide.PATH}`")
    answers = state.get("answers") or []
    earlier = state.get("previous") or []
    parts = []
    if earlier:
        parts.append("## Settled for an earlier build of this project\n\nStill true unless the specification "
                     "changed it; do not ask these again:\n\n"
                     + "\n".join(f"- {line}" for line in earlier))
    if answers:
        parts.append("## Answered so far\n\n" + "\n".join(f"- Q: {row['question']}\n  A: {row['answer']}"
                                                         for row in answers))
    if str(state.get("problem") or "").strip():
        parts.append("## What went wrong just now\n\n" + str(state["problem"]).strip() + "\n\nAsk the customer how "
                     "to go on, with the ways forward you see and what each one costs or changes — or, when one way is "
                     "clearly right and costs them nothing, settle it yourself.")
    return prompts.load(
        "builder/setup", stack=stack, facts=json.dumps(found, ensure_ascii=False, indent=2),
        reading="; ".join(reading) + ".",
        direction=(f"What the customer asked for on this build: {state['direction'].strip()}"
                   if str(state.get("direction") or "").strip() else ""),
        questions_left=(prompts.load("changes/questions-left", count=left).strip() if left > 0
                        else prompts.load("changes/no-questions").strip()),
        answers="\n\n".join(parts), database_shape=database_shape(stack))


def _make_room(supabase: dict, account: dict, this: dict | None, answers: list[dict]) -> dict | None:
    """The project the customer agreed to pause or delete so a new one fits — checked against what is real: one of
    the account's projects, not this project's own, and one the customer was asked about by name."""
    room = supabase.get("make_room")
    if not room:
        return None
    if supabase.get("use") != "new":
        raise ValueError('"make_room" only goes with "use": "new"')
    if not isinstance(room, dict) or room.get("action") not in ("pause", "delete"):
        raise ValueError('"make_room.action" must be "pause" or "delete"')
    projects = {str(p.get("ref")): p for p in account.get("projects") or [] if isinstance(p, dict) and p.get("ref")}
    target = projects.get(str(room.get("project") or ""))
    if not target:
        raise ValueError('"make_room.project" must be the ref of one of the account\'s projects in the facts')
    if this and str(this.get("ref") or "") == str(target["ref"]):
        raise ValueError("this project's own Supabase project is never paused or deleted to make room for a new one")
    names = {str(target.get("name") or "").strip().lower(), str(target["ref"]).lower()} - {""}
    if not any(name in str(row.get("question") or "").lower() for row in answers for name in names):
        raise ValueError(f'the customer has not been asked about {target.get("name") or target["ref"]}: ask them first, '
                         f'naming it, whether to {room["action"]} it — a project of theirs is paused or deleted only '
                         "when they chose that for it")
    return {"action": room["action"], "project": str(target["ref"]), "name": str(target.get("name") or "")}


def check(data: Any, may_ask: bool, stack: str, found: dict, answers: list[dict] | None = None) -> dict:
    """The model's reply as a clean question or a settled, carry-out-able `database`. What is wrong is the repair."""
    if not isinstance(data, dict):
        raise ValueError("return one JSON object")
    if data.get("kind") == "question":
        return changes.check_question(data, may_ask)
    if data.get("kind") != "ready":
        raise ValueError('"kind" must be "question" or "ready"')
    database = data.get("database")
    if not isinstance(database, dict):
        raise ValueError('a "ready" needs "database"')
    supabase = database.get("supabase")
    if not isinstance(supabase, dict) or supabase.get("use") not in ("this", "new"):
        raise ValueError('"database.supabase.use" must be "this" or "new"')
    if supabase["use"] == "this" and not (found.get("supabase") or {}).get("this_project"):
        raise ValueError('this project has no Supabase project yet, so "database.supabase.use" must be "new"')
    if supabase["use"] == "new":
        account = (found.get("supabase") or {}).get("account") or {}
        organizations = {str(o.get("id")) for o in account.get("organizations") or [] if isinstance(o, dict)}
        if organizations and str(supabase.get("organization") or "") not in organizations:
            raise ValueError('"database.supabase.organization" must be one of the organization ids in the facts')
        if supabase.get("region") and not _REGION.match(str(supabase["region"])):
            raise ValueError('"database.supabase.region" must be a Supabase region code such as the facts show')
    settled = {"supabase": {key: str(supabase.get(key) or "") for key in ("use", "organization", "region")}}
    room = _make_room(supabase, (found.get("supabase") or {}).get("account") or {},
                      (found.get("supabase") or {}).get("this_project"), list(answers or []))
    if room:
        settled["supabase"]["make_room"] = room
    if uses_mongodb(stack):
        mongodb = database.get("mongodb")
        if not isinstance(mongodb, dict) or mongodb.get("use") not in ("atlas", "saved", "local"):
            raise ValueError('"database.mongodb.use" must be "atlas", "saved" or "local"')
        mongo_facts = found.get("mongodb") or {}
        if mongodb["use"] == "atlas" and not mongo_facts.get("atlas_connected"):
            raise ValueError("no Atlas account is connected, so the cluster cannot be made there: ask for a connection "
                             'string ("saved") or use this computer\'s MongoDB ("local")')
        if mongodb["use"] == "saved" and not mongo_facts.get("connection_string_saved"):
            raise ValueError('no connection string is saved yet: ask for it first (variable MONGODB_URI, secret, '
                             'check "mongodb"), or choose another way')
        if mongodb.get("region") and not _REGION.match(str(mongodb["region"])):
            raise ValueError('"database.mongodb.region" must be an Atlas region name')
        settled["mongodb"] = {key: str(mongodb.get(key) or "") for key in ("use", "region")}
    decisions = [str(line).strip() for line in data.get("decisions") or [] if str(line).strip()]
    return {"kind": "ready", "database": settled, "decisions": decisions}


def apply(project: str, name: str, database: dict, say: Any) -> None:
    """Carry out where the data lives, exactly as settled. A no-op for what already exists."""
    supabase = database.get("supabase") or {}
    room = supabase.get("make_room") or {}
    if room and supabase.get("use") == "new":
        supabase_connect.make_room(room["project"], room["action"], log=say)
    supabase_connect.ensure_project(project, name=name, log=say, region=supabase.get("region", ""),
                                    org_id=supabase.get("organization", ""),
                                    fresh=supabase.get("use") == "new" and bool(supabase_connect.record(project)))
    mongodb = database.get("mongodb") or {}
    if mongodb.get("use") == "atlas":
        mongo_connect.ensure_cluster(log=say, region=mongodb.get("region", ""))


def settled_block(state: dict) -> str:
    """What the build request is told was settled before it, so it never asks any of it again."""
    rows = [f"- Q: {row['question']}\n  A: {row['answer']}" for row in state.get("answers") or []]
    rows += [f"- {line}" for line in state.get("decisions") or []]
    if not rows:
        return ""
    return ("\n\n## Settled with the customer before this build\n\nThese were asked and answered before the plan. "
            "Build on them and do not ask any of them again:\n\n" + "\n".join(rows))
