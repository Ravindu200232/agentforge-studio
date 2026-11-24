"""Stack registry and the build guidance staged for each selected stack."""
from __future__ import annotations

import re
from pathlib import Path

GUIDES = Path(__file__).resolve().parents[2] / "prompts" / "builder" / "stacks"
STACK_GUIDES = {
    "nextjs-supabase": "nextjs-supabase.md",
    "nextjs-mongo": "nextjs-mongo.md",
    "vite-supabase": "vite-supabase.md",
    "vite-mongo": "vite-mongo.md",
    "remix-supabase": "remix-supabase.md",
    "mern-microservices": "mern-microservices.md",
    "remix-mongo": "remix-mongo.md",
    # The same applications without Supabase: MongoDB is the only account they need.
    "nextjs-mongo-only": "nextjs-mongo.md",
    "vite-mongo-only": "vite-mongo.md",
    "mern-microservices-only": "mern-microservices.md",
    "remix-mongo-only": "remix-mongo.md",
}
# The stacks that run on MongoDB and never touch Supabase. Their twins without "-only" keep Supabase for one thing: the
# bucket uploaded files go in (both versions use the same framework and MongoDB for data).
MONGO_ONLY = frozenset({"nextjs-mongo-only", "vite-mongo-only", "mern-microservices-only", "remix-mongo-only"})
MONGO_STACKS = frozenset({"nextjs-mongo", "vite-mongo", "mern-microservices", "remix-mongo"}) | MONGO_ONLY
# Where uploaded files are kept when no uploads plugin is selected, for the MongoDB stacks: the Supabase-bucket ones
# use Supabase Storage, the Mongo-only ones use MongoDB's own GridFS. (The Supabase-database stacks say it in their guide.)
UPLOAD_GUIDES = {**{stack: "uploads-supabase.md" for stack in MONGO_STACKS - MONGO_ONLY},
                 **{stack: "uploads-gridfs.md" for stack in MONGO_ONLY}}
TEST_GUIDES = ("vitest.md", "playwright.md", "visual.md", "axe.md", "lighthouse.md", "zap.md")
# Not about one app: mistakes every build of every stack has made, and practice recommended to each. Read before the stack guide so they are not learned again by failing.
COMMON_GUIDES = ("pitfalls.md", "unit-tests.md")
ENGINE_ENTRIES = frozenset({".agentforge", ".agents", ".git", ".gitignore", ".env",
                            ".env.local", ".env.example", ".vscode", ".idea", "node_modules",
                            "media"})


def uses_mongodb(stack: str) -> bool:
    return stack in MONGO_STACKS


def uses_supabase(stack: str) -> bool:
    """Whether a build of this stack needs the customer's Supabase account: every stack but the Mongo-only ones."""
    return stack in STACK_GUIDES and stack not in MONGO_ONLY


def _uploads(stack: str) -> tuple[str, ...]:
    return (UPLOAD_GUIDES[stack],) if stack in UPLOAD_GUIDES else ()


def _pitfalls(stack: str) -> tuple[str, ...]:
    """The shared pitfalls; a stack that uses Supabase (or a caller that does not say) also gets the Supabase ones."""
    return ("pitfalls.md", *(("pitfalls-supabase.md",) if not stack or uses_supabase(stack) else ()))


def project_slug(project: str) -> str:
    """A project id unique to this workspace: lowercase, `_`, at most 38 characters.

    Used as the local Supabase CLI's `project_id` (`supabase/config.toml`) and as the
    test schema name, so a build's own `supabase start`/tests never collide with another
    project's local stack.
    """
    name = re.sub(r"[^a-z0-9_]+", "_", project.lower()).strip("_")[:38].strip("_")
    return name or "app"


def describe_workspace(workspace: Path, stack: str) -> dict:
    """Describe the work available for a new or resumed build without creating application files."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    if not workspace.is_dir():
        raise ValueError("project workspace does not exist")
    existing = sorted(p.name for p in workspace.iterdir() if p.name not in ENGINE_ENTRIES)
    return {"stack": stack, "project_slug": project_slug(workspace.name),
            "mode": "continue" if existing else "from_scratch", "existing": existing}


def _guide_bodies(names: tuple[str, ...]) -> dict[str, str]:
    return {name: (GUIDES / name).read_text(encoding="utf-8") for name in names}


def _guides(names: tuple[str, ...]) -> str:
    return "\n\n".join(f"### {name}\n{body}" for name, body in _guide_bodies(names).items())


def guide_files(stack: str) -> dict[str, str]:
    """Every guide a QA run reads for this stack - common, stack, then test guides - as name->body for staging."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guide_bodies((*_pitfalls(stack), "unit-tests.md", STACK_GUIDES[stack], *_uploads(stack), *TEST_GUIDES))


def build_guide_files(stack: str) -> dict[str, str]:
    """Application, selected stack and QA guidance for planning and implementation."""
    if stack not in STACK_GUIDES:
        raise ValueError(f"unsupported build stack: {stack}")
    return _guide_bodies((*_pitfalls(stack), "application.md", STACK_GUIDES[stack], *_uploads(stack), *TEST_GUIDES))


def common_context(stack: str = "") -> str:
    """Only the stack-neutral guidance, for a change to an application already built."""
    return _guides((*_pitfalls(stack), "unit-tests.md"))
