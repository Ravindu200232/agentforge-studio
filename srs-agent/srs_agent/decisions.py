"""The specification's open decisions, asked as questions in their own tab and settled by the customer's answers.

The decisions are the document's `ambiguities` that still `needs_clarification`: places where the specification had to assume
something the customer never said. The overview used to say only "12 decisions needed" and point at chapter 10. Now each one is
a question with answers to choose from (the first is always the assumption already made) and a box for an answer of one's own:

- choosing the assumption settles the decision at once: the specification already follows it;
- any other answer settles it at once too, and is then written into the specification by the agent (`decision-apply`), the
  next time no other run is working on the project; when that cannot be done, the decision is open again, saying so, and is
  answered again.

The questions are written once by a model, from the decisions themselves, and kept with them in `srs.json`.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from server_modules import bus, llm, prompts, store
from server_modules.session import RunCancelled, session_for

from . import document as srs_document

MAX_OPTIONS = 4
WAIT_SECONDS = 15                  # how often a waiting answer looks again whether the project is free
WAIT_LIMIT = 12 * 60 * 60          # how long it waits for a run to end before it gives up (the answer is applied next time)
APPLYING = "decision_applying"     # set on a decision whose answer is still to be written into the specification
FAILED = "decision_error"          # why the last answer could not be written in

_lock = threading.Lock()
_workers: dict[str, threading.Thread] = {}


def _load(project: str) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = srs_document.document(project)
    return envelope, envelope.get("srs_document") or {}


def _save(project: str, envelope: dict[str, Any]) -> None:
    session_for(project).write_record(*srs_document.DOCUMENT, data=envelope)
    # The open views of the specification read it again (their "decisions needed" count goes down).
    bus.sync_state(project, "clean", "Decisions updated", source="srs", srs_status="completed")


def _rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in doc.get("ambiguities") or [] if isinstance(a, dict) and a.get("id")]


def _is_open(entry: dict[str, Any]) -> bool:
    return bool(entry.get("needs_clarification"))


def _fallback(entry: dict[str, Any]) -> tuple[str, list[str]]:
    area, issue = str(entry.get("area") or "").strip(), str(entry.get("description") or "").strip()
    assumed = str(entry.get("assumption_made") or "").strip()
    return (f"{area}: {issue}" if area else issue), ([f"Keep the assumption: {assumed}"] if assumed else [])


def listing(project: str) -> dict[str, Any]:
    """What the Decisions tab shows: the open decisions as questions, and the ones already settled with their answers."""
    _envelope, doc = _load(project)
    open_rows, settled = [], []
    for entry in _rows(doc):
        question, options = _fallback(entry)
        question = str(entry.get("question") or question)
        options = [str(o) for o in entry.get("options") or options]
        if _is_open(entry):
            open_rows.append({"id": entry["id"], "area": str(entry.get("area") or ""), "issue": str(entry.get("description") or ""),
                              "assumption": str(entry.get("assumption_made") or ""), "question": question, "options": options,
                              "error": str(entry.get(FAILED) or "")})
        elif entry.get("resolution"):
            settled.append({"id": entry["id"], "area": str(entry.get("area") or ""), "question": question,
                            "answer": str(entry["resolution"]), "by": str(entry.get("resolved_by") or ""),
                            "applying": bool(entry.get(APPLYING))})
    return {"open": open_rows, "settled": settled, "count": len(open_rows)}


def _questions_validator(ids: set[str]):
    def check(data: Any) -> dict[str, dict[str, Any]]:
        rows = data.get("decisions") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError('"decisions" must be a list with one entry per decision')
        found: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or str(row.get("id") or "") not in ids:
                continue
            question = str(row.get("question") or "").strip()
            options = [str(o).strip()[:240] for o in row.get("options") or [] if str(o).strip()]
            if question and len(options) >= 2:
                found[str(row["id"])] = {"question": question[:400], "options": options[:MAX_OPTIONS]}
        if not found:
            raise ValueError("write a question and at least two answers for each decision")
        return found
    return check


def prepare(project: str) -> dict[str, Any]:
    """Write the questions of the open decisions that have none yet (once: they are kept), then return the listing. A model that
    cannot be reached leaves each decision asked as it is, with its assumption as the one answer to choose."""
    envelope, doc = _load(project)
    rows = [entry for entry in _rows(doc) if _is_open(entry) and not entry.get("options")]
    if rows:
        listing_text = "\n".join(f"- {e['id']} · {e.get('area', '')}: {e.get('description', '')} "
                                 f"(assumed: {e.get('assumption_made', '')})" for e in rows)
        language = str((store.get(project) or {}).get("language") or "English")
        try:
            written = llm.complete_json(system=prompts.load("srs/system"),
                                        user=prompts.load("srs/decision-questions", decisions=listing_text, language=language),
                                        validator=_questions_validator({str(e["id"]) for e in rows}),
                                        label="srs_decisions", project=project)
        except RunCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - each decision is still asked, with its own assumption as the answer
            bus.log(project, "WARN", f"The decisions could not be turned into questions ({str(exc)[:200]}); they are asked as written.")
            written = {}
        for entry in rows:
            question, options = _fallback(entry)
            made = written.get(str(entry["id"]))
            entry["question"] = made["question"] if made else question
            entry["options"] = made["options"] if made else options
        _save(project, envelope)
    _resume(project)
    return listing(project)


def answer(project: str, ident: str, given: str, option: int | None = None) -> dict[str, Any]:
    """The customer's answer to one open decision: one of its options (`option`, its index) or their own words (`given`)."""
    given = str(given or "").strip()
    if not given:
        raise ValueError("choose one of the answers, or type your own")
    envelope, doc = _load(project)
    entry = next((e for e in _rows(doc) if str(e["id"]) == str(ident)), None)
    if entry is None:
        raise ValueError(f"the specification has no decision {ident}")
    if not _is_open(entry):
        raise ValueError(f"{ident} is already settled")
    options = [str(o) for o in entry.get("options") or _fallback(entry)[1]]
    keeps = option == 0 or (bool(options) and given == options[0])
    entry.update(needs_clarification=False, resolution=given, resolved_by="customer answer")
    entry.pop(FAILED, None)
    if keeps:
        entry.pop(APPLYING, None)                    # the specification already follows the assumption
    else:
        entry[APPLYING] = True
    _save(project, envelope)
    bus.agent_msg(project, f"{ident} settled: {given}" + ("" if keeps else " It is being written into the specification."),
                  title="Specification decision", kind="narration")
    if not keeps:
        _resume(project)
    return listing(project)


