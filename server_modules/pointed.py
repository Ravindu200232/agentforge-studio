"""What the customer pointed at on a page, put into words for the agent.

The Studio's select and pencil tools pick things out of the framed app (`studio/lib/picker.js`): each is a small record of the element
(its tag, the words in it, its address in the page, a piece of its markup). A model that is only sent words cannot see a record, so a
change that came with some is told, in the request, what they were.
"""
from __future__ import annotations

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
