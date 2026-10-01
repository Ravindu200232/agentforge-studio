"""Rendering a diagram to SVG.

The studio's diagram viewer injects an SVG string; a `.mmd` source alone shows a
file path where a picture should be. Mermaid's own CLI is the renderer, found
once and reused. When it is not installed the source is still written and the
diagram is marked unrendered, which is a diagram you can copy rather than one
that silently is not there.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()
# Without this every mmdc/npx/Chromium launch flashes a console window on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_cli: list[str] | None | bool = False   # False = not looked for yet

# Mermaid needs a browser; on a headless machine it needs to be told it may run
# without a sandbox. Written next to the call rather than into the project.
_PUPPETEER = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
_STUDIO_ROOT = Path(__file__).resolve().parents[1] / "studio"

# Mermaid cannot reproduce every Visual Paradigm primitive (for example a
# stick actor or a 3-D deployment node), but this shared rendering contract
# keeps every supported approximation readable and recognisably technical:
# white canvas, pale blue figures, dark connectors, familiar UML typography,
# and enough space to inspect the notation.  Diagram-specific source still
# supplies the UML/BPMN/DFD semantics.
_VISUAL_CONFIG = {
    "theme": "base",
    "themeVariables": {
        "background": "#ffffff",
        "fontFamily": "Arial, Helvetica, sans-serif",
        "fontSize": "16px",
        "primaryColor": "#75c5e8",
        "primaryTextColor": "#102a43",
        "primaryBorderColor": "#1f2937",
        "secondaryColor": "#eef8fc",
        "secondaryTextColor": "#102a43",
        "secondaryBorderColor": "#334155",
        "tertiaryColor": "#ffffff",
        "tertiaryTextColor": "#102a43",
        "tertiaryBorderColor": "#64748b",
        "lineColor": "#1f2937",
        "clusterBkg": "#eef8fc",
        "clusterBorder": "#75c5e8",
        "edgeLabelBackground": "#ffffff",
        "actorBkg": "#75c5e8",
        "actorBorder": "#1f2937",
        "actorTextColor": "#102a43",
        "activationBkgColor": "#8fd3ee",
        "activationBorderColor": "#1f2937",
        "noteBkgColor": "#fff8c5",
        "noteBorderColor": "#64748b",
    },
    "flowchart": {"htmlLabels": True, "nodeSpacing": 58, "rankSpacing": 76,
                  "padding": 16, "curve": "basis"},
    "sequence": {"useMaxWidth": False, "wrap": True, "diagramMarginX": 28,
                 "diagramMarginY": 20, "actorMargin": 56, "messageMargin": 44,
                 "noteMargin": 14},
    "class": {"useMaxWidth": False},
    "er": {"useMaxWidth": False},
}


def _node_binaries() -> list[str]:
    """Find Node without assuming the desktop app inherited a shell PATH.

    The Studio packages Mermaid CLI with its front-end dependencies.  Desktop
    launches do not necessarily inherit the developer's PATH, while Codex and
    the packaged app can provide Node beside the Python runtime.  Prefer an
    explicit override, then PATH, then that sibling runtime location.
    """
    candidates: list[Path | str | None] = [
        os.environ.get("AGENTFORGE_NODE_BINARY"),
        shutil.which("node") or shutil.which("node.exe"),
    ]
    try:
        runtime = Path(sys.executable).resolve().parent.parent
        candidates.extend((runtime / "node" / "bin" / "node.exe",
                           runtime / "node" / "bin" / "node"))
    except OSError:
        pass

    found: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and str(path) not in found:
            found.append(str(path))
    return found


def _installed_browser() -> str | None:
    """Use Puppeteer's browser when present, otherwise a system Chrome/Edge."""
    candidates = [
        Path(os.environ.get("PUPPETEER_EXECUTABLE_PATH", "")),
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            return str(candidate)
    return None


def _find_cli() -> list[str] | None:
    """The first mermaid-cli invocation that actually works, or None."""
    global _cli
    with _lock:
        if _cli is not False:
            return _cli  # type: ignore[return-value]
        _cli = None
        candidates: list[list[str]] = []
        local_cli = (_STUDIO_ROOT / "node_modules" / "@mermaid-js"
                     / "mermaid-cli" / "src" / "cli.js")
        if local_cli.is_file():
            candidates.extend([[node, str(local_cli)] for node in _node_binaries()])
        for name in ("mmdc", "mmdc.cmd"):
            found = shutil.which(name)
            if found:
                candidates.append([found])
        for candidate in candidates:
            try:
                probe = subprocess.run([*candidate, "--version"], capture_output=True,
                                       text=True, timeout=180, check=False,
                                       cwd=str(_STUDIO_ROOT), creationflags=_NO_WINDOW)
                if probe.returncode == 0:
                    _cli = candidate
                    break
            except (OSError, subprocess.SubprocessError):
                continue
        return _cli  # type: ignore[return-value]


def available() -> bool:
    return _find_cli() is not None


def render(source: str, out_path: Path, timeout: int = 180) -> tuple[bool, str]:
    """Draw one Mermaid source to `out_path`.

    Returns whether an SVG landed and, when it did not, what Mermaid said about
    it. That message is the only reliable parser there is — a hand-written
    syntax check passes `Member --> (Login)`, which Mermaid rejects — so it goes
    back to the model as the repair instruction.
    """
    cli = _find_cli()
    if not cli:
        return False, "no mermaid renderer is installed"
    if not str(source or "").strip():
        return False, "the source is empty"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        mmd = work / "diagram.mmd"
        mmd.write_text(source, encoding="utf-8")
        config = work / "puppeteer.json"
        visual_config = work / "mermaid.json"
        puppeteer_config = dict(_PUPPETEER)
        browser = _installed_browser()
        if browser:
            puppeteer_config["executablePath"] = browser
        config.write_text(json.dumps(puppeteer_config), encoding="utf-8")
        visual_config.write_text(json.dumps(_VISUAL_CONFIG), encoding="utf-8")
        try:
            done = subprocess.run(
                [*cli, "-i", str(mmd), "-o", str(out_path), "-b", "white",
                 "-c", str(visual_config), "-p", str(config)],
                capture_output=True, text=True, timeout=timeout, check=False,
                cwd=str(_STUDIO_ROOT), creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            return False, f"the renderer timed out after {timeout}s"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"the renderer could not run: {exc}"
        if done.returncode != 0 or not out_path.is_file():
            noise = ((done.stderr or "") + "\n" + (done.stdout or "")).strip()
            return False, _readable_error(noise)
    return (out_path.stat().st_size > 0, "")


_UC_NODE = re.compile(r'^\s*(\w+)\s*\(\[\s*"?([^"\]]+?)"?\s*\]\)')
_UC_ACTOR = re.compile(r'^\s*(\w+)\s*\[/\s*"?([^"/]+?)"?\s*/\]')
_UC_BOUNDARY = re.compile(r'subgraph\s+\w+\s*\[\s*"?([^\]"]+?)"?\s*\]')
_UC_ASSOC = re.compile(r'^\s*(\w+)\s*---\s*(\w+)\s*$')
_UC_DASHED = re.compile(r'^\s*(\w+)\s*-\.->\s*\|\s*"?([^|"]+?)"?\s*\|\s*(\w+)')
_UC_LABELED = re.compile(r'^\s*(\w+)\s*-->\s*\|\s*"?([^|"]+?)"?\s*\|\s*(\w+)')


def _uc_actor_svg(x: float, y: float) -> str:
    return (f'<circle cx="{x}" cy="{y - 22}" r="10" fill="#75c5e8" stroke="#111827" stroke-width="1.8"/>'
            f'<path d="M{x} {y - 12}V{y + 24}M{x - 20} {y}H{x + 20}M{x} {y + 24}L{x - 18} {y + 48}'
            f'M{x} {y + 24}L{x + 18} {y + 48}" fill="none" stroke="#111827" stroke-width="1.8" stroke-linecap="round"/>')


def _render_use_case_svg(source: str, out_path: Path) -> bool:
    """Real stick-figure actors, true ovals and a named system boundary - the
    UML use-case primitives Mermaid has no native shape for at all."""
    text = str(source or "")
    boundary = "System"
    hit = _UC_BOUNDARY.search(text)
    if hit:
        boundary = hit.group(1).strip()

    use_cases: dict[str, str] = {}
    actors: dict[str, str] = {}
    for line in text.splitlines():
        m = _UC_NODE.match(line)
        if m:
            use_cases[m.group(1)] = m.group(2).strip()
            continue
        m = _UC_ACTOR.match(line)
        if m:
            actors[m.group(1)] = m.group(2).strip()

    if not use_cases or not actors:
        return False

    assoc: list[tuple[str, str]] = []
    dashed: list[tuple[str, str, str]] = []
    labeled: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        m = _UC_DASHED.match(line)
        if m:
            dashed.append((m.group(1), m.group(2).strip(), m.group(3)))
            continue
        m = _UC_LABELED.match(line)
        if m:
            labeled.append((m.group(1), m.group(2).strip(), m.group(3)))
            continue
        m = _UC_ASSOC.match(line)
        if m and (m.group(1) in actors or m.group(2) in actors):
            assoc.append((m.group(1), m.group(2)))

    # A primary/human actor sits on the left, like the reference's Customer and
    # Cellular Phone; an actor that reads as an external system sits on the
    # right, like the reference's External Phone Company.
    external_hint = re.compile(r"\b(external|company|provider|gateway|service|system|api|bureau|agency|network)\b",
                               re.IGNORECASE)
    left_actors = [a for a in actors if not external_hint.search(actors[a])]
    right_actors = [a for a in actors if external_hint.search(actors[a])]
    if not left_actors or not right_actors:
        names = list(actors)
        mid = max(1, len(names) // 2)
        left_actors, right_actors = names[:mid], names[mid:]

    # Dense stakeholder maps remain readable as a two-column use-case grid,
    # matching the visual hierarchy of the supplied UML reference instead of
    # becoming one very tall stack of ovals.
    uc_columns = 2 if len(use_cases) > 7 else 1
    uc_rows = (len(use_cases) + uc_columns - 1) // uc_columns
    rows = max(uc_rows, len(left_actors), len(right_actors), 1)
    width = 1840 if uc_columns == 2 else 1440
    height = max(650, 200 + rows * 130)
    bound_w = 980 if uc_columns == 2 else 480
    bound_x = (width - bound_w) / 2
    bound_y, bound_h = 80, height - 160
    left_x, right_x = 170, width - 170

    def row_y(index: int, total: int) -> float:
        return height / 2 if total <= 1 else bound_y + 60 + index * ((bound_h - 120) / max(total - 1, 1))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<defs><marker id="uc_arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#111827"/></marker><marker id="uc_generalization" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1L11 6L1 11Z" fill="#ffffff" stroke="#111827" stroke-width="1.4"/></marker></defs>',
           f'<rect width="{width}" height="{height}" fill="#fff"/>',
           f'<rect x="{bound_x}" y="{bound_y}" width="{bound_w}" height="{bound_h}" fill="#75c5e8" stroke="#111827" stroke-width="2"/>',
           _context_text(bound_x + bound_w / 2, bound_y + 24, boundary, 16, "700")]

    uc_pos: dict[str, tuple[float, float]] = {}
    uc_size: dict[str, tuple[float, float]] = {}
    for i, (node, label) in enumerate(use_cases.items()):
        col, row = divmod(i, uc_rows)
        cx = bound_x + (col + 0.5) * bound_w / uc_columns
        cy = row_y(row, uc_rows) + 20
        rx, ry = min(190, bound_w / uc_columns / 2 - 38), 34
        uc_pos[node] = (cx, cy)
        uc_size[node] = (rx, ry)
        svg.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#75c5e8" stroke="#111827" stroke-width="1.6"/>')
        svg.append(_context_text(cx, cy, label, 14, "600"))

    actor_pos: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(left_actors):
        linked = [uc_pos[b][1] for a, b in assoc if a == node and b in uc_pos]
        x, y = left_x, (sum(linked) / len(linked) if linked else row_y(i, len(left_actors)) + 20)
        actor_pos[node] = (x, y)
        svg.append(_uc_actor_svg(x, y))
        svg.append(_context_text(x, y + 68, actors[node], 14))
    for i, node in enumerate(right_actors):
        linked = [uc_pos[b][1] for a, b in assoc if a == node and b in uc_pos]
        x, y = right_x, (sum(linked) / len(linked) if linked else row_y(i, len(right_actors)) + 20)
        actor_pos[node] = (x, y)
        svg.append(_uc_actor_svg(x, y))
        svg.append(_context_text(x, y + 68, actors[node], 14))

    def uc_connector(start_node: str, end_node: str) -> tuple[float, float, float, float]:
        """Join two ovals at their borders, never through their labels."""
        sx, sy = uc_pos[start_node]
        ex, ey = uc_pos[end_node]
        dx, dy = ex - sx, ey - sy
        if dx == 0 and dy == 0:
            return sx, sy, ex, ey
        sr_x, sr_y = uc_size[start_node]
        er_x, er_y = uc_size[end_node]
        start_scale = 1 / max(((dx / sr_x) ** 2 + (dy / sr_y) ** 2) ** 0.5, 1e-6)
        end_scale = 1 / max(((dx / er_x) ** 2 + (dy / er_y) ** 2) ** 0.5, 1e-6)
        return sx + dx * start_scale, sy + dy * start_scale, ex - dx * end_scale, ey - dy * end_scale

    for a, b in assoc:
        start = actor_pos.get(a) or uc_pos.get(a)
        end = actor_pos.get(b) or uc_pos.get(b)
        if not start or not end:
            continue
        x1, y1, x2, y2 = start[0], start[1], end[0], end[1]
        if a in actor_pos and b in uc_pos:
            x1 += 26 if x1 < x2 else -26
            x2 += -uc_size[b][0] if x1 < x2 else uc_size[b][0]
        elif a in uc_pos and b in actor_pos:
            x1 += uc_size[a][0] if x1 < x2 else -uc_size[a][0]
            x2 += -26 if x1 < x2 else 26
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#111827" stroke-width="1.4"/>')

    for a, label, b in dashed:
        start, end = uc_pos.get(a), uc_pos.get(b)
        if not start or not end:
            continue
        display_label = label.replace("<<", "«").replace(">>", "»")
        mid_x, mid_y = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - 14
        x1, y1, x2, y2 = uc_connector(a, b)
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                   f'stroke="#111827" stroke-width="1.4" stroke-dasharray="6,4" marker-end="url(#uc_arrow)"/>')
        svg.append(f'<rect x="{mid_x - 60}" y="{mid_y - 12}" width="120" height="18" fill="#fff"/>')
        svg.append(_context_text(mid_x, mid_y, display_label, 11))

    for a, label, b in labeled:
        start, end = actor_pos.get(a), actor_pos.get(b)
        if start and end and label.lower().replace(" ", "") in {"isa", "generalizes"}:
            svg.append(f'<line x1="{start[0]}" y1="{start[1]}" x2="{end[0]}" y2="{end[1]}" '
                       'stroke="#111827" stroke-width="1.4" marker-end="url(#uc_generalization)"/>')
            continue
        start, end = uc_pos.get(a), uc_pos.get(b)
        if not start or not end:
            continue
        display_label = label.replace("<<", "«").replace(">>", "»")
        mid_x, mid_y = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - 14
        x1, y1, x2, y2 = uc_connector(a, b)
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                   f'stroke="#111827" stroke-width="1.4" stroke-dasharray="6,4" marker-end="url(#uc_arrow)"/>')
        svg.append(f'<rect x="{mid_x - 60}" y="{mid_y - 12}" width="120" height="18" fill="#fff"/>')
        svg.append(_context_text(mid_x, mid_y, display_label, 11))

    svg.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(svg), encoding="utf-8")
    return True


