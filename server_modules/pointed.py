"""What the customer pointed at on a page, put into words for the agent.

The Studio's select and pencil tools pick things out of the framed app (`studio/lib/picker.js`): each is a small record of the element
(its tag, the words in it, its address in the page, a piece of its markup). A model that is only sent words cannot see a record, so a
change that came with some is told, in the request, what they were.
"""
from __future__ import annotations

import json
from typing import Any

MOST = 6
TEXT = 120
HTML = 320
ATTRIBUTES = ("href", "type", "placeholder", "name", "alt", "aria-label", "role")


def _one(number: int, element: dict[str, Any]) -> str:
    tag = str(element.get("tag") or "element").strip() or "element"
    text = " ".join(str(element.get("text") or "").split())[:TEXT]
    head = f"{number}. `<{tag}>`" + (f" with the words “{text}”" if text else "")
    route = str(element.get("route") or "").strip()
    if route:
        head += f", on the page `{route}`"
    lines = [head]
    attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
    shown = [f'{key}="{str(attrs[key])[:80]}"' for key in ATTRIBUTES if attrs.get(key)]
    if shown:
        lines.append("   attributes: " + ", ".join(shown))
    inside = []
    for parent in reversed((element.get("chain") or [])[:3]):
        if isinstance(parent, dict) and parent.get("tag"):
            words = " ".join(str(parent.get("text") or "").split())[:50]
            inside.append(f"<{parent['tag']}>" + (f" “{words}”" if words else ""))
    if inside:
        lines.append("   inside: " + " › ".join(inside))
    html = " ".join(str(element.get("outerHTML") or "").split())[:HTML]
    if html:
        lines.append(f"   markup: `{html}`")
    return "\n".join(lines)


def describe(elements: Any) -> str:
    """The pointed-at elements as a paragraph to put after the request, or "" when there are none."""
    rows = [e for e in (elements if isinstance(elements, list) else []) if isinstance(e, dict)][:MOST]
    if not rows:
        return ""
    return ("\n\nThey pointed at " + ("this" if len(rows) == 1 else "these") + " on the page (find it in the app's files by its words "
            "and its markup):\n" + "\n".join(_one(n, e) for n, e in enumerate(rows, 1)))


def move_details(move: Any) -> str:
    """Describe the browser's selected element and drop target without accepting an edit prompt."""
    if not isinstance(move, dict) or move.get("placement") not in ("before", "after", "inside"):
        raise ValueError("choose where to drop the element")
    details = {"placement": move["placement"], "source": _layout_element(move.get("source")),
               "target": _layout_element(move.get("target"))}
    if details["source"]["selector"] == details["target"]["selector"]:
        raise ValueError("drop the element at a different location")
    details["pointer"] = _geometry(move.get("point"), ("x", "y"))
    details["desired_top_left"] = _geometry(move.get("origin"), ("x", "y"))
    details["scroll"] = _geometry(move["source"].get("scroll"), ("x", "y"))
    details["viewport"] = _geometry(move["source"].get("viewport"), ("w", "h"))
    return json.dumps(details, ensure_ascii=False)


def resize_details(resize: Any) -> str:
    if not isinstance(resize, dict) or resize.get("handle") not in ("n", "ne", "e", "se", "s", "sw", "w", "nw"):
        raise ValueError("resize the element with an edge or corner handle")
    source = _layout_element(resize.get("source"))
    bounds = _geometry(resize.get("bounds"), ("x", "y", "w", "h"))
    original = source["rect"]
    if any(len(rect) != 4 or rect["w"] < 1 or rect["h"] < 1 for rect in (original, bounds)):
        raise ValueError("supply valid original and resized dimensions")
    if (original["w"], original["h"]) == (bounds["w"], bounds["h"]):
        raise ValueError("the element size did not change")

    element = resize["source"]
    return json.dumps({
        "handle": resize["handle"], "source": source, "bounds": bounds,
        "viewport": _geometry(element.get("viewport"), ("w", "h")),
        "scroll": _geometry(element.get("scroll"), ("x", "y")),
    }, ensure_ascii=False)


def combined_layout_details(layout: Any) -> str:
    if not isinstance(layout, dict):
        raise ValueError("include a position and size change")
    move = json.loads(move_details(layout.get("move")))
    resize = json.loads(resize_details(layout.get("resize")))
    if move["source"]["selector"] != resize["source"]["selector"]:
        raise ValueError("move and resize the same element before saving")
    return json.dumps({"move": move, "resize": resize}, ensure_ascii=False)


def insert_details(insert: Any) -> str:
    if not isinstance(insert, dict) or insert.get("shape") not in ("rectangle", "ellipse", "textbox"):
        raise ValueError("choose a wireframe shape or text box")
    bounds = _geometry(insert.get("bounds"), ("x", "y", "w", "h"))
    if len(bounds) != 4 or bounds["w"] < 1 or bounds["h"] < 1:
        raise ValueError("draw a box on the wireframe before saving")
    text = insert.get("text", "")
    if insert["shape"] == "textbox" and (not isinstance(text, str) or not text.strip() or len(text) > 300):
        raise ValueError("enter up to 300 characters for the text box")
    target = _layout_element(insert.get("target"))
    scroll = _geometry(insert.get("scroll"), ("x", "y"))
    details = {
        "shape": insert["shape"], "text": text if insert["shape"] == "textbox" else "",
        "target": target, "bounds": bounds, "scroll": scroll,
        "viewport": _geometry(insert.get("viewport"), ("w", "h")),
    }
    if "x" in target["rect"] and "y" in target["rect"]:
        details["offset_within_target"] = {axis: bounds[axis] - target["rect"][axis] - scroll.get(axis, 0)
                                            for axis in ("x", "y")}
    return json.dumps(details, ensure_ascii=False)


def _layout_element(element: Any) -> dict[str, Any]:
    if not isinstance(element, dict) or not isinstance(element.get("selector"), str) or not element["selector"].strip():
        raise ValueError("identify the element in the preview")
    return {"selector": element["selector"][:1200], "element": _one(1, element),
            "rect": _geometry(element.get("rect"), ("x", "y", "w", "h"))}


def _geometry(value: Any, keys: tuple[str, ...]) -> dict[str, int]:
    return {key: round(number) for key in keys
            if isinstance(value, dict) and type(number := value.get(key)) in (int, float) and abs(number) < 1_000_000}
