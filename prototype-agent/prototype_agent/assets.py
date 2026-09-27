"""Validate and repair model-authored inline prototype images."""
from __future__ import annotations

import base64
import binascii
import re
from xml.etree import ElementTree

_SVG = re.compile(r'src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"')
_COLOR = re.compile(r'((?:fill|stroke)="#)([0-9a-fA-F]+)(")')


def normalize_inline_svg(html: str, design: dict) -> str:
    palette = ((design.get("tokens") or {}).get("light") or
               (design.get("tokens") or {}).get("dark") or {})
    accent = str(palette.get("accent") or "currentColor")

    def repair(match: re.Match) -> str:
        try:
            svg = base64.b64decode(match.group(1), validate=True).decode("utf-8")
            svg = svg.replace('""', '"')
            svg = _COLOR.sub(lambda color: color.group(0) if len(color.group(2)) in {3, 4, 6, 8}
                             else f'{color.group(1)}{accent.lstrip("#")}{color.group(3)}'
                             if accent.startswith("#") else f'{color.group(1)}888888{color.group(3)}', svg)
            ElementTree.fromstring(svg)
        except (ValueError, UnicodeError, binascii.Error, ElementTree.ParseError):
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 180">'
                   f'<rect width="300" height="180" fill="{accent}"/></svg>')
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f'src="data:image/svg+xml;base64,{encoded}"'

    return _SVG.sub(repair, html)
