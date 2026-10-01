"""The requirements interview.

One question at a time, each one chosen by the model from what is still
unknown. There is no fixed question list and no fixed order: every turn, the
model sees the full accumulated picture — what's KNOWN, PARTIAL or UNKNOWN
across a hardcoded taxonomy of requirement categories (`server_modules
.coverage`) — and decides for itself what single gap is most valuable to ask
about next, in this particular project's own words. A single-screen tool
finishes in a handful of questions and a multi-role system does not, and only
something that has read the answers so far can tell which this is.

The one question the catalogue still owns is the very first: which kind of
product this is. Asking it before any model call anchors everything that
follows, and costs nothing — the customer sees it the moment they press Start.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from server_modules import bus, config, coverage, llm, prompts, store
from server_modules.session import ProjectSession, session_for

RECORD = ("interview.json",)

ANSWER_TYPES = {"single_choice", "multi_choice", "yes_no", "number", "free_text"}
KINDS = {"single_choice": "single", "multi_choice": "multi", "yes_no": "yes_no",
         "number": "number", "free_text": "text"}

# The catalogue's own key for this topic. Storing the answer under anything else
# — `app_type:1`, say — leaves `app_type` looking unanswered, so the queue asks
# it again and the model phrases the *next* topic's question under its name.
APP_TYPE_KEY = "app_type"


def catalogue() -> dict[str, Any]:
    try:
        return prompts.data("interview/app-types")
    except prompts.MissingPrompt:
        return {"default": "other", "types": {}}


# Words that appear in every description and every idea, and so tell the guess
# nothing. Without this, "with" in "Subscription product with accounts" matched
# "a hotel that takes bookings with payment" and every idea looked like SaaS.
_NOISE_WORDS = {
    "with", "that", "this", "from", "into", "your", "their", "them", "they",
    "have", "has", "will", "would", "should", "must", "need", "needs", "want",
    "wants", "make", "made", "take", "takes", "taken", "give", "gives", "also",
    "some", "each", "every", "only", "other", "another", "when", "where", "what",
    "which", "than", "then", "there", "here", "over", "under", "about", "after",
    "before", "page", "pages", "site", "app", "apps", "product", "products",
    "system", "systems", "online", "website", "web", "user", "users", "people",
    "thing", "things", "something", "anything", "built", "build", "building",
}


def _stems(text: str) -> set[str]:
    """Words worth matching on, reduced to a crude stem.

    Crude on purpose: "bookings" and "booking", "rooms" and "room" have to meet,
    and a five-character prefix does that without a stemmer.
    """
    out: set[str] = set()
    for word in re.split(r"[^a-z]+", str(text or "").lower()):
        if len(word) > 3 and word not in _NOISE_WORDS:
            out.add(word[:5])
    return out


def _guess_app_type(idea: str) -> str:
    """The type this idea most sounds like, for the first question's default.

    A weak signal deliberately: it preselects nothing the customer cannot change
    in one click, and a wrong guess costs them that click.
    """
    words = _stems(idea)
    if not words:
        return ""
    best, best_score = "", 0
    for key, entry in (catalogue().get("types") or {}).items():
        if key == "other":
            continue
        hints = _stems(" ".join([
            str(entry.get("label", "")), str(entry.get("desc", "")),
            *(str(p) for p in (entry.get("asks_about") or [])),
        ]))
        score = len(hints & words)
        if score > best_score:
            best, best_score = key, score
    return best


def _app_type_question(idea: str, index: int, total: int) -> dict[str, Any]:
    """The first question, built from the catalogue rather than from the model.

    Asking it first is what stops the interview drifting: once the product has a
    shape, every later question is asked inside that shape instead of exploring
    the space of all possible products. It costs no model call, so the customer
    sees it the moment they press Start.
    """
    pack = catalogue()
    options = [{"label": f"{entry.get('icon', '')} {entry.get('label', key)}".strip(),
                "value": key, "hint": entry.get("desc", "")}
               for key, entry in (pack.get("types") or {}).items()]
    guess = _guess_app_type(idea) or pack.get("default") or ""
    return {
        "id": APP_TYPE_KEY, "key": APP_TYPE_KEY, "topic": "app_type",
        "question": "Which of these best describes what you want built?",
        "why_needed": "This sets the shape of the product, so the rest of these "
                      "questions are about your product rather than about software "
                      "in general.",
        "answer_type": "single_choice", "kind": "single",
        "options": options,
        "suggested_options": [o["label"] for o in options],
        "recommended": guess or None,
        "prefill": [], "prefill_note": "", "placeholder": "",
        "coverage_areas": ["app_type"], "maps_to_srs_fields": ["app_type"],
        "required": True, "optional": False, "multiline": False,
        "index": index, "total": total,
    }


def _blank() -> dict[str, Any]:
    return {"transcript": [], "answers": {}, "order": [], "done": False,
            "started_at": time.time(), "stage": "gathering",
            "coverage": coverage.blank_coverage(), "contradictions": [], "assumptions": []}


def state(session: ProjectSession) -> dict[str, Any]:
    saved = session.read_record(*RECORD, fallback=None)
    data = saved if isinstance(saved, dict) else _blank()
    # Defensive backfill for a record saved before these fields existed —
    # never a reason to lose an interview already in progress.  In particular,
    # do not let one partial/old record turn an ordinary retry into a KeyError
    # (and therefore an HTTP 500) while the customer is answering a question.
    transcript = data.get("transcript")
    data["transcript"] = [row for row in transcript if isinstance(row, dict)] \
                         if isinstance(transcript, list) else []
    answers = data.get("answers")
    data["answers"] = {str(key): entry for key, entry in answers.items()
                       if isinstance(entry, dict)} if isinstance(answers, dict) else {}
    order = data.get("order")
    data["order"] = [str(key) for key in order if str(key).strip()] \
                    if isinstance(order, list) else []
    if data.get("pending") is not None and not isinstance(data.get("pending"), dict):
        data["pending"] = None
    data.setdefault("pending", None)
    data.setdefault("done", False)
    data.setdefault("stage", "gathering")
    baseline_coverage = coverage.blank_coverage()
    if not isinstance(data.get("coverage"), dict):
        data["coverage"] = baseline_coverage
    else:
        for key, fallback in baseline_coverage.items():
            if not isinstance(data["coverage"].get(key), dict):
                data["coverage"][key] = fallback
    contradictions = data.get("contradictions")
    data["contradictions"] = [row for row in contradictions if isinstance(row, dict)] \
                             if isinstance(contradictions, list) else []
    if not isinstance(data.get("assumptions"), list):
        data["assumptions"] = []
    return data


def save(session: ProjectSession, data: dict[str, Any]) -> None:
    session.write_record(*RECORD, data=data)


def _announce_question(project: str, session: ProjectSession, data: dict[str, Any],
                       question: dict[str, Any]) -> None:
    """Put each interview question in the project's one durable chat stream.

    The interview used to keep its questions only inside its own screen, so
    the shared SRS → wireframe → prototype → build → deploy conversation had
    the customer's answers but not the questions they answered. Marking the
    question before publishing makes refreshes safe: a reload can show the
    same pending question without inserting it into the stream again.
    """
    if question.get("announced"):
        return
    question["announced"] = True
    save(session, data)
    bus.agent_msg(project, question.get("question") or "Interview question",
                  agent=bus.DEVELOPER, title="Interview question", kind="interview")


def _chosen_app_type(data: dict[str, Any]) -> str:
    """Which kind of product the customer picked, if they have."""
    entry = (data.get("answers") or {}).get(APP_TYPE_KEY) or {}
    picked = entry.get("selected_values") or []
    if picked:
        return str(picked[0])
    return str(entry.get("value") or "")


def _attachment_digest(session: ProjectSession) -> str:
    rows = session.read_record("attachments.json", fallback=[]) or []
    if not rows:
        return "(nothing attached)"
    lines = [
        "The customer attached source files. Before asking follow-up questions, use your "
        "read, line, and search tools on the workspace-relative locations below; do not "
        "guess from their filenames or only the extraction preview."
    ]
    for row in rows:
        path = str(row.get("path") or "").strip() or "(saved attachment path unavailable)"
        preview = str(row.get("text") or "").strip()[:1500]
        lines.append(
            f"- {row.get('filename', 'attachment')} ({row.get('mode', 'file')}) at {path}"
            + (f": extracted preview: {preview}" if preview else "")
        )
    return "\n".join(lines)


def transcript_text(data: dict[str, Any]) -> str:
    """What the customer has told us so far, as the model should read it back."""
    lines: list[str] = []
    for key in data.get("order", []):
        asked = next((q for q in data["transcript"] if q.get("id") == key), None)
        answer = data["answers"].get(key)
        if not asked or not answer:
            continue
        said = answer.get("text") or answer.get("value")
        if isinstance(said, list):
            said = ", ".join(str(x) for x in said)
        lines.append(f"Q: {asked.get('question', '')}\nA: {said}")
        for note in answer.get("attachments", []):
            lines.append(f"   (they attached {note})")
    return "\n\n".join(lines) or "(nothing yet)"


def _question_from_turn(next_payload: dict[str, Any], index: int, total: int) -> dict[str, Any]:
    """One turn's `next` question, in the shape the studio's Interview screen reads."""
    topic = str(next_payload.get("topic") or f"q{index}").strip() or f"q{index}"
    key = f"{topic}:{index}"
    answer_type = str(next_payload.get("answer_type") or "single_choice")
    if answer_type not in ANSWER_TYPES:
        answer_type = "free_text"

    options = []
    for option in (next_payload.get("options") or []):
        if isinstance(option, dict) and str(option.get("label") or "").strip():
            options.append({
                "label": str(option["label"]).strip(),
                "value": option.get("value", option["label"]),
                **({"hint": str(option["hint"])} if option.get("hint") else {}),
            })
        elif isinstance(option, str) and option.strip():
            options.append({"label": option.strip(), "value": option.strip()})

    known = [v for v in (next_payload.get("known") or []) if str(v).strip()]
    if options:
        allowed = {str(o["value"]) for o in options}
        known = [v for v in known if str(v) in allowed]
        if answer_type != "multi_choice":
            known = known[:1]

    return {
        "id": key,
        "key": key,
        "topic": topic,
        "subject": None,
        "question": str(next_payload.get("question") or "").strip(),
        "why_needed": str(next_payload.get("why_needed") or "").strip()[:240],
        "answer_type": answer_type,
        "kind": KINDS[answer_type],
        "options": options,
        "suggested_options": [o["label"] for o in options],
        "recommended": next_payload.get("recommended"),
        "prefill": known,
        "prefill_note": str(next_payload.get("known_quote") or "").strip()[:240],
        "placeholder": str(next_payload.get("placeholder") or "").strip(),
        "coverage_areas": [str(c) for c in (next_payload.get("coverage") or [])],
        "maps_to_srs_fields": [str(c) for c in (next_payload.get("coverage") or [])],
        "required": answer_type != "free_text",
        "optional": answer_type == "free_text",
        "multiline": answer_type == "free_text",
        "index": index,
        "total": max(index, int(next_payload.get("remaining_estimate") or 0) + index),
    }


def _confirmation_question(summary: str, index: int, total: int) -> dict[str, Any]:
    """The end-of-interview recap, delivered as an ordinary pending question so
    the frontend needs no special case for it."""
    return {
        "id": f"confirm:{index}", "key": f"confirm:{index}", "topic": "confirmation",
        "subject": None,
        "question": summary or "Here is what I understood — is this correct?",
        "why_needed": "Confirming before writing the specification.",
        "answer_type": "single_choice", "kind": "single",
        "options": [{"label": "Yes, that's right", "value": "confirmed"},
                    {"label": "I need to change something", "value": "correct"}],
        "suggested_options": ["Yes, that's right", "I need to change something"],
        "recommended": "confirmed",
        "prefill": [], "prefill_note": "",
        "placeholder": "Or describe what to change",
        "coverage_areas": [], "maps_to_srs_fields": [],
        "required": True, "optional": False, "multiline": False,
        "index": index, "total": max(total, index),
    }


def _turn_validator(valid_categories: set[str]):
    """The turn's JSON, checked against the coverage contract before it is
    trusted — feeds `complete_json`'s own repair loop on failure."""

    def check(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("the turn result must be a JSON object")
        updates = payload.get("coverage_updates")
        if updates is None:
            payload["coverage_updates"] = {}
        elif not isinstance(updates, dict):
            raise ValueError("coverage_updates must be an object keyed by category")
        else:
            bad = [k for k in updates if k not in valid_categories]
            if bad:
                raise ValueError(f"coverage_updates named unknown categories: {', '.join(bad)}. "
                                 f"Only use: {', '.join(sorted(valid_categories))}")
        stage = str(payload.get("stage") or "gathering")
        if stage not in ("gathering", "confirming"):
            raise ValueError("stage must be exactly 'gathering' or 'confirming'")
        payload["stage"] = stage
        if stage == "gathering":
            next_q = payload.get("next")
            if not isinstance(next_q, dict) or not str(next_q.get("question") or "").strip():
                raise ValueError("stage is 'gathering' but next.question is empty")
        elif not str(payload.get("confirmation_summary") or "").strip():
            raise ValueError("stage is 'confirming' but confirmation_summary is empty")
        return payload

    return check


def _apply_turn(data: dict[str, Any], turn: dict[str, Any], source: str) -> None:
    """Fold one turn's deltas into the persisted state, in place.

    Deltas only — a category the model did not mention this turn keeps
    whatever it already had, so one bad turn can never wipe an earlier fact.
    """
    now = time.time()
    cov = data["coverage"]
    for key, delta in (turn.get("coverage_updates") or {}).items():
        if key not in cov or not isinstance(delta, dict):
            continue
        entry = cov[key]
        status = str(delta.get("status") or entry.get("status") or "UNKNOWN")
        if status in coverage.STATUSES:
            entry["status"] = status
        entry["confidence"] = str(delta.get("confidence") or entry.get("confidence") or "low")
        facts = [str(f) for f in (delta.get("facts") or []) if str(f).strip()]
        if facts:
            entry["facts"] = facts
        entry["source"] = source
        entry["updated_at"] = now

    contradiction = turn.get("contradiction")
    # The validator does not shape this field; a bare "yes" or `true` here used to raise and turn
    # the whole question into an HTTP 500.
    if isinstance(contradiction, dict) and contradiction.get("found"):
        data["contradictions"].append({
            "id": f"c{len(data['contradictions']) + 1}",
            "category": contradiction.get("category"),
            "resolved": False,
            "statement_a": contradiction.get("statement_a") or {},
            "statement_b": contradiction.get("statement_b") or {},
            "raised_at": now, "resolution": None,
        })

    for item in turn.get("assumptions") or []:
        if isinstance(item, dict) and str(item.get("fact") or "").strip():
            data["assumptions"].append({
                "category": item.get("category"), "fact": str(item["fact"]),
                "confidence": str(item.get("confidence") or "medium"),
                "basis": str(item.get("basis") or ""),
            })

    data["stage"] = turn["stage"]


_asking: dict[str, threading.RLock] = {}
_asking_guard = threading.Lock()


def _ask_lock(project: str) -> threading.RLock:
    """One interview transition at a time per project.

    The studio's interview screen can fire its refresh more than once — a
    reload, a double effect, an impatient click, or a retry after a lost
    response.  Questions *and* answers must use the same lock: otherwise a
    duplicate answer can overwrite the next question while the browser is
    refreshing, which used to leave an invalid transient state and an HTTP 500.
    """
    with _asking_guard:
        return _asking.setdefault(project, threading.RLock())


def next_question(project: str) -> dict[str, Any]:
    """Ask the next question, or report that the interview is finished."""
    with _ask_lock(project):
        return _next_question(project)


def _next_question(project: str) -> dict[str, Any]:
    record = store.require(project)
    session = session_for(project)
    data = state(session)

    if data.get("done"):
        return view(session, data)

    # A question already on screen is asked again rather than replaced, so a
    # browser reload does not cost the customer an answer.
    if data.get("pending"):
        _announce_question(project, session, data, data["pending"])
        return view(session, data)

    session.role = bus.DEVELOPER
    index = len(data["order"]) + 1
    budget = max(3, int(config.setting("interview_max_questions", 25)))

    # The first question is the product's shape, and it comes from the catalogue
    # rather than the model — instant, and it anchors everything after it.
    if index == 1:
        question = _app_type_question(record.get("idea", ""), index, budget)
        data["pending"] = question
        data["transcript"] = [question]
        save(session, data)
        _announce_question(project, session, data, question)
        return view(session, data)

    # A safety ceiling, not a target: past it, stop gathering and ask for
    # confirmation instead of cutting the customer off with nothing to show.
    if index > budget:
        data["stage"] = "confirming"

    bus.agent_state(project, "asking", agent=bus.DEVELOPER)

    cats = coverage.categories()
    chosen = _chosen_app_type(data)
    app_label = (catalogue().get("types", {}).get(chosen) or {}).get("label") or chosen
    open_contradictions = [c for c in data["contradictions"] if not c.get("resolved")]
    language = record.get("language", "English")

    turn = llm.complete_json(
        system=prompts.load("interview/system", language=language),
        user=prompts.load("interview/turn",
                          idea=record.get("idea", ""),
                          stack=record.get("stack", ""),
                          language=language,
                          attachments=_attachment_digest(session),
                          transcript=transcript_text(data),
                          app_type=app_label,
                          coverage_json=json.dumps(data["coverage"], ensure_ascii=False),
                          categories_json=json.dumps(cats, ensure_ascii=False),
                          open_contradictions_json=json.dumps(open_contradictions, ensure_ascii=False),
                          stage=data["stage"],
                          asked=index - 1,
                          budget=budget),
        validator=_turn_validator(set(cats)),
        label="interview:turn",
        # `project` reports this turn's context to the chat's meter. The read tools come only
        # with attached files: the prompt then tells the model to read them, which it cannot
        # do without a workspace, and a turn with nothing to read stays a fast tool-less call.
        project=project,
        workspace=session.workspace if session.read_record("attachments.json", fallback=[]) else None)

    _apply_turn(data, turn, source=f"turn:{index}")

    if data["stage"] == "confirming":
        question = _confirmation_question(turn.get("confirmation_summary", ""), index, budget)
    else:
        question = _question_from_turn(turn.get("next") or {}, index, budget)

    data["pending"] = question
    data["transcript"] = [q for q in data["transcript"] if q.get("id") != question["id"]]
    data["transcript"].append(question)
    save(session, data)
    _announce_question(project, session, data, question)
    bus.agent_state(project, "", agent=bus.DEVELOPER)
    return view(session, data)


def record_answer(project: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Store one answer and let the conversation see it."""
    with _ask_lock(project):
        session = session_for(project)
        data = state(session)
        key = str(payload.get("key") or "").strip()
        if not key:
            raise ValueError("an answer needs the key of the question it answers")

        # A browser may retry a POST after its response was interrupted.  The
        # first request already owns the answer, so replay its current view
        # instead of treating that retry as a fresh mutation.
        if key in data["answers"]:
            return view(session, data)

        pending = data.get("pending") or {}
        if pending.get("id") != key:
            raise ValueError("that question is no longer awaiting an answer; refresh and answer the current question")

        asked = next((q for q in data["transcript"] if q.get("id") == key), None)
        if not asked:
            raise ValueError("that interview question is unavailable; refresh and try again")

        selected = [str(v) for v in (payload.get("selected") or [])]
        custom = str(payload.get("custom") or "").strip()
        text = str(payload.get("text") or "").strip()
        attachments = [str(a) for a in (payload.get("attachments") or [])]

        entry = {
            "question_id": key,
            "topic": key.split(":", 1)[0],
            "value": payload.get("value"),
            "text": text or custom or ", ".join(selected),
            "selected_values": selected,
            "custom_text": custom,
            "attachments": attachments,
            "at": time.time(),
        }
        data["answers"][key] = entry
        if key not in data["order"]:
            data["order"].append(key)
        data["pending"] = None
        save(session, data)

        said = entry["text"] or str(entry["value"] or "")
        bus.user_msg(project, said, agent=bus.DEVELOPER)

        # A plain "yes, that's right" to the confirmation question ends the
        # interview outright — no model call needed just to agree with itself.
        # `text` always carries the picked option's own label (see Interview.jsx's
        # submitAnswer — `text: combined || customText || selectedText`), so it is
        # never empty for a plain click; only `custom` (what the customer typed
        # themselves) tells a bare acceptance apart from an actual correction.
        if data["stage"] == "confirming" and "confirmed" in selected and not custom:
            data["done"] = True
            save(session, data)
            bus.log(project, "SUCCESS", "The customer confirmed the summary — writing the plan next.")
            bus.agent_state(project, "", agent=bus.DEVELOPER)
            store.advance(project, "plan")
            session.note("Interview confirmed. The customer signed off on the requirements summary.")
            return view(session, data)

        # Into the project's one memory, so the prototype, the build and the
        # deployment all know what the customer actually said — without a model call
        # and without re-reading the transcript at every stage.
        asked_text = asked.get("question") or key
        session.note(f"Interview — {asked_text}\nThe customer answered: {said}")
        # No acknowledgement call. It cost a whole model round per answer and said
        # nothing the customer needed; the transcript on disk is what every later
        # stage reads, and it already has this answer. A correction to the
        # confirmation summary re-enters the same turn loop on the next call,
        # through the ordinary path above — no special case needed here.
        return view(session, data)


def view(session: ProjectSession, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the studio's Interview screen reads."""
    data = data if data is not None else state(session)
    answers = [{
        "question_id": key,
        "value": entry.get("value"),
        "raw_text": entry.get("text"),
        "selected": entry.get("selected_values") or [],
        "custom": entry.get("custom_text") or "",
    } for key, entry in data.get("answers", {}).items()]
    return {
        "question": data.get("pending"),
        "transcript": [{"id": q["id"], "question": q["question"]}
                       for q in data.get("transcript", [])],
        "answers": answers,
        "done": bool(data.get("done")),
    }


def snapshot(project: str) -> dict[str, Any]:
    return view(session_for(project))


def full_transcript(project: str) -> str:
    return transcript_text(state(session_for(project)))
