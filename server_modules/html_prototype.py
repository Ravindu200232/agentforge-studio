"""Publish authored HTML, CSS and JavaScript as one offline prototype preview."""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote

MANIFEST = "preview.json"
PARTIAL = "partial.html"
RUNTIME = Path(__file__).with_name("scripts") / "html-prototype.js"
_ASSETS = ("assets/prototype.css", "assets/prototype.js")
_IMAGE = re.compile(r"(?<![\w/])(?:\./)?(assets/uploads/[^\"'<>\n)]+)")


def sources(app: Path):
    yield app / "index.html"
    yield app / MANIFEST
    for folder in ("pages", "assets"):
        yield from sorted(path for path in (app / folder).rglob("*") if path.is_file())


def missing(app: Path, rows: list[dict]) -> list[str]:
    absent = [name for name in ("index.html", *_ASSETS) if not (app / name).is_file()]
    return absent + [row["route"] for row in rows if not (app / row["file"].removeprefix("app/")).is_file()]


def published_routes(app: Path) -> list[str]:
    try:
        record = json.loads((app / MANIFEST).read_text(encoding="utf-8"))
        return [row["route"] for row in record["routes"] if (app / row["file"].removeprefix("app/")).is_file()]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def publish_partial(app: Path) -> Path:
    preview = app / PARTIAL
    pending = preview.with_suffix(".tmp")
    try:
        pending.write_text(compose(app, partial=True), encoding="utf-8")
        pending.replace(preview)
    finally:
        pending.unlink(missing_ok=True)
    return preview


def compose(app: Path, *, partial: bool = False) -> str:
    """Inline the authored screens and assets, plus the Studio's preview navigation runtime."""
    root = app.resolve()
    record = json.loads((app / MANIFEST).read_text(encoding="utf-8"))
    rows = record["routes"]
    absent = missing(app, [] if partial else rows)
    if absent:
        raise ValueError("missing HTML prototype files: " + ", ".join(absent))

    urls = {}
    for file in (app / "assets" / "uploads").glob("*"):
        mime = mimetypes.guess_type(file.name)[0] or ""
        if file.is_file() and file.resolve().is_relative_to(root) and mime.startswith("image/"):
            uri = f"data:{mime};base64," + base64.b64encode(file.read_bytes()).decode("ascii")
            urls[f"assets/uploads/{file.name}"] = urls[f"assets/uploads/{quote(file.name)}"] = uri

    def read(relative: str) -> str:
        file = (root / relative).resolve()
        if not file.is_relative_to(root):
            raise ValueError(f"HTML prototype path leaves the application: {relative}")
        return _IMAGE.sub(lambda hit: urls.get(hit[1], hit[0]), file.read_text(encoding="utf-8"))

    index = read("index.html")
    if not re.search(r"\bid\s*=\s*(['\"])af-page\1", index, re.IGNORECASE):
        raise ValueError('index.html must contain a page mount with id="af-page"')
    screens = []
    for row in rows:
        relative = row["file"].removeprefix("app/")
        pending = partial and not (app / relative).is_file()
        screens.append({**row, "pending": pending, "markup": "" if pending else read(relative)})
    payload = json.dumps({**record, "routes": screens}, ensure_ascii=True).replace("<", "\\u003c")
    css = f"<style>{read(_ASSETS[0])}</style>"
    script = re.sub(r"</script", r"<\\/script", read(_ASSETS[1]), flags=re.IGNORECASE)
    insertion = (f"<script>window.__afPreview = {payload};\n{RUNTIME.read_text(encoding='utf-8')}\n</script>"
                 f"<script>{script}</script>")
    head = re.search(r"</head\s*>", index, re.IGNORECASE)
    index = index[:head.start()] + css + index[head.start():] if head else css + index
    end = re.search(r"</body\s*>", index, re.IGNORECASE)
    return index[:end.start()] + insertion + index[end.start():] if end else index + insertion
