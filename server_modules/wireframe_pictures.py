"""Save picture layers as ordinary HTML and local image files in a wireframe."""
from __future__ import annotations

import base64
import binascii
import hashlib
import html
import json
import re
import uuid
from pathlib import Path
from typing import Any

_BLOCK = re.compile(r"<!-- agentforge-pictures:start -->(.*?)<!-- agentforge-pictures:end -->", re.S)
_DATA = re.compile(r'<script type="application/json" data-af-picture-data>(.*?)</script>', re.S)
_ASSET = re.compile(r"[a-f0-9]{64}\.(?:png|jpg|webp|gif)")
_ID = re.compile(r"[a-zA-Z0-9_-]{1,64}")
_LIMIT = 8 * 1024 * 1024
_FIELDS = {
    "x": (0, 0, 50000), "y": (0, 0, 50000), "w": (240, 8, 10000), "h": (160, 8, 10000),
    "naturalW": (1, 1, 100000), "naturalH": (1, 1, 100000), "rotation": (0, -360, 360),
    "zoom": (1, 1, 5), "panX": (0, -10000, 10000), "panY": (0, -10000, 10000),
    "radius": (16, 0, 5000), "border": (0, 0, 100), "opacity": (100, 0, 100),
    "shadow": (0, 0, 64), "brightness": (100, 0, 200), "contrast": (100, 0, 200),
    "saturation": (100, 0, 200),
}
_SHAPES = ("rectangle", "square", "rounded", "circle", "ellipse", "triangle")
LAYER_STYLE = "position:absolute;top:0;left:0;width:100%;height:0;pointer-events:none;z-index:100"


