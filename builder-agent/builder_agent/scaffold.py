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
    "nextjs-supabase": "nextjs-supabase.md",
    "nextjs-mongo": "nextjs-mongo.md",
    "vite-supabase": "vite-supabase.md",
    "vite-mongo": "vite-mongo.md",
    "remix-supabase": "remix-supabase.md",
    "mern-microservices": "mern-microservices.md",
}
TEST_GUIDES = ("vitest.md", "playwright.md", "visual.md", "axe.md", "lighthouse.md", "zap.md")
# Not about one app: mistakes every build of every stack has made, and the scaffold's
# answer to each. Read before the stack guide so they are not learned again by failing.
COMMON_GUIDES = ("pitfalls.md", "unit-tests.md")
# Stack-neutral placeholder in the templates. Every generated app gets a project slug of
# its own (the local Supabase `project_id`, and the schema a test run uses) - a shared
# default let one app's tests and local stack touch another's data.
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


def project_slug(project: str) -> str:
    """A project id unique to this workspace: lowercase, `_`, at most 38 characters.

    Used as the local Supabase CLI's `project_id` (`supabase/config.toml`) and as the
    test schema name, so a build's own `supabase start`/tests never collide with another
    project's local stack.
    """
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
    slug = project_slug(workspace.name)
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
        body = body.replace(DB_PLACEHOLDER, slug)
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


def guide_files(stack: str) -> dict[str, str]:
    """Every guide a QA run reads for this stack - common, stack, then test guides - as name->body for staging."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guide_bodies((*COMMON_GUIDES, STACK_GUIDES[stack], *TEST_GUIDES))


def build_guide_files(stack: str) -> dict[str, str]:
    """The guides a build reads while implementing (pitfalls and the stack guide), as name->body for staging."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guide_bodies(("pitfalls.md", STACK_GUIDES[stack]))


def common_context() -> str:
    """Only the stack-neutral guidance, for a change to an application already built."""
    return _guides(COMMON_GUIDES)
