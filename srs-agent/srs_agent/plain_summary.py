"""The specification in plain words, for someone who is not technical: what the product is, who uses it, what it does (the
functional requirements, grouped), how well it works (the quality requirements) and how it keeps people safe.

A model writes it once from the specification and it is kept in `srs.json` with a fingerprint of what it was written from, so
it is written again only when the specification has changed. The Overview shows it first.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from server_modules import bus, llm, prompts, store
from server_modules.session import RunCancelled, session_for

from . import document as srs_document

KEY = "plain_summary"
MAX_INPUT = 40_000


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("requirement") or value.get("description") or value.get("name") or value.get("role_name")
                   or json.dumps(value, ensure_ascii=False))
    return str(value or "")


def _source(doc: dict[str, Any]) -> str:
    """What the summary is written from: the product, its people, its requirements grouped by part, its quality and security."""
    summary = doc.get("app_summary") or {}
    lines = [f"Product: {summary.get('app_name') or doc.get('project_name') or ''}",
             f"Description: {summary.get('short_description') or ''}",
             f"Business goal: {summary.get('business_goal') or ''}", "", "People:"]
    for role in doc.get("roles") or []:
        if isinstance(role, dict):
            lines.append(f"- {role.get('role_name') or role.get('role_key')}: {role.get('description') or ''}")
    lines += ["", "What it must do, by part:"]
    by_part: dict[str, list[str]] = {}
    for item in doc.get("functional_requirements") or []:
        if isinstance(item, dict):
            by_part.setdefault(str(item.get("module") or "General"), []).append(_text(item))
    for part, items in by_part.items():
        lines.append(f"{part}:")
        lines += [f"- {item}" for item in items]
    lines += ["", "How well it must work:"]
    lines += [f"- {item.get('category', '') + ': ' if isinstance(item, dict) else ''}{_text(item)}"
              for item in doc.get("non_functional_requirements") or []]
    lines += ["", "Security:"] + [f"- {_text(item)}" for item in doc.get("security_requirements") or []]
    lines += ["", "Main workflows:"] + [f"- {w.get('workflow_name')}" for w in doc.get("business_workflows") or []
                                         if isinstance(w, dict) and w.get("workflow_name")]
    return "\n".join(lines)[:MAX_INPUT]


def fingerprint(doc: dict[str, Any]) -> str:
    return hashlib.sha256(_source(doc).encode("utf-8")).hexdigest()[:20]


def _clean(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("reply with one JSON object")
    text = lambda value, most=600: str(value or "").strip()[:most]  # noqa: E731
    lines = lambda value, most, size=400: [text(x, size) for x in (value if isinstance(value, list) else [value])  # noqa: E731
                                           if text(x)][:most]
    out = {"headline": text(data.get("headline"), 300),
           "story": lines(data.get("story"), 6, 1200),
           "people": [{"who": text(p.get("who"), 120), "does": text(p.get("does"), 500)}
                      for p in data.get("people") or [] if isinstance(p, dict) and text(p.get("who"))][:10],
           "what_you_can_do": [{"area": text(a.get("area"), 120), "points": lines(a.get("points"), 8, 300)}
                               for a in data.get("what_you_can_do") or [] if isinstance(a, dict) and text(a.get("area"))][:14],
           "a_day_with_it": [{"title": text(d.get("title"), 120), "steps": lines(d.get("steps"), 8, 300)}
                             for d in data.get("a_day_with_it") or [] if isinstance(d, dict) and text(d.get("title"))][:6],
           "how_it_feels": [{"topic": text(h.get("topic"), 80), "plain": text(h.get("plain"), 300)}
                            for h in data.get("how_it_feels") or [] if isinstance(h, dict) and text(h.get("plain"))][:8],
           "keeping_safe": lines(data.get("keeping_safe"), 6, 300),
           "what_the_business_gets": lines(data.get("what_the_business_gets"), 6, 300)}
    if not out["headline"] or not out["what_you_can_do"] or not out["story"]:
        raise ValueError('"headline", "story" and "what_you_can_do" are needed')
    return out


def read(project: str) -> dict[str, Any]:
    """The summary kept with the specification, and whether it still matches it ({"status": "ready" | "stale" | "missing"})."""
    doc = srs_document.document(project).get("srs_document") or {}
    kept = doc.get(KEY)
    if not isinstance(kept, dict) or not kept.get("headline"):
        return {"status": "missing"}
    return {"status": "ready" if kept.get("fingerprint") == fingerprint(doc) else "stale", **kept}


def write(project: str, again: bool = False) -> dict[str, Any]:
    """Write the summary when there is none, when the specification changed since it was written, or when asked (`again`)."""
    current = read(project)
    if current["status"] == "ready" and not again:
        return current
    envelope = srs_document.document(project)
    doc = envelope.get("srs_document") or {}
    language = str((store.get(project) or {}).get("language") or doc.get("document_language") or "English")
    try:
        made = llm.complete_json(system=prompts.load("srs/system"),
                                 user=prompts.load("srs/plain-summary", specification=_source(doc), language=language),
                                 validator=_clean, label="srs_plain_summary", project=project)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - the Overview still shows everything else; it says this could not be written
        bus.log(project, "WARN", f"The plain-language summary could not be written: {str(exc)[:200]}")
        return {**current, "status": current["status"] if current["status"] != "missing" else "failed",
                "reason": str(exc)[:200]}
    doc[KEY] = {"fingerprint": fingerprint(doc), **made}
    session_for(project).write_record(*srs_document.DOCUMENT, data=envelope)
    return {"status": "ready", **doc[KEY]}