def _revision(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _read(source: str) -> list[dict]:
    block = _BLOCK.search(source)
    data = _DATA.search(block[1]) if block else None
    return json.loads(data[1]) if data else []


def read(page: Path) -> dict:
    source = page.read_text(encoding="utf-8")
    return {"pictures": _read(source), "revision": _revision(source)}


def _image_bytes(encoded: Any) -> tuple[bytes, str]:
    if not isinstance(encoded, str) or len(encoded) > (_LIMIT * 4 // 3 + 8):
        raise ValueError("each picture must be 8 MB or smaller")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("could not read the picture data") from exc
    if len(raw) > _LIMIT:
        raise ValueError("each picture must be 8 MB or smaller")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return raw, "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return raw, "jpg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return raw, "gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return raw, "webp"
    raise ValueError("choose a PNG, JPEG, GIF or WebP picture")


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    if type(value) not in (float, int) or not minimum <= value <= maximum:
        return default
    return round(value, 2)


def _picture(value: Any, stored: dict[str, bytes], folder: Path) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not _ID.fullmatch(value["id"]):
        raise ValueError("a picture is missing its ID")
    asset = str(value.get("asset") or "")
    if asset != "placeholder" and (not _ASSET.fullmatch(asset) or (asset not in stored and
                                    (not (folder / asset).is_file() or (folder / asset).is_symlink()))):
        raise ValueError("a picture file is missing")
    picture = {key: _number(value.get(key), *limits) for key, limits in _FIELDS.items()}
    picture["id"] = value["id"]
    picture["asset"] = asset
    picture["name"] = str(value.get("name") or "Picture")[:160]
    picture["alt"] = str(value.get("alt") or "")[:300]
    group = str(value.get("group") or "")
    picture["group"] = group if _ID.fullmatch(group) else ""
    picture["shape"] = value["shape"] if value.get("shape") in _SHAPES else "rectangle"
    picture["fit"] = "fit" if value.get("fit") == "fit" else "fill"
    picture["flipX"] = value.get("flipX") is True
    picture["flipY"] = value.get("flipY") is True
    picture["locked"] = value.get("locked") is True
    color = str(value.get("color") or "")
    picture["color"] = color if re.fullmatch(r"#[A-Fa-f0-9]{6}", color) else "#222222"
    if picture["shape"] in ("square", "circle"):
        picture["h"] = picture["w"]
    return picture


def _geometry(p: dict) -> tuple[str, str]:
    w, h = p["w"], p["h"]
    if p["shape"] == "triangle":
        return "polygon", f'points="{w / 2},0 {w},{h} 0,{h}"'
    if p["shape"] in ("circle", "ellipse"):
        return "ellipse", f'cx="{w / 2}" cy="{h / 2}" rx="{w / 2}" ry="{h / 2}"'
    radius = min(p["radius"], w / 2, h / 2) if p["shape"] == "rounded" else 0
    return "rect", f'width="{w}" height="{h}" rx="{radius}"'


def _render(p: dict) -> str:
    w, h = p["w"], p["h"]
    scale = min if p["fit"] == "fit" else max
    ratio = scale(w / p["naturalW"], h / p["naturalH"]) * p["zoom"]
    iw, ih = p["naturalW"] * ratio, p["naturalH"] * ratio
    tag, geometry = _geometry(p)
    clip = "af-pic-" + p["id"]
    x, y = w / 2 + p["panX"], h / 2 + p["panY"]
    fx, fy = (-1 if p[k] else 1 for k in ("flipX", "flipY"))
    filters = " ".join(f"{f}({p[k]}%)" for f, k in (("brightness", "brightness"), ("contrast", "contrast"),
                                                     ("saturate", "saturation")))
    style = (f'position:absolute;left:{p["x"]}px;top:{p["y"]}px;width:{w}px;height:{h}px;'
             f'transform:rotate({p["rotation"]}deg);opacity:{p["opacity"] / 100};'
             f'filter:drop-shadow(0 {p["shadow"] / 3}px {p["shadow"]}px #0005);overflow:visible')
    label = html.escape(p["alt"] or p["name"], quote=True)
    if p["asset"] == "placeholder":
        size = min(48, min(w, h) * 0.44)
        content = (f'<{tag} {geometry} fill="#e5e5e5"/>'
                   f'<svg x="{(w - size) / 2}" y="{(h - size) / 2}" width="{size}" height="{size}" '
                   'viewBox="0 0 24 24" fill="none" stroke="#737373" stroke-width="1.5" stroke-linejoin="round">'
                   '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/>'
                   '<path d="m3 17 5-4 3 3 4-6 6 7"/></svg>')
    else:
        content = (f'<image href="assets/pictures/{p["asset"]}" '
                   f'x="{-iw / 2}" y="{-ih / 2}" width="{iw}" height="{ih}" preserveAspectRatio="none" '
                   f'transform="translate({x} {y}) scale({fx} {fy})" style="filter:{filters}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{label}" '
            f'data-af-picture="{p["id"]}" viewBox="0 0 {w} {h}" style="{style}">'
            f'<defs><clipPath id="{clip}"><{tag} {geometry}/></clipPath></defs>'
            f'<g clip-path="url(#{clip})">{content}'
            f'<{tag} {geometry} fill="none" stroke="{p["color"]}" stroke-width="{p["border"] * 2}"/></g></svg>')


def save(session, page: Path, body: dict) -> dict:
    with session.lock:
        source = page.read_text(encoding="utf-8")
        if body.get("revision") != _revision(source):
            raise ValueError("the wireframe changed while you were editing. Reopen the picture editor to load the latest page")
        rows = body.get("pictures")
        uploads = body.get("uploads") if isinstance(body.get("uploads"), dict) else {}
        if not isinstance(rows, list) or len(rows) > 100 or len(uploads) > 100:
            raise ValueError("a wireframe page can have up to 100 pictures")
        folder = (page.parent / "assets/pictures").resolve()
        if not folder.is_relative_to(page.parent.resolve()):
            raise ValueError("the picture folder must be inside the wireframe")
        stored: dict[str, bytes] = {}
        mapping = {}
        total = 0
        for key, encoded in uploads.items():
            data, ext = _image_bytes(encoded)
            total += len(data)
            if total > _LIMIT * 4:
                raise ValueError("save up to 32 MB of new pictures at a time")
            asset = f"{hashlib.sha256(data).hexdigest()}.{ext}"
            mapping[key] = asset
            stored[asset] = data
        pictures = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("asset"), str):
                raise ValueError("invalid picture settings")
            picture = _picture({**row, "asset": mapping.get(row["asset"], row["asset"])}, stored, folder)
            if picture["id"] in seen:
                raise ValueError("duplicate picture ID")
            seen.add(picture["id"])
            pictures.append(picture)

        if stored:
            folder.mkdir(parents=True, exist_ok=True)
            for asset, data in stored.items():
                path = folder / asset
                if path.is_symlink():
                    raise ValueError("the picture path must be a local file")
                if not path.exists():
                    temporary = path.with_name(f".{asset}.{uuid.uuid4().hex}.tmp")
                    try:
                        temporary.write_bytes(data)
                        temporary.replace(path)
                    finally:
                        temporary.unlink(missing_ok=True)

        source = _BLOCK.sub("", source)
        if pictures:
            data = json.dumps(pictures, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
            block = ('<!-- agentforge-pictures:start -->'
                     f'<script type="application/json" data-af-picture-data>{data}</script>'
                     f'<div data-af-picture-layer style="{LAYER_STYLE}">{"".join(map(_render, pictures))}</div>'
                     '<!-- agentforge-pictures:end -->')
            end = re.search(r"</body\s*>", source, re.I)
            source = source[:end.start()] + block + source[end.start():] if end else source + block
        session.write_record(*page.relative_to(session.record).parts, data=source)
        return {"pictures": pictures, "revision": _revision(source)}