_DEP_SUBGRAPH_START = re.compile(r'subgraph\s+(\w+)\s*\[\s*"?([^\]"]+?)"?\s*\]')
_DEP_NODE = re.compile(r'^\s*(\w+)\s*\[\s*"([^"]+)"\s*\]')
_DEP_DEPLOY = re.compile(r'^\s*(\w+)\s*-\.->\s*\|\s*"?\s*<<deploy>>\s*"?\s*\|\s*(\w+)', re.IGNORECASE)
_DEP_LINK = re.compile(r'^\s*(\w+)\s*(?:---|-->)\s*(?:\|[^|]*\|\s*)?(\w+)\s*$')
_DEP_STEREOTYPE = re.compile(r'^\s*<<([^>]+)>>\s*(?:\\n|\n)\s*(.+)$', re.IGNORECASE | re.DOTALL)


def _dep_box_svg(x: float, y: float, w: float, h: float, fill: str, threed: bool) -> list[str]:
    """A plain box, or the reference's 3-D processor/device box (a top and a
    side face offset by a small skew) - Mermaid has no such primitive at all."""
    if not threed:
        return [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="#111827" stroke-width="1.6"/>']
    d = 14
    return [
        f'<polygon points="{x},{y} {x + d},{y - d} {x + w + d},{y - d} {x + w},{y}" fill="{fill}" stroke="#111827" stroke-width="1.4"/>',
        f'<polygon points="{x + w},{y} {x + w + d},{y - d} {x + w + d},{y + h - d} {x + w},{y + h}" fill="{fill}" stroke="#111827" stroke-width="1.4" opacity="0.75"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="#111827" stroke-width="1.6"/>',
    ]


def _dep_artifact_svg(x: float, y: float, w: float, h: float) -> list[str]:
    """The reference's dog-eared page icon for an `<<artifact>>` node."""
    fold = 12
    return [
        f'<path d="M{x} {y}H{x + w - fold}L{x + w} {y + fold}V{y + h}H{x}Z" fill="#eef8fc" stroke="#111827" stroke-width="1.4"/>',
        f'<path d="M{x + w - fold} {y}V{y + fold}H{x + w}" fill="none" stroke="#111827" stroke-width="1.2"/>',
    ]


def _render_deployment_svg(source: str, out_path: Path) -> bool:
    """Real 3-D processor/device boxes and page-icon artifacts joined by a
    dashed `<<deploy>>` arrow - the reference's defining deployment notation,
    which Mermaid's flowchart shapes cannot approximate at all."""
    text = str(source or "")
    boundaries: list[tuple[str, str, list[str]]] = []
    stack: list[tuple[str, str, list[str]]] = []
    nodes: dict[str, tuple[str, str]] = {}  # id -> (stereotype or "", name)
    free_nodes: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("end"):
            if stack:
                boundaries.append(stack.pop())
            continue
        hit = _DEP_SUBGRAPH_START.search(line)
        if hit:
            stack.append((hit.group(1), hit.group(2).strip(), []))
            continue
        hit = _DEP_NODE.match(line)
        if hit:
            node_id, label = hit.group(1), hit.group(2)
            stereo_hit = _DEP_STEREOTYPE.match(label)
            stereotype, name = (stereo_hit.group(1).strip(), stereo_hit.group(2).strip()) if stereo_hit else ("", label.strip())
            nodes[node_id] = (stereotype, name)
            if stack:
                stack[-1][2].append(node_id)
            else:
                free_nodes.append(node_id)
    while stack:
        boundaries.append(stack.pop())
    if not nodes:
        return False

    deploys: list[tuple[str, str]] = []
    links: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        hit = _DEP_DEPLOY.match(line)
        if hit:
            deploys.append((hit.group(1), hit.group(2)))
            continue
        hit = _DEP_LINK.match(line)
        if hit and hit.group(1) in nodes and hit.group(2) in nodes:
            links.append((hit.group(1), hit.group(2)))

    artifacts = [n for n in free_nodes if "artifact" in nodes[n][0].lower()] or \
                [n for n in nodes if "artifact" in nodes[n][0].lower() and n not in sum((b[2] for b in boundaries), [])]
    boundaries = [(bid, name, [n for n in members if n not in artifacts]) for bid, name, members in boundaries]
    if not boundaries:
        return False

    col_w, col_gap = 260, 70
    width = max(1200, len(boundaries) * (col_w + col_gap) + col_gap)
    node_h, node_gap = 90, 34
    max_members = max((len(m) for _, _, m in boundaries), default=1)
    top_h = 70 + max_members * (node_h + node_gap)
    art_h = 90 if artifacts else 0
    height = top_h + (art_h + 60 if artifacts else 20)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<defs><marker id="dep_arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#111827"/></marker></defs>',
           f'<rect width="{width}" height="{height}" fill="#fff"/>']

    node_pos: dict[str, tuple[float, float, float, float]] = {}
    bx = col_gap
    for bid, name, members in boundaries:
        bw = col_w
        svg.append(f'<rect x="{bx}" y="30" width="{bw}" height="{top_h - 10}" fill="#eef8fc" stroke="#75c5e8" stroke-width="2"/>')
        svg.append(_context_text(bx + bw / 2, 54, name, 15, "700"))
        ny = 80
        for member in members:
            stereotype, mname = nodes[member]
            threed = stereotype.lower() in {"processor", "device", "execution environment"}
            nx, nw = bx + 20, bw - 40
            svg.extend(_dep_box_svg(nx, ny, nw, node_h - 30, "#75c5e8", threed))
            label = f"<<{stereotype}>>\n{mname}" if stereotype else mname
            for i, part in enumerate(label.split("\n")):
                svg.append(_context_text(nx + nw / 2, ny + 22 + i * 16, part, 12, "700" if i else "400"))
            node_pos[member] = (nx, ny, nw, node_h - 30)
            ny += node_h + node_gap
        bx += col_w + col_gap

    ay = top_h + 40
    ax = col_gap
    aw = 200
    for artifact in artifacts:
        stereotype, aname = nodes[artifact]
        svg.extend(_dep_artifact_svg(ax, ay, aw, 56))
        svg.append(_context_text(ax + aw / 2, ay + 20, "<<artifact>>", 10, "700"))
        svg.append(_context_text(ax + aw / 2, ay + 38, aname, 12, "400"))
        node_pos[artifact] = (ax, ay, aw, 56)
        ax += aw + 40

    for start, end in deploys:
        s, e = node_pos.get(start), node_pos.get(end)
        if not s or not e:
            continue
        x1, y1 = s[0] + s[2] / 2, s[1]
        x2, y2 = e[0] + e[2] / 2, e[1] + e[3]
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#111827" stroke-width="1.4" '
                   f'stroke-dasharray="6,4" marker-end="url(#dep_arrow)"/>')
        svg.append(_context_text((x1 + x2) / 2 + 40, (y1 + y2) / 2, "<<deploy>>", 10))

    for start, end in links:
        s, e = node_pos.get(start), node_pos.get(end)
        if not s or not e:
            continue
        x1, y1 = s[0] + s[2], s[1] + s[3] / 2
        x2, y2 = e[0], e[1] + e[3] / 2
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#111827" stroke-width="1.4"/>')

    svg.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(svg), encoding="utf-8")
    return True


