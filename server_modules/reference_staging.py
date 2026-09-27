"""Stage a reference document that lives outside the project workspace into it.

The agent's file tools stop at the workspace's edge (`WorkspaceTools._path()`
rejects anything outside `root`), but a theme page, a skill page or a build
guide lives beside this application, in `prompts/` or an agent's own `assets/`
tree. This copies such a page into the workspace so a real `read_file` tool
call can reach it, and tracks whether the model actually read it — the same
pattern `deploy_agent/deploy.py`'s `stage_skills()`/`_reads()` already used
for deployment skill pages, generalized so every stage can share it instead
of each inventing its own copy mechanism.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from . import bus


def stage(workspace: Path, subdir: str, files: dict[str, str], fresh: bool = True) -> list[str]:
    """Write name->content pairs into `workspace/subdir`, return their workspace-relative paths.

    `fresh=True` clears the folder first, so an edited source page takes
    effect on the next run rather than leaving a stale copy behind.
    """
    folder = workspace / subdir
    if fresh:
        shutil.rmtree(folder, ignore_errors=True)
    out = []
    for name, body in files.items():
        destination = folder / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")
        out.append((folder.relative_to(workspace) / name).as_posix())
    return out


def reads_since(project: str, since: float) -> set[str]:
    """Workspace-relative paths read via `read_file` since a bus event timestamp."""
    return {str(row.get("name")) for row in bus.history(project)
            if row.get("type") == "file_read" and float(row.get("at") or 0) >= since}


def unread(paths: Iterable[str], project: str, since: float) -> list[str]:
    """Which of `paths` the model has not yet `read_file`'d since `since`."""
    seen = reads_since(project, since)
    return [path for path in paths if path not in seen]


def as_bullets(paths: Iterable[str]) -> str:
    """`   - `path`` lines, for a prompt naming files to read."""
    return "\n".join(f"   - `{path}`" for path in paths)
