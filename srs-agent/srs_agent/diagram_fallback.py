"""A diagram drawn straight from the specification, for when the model could not produce one.

The last resort of `document._draw_diagram`, after the model has been asked again without tools and still did not
return Mermaid. It only restates facts the specification already holds - the same compact slice the model is given
(`document._diagram_context`) - so nothing here is invented: a workflow's own steps become messages, a status field's
own values become states, the tables and their relationships become entities. It never replaces a diagram the model
drew, and a kind with no such facts yields "" (the diagram is then reported as not drawn, never faked).
"""
from __future__ import annotations

import re
from typing import Any, Callable

# Kept in a label: letters, digits, spaces and plain punctuation. Quotes, brackets, semicolons and '#' are what end a
# Mermaid label early, so they go.
_UNSAFE = re.compile(r"[^\w .,:/'&%+-]")
_STATES = re.compile(r"\s*enum\((?P<values>.*)\)\s*$", re.IGNORECASE | re.DOTALL)


def _label(value: Any, limit: int = 60) -> str:
    text = _UNSAFE.sub("", " ".join(str(value or "").split())).strip()
    return text[:limit - 1].rstrip() + "…" if len(text) > limit else text


def _ident(value: Any, fallback: str = "x") -> str:
    text = re.sub(r"\W+", "_", str(value or "")).strip("_") or fallback
    return text if not text[0].isdigit() else "n" + text


def _workflow(context: dict) -> tuple[dict, list[str]]:
    """The first workflow with something to say: its row, and up to eight of its steps."""
    for row in context.get("business_workflows") or []:
        if not isinstance(row, dict):
            continue
        steps = [step for step in (row.get("steps") or []) if str(step).strip()]
        if str(row.get("workflow_name") or "").strip() and len(steps) >= 2:
            return row, steps[:8]
    return {}, []


def _sequence(context: dict) -> str:
    row, steps = _workflow(context)
    if not steps:
        return ""
    who = _label(row.get("who"), 30) or "User"
    system = _label((context.get("app_summary") or {}).get("app_name"), 40) or "System"
    lines = ["sequenceDiagram", f"    actor U as {who}", f"    participant S as {system}"]
    lines += [f"    U->>S: {_label(step, 80)}" for step in steps]
    return "\n".join(lines)


def _activity(context: dict) -> str:
    _, steps = _workflow(context)
    if not steps:
        return ""
    lines = ["flowchart TD", "    start((●)) --> a1"]
    for index, step in enumerate(steps, 1):
        lines.append(f'    a{index}("{_label(step, 80)}")' + (f" --> a{index + 1}" if index < len(steps) else ""))
    lines.append(f"    a{len(steps)} --> finish((◉))")
    return "\n".join(lines)


def _state_values(context: dict) -> list[str]:
    for row in context.get("lifecycle_candidates") or []:
        found = _STATES.match(str(row.get("states") or "")) if isinstance(row, dict) else None
        values = [v.strip().strip("'\"") for v in found.group("values").split(",") if v.strip()] if found else []
        if len(values) >= 2:
            return values[:10]
    return []


def _state_machine(context: dict) -> str:
    values = _state_values(context)
    if not values:
        return ""
    ids = [f"s{index}_{_ident(value)}" for index, value in enumerate(values)]
    lines = ["stateDiagram-v2", "    direction LR"]
    lines += [f'    state "{_label(value, 30)}" as {sid}' for value, sid in zip(values, ids)]
    lines.append(f"    [*] --> {ids[0]}")
    lines += [f"    {a} --> {b}" for a, b in zip(ids, ids[1:])]
    lines.append(f"    {ids[-1]} --> [*]")
    return "\n".join(lines)


# How a relationship's type reads from its `from` table (the side holding the key) to its `to` table.
_LINKS = {"many_to_one": "}o--||", "one_to_many": "||--o{", "one_to_one": "||--||", "many_to_many": "}o--o{"}


def _erd(context: dict) -> str:
    database = context.get("database_design") or {}
    tables = [t for t in (database.get("tables") or []) if isinstance(t, dict) and t.get("table_name")][:12]
    if not tables:
        return ""
    names = {str(t["table_name"]): _ident(t["table_name"]).upper() for t in tables}
    lines = ["erDiagram"]
    for table in tables:
        lines.append(f"    {names[str(table['table_name'])]} " + "{")
        for field in (table.get("fields") or [])[:7]:
            kind = _ident(str(field.get("type") or "text").split("(")[0], "text")
            key = " PK" if field.get("primary_key") else " FK" if field.get("references") else ""
            lines.append(f"        {kind} {_ident(field.get('name'), 'field')}{key}")
        lines.append("    }")
    for relation in database.get("relationships") or []:
        left = str(relation.get("from") or "").split(".", 1)[0]
        right = str(relation.get("to") or "").split(".", 1)[0]
        if left in names and right in names and left != right:
            link = _LINKS.get(str(relation.get("type") or "").lower(), "||--o{")
            lines.append(f'    {names[left]} {link} {names[right]} : "{_label(relation.get("description"), 40) or "relates to"}"')
    return "\n".join(lines)


_BUILDERS: dict[str, Callable[[dict], str]] = {
    "sequence": _sequence, "activity": _activity, "state_machine": _state_machine, "erd": _erd,
}


def build(kind: str, context: dict) -> str:
    """Mermaid source for this kind from the specification slice, or "" when the kind has no such source of facts."""
    builder = _BUILDERS.get(kind)
    return builder(context if isinstance(context, dict) else {}) if builder else ""