def render_diagram(kind: str, source: str, out_path: Path, timeout: int = 180) -> tuple[bool, str]:
    """Render the LLM-produced Mermaid source with its installed renderer.

    Mermaid CLI remains the source renderer.  The use-case adapter reads only
    the produced Mermaid relationships to emit the UML primitives that Mermaid
    itself does not implement (stick actors, ovals and generalization).  It is
    deliberately a presentation adapter, never a content generator or gate.
    """
    if kind == "use_case":
        try:
            if _render_use_case_svg(source, out_path):
                return True, ""
        except (OSError, ValueError) as exc:
            return False, f"the use-case renderer could not draw the SVG: {exc}"
    return render(source, out_path, timeout=timeout)


def _context_escape(value: str) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _context_text(x: float, y: float, value: str, size: int = 15, weight: str = "400") -> str:
    words = str(value or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > 28:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current or "")
    first = y - (len(lines) - 1) * 9
    spans = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 18}">{_context_escape(line)}</tspan>'
                    for i, line in enumerate(lines))
    return (f'<text x="{x}" y="{first}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="#111827">{spans}</text>')


def _render_system_context_svg(source: str, out_path: Path) -> bool:
    """Turn compact context Mermaid into a UML-style, reference-colour SVG."""
    lines = str(source or "").splitlines()
    system_id = ""
    boundary = "System boundary"
    labels: dict[str, str] = {}
    edges: list[tuple[str, str, str]] = []
    for line in lines:
        if "subgraph" in line:
            hit = re.search(r'subgraph\s+\w+\s*\[\s*"?([^\]"]+)', line)
            if hit:
                boundary = hit.group(1).strip()
        if "--" in line:
            hit = re.match(r'\s*(\w+)\s*--?>\s*\|\s*"?([^|"]+?)"?\s*\|\s*(\w+)', line)
            if hit:
                edges.append((hit.group(1), hit.group(2).strip(), hit.group(3)))
            continue
        hit = re.match(r'\s*(\w+).*?"([^"]+)"', line)
        if hit:
            node, label = hit.group(1), hit.group(2).strip()
            labels[node] = label
            if "[[" in line:
                system_id = node
    if not system_id or system_id not in labels:
        return False

    incoming = list(dict.fromkeys(start for start, _label, end in edges if end == system_id))
    outgoing = list(dict.fromkeys(end for start, _label, end in edges if start == system_id))
    actors = [node for node in incoming if node != system_id]
    services = [node for node in outgoing if node != system_id]
    if not actors and not services:
        return False

    rows = max(len(actors), len(services), 1)
    width, height = 1680, max(660, 220 + rows * 128)
    left_x, bound_x, bound_w, right_x = 205, 560, 560, 1325
    bound_y, bound_h = 100, height - 200
    sys_x, sys_y, sys_w, sys_h = bound_x + 130, height / 2 - 55, 300, 110
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#111827"/></marker></defs>',
           f'<rect width="{width}" height="{height}" fill="#fff"/>',
           f'<rect x="{bound_x}" y="{bound_y}" width="{bound_w}" height="{bound_h}" fill="#75c5e8" stroke="#111827" stroke-width="2"/>',
           _context_text(bound_x + bound_w / 2, bound_y + 25, boundary, 18, "700"),
           f'<rect x="{sys_x}" y="{sys_y}" width="{sys_w}" height="{sys_h}" fill="#8bd0ed" stroke="#111827" stroke-width="2.5"/>',
           _context_text(sys_x + sys_w / 2, sys_y + sys_h / 2, labels[system_id], 18, "700")]

    def row(index: int, total: int) -> float:
        return height / 2 if total == 1 else 175 + index * ((height - 350) / (total - 1))

    actor_y = {node: row(i, len(actors)) for i, node in enumerate(actors)}
    service_y = {node: row(i, len(services)) for i, node in enumerate(services)}
    for node, y in actor_y.items():
        svg.extend([f'<circle cx="{left_x}" cy="{y - 22}" r="10" fill="#75c5e8" stroke="#111827" stroke-width="1.6"/>',
                    f'<path d="M{left_x} {y - 12}V{y + 24}M{left_x - 20} {y}H{left_x + 20}M{left_x} {y + 24}L{left_x - 18} {y + 48}M{left_x} {y + 24}L{left_x + 18} {y + 48}" fill="none" stroke="#111827" stroke-width="1.8" stroke-linecap="round"/>',
                    _context_text(left_x, y + 70, labels.get(node, node), 16)])
    for node, y in service_y.items():
        x, w, h = right_x - 115, 230, 64
        svg.extend([f'<rect x="{x}" y="{y - h / 2}" width="{w}" height="{h}" fill="#fff" stroke="#111827" stroke-width="1.8"/>',
                    f'<path d="M{x + w - 22} {y - h / 2}V{y - h / 2 + 18}H{x + w}" fill="none" stroke="#111827" stroke-width="1.3"/>',
                    _context_text(right_x, y, labels.get(node, node), 15)])
    for start, label, end in edges:
        if start in actor_y and end == system_id:
            x1, x2, y = left_x + 25, sys_x, actor_y[start]
        elif start == system_id and end in service_y:
            x1, x2, y = sys_x + sys_w, right_x - 115, service_y[end]
        elif start in service_y and end == system_id:
            x1, x2, y = right_x - 115, sys_x + sys_w, service_y[start] + 20
        elif start == system_id and end in actor_y:
            x1, x2, y = sys_x, left_x + 25, actor_y[end] - 20
        else:
            continue
        mid = (x1 + x2) / 2
        svg.extend([f'<path d="M{x1} {y}H{x2}" fill="none" stroke="#111827" stroke-width="1.7" marker-end="url(#arrow)"/>',
                    f'<rect x="{mid - 88}" y="{y - 28}" width="176" height="22" fill="#fff"/>',
                    _context_text(mid, y - 16, label, 12)])
    svg.append('</svg>')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(svg), encoding="utf-8")
    return True


