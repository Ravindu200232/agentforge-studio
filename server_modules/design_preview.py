"""Apply a theme to a disposable copy of the project's home wireframe."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

from . import web_app

_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_FONT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .-]{0,79}")
_HEAD_END = re.compile(rb"</head\s*>", re.IGNORECASE)
_STYLE = Path(__file__).with_name("assets") / "design-preview.css"
_POLICY = web_app.HTML_POLICY.replace("style-src 'self' 'unsafe-inline'",
                                     "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com").replace(
    "font-src data:;", "font-src data: https://fonts.gstatic.com;")


def home_row(pages: list[dict]) -> dict | None:
    by_route = {row["route"]: row for row in pages}
    public = [row for row in pages if not row["signedIn"]]
    return by_route.get("/") or by_route.get("/home") or (public[0] if public else None)


def _foreground(color: str) -> str:
    rgb = [int(color[start:start + 2], 16) / 255 for start in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb]
    luminance = sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#000000" if luminance > 0.179 else "#ffffff"


def render(source: bytes, colors: list[str], heading: str, body: str) -> bytes:
    if len(colors) != 4 or not all(_HEX.fullmatch(color) for color in colors):
        raise ValueError("Choose four valid hex colours before testing the design.")
    if not _FONT.fullmatch(heading) or not _FONT.fullmatch(body):
        raise ValueError("Choose a valid heading font and body font before testing the design.")

    primary, secondary, accent, surface = colors
    families = list(dict.fromkeys((heading, body)))
    url = urlencode({"family": families, "display": "swap"}, doseq=True).replace("&", "&amp;")
    additions = (f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{url}">\n'
                 '<style id="agentforge-theme">:root{'
                 f'--af-primary:{primary};--af-secondary:{secondary};--af-accent:{accent};--af-surface:{surface};'
                 f'--af-on-primary:{_foreground(primary)};--af-heading-font:"{heading}";--af-body-font:"{body}";'
                 '}\n' + _STYLE.read_text(encoding="utf-8") + '\n</style>').encode("utf-8")
    end = _HEAD_END.search(source)
    page = source[:end.start()] + additions + source[end.start():] if end else additions + source
    return web_app.preview_page(page, _POLICY)
