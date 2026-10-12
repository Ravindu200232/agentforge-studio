"""Keep the terminal agent's own source separate from generated projects."""

from __future__ import annotations

from pathlib import Path


class Snapshot(dict):
    """The protected files as they were, and the commit the app's own repository was on then."""

    head: str = ""


class SourceGuard:
    """Restore CLI source files if a project command changes them."""

    def __init__(self, app_root: Path):
        self.root = app_root.resolve()
        # What changed during the last command but was left alone, because the change was the
        # repository's own (a pull, a checkout, a commit), not the command's.
        self.left_alone: list[str] = []

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

    def head(self) -> str:
        """The commit the app's own repository is on, or "" when it is not a repository."""
        git = self.root / ".git"
        try:
            if git.is_file():                      # a worktree: `.git` names the real folder
                pointer = git.read_text(encoding="utf-8").strip()
                git = (self.root / pointer.removeprefix("gitdir:").strip()).resolve()
            ref = (git / "HEAD").read_text(encoding="utf-8").strip()
            if not ref.startswith("ref: "):
                return ref                         # a detached HEAD is the commit itself
            name = ref[5:]
            loose = git / name
            if loose.is_file():
                return loose.read_text(encoding="utf-8").strip()
            packed = git / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + name):
                        return line.split(" ", 1)[0]
            return ref
        except OSError:
            return ""

    def snapshot(self) -> Snapshot:
        taken = Snapshot((path, path.read_bytes()) for path in self._paths())
        taken.head = self.head()
        return taken

    def _changes(self, before: dict[Path, bytes]) -> tuple[list[Path], list[Path]]:
        added = [path for path in self._paths() if path not in before]
        altered = [path for path, data in before.items() if not path.is_file() or path.read_bytes() != data]
        return added, altered

    def restore(self, before: dict[Path, bytes]) -> list[str]:
        self.left_alone = []
        added, altered = self._changes(before)
        names = [path.relative_to(self.root).as_posix() for path in [*added, *altered]]
        # The repository moved while the command ran: those files are a pull or a checkout landing,
        # and putting the old copies back would quietly undo it.
        head = getattr(before, "head", "")
        if head and self.head() != head:
            self.left_alone = names
            return []
        for path in added:
            path.unlink()
        for path in altered:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(before[path])
        return names
