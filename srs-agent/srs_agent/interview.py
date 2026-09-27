"""The requirements interview.

One question at a time, each one chosen by the model from what is still unknown.
There is no topic catalogue and no fixed question list: a single-screen tool
finishes in a handful of questions and a multi-role system does not, and only
something that has read the answers so far can tell which this is.

The whole interview lives in the project's shared conversation, so by the time
the plan is drafted the model has not been told what the customer said — it was
there.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from server_modules import bus, config, llm, prompts, store, topics
from server_modules.session import ProjectSession, session_for

RECORD = ("interview.json",)

ANSWER_TYPES = {"single_choice", "multi_choice", "yes_no", "number", "free_text"}

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
            "started_at": time.time()}


def state(session: ProjectSession) -> dict[str, Any]:
    saved = session.read_record(*RECORD, fallback=None)
    return saved if isinstance(saved, dict) else _blank()


def save(session: ProjectSession, data: dict[str, Any]) -> None:
    session.write_record(*RECORD, data=data)


def _chosen_app_type(data: dict[str, Any]) -> str:
    """Which kind of product the customer picked, if they have."""
    entry = (data.get("answers") or {}).get(APP_TYPE_KEY) or {}
    picked = entry.get("selected_values") or []
    if picked:
        return str(picked[0])
    return str(entry.get("value") or "")


def app_type(project: str) -> str:
    return _chosen_app_type(state(session_for(project)))


def _attachment_digest(session: ProjectSession) -> str:
    rows = session.read_record("attachments.json", fallback=[]) or []
    if not rows:
        return "(nothing attached)"
    return "\n".join(
        f"- {row.get('filename', 'attachment')} ({row.get('mode', 'file')}): "
        f"{str(row.get('text') or '')[:1500]}" for row in rows)


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


KINDS = {"single": "single_choice", "multi": "multi_choice", "yes_no": "yes_no",
         "number": "number", "text": "free_text", "upload": "single_choice"}


def _options_for(topic: dict, payload: dict) -> list[dict]:
    """The choices this question offers.

    A topic with `options_locked` owns its machine values — the model may
    translate a label but must not invent a value, because downstream code reads
    those values. Otherwise the model's own options win, since they can name the
    customer's actual trade and goods; the catalogue's are the floor.
    """
    fallback = [o for o in (topic.get("fallback_options") or []) if isinstance(o, dict)]
    proposed = []
    for option in (payload.get("options") or []):
        if isinstance(option, dict) and str(option.get("label") or "").strip():
            proposed.append({"label": str(option["label"]).strip(),
                             "value": option.get("value", option["label"]),
                             **({"hint": str(option["hint"])} if option.get("hint") else {})})
        elif isinstance(option, str) and option.strip():
            proposed.append({"label": option.strip(), "value": option.strip()})

    if topic.get("options_locked") and fallback:
        translated = {str(o.get("value")): o for o in proposed}
        return [{**original,
                 "label": str(translated.get(str(original.get("value")), {}).get("label")
                              or original.get("label") or "")}
                for original in fallback]
    return proposed or fallback


def _from_topic(topic: dict, item: dict, index: int, total: int, question: str,
                payload: dict | None = None) -> dict[str, Any]:
    """One question, carrying the catalogue's contract and the model's wording."""
    payload = payload or {}
    kind = str(topic.get("kind") or "single")
    options = _options_for(topic, payload)
    subject = item.get("subject")

    known = [v for v in (payload.get("known") or []) if str(v).strip()]
    if options:
        allowed = {str(o["value"]) for o in options}
        known = [v for v in known if str(v) in allowed]
        if kind != "multi":
            known = known[:1]

    return {
        "id": item["key"], "key": item["key"], "topic": item["topic"],
        "subject": subject,
        "question": question or topic.get("intent", ""),
        "why_needed": str(payload.get("why_needed") or topic.get("intent") or "")[:240],
        "answer_type": KINDS.get(kind, "single_choice"), "kind": kind,
        "options": options,
        "suggested_options": [o["label"] for o in options],
        "recommended": payload.get("recommended"),
        "prefill": known,
        "prefill_note": str(payload.get("known_quote") or "").strip()[:240],
        "placeholder": str(payload.get("placeholder") or topic.get("placeholder") or "").strip(),
        "coverage_areas": list(topic.get("coverage") or []),
        "maps_to_srs_fields": list(topic.get("srs_fields") or []),
        "required": not topic.get("optional"),
        "optional": bool(topic.get("optional")),
        "multiline": bool(topic.get("multiline")),
        "index": index, "total": max(total, index),
    }


def _normalise(payload: dict[str, Any], index: int) -> dict[str, Any]:
    """The model's answer, in the shape the studio's Interview screen reads."""
    topic = str(payload.get("topic") or f"q{index}").strip() or f"q{index}"
    key = f"{topic}:{index}"
    answer_type = str(payload.get("answer_type") or "single_choice")
    if answer_type not in ANSWER_TYPES:
        answer_type = "free_text"

    options = []
    for option in (payload.get("options") or []):
        if isinstance(option, dict) and str(option.get("label") or "").strip():
            options.append({
                "label": str(option["label"]).strip(),
                "value": option.get("value", option["label"]),
                **({"hint": str(option["hint"])} if option.get("hint") else {}),
            })
        elif isinstance(option, str) and option.strip():
            options.append({"label": option.strip(), "value": option.strip()})

    known = [v for v in (payload.get("known") or []) if str(v).strip()]
    if options:
        allowed = {str(o["value"]) for o in options}
        known = [v for v in known if str(v) in allowed]
        if answer_type != "multi_choice":
            known = known[:1]

    return {
        "id": key,
        "key": key,
        "topic": topic,
        "question": str(payload.get("question") or "").strip(),
        "why_needed": str(payload.get("why_needed") or "").strip()[:240],
        "answer_type": answer_type,
        "kind": {"single_choice": "single", "multi_choice": "multi", "yes_no": "yes_no",
                 "number": "number", "free_text": "text"}[answer_type],
        "options": options,
        "suggested_options": [o["label"] for o in options],
        "recommended": payload.get("recommended"),
        "prefill": known,
        "prefill_note": str(payload.get("known_quote") or "").strip()[:240],
        "placeholder": str(payload.get("placeholder") or "").strip(),
        "coverage_areas": [str(c) for c in (payload.get("coverage") or [])],
        "maps_to_srs_fields": [str(c) for c in (payload.get("coverage") or [])],
        "required": answer_type != "free_text",
        "optional": answer_type == "free_text",
        "multiline": answer_type == "free_text",
        "index": index,
        "total": max(index, int(payload.get("remaining_estimate") or 0) + index),
    }


_asking: dict[str, threading.Lock] = {}
_asking_guard = threading.Lock()


def _ask_lock(project: str) -> threading.Lock:
    """One question at a time per project.

    The studio's interview screen can fire its refresh more than once — a
    reload, a double effect, an impatient click — and without this each of those
    runs its own model call and writes its own `interview.json`, so two answers
    race and one is lost.
    """
    with _asking_guard:
        return _asking.setdefault(project, threading.Lock())


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
    pending = data.get("pending")
    if pending:
        return view(session, data)

    session.role = bus.DEVELOPER
    index = len(data["order"]) + 1
    budget = max(3, int(config.setting("interview_max_questions",
                                       topics.max_questions())))

    # The first question is the product's shape, and it comes from the catalogue
    # rather than the model — instant, and it anchors everything after it.
    if index == 1:
        question = _app_type_question(record.get("idea", ""), index, budget)
        data["pending"] = question
        data["transcript"] = [question]
        save(session, data)
        return view(session, data)

    chosen = _chosen_app_type(data)
    types = catalogue().get("types") or {}
    queue = topics.build_queue(data["answers"], chosen, types)

    # The catalogue decides what is asked and in what order; the model only
    # phrases it. That is what makes this a requirements session rather than a
    # conversation that follows whatever the last answer made interesting.
    if not queue or index > budget:
        data["done"] = True
        data["pending"] = None
        save(session, data)
        bus.log(project, "INFO",
                f"Interview complete — {index - 1} question(s) asked"
                + ("" if queue else ", every topic covered") + ".")
        bus.agent_state(project, "", agent=bus.DEVELOPER)
        store.advance(project, "plan")
        return view(session, data)

    bus.agent_state(project, "asking", agent=bus.DEVELOPER)
    item = queue[0]
    topic = topics.by_key().get(item["topic"], {})
    total = min(budget, topics.total_estimate(data["answers"], chosen, types))

    # A topic with fixed wording is asked as written — those exist precisely
    # because their phrasing was settled and should not be re-invented.
    if topic.get("fixed"):
        question = _from_topic(topic, item, index, total, topic["fixed"])
        data["pending"] = question
        data["transcript"] = [q for q in data["transcript"] if q.get("id") != question["id"]]
        data["transcript"].append(question)
        save(session, data)
        bus.agent_state(project, "", agent=bus.DEVELOPER)
        return view(session, data)

    answer = llm.complete_json(
        system=prompts.load("interview/system"),
        user=prompts.load("interview/next-question",
                          idea=record.get("idea", ""),
                          stack=record.get("stack", ""),
                          language=record.get("language", "English"),
                          attachments=_attachment_digest(session),
                          transcript=transcript_text(data),
                          app_type=(types.get(chosen) or {}).get("label") or chosen,
                          topic_key=item["topic"],
                          topic_label=topic.get("label", item["topic"]),
                          topic_intent=topic.get("intent", ""),
                          topic_kind=topic.get("kind", "single"),
                          subject=item.get("subject") or "(not about one particular thing)",
                          options=json.dumps(topic.get("fallback_options") or [],
                                             ensure_ascii=False),
                          options_locked=str(bool(topic.get("options_locked"))).lower(),
                          asked=index - 1,
                          budget=budget,
                          remaining=max(0, total - index + 1)),
        label=f"interview:{item['topic']}")

    question = _from_topic(topic, item, index, total,
                           str((answer or {}).get("question") or "").strip(),
                           answer if isinstance(answer, dict) else {})
    data["pending"] = question
    data["transcript"] = [q for q in data["transcript"] if q.get("id") != question["id"]]
    data["transcript"].append(question)
    save(session, data)
    bus.agent_state(project, "", agent=bus.DEVELOPER)
    return view(session, data)


def record_answer(project: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Store one answer and let the conversation see it."""
    session = session_for(project)
    data = state(session)
    key = str(payload.get("key") or "").strip()
    if not key:
        raise ValueError("an answer needs the key of the question it answers")

    asked = next((q for q in data["transcript"] if q.get("id") == key), None)
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

    # Into the project's one memory, so the prototype, the build and the
    # deployment all know what the customer actually said — without a model call
    # and without re-reading the transcript at every stage.
    asked_text = (asked or {}).get("question") or key
    session.note(f"Interview — {asked_text}\nThe customer answered: {said}")
    # No acknowledgement call. It cost a whole model round per answer and said
    # nothing the customer needed; the transcript on disk is what every later
    # stage reads, and it already has this answer.
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
