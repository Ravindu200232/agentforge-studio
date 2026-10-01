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

from server_modules import auth_guide, changes, mongo_connect, prompts, supabase_connect

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
                '"region": "<a Supabase region code, for new>"}')
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


def check(data: Any, may_ask: bool, stack: str, found: dict) -> dict:
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
