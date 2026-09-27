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
        node = shutil.which("node") or shutil.which("node.exe")
        local_cli = (_STUDIO_ROOT / "node_modules" / "@mermaid-js"
                     / "mermaid-cli" / "src" / "cli.js")
        if node and local_cli.is_file():
            candidates.append([node, str(local_cli)])
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
        puppeteer_config = dict(_PUPPETEER)
        browser = _installed_browser()
        if browser:
            puppeteer_config["executablePath"] = browser
        config.write_text(json.dumps(puppeteer_config), encoding="utf-8")
        try:
            done = subprocess.run(
                [*cli, "-i", str(mmd), "-o", str(out_path), "-b", "white",
                 "-p", str(config)],
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
    return []
