"""Keeps the screenshots the end-to-end tests take, so a later test run does not take them away.

Playwright empties its output folder (`test-results/artifacts`) at the start of every run. The screens the journeys left are gone as
soon as the accessibility run, or one re-run of a single test, begins: the JSON a run kept still names them, but the files are not
there, and the review of the screens found nothing to look at. While a build or a testing run is going, the pictures are copied
here as they appear, under the same path inside `KEPT`, and a screenshot whose original is gone is read from its copy
(`build_evidence._screenshot_of`).
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

ARTIFACTS = "test-results/artifacts"
KEPT = ".agentforge/qa/screens"
SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SETTLE_SECONDS = 1.0               # a file touched this recently may still be being written
MAX_BYTES = 6_000_000


def kept_for(workspace: Path, path: str | Path) -> Path | None:
    """The kept copy of the screenshot at `path` (as Playwright reported it, absolute or relative to the workspace), if there is one."""
    try:
        picture = Path(path)
        picture = (picture if picture.is_absolute() else workspace / picture).resolve()
        relative = picture.relative_to((workspace / ARTIFACTS).resolve())
    except (OSError, ValueError):
        return None
    copy = workspace / KEPT / relative
    return copy if copy.is_file() else None


def sweep(workspace: Path, settled: bool = True) -> int:
    """Copy the screenshots in the output folder that have no up-to-date copy yet. Returns how many were copied.
    `settled`: leave a file touched in the last moment for the next sweep (the final sweep takes everything)."""
    source = workspace / ARTIFACTS
    copied = 0
    try:
        files = [p for p in source.rglob("*") if p.suffix.lower() in SUFFIXES] if source.is_dir() else []
    except OSError:
        return 0
    now = time.time()
    for path in files:
        try:
            stat = path.stat()
            if not path.is_file() or stat.st_size > MAX_BYTES or (settled and now - stat.st_mtime < SETTLE_SECONDS):
                continue
            target = workspace / KEPT / path.relative_to(source)
            if target.is_file() and target.stat().st_size == stat.st_size and target.stat().st_mtime >= stat.st_mtime:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
        except OSError:
            continue                                   # a file a test is replacing right now: the next sweep has it
    return copied


class Keeper:
    """`with Keeper(workspace):` copies the test screenshots while the block runs and once more when it ends. It never raises."""

    def __init__(self, workspace: Path, every: float = 1.0):
        self.workspace = Path(workspace)
        self.every = every
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sweep(self.workspace)
            except Exception:  # noqa: BLE001 - keeping pictures must never disturb the run that takes them
                pass
            self._stop.wait(self.every)

    def __enter__(self) -> "Keeper":
        self._thread = threading.Thread(target=self._loop, name=f"screen-keeper:{self.workspace.name}", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        try:
            sweep(self.workspace, settled=False)
        except Exception:  # noqa: BLE001
            pass