_NOISE = re.compile(r"^\s*(at |\s*\^+\s*$|Store is a function|\(node:|Generating)")


def _readable_error(text: str) -> str:
    """Mermaid's complaint, without the Node stack trace around it."""
    lines = [line.rstrip() for line in (text or "").splitlines()
             if line.strip() and not _NOISE.match(line)]
    keep = [line for line in lines
            if any(word in line.lower() for word in
                   ("error", "expecting", "parse", "unexpected", "got '", "syntax"))]
    return " | ".join((keep or lines)[:6])[:600] or "the renderer failed without a message"


_FENCE = re.compile(r"```(?:mermaid)?\s*(.+?)```", re.DOTALL)

# Mermaid deliberately accepts a broad textual subset of class-diagram syntax.
# The generator, however, promises recognizable UML rather than merely a
# parseable graph.  These checks make the Visual Paradigm / UML conventions
# actionable before an SVG is accepted.  They cannot infer product facts (that
# remains the SRS traceability review), but they catch notation drift such as a
# missing visibility symbol or the vague multiplicity "many".
_CLASS_BLOCK = re.compile(r"^\s*class\s+[^\s{]+(?:\s*\[[^\]]+\])?\s*\{(?P<body>.*?)^\s*\}",
                          re.MULTILINE | re.DOTALL)
