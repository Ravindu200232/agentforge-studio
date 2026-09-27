"""Keep the terminal agent's own source separate from generated projects."""

from __future__ import annotations

from pathlib import Path


class SourceGuard:
    """Restore CLI source files if a project command changes them."""

    def __init__(self, app_root: Path):
        self.root = app_root.resolve()

    # Everything that is this application rather than one of its projects. A
    # generated project's own build command runs with the user's permissions, so
    # a stray `rm -rf` or an over-eager formatter reaches all of it.
    FILES = ("pyproject.toml", "README.md", "run.ps1", "start.bat",
             "studio.ps1", "studio.bat", "server.py")
    FOLDERS = ("src/ollama_terminal", "tests", "server_modules", "prompts",
               "srs-agent", "prototype-agent", "builder-agent", "qa-agent",
               "deploy-agent")
    SKIP_PARTS = {"__pycache__", "node_modules", ".next", ".git"}

    def _paths(self) -> list[Path]:
        paths = [self.root / name for name in self.FILES]
        for name in self.FOLDERS:
            folder = self.root / name
            if folder.is_dir():
                paths.extend(p for p in folder.rglob("*")
                             if p.is_file() and p.suffix != ".pyc"
                             and not self.SKIP_PARTS.intersection(p.parts))
        return [path for path in paths if path.is_file()]

    def snapshot(self) -> dict[Path, bytes]:
        return {path: path.read_bytes() for path in self._paths()}

    def restore(self, before: dict[Path, bytes]) -> list[str]:
        changed: list[str] = []
        for path in self._paths():
            if path not in before:
                path.unlink()
                changed.append(path.relative_to(self.root).as_posix())
        for path, data in before.items():
            if not path.is_file() or path.read_bytes() != data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                changed.append(path.relative_to(self.root).as_posix())
        return changed
