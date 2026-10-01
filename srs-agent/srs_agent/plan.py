"""The approval plan.

What the customer actually reads and signs off on. It is a ceiling, not a
summary: the specification's tables come from its records, its roles from its
users, its pages from its screens, and nothing downstream may exceed it.
"""
from __future__ import annotations

import json
import time
from typing import Any

from server_modules import bus, llm, prompts, store
from server_modules.session import ProjectSession, session_for
from server_modules.validation import plan_rules

from . import interview

RECORD = ("plan.json",)

# Sections a revision may return on their own; anything returned replaces that
# section outright, and anything omitted is kept.
SECTIONS = ("app_name", "product_intent", "users", "screens", "records",
            "workflows", "features", "account_policy", "look_and_feel",
            "assumptions", "open_questions")


def _blank() -> dict[str, Any]:
    return {"plan": None, "version": 0, "versions": [], "approved": False}


def state(session: ProjectSession) -> dict[str, Any]:
    saved = session.read_record(*RECORD, fallback=None)
    return saved if isinstance(saved, dict) else _blank()


def save(session: ProjectSession, data: dict[str, Any]) -> None:
    session.write_record(*RECORD, data=data)


def _merge(previous: dict[str, Any] | None, revised: dict[str, Any]) -> dict[str, Any]:
    """A revision replaces the sections it returns and keeps the ones it does not.

    `open_questions` is the exception: a revision that returns none has settled
    them all, which is what lets the customer approve.
    """
    if not previous:
        return revised
    merged = dict(previous)
    for key in SECTIONS:
        if key in revised:
            merged[key] = revised[key]
    merged["open_questions"] = revised.get("open_questions", [])
    return merged


def _can_approve(plan: dict[str, Any]) -> tuple[bool, str]:
    blocking = [q for q in (plan.get("open_questions") or [])
                if isinstance(q, dict) and q.get("required")
                and str(q.get("question") or "").strip()]
    if blocking:
        first = str(blocking[0].get("question", "")).strip()
        return False, (f"{len(blocking)} question{'s' if len(blocking) > 1 else ''} "
                       f"still needs an answer, starting with: {first}")
    return True, ""


def _markdown(plan: dict[str, Any]) -> str:
    """The plan as a document, for the specification to carry and the PDF to show."""
    out = [f"# {plan.get('app_name') or 'The plan'}", "",
           str(plan.get("product_intent") or ""), ""]

    def block(title: str, rows: Any, render) -> None:
        items = [render(r) for r in (rows or []) if r]
        if items:
            out.extend([f"## {title}", ""] + items + [""])

    block("Who uses it", plan.get("users"),
          lambda u: f"- **{u.get('role', '')}** — " + "; ".join(u.get("can_do") or []))
    block("Screens", plan.get("screens"),
          lambda s: f"- **{s.get('name', '')}** (`{s.get('route', '')}`) — "
                    f"{s.get('purpose', '')}"
                    + (f" _[{', '.join(s.get('who') or [])}]_" if s.get("who") else ""))
    block("What it remembers", plan.get("records"),
          lambda r: f"- **{r.get('name', '')}** — " + ", ".join(r.get("keeps") or []))
    block("Journeys", plan.get("workflows"),
          lambda w: f"- **{w.get('name', '')}** ({w.get('who', '')}): "
                    + " → ".join(w.get("steps") or []))
    block("What it does", plan.get("features"), lambda f: f"- {f}")
    block("Assumptions", plan.get("assumptions"), lambda a: f"- {a}")
    block("Still open", plan.get("open_questions"),
          lambda q: f"- {q.get('question', '')}"
                    + (f" _({', '.join(q.get('options') or [])})_" if q.get("options") else ""))

    if plan.get("look_and_feel"):
        out.extend(["## Look and feel", "", str(plan["look_and_feel"]), ""])
    return "\n".join(out)


def current(project: str) -> dict[str, Any]:
    """The plan as it stands, without asking the model for anything."""
    session = session_for(project)
    data = state(session)
    plan = data.get("plan")
    if not plan:
        return {"plan": None, "version": 0, "versions": [], "approved": False,
                "can_approve": False, "reason": "", "markdown": ""}
    ok, reason = _can_approve(plan)
    return {"plan": plan, "version": data.get("version", 1),
            "versions": data.get("versions", []), "approved": bool(data.get("approved")),
            "can_approve": ok, "reason": reason, "markdown": _markdown(plan)}


def draft(project: str, revision: str = "", answers: dict[str, str] | None = None) -> dict[str, Any]:
    """Write the plan, or revise the one that exists."""
    record = store.require(project)
    session = session_for(project)
    data = state(session)
    session.role = bus.DEVELOPER

    previous = data.get("plan")
    language = record.get("language", "English")
    said = (revision or "").strip()

    answered = "\n".join(f"- {q}: {a}" for q, a in (answers or {}).items() if str(a).strip())

    if previous and (said or answered):
        bus.agent_state(project, "revising the plan", thinking=True)
        prompt = prompts.load("plan/revise",
                              plan=json.dumps(previous, ensure_ascii=False, indent=2),
                              transcript=interview.full_transcript(project),
                              revision=said or "(no separate instruction)",
                              answers=answered or "(none)",
                              language=language)
    else:
        bus.agent_state(project, "drafting the plan", thinking=True)
        prompt = prompts.load("plan/draft",
                              idea=record.get("idea", ""),
                              stack=record.get("stack", ""),
                              language=language,
                              transcript=interview.full_transcript(project))

    def check(proposed: Any) -> dict:
        if not isinstance(proposed, dict):
            raise ValueError("the plan must be a JSON object")
        merged = _merge(previous, proposed)
        plan_rules.plan_validator(plan_rules.archetype_pack(merged))(merged)
        return merged

    memory = session.memory_digest()
    merged = llm.complete_json(
        system=prompts.load("plan/system")
        + (f"\n\n## What this project already knows\n\n{memory}" if memory else ""),
        user=prompt, validator=check, label="plan", project=project)

    data["versions"] = (data.get("versions") or []) + [{
        "version": data.get("version", 0) + 1,
        "at": time.time(),
        "revision": said,
    }]
    data["version"] = data.get("version", 0) + 1
    data["plan"] = merged
    data["approved"] = False
    save(session, data)
    session.write_record("plan.md", data=_markdown(merged))

    bus.agent_state(project, "")
    store.advance(project, "plan")
    return current(project)


def approve(project: str) -> dict[str, Any]:
    """Accept the plan as the ceiling for everything that follows."""
    session = session_for(project)
    data = state(session)
    plan = data.get("plan")
    if not plan:
        raise ValueError("there is no plan to approve yet")

    ok, reason = _can_approve(plan)
    if not ok:
        raise ValueError(reason)

    data["approved"] = True
    data["approved_at"] = time.time()
    save(session, data)

    name = str(plan.get("app_name") or "").strip()
    if name:
        store.rename(project, name)
    store.advance(project, "srs")
    bus.log(project, "SUCCESS", "Plan approved — it is the boundary for the specification.")
    session.note(
        "The customer approved this plan. From here it is the boundary: later "
        "stages may detail and sharpen it, never widen it.\n\n"
        + _markdown(plan))
    return current(project)


def approved_plan(project: str) -> dict[str, Any]:
    data = state(session_for(project))
    return data.get("plan") or {}


def markdown(project: str) -> str:
    plan = approved_plan(project)
    return _markdown(plan) if plan else ""