_CLASS_MEMBER = re.compile(r"^\s*([+\-#~])\s*[^\s:].*", re.MULTILINE)
_CLASS_STEREOTYPE = re.compile(r"^\s*<<(?:interface|enumeration|object)>>\s*$", re.IGNORECASE)
_INLINE_MEMBER = re.compile(r"^\s*[^\s:]+\s*:\s*([+\-#~])\s*\S+", re.MULTILINE)
_RELATION = re.compile(
    r"^\s*[^\s:]+(?:\s+\"[^\"]+\")?\s*"
    r"(?P<token><\|--|--\|>|\.\.\|>|<\|\.\.|\*--|--\*|o--|--o|-->|<--|\.\.>|<\.\.|--|\.\.)"
    r"\s*(?:\"(?P<right>[^\"]+)\"\s*)?[^\s:]+(?:\s*:\s*(?P<label>.+))?\s*$",
    re.MULTILINE)
_MULTIPLICITY = re.compile(r"^(?:0\.\.1|1|0\.\.\*|1\.\.\*|\*|[2-9]\d*|(?:0|1)\.\.[2-9]\d*)$")
def _diagram_notation_problems(kind: str, text: str) -> list[str]:
    """Small, deterministic guards for the defining notation of every kind.

    Mermaid verifies grammar.  These checks verify the semantic *shape* that
    grammar alone cannot see (for example, a sequence source can parse without
    a return arrow, and a context diagram can parse without a system boundary).
    They intentionally never invent project content or require optional parts.
    """
    found: list[str] = []

    if re.search(r"^\s*(?:click|action)\b", text, re.IGNORECASE | re.MULTILINE):
        found.append("customer-facing SRS diagrams must not contain interactive `click` or `action` directives")

    if kind == "use_case":
        if not re.search(r"\bsubgraph\b", text, re.IGNORECASE):
            found.append("a use-case diagram needs one named system-boundary `subgraph`")
        if not re.search(r"\w+\s*\(\[", text):
            found.append("use cases must use Mermaid stadium/oval approximation `id([\"Goal\"])`")
        if not re.search(r"\w+\s*\[\/", text):
            found.append("use-case actors must use the distinct external-actor trapezoid form `actor[/\"Role\"/]`")
        if "---" not in text:
            found.append("a use-case diagram needs at least one solid actor-to-goal association")
    elif kind == "activity":
        if not re.search(r"\(\(●\)\)", text):
            found.append("an activity diagram needs the initial node `((●))`")
        if not re.search(r"\(\(◉\)\)", text):
            found.append("every activity path must finish at a final node `((◉))`")
    elif kind == "bpmn":
        if not re.search(r"\bsubgraph\b", text, re.IGNORECASE):
            found.append("a BPMN diagram needs a named pool/lane `subgraph`")
        # BPMN defines an event by its circle, not by the English words
        # "Start" and "End".  Mermaid approximates the start event with a
        # double circle and the end event with a triple circle; accept any
        # evidence-based label in those shapes rather than rejecting a
        # customer-domain label such as "Order received".
        has_start = bool(re.search(r"(?<!\()\(\(\s*(?!\()[^)]+\)\)(?!\))", text))
        has_end = bool(re.search(r"(?<!\()\(\(\(\s*[^)]+\)\)\)(?!\))", text))
        if not has_start or not has_end:
            found.append("a BPMN diagram needs a single-circle start-event approximation `id((\"event\"))` and a double-circle end-event approximation `id(((\"event\")))`")
    elif kind == "erd":
        if not re.search(r"^\s*[A-Z][A-Z0-9_]*\s*\{", text, re.MULTILINE):
            found.append("an ERD needs at least one uppercase entity block with typed attributes")
        if re.search(r"^\s*\S+\s+--\s+\S+", text, re.MULTILINE):
            found.append("an ERD relationship must use Crow's Foot cardinality, not a plain `--` line")
    elif kind == "sequence":
        lifelines = re.findall(r"^\s*(?:actor|participant)\s+", text, re.IGNORECASE | re.MULTILINE)
        if len(lifelines) < 2:
            found.append("a sequence diagram needs at least two declared actor/participant lifelines")
        if not re.search(r"(?:->>|-->>)", text):
            found.append("a sequence diagram needs at least one message arrow")
        if not re.search(r"(?:activate\s+|->>\+)", text, re.IGNORECASE):
            found.append("a sequence diagram needs an activation span for an executing participant")
        if "->>" in text and not re.search(r"-->>", text):
            found.append("a synchronous sequence call needs a dashed return message")
    elif kind == "state_machine":
        if not re.search(r"\[\*\]\s*-->", text):
            found.append("a state machine needs an initial pseudostate `[*] --> State`")
        if not re.search(r"-->\s*\[\*\]", text):
            found.append("a state machine needs a terminal transition `State --> [*]`")
    elif kind == "dfd":
        if not re.search(r"\(\(\s*[\"']?\s*\d+\.\s*[^)]+\)\)", text):
            found.append("a DFD needs a numbered verb-noun process such as `((1. Validate order))`")
        for line in text.splitlines():
            if "-->" in line and "|" not in line:
                found.append("every DFD data flow must have a named-data label between `|` characters")
                break
        if len(re.findall(r"\(\(\s*[\"']?\s*\d+\.\s*[^)]+\)\)", text)) < 2:
            found.append("a Level-1 DFD needs at least two numbered data-transforming processes")
    elif kind == "component":
        if "<<component>>" not in text.lower():
            found.append("a component diagram needs `<<component>>`-stereotyped components")
        if len(re.findall(r"\bsubgraph\b", text, re.IGNORECASE)) < 2:
            found.append("a component diagram needs responsibility-band `subgraph` groups")
        if not re.search(r"-\.->", text):
            found.append("component dependencies must use dashed arrows, not an unlabeled solid connection")
    elif kind == "deployment":
        if not re.search(r"<<(?:device|execution environment|processor)>>", text, re.IGNORECASE):
            found.append("a deployment diagram needs `<<device>>`, `<<processor>>` or `<<execution environment>>` nodes")
        if "<<artifact>>" not in text.lower():
            found.append("a deployment diagram needs at least one deployed `<<artifact>>`")
        if not re.search(r"<<deploy>>", text, re.IGNORECASE):
            found.append("every artifact must connect to the runtime node that hosts it with a dashed `<<deploy>>` arrow - never nested inside that node's own box")
        if not re.search(r"-->|---", text):
            found.append("a deployment diagram needs a plain connection between the runtime boundaries/nodes that communicate")
    elif kind == "system_context":
        if not re.search(r"\[\[.+?\]\]", text):
            found.append("a system-context diagram needs exactly one visually distinct system-boundary node `sys[[\"System\"]]`")
        for line in text.splitlines():
            if "-->" in line and "|" not in line:
                found.append("every system-context interaction must have a label between `|` characters")
                break
    return found


