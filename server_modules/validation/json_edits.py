"""Small, exact edits to a JSON document, so a repair changes only what is wrong.

A model fixing one finding used to return the whole document again: slow, and every
untouched part was one more chance to lose something that was right. Instead it returns
edits, applied here:

    {"op": "set",    "path": "functional_requirements[id=FR-012].requirement", "value": "The system shall ..."}
    {"op": "add",    "path": "requirement_traceability_matrix", "value": {"requirement_id": "FR-031", ...}}
    {"op": "remove", "path": "protected_pages[route=/old]"}

A path is dot-separated keys. A list item is picked by one of its own fields (`[id=FR-012]`,
`[route=/admin]`, `[table_name=orders]`) or, when it has none, by position (`[3]`). `add`
appends to the list the path names. Every problem is reported with the edit it came from, so
the model can correct exactly that edit.
"""
from __future__ import annotations

import copy
import re
from typing import Any

_PART = re.compile(r"^(?P<name>[A-Za-z_][\w-]*)?(?:\[(?P<select>[^\]]*)\])?$")


class EditError(ValueError):
    pass


def _parts(path: str) -> list[tuple[str, str | None]]:
    text = str(path or "").strip().lstrip(".")
    text = re.sub(r"^srs_document\.", "", text)
    parts, current, depth = [], "", 0
    for char in text:
        depth += char == "["
        depth -= char == "]"
        if char == "." and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    out = []
    for part in parts:
        match = _PART.match(part.strip())
        if not part.strip() or not match or not (match.group("name") or match.group("select") is not None):
            raise EditError(f"`{path}` is not a path like `functional_requirements[id=FR-012].requirement`")
        out.append((match.group("name") or "", match.group("select")))
    return out


def _pick(items: list, select: str, where: str) -> int:
    select = select.strip()
    if re.fullmatch(r"-?\d+", select):
        index = int(select)
        if not -len(items) <= index < len(items):
            raise EditError(f"{where} has {len(items)} items, so there is no item [{select}]")
        return index % len(items)
    key, _, value = select.partition("=")
    key, value = key.strip(), value.strip().strip("\"'")
    if not key or not _:
        raise EditError(f"[{select}] in {where} must be [field=value] or a position like [0]")
    found = [i for i, item in enumerate(items) if isinstance(item, dict) and str(item.get(key, "")).strip() == value]
    if not found:
        raise EditError(f"no item in {where} has {key}={value}")
    if len(found) > 1:
        raise EditError(f"{len(found)} items in {where} have {key}={value}; pick one by position instead")
    return found[0]


def _locate(document: dict, path: str, create: bool) -> tuple[Any, Any]:
    """The container that holds what `path` names, and its key or index in that container."""
    parts = _parts(path)
    node: Any = document
    where = "the document"
    for number, (name, select) in enumerate(parts):
        last = number == len(parts) - 1
        if name:
            if not isinstance(node, dict):
                raise EditError(f"{where} is not an object, so it has no `{name}`")
            if select is None and last:
                return node, name
            if name not in node:
                if not create or select is not None:
                    raise EditError(f"{where} has no `{name}`")
                node[name] = {}
            node, where = node[name], name
        if select is not None:
            if not isinstance(node, list):
                raise EditError(f"`{where}` is not a list, so [{select}] picks nothing")
            index = _pick(node, select, where)
            if last:
                return node, index
            node, where = node[index], f"{where}[{select}]"
    raise EditError(f"`{path}` names nothing")


def apply_edits(document: dict, edits: Any) -> dict:
    """A copy of `document` with every edit applied; raises `EditError` listing each edit that does not fit."""
    if isinstance(edits, dict):
        edits = edits.get("edits")
    if not isinstance(edits, list) or not edits:
        raise EditError('return {"edits": [ ... ]} with at least one edit')
    out = copy.deepcopy(document)
    problems = []
    for number, edit in enumerate(edits, 1):
        label = f"edit {number}"
        try:
            if not isinstance(edit, dict):
                raise EditError("each edit is an object with `op` and `path`")
            op, path = str(edit.get("op") or "").strip().lower(), str(edit.get("path") or "")
            label = f"edit {number} ({op} {path})"
            if op == "set":
                if "value" not in edit:
                    raise EditError("`set` needs a `value`")
                container, key = _locate(out, path, create=True)
                container[key] = edit["value"]
            elif op == "add":
                if "value" not in edit:
                    raise EditError("`add` needs a `value`")
                container, key = _locate(out, path, create=True)
                target = container.setdefault(key, []) if isinstance(container, dict) else container[key]
                if not isinstance(target, list):
                    raise EditError("`add` appends to a list; use `set` to change a single value")
                target.append(edit["value"])
            elif op == "remove":
                container, key = _locate(out, path, create=False)
                if isinstance(container, dict) and key not in container:
                    raise EditError(f"there is no `{key}` to remove")
                del container[key]
            else:
                raise EditError("`op` must be set, add or remove")
        except EditError as exc:
            problems.append(f"{label}: {exc}")
    if problems:
        raise EditError("these edits could not be applied:\n- " + "\n- ".join(problems[:20]))
    return out
