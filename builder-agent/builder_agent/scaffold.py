"""Install the selected, bundled application template before the build plan.

Only an empty application workspace is scaffolded. Existing work is never
replaced, and template files remain inert inside AgentForge itself.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "assets" / "templates"
STACK_GUIDES = {
    "nextjs-mongo": "next.md",
    "mern-microservices": "mern+miro.md",
    "remix-mongo": "remix.md",
}
TEST_GUIDES = ("vitest.md", "playwright.md", "axe.md", "lighthouse.md", "zap.md")
# Not about one app: mistakes every build of every stack has made, and the scaffold's
# answer to each. Read before the stack guide so they are not learned again by failing.
COMMON_GUIDES = ("pitfalls.md", "unit-tests.md")
# Stack-neutral placeholder in the templates. Every generated app gets a database of
# its own; a shared default name let one app's tests and seed touch another's data.
DB_PLACEHOLDER = "__APP_DB__"
ENGINE_ENTRIES = frozenset({".agentforge", ".agents", ".git", ".gitignore", ".env",
                            ".env.local", ".env.example", ".vscode", ".idea", "node_modules",
                            "media"})


def _files(root: Path) -> list[tuple[Path, str]]:
    result = []
    for source in sorted(root.rglob("*")):
        if not source.is_file():
            continue
        rel = source.relative_to(root).as_posix()
        # Service skeletons are examples; their manifests must remain inert.
        target = rel if rel.startswith("scaffold/") else rel.removesuffix(".tpl")
        result.append((source, target))
    return result


def database_name(project: str) -> str:
    """A MongoDB database name unique to this project: lowercase, `_`, at most 38 characters."""
    name = re.sub(r"[^a-z0-9_]+", "_", project.lower()).strip("_")[:38].strip("_")
    return name or "app"


def install(workspace: Path, stack: str) -> dict:
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValueError("project workspace does not exist")
    existing = [p.name for p in workspace.iterdir() if p.name not in ENGINE_ENTRIES]
    if existing:
        return {"stack": stack, "scaffolded": False,
                "reason": "Existing application preserved", "existing": existing, "files": []}

    package_name = re.sub(r"[^a-z0-9._-]+", "-", workspace.name.lower()).strip("-._") or "app"
    db_name = database_name(workspace.name)
    files, preserved = [], []
    for source, target in _files(ROOT / stack) + _files(ROOT / "_testing"):
        dest = (workspace / target).resolve()
        if not dest.is_relative_to(workspace):
            raise ValueError(f"unsafe scaffold path: {target}")
        if dest.exists():
            preserved.append(target)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = source.read_text(encoding="utf-8")
        if target == "package.json":
            body = re.sub(r'"name": "[^"]*"', f'"name": "{package_name}"', body, count=1)
        body = body.replace(DB_PLACEHOLDER, db_name)
        dest.write_text(body, encoding="utf-8")
        files.append(target)

    result = {"stack": stack, "scaffolded": True, "files": files, "preserved": preserved,
              "source": f"builder_agent/assets/templates/{stack}"}
    manifest = workspace / ".agentforge" / "build" / "scaffold.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _guide_bodies(names: tuple[str, ...]) -> dict[str, str]:
    return {name: (ROOT / "_guides" / name).read_text(encoding="utf-8") for name in names}


def _guides(names: tuple[str, ...]) -> str:
    return "\n\n".join(f"### {name}\n{body}" for name, body in _guide_bodies(names).items())


def guide_context(stack: str) -> str:
    """Give the plan the actual local guidance, not a guessed remote path."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guides((*COMMON_GUIDES, STACK_GUIDES[stack], *TEST_GUIDES))


def guide_files(stack: str) -> dict[str, str]:
    """The same guidance `guide_context` describes, as name->body for staging into a workspace."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guide_bodies((*COMMON_GUIDES, STACK_GUIDES[stack], *TEST_GUIDES))


def build_context(stack: str) -> str:
    """Guidance needed while implementing the app, without test-suite material."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guides(("pitfalls.md", STACK_GUIDES[stack]))


def build_guide_files(stack: str) -> dict[str, str]:
    """The same guidance `build_context` describes, as name->body for staging into a workspace."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guide_bodies(("pitfalls.md", STACK_GUIDES[stack]))


def unit_context() -> str:
    """Guidance for the focused business-logic unit-test phase."""
    return _guides(("unit-tests.md", "vitest.md"))


def quality_context() -> str:
    """Guidance for the final browser and quality phase."""
    return _guides(("playwright.md", "axe.md", "lighthouse.md", "zap.md"))


def common_context() -> str:
    """Only the stack-neutral guidance, for a change to an application already built."""
    return _guides(COMMON_GUIDES)
