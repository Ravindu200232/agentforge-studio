"""Markdown into a real PDF, with the headless browser the Studio already runs for Mermaid.

No PDF library is bundled with the backend, but every Studio already has Node, `marked` and
Puppeteer (studio/node_modules) and a Chrome or Edge to drive - the same pieces
`mermaid.py` renders diagrams with - so `scripts/render-pdf.mjs` prints the page that browser
lays out. Anything that stops it is a plain error the download shows, never a file that only
looks like a PDF.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from . import mermaid

SCRIPT = Path(__file__).resolve().parent / "scripts" / "render-pdf.mjs"
TIMEOUT = 240


def render_markdown(markdown: str, base_dir: Path, title: str) -> bytes:
    """`markdown` as PDF bytes; relative links (diagram images) resolve against `base_dir`."""
    nodes = mermaid._node_binaries()  # noqa: SLF001 - the one Node lookup the Studio has
    if not nodes:
        raise ValueError("Making a PDF needs Node.js, and the Studio could not find it. "
                         "Install Node.js and try again.")
    env = {**os.environ, "STUDIO_ROOT": str(mermaid._STUDIO_ROOT)}  # noqa: SLF001
    browser = mermaid._installed_browser()  # noqa: SLF001
    if browser:
        env["PDF_BROWSER"] = browser
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        source, out = work / "document.md", work / "document.pdf"
        source.write_text(markdown, encoding="utf-8")
        try:
            done = subprocess.run([nodes[0], str(SCRIPT), str(source), str(out), title, str(base_dir)],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=TIMEOUT, cwd=str(mermaid._STUDIO_ROOT), env=env,  # noqa: SLF001
                                  creationflags=mermaid._NO_WINDOW)  # noqa: SLF001
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"The PDF took longer than {TIMEOUT}s to render.") from exc
        if done.returncode != 0 or not out.is_file():
            said = [line for line in (done.stderr or done.stdout or "").splitlines() if line.strip()]
            raise ValueError("The PDF could not be rendered: " + (said[-1][:300] if said else "the renderer stopped"))
        return out.read_bytes()