# --- writing the answers into the specification -------------------------------------------------------------------------

def _pending(project: str) -> list[dict[str, Any]]:
    try:
        _envelope, doc = _load(project)
    except Exception:  # noqa: BLE001 - a specification that cannot be read has nothing pending
        return []
    return [e for e in _rows(doc) if e.get(APPLYING)]


def _resume(project: str) -> None:
    """Make sure answers still to be written into the specification are being written: one waiting worker per project, which
    also picks up answers left waiting by a Studio that was closed."""
    if not _pending(project):
        return
    with _lock:
        worker = _workers.get(project)
        if worker and worker.is_alive():
            return
        worker = threading.Thread(target=_wait_and_apply, args=(project,), daemon=True, name=f"decisions:{project}")
        _workers[project] = worker
    worker.start()


def _wait_and_apply(project: str) -> None:
    """Wait until no other run works on the project, then write every waiting answer in, as one run of its own."""
    from server_modules import runs

    name = f"decisions:{project}"
    deadline = time.time() + WAIT_LIMIT
    while time.time() < deadline and _pending(project):
        if runs.active_run(project):
            time.sleep(WAIT_SECONDS)
            continue
        try:
            runs._in_background(name, project, bus.DEVELOPER, apply_answers, project, _project=project)  # noqa: SLF001
        except ValueError:                                     # another run took the project first
            time.sleep(WAIT_SECONDS)
            continue
        while runs.active_run(project) == name:
            time.sleep(1)


def apply_answers(project: str) -> None:
    """One run of the agent that writes the customer's answers into the specification. An answer that could not be written in
    opens its decision again, with why, so it is answered again."""
    pending = _pending(project)
    if not pending:
        return
    lines = "\n".join(f"- {e['id']} ({e.get('area', '')}): {e.get('question') or e.get('description', '')}\n"
                      f"  The customer's answer: {e.get('resolution', '')}" for e in pending)
    session = session_for(project)
    session.begin("srs-edit")
    done, why = False, ""
    try:
        result = session.run_task(prompts.load(
            "chat/update", message=prompts.load("srs/decision-apply", decisions=lines).strip(), stage="specification",
            artifacts="the specification, its diagrams and its wireframes",
            language=str((store.get(project) or {}).get("language") or "English")))
        done = result.get("status") == "complete"
        why = "" if done else str(result.get("text") or "the agent stopped before it was done")[:300]
    except RunCancelled:
        why = "it was stopped"
        raise
    except Exception as exc:  # noqa: BLE001 - the decisions open again; nothing is lost
        why = str(exc)[:300]
    finally:
        _settle(project, pending, done, why)
    if done:
        session.finish("The answers are in the specification.")
    else:
        session.fail(f"The answers could not be written into the specification: {why}")


def _settle(project: str, pending: list[dict[str, Any]], done: bool, why: str) -> None:
    """After the agent's run: each answered decision settled (it may have rewritten `ambiguities`), or open again with why."""
    envelope, doc = _load(project)
    entries = doc.setdefault("ambiguities", [])
    by_id = {str(e.get("id")): e for e in entries if isinstance(e, dict)}
    for asked in pending:
        entry = by_id.get(str(asked["id"]))
        if entry is None:                                     # the agent dropped it: it is put back, as it was answered
            entry = {k: v for k, v in asked.items() if k not in (APPLYING, FAILED)}
            entries.append(entry)
        entry.pop(APPLYING, None)
        if done:
            entry.update(needs_clarification=False, resolution=asked.get("resolution", ""), resolved_by="customer answer")
            entry.pop(FAILED, None)
        else:
            entry.update(needs_clarification=True)
            entry.pop("resolution", None)
            entry[FAILED] = f"Your answer could not be written into the specification ({why}). Choose it again."
    _save(project, envelope)
    ids = ", ".join(str(e["id"]) for e in pending)
    bus.agent_msg(project, (f"The answers to {ids} are in the specification." if done else
                            f"The answers to {ids} could not be written into the specification ({why}); "
                            "they are open again in the Decisions tab."),
                  title="Specification decisions", kind="narration")