def _class_object_problems(text: str) -> list[str]:
    """Return UML-notation faults which Mermaid's syntax parser cannot know."""
    problems: list[str] = []
    blocks = list(_CLASS_BLOCK.finditer(text))
    if not blocks:
        return ["a class/object diagram needs at least one compartmented `class Name { ... }` box"]

    for block in blocks:
        body = block.group("body")
        header = block.group(0).split("{", 1)[0]
        # An object compartment holds concrete slot values rather than class
        # attributes/operations, so UML visibility is not meaningful there.
        if re.search(r"<<object>>", body, re.IGNORECASE):
            continue
        if "[" in header and ":" in header:
            problems.append("an object-instance label `instance : Class` must include the `<<object>>` stereotype")
        if re.search(r"<<enumeration>>", body, re.IGNORECASE):
            # Enumeration literals are not classifier attributes or operations;
            # UML writes their names plainly below the enumeration stereotype.
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped or _CLASS_STEREOTYPE.match(stripped):
                    continue
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stripped):
                    problems.append("an enumeration contains plain literal names only, below `<<enumeration>>`")
                    break
            continue
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("%%") or _CLASS_STEREOTYPE.match(stripped):
                continue
            if not _CLASS_MEMBER.match(line):
                problems.append("every class attribute and operation must begin with UML visibility "
                                "(`+`, `-`, `#`, or `~`)")
                break
            if "(" in stripped:
                if not re.search(r"\)\s*:\s*\S+", stripped):
                    problems.append("every class operation must use `operation(parameter: Type): ReturnType`")
                    break
            elif ":" not in stripped:
                problems.append("every class attribute must use `visibility name: Type`")
                break

    # Mermaid also permits Class : member declarations outside a compartment.
    # Keep the same visibility rule there.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("class ", "%%")) or ":" not in stripped:
            continue
        if _RELATION.match(line):
            continue
        if re.match(r"^\s*[^\s:]+\s*:", line) and not _INLINE_MEMBER.match(line):
            problems.append("every inline class member must begin with UML visibility "
                            "(`+`, `-`, `#`, or `~`)")
            break

    for match in _RELATION.finditer(text):
        line = match.group(0)
        quoted = re.findall(r'"([^\"]+)"', line)
        if len(quoted) == 1:
            problems.append("a relationship with multiplicity must state a valid multiplicity at both ends")
        elif len(quoted) >= 2:
            for value in quoted[:2]:
                if not _MULTIPLICITY.match(value.strip()):
                    problems.append("use exact UML multiplicity (`0..1`, `1`, `0..*`, `1..*`, `*`, or a fixed range), "
                                    f"not {value!r}")
                    break
        if not (match.group("label") or "").strip():
            problems.append("every class relationship needs a short domain verb/verb-phrase label after `:`")
    return list(dict.fromkeys(problems))

# What each kind's source has to open with for Mermaid to parse it at all.
OPENERS = {
    "erd": ("erdiagram",),
    "sequence": ("sequencediagram",),
    "class_object": ("classdiagram",),
    "state_machine": ("statediagram", "statediagram-v2"),
    "use_case": ("flowchart", "graph"),
    "activity": ("flowchart", "graph"),
    "dfd": ("flowchart", "graph"),
    "bpmn": ("flowchart", "graph"),
    "system_context": ("flowchart", "graph"),
    "component": ("flowchart", "graph"),
    "deployment": ("flowchart", "graph"),
}


def clean(source: str) -> str:
    """The Mermaid source out of whatever the model wrapped it in."""
    raw = str(source or "").strip()
    fenced = _FENCE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    return raw


def problems(kind: str, source: str) -> list[str]:
    """Why this source will not parse, in terms the model can act on."""
    text = clean(source)
    if not text:
        return ["the source is empty"]
    first = text.splitlines()[0].strip().lower()
    wanted = OPENERS.get(kind, ())
    if wanted and not first.startswith(wanted):
        return [f"a {kind} diagram must start with one of "
                f"{', '.join(wanted)}; this starts with {first[:40]!r}"]
    if text.count("(") != text.count(")"):
        return ["unbalanced parentheses in a node label"]
    if text.count("[") != text.count("]"):
        return ["unbalanced square brackets in a node label"]
    if kind == "class_object":
        return _class_object_problems(text)
    return _diagram_notation_problems(kind, text)
