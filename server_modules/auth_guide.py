"""The one authentication guide the wireframes, the prototype and the build all read.

Like the selected design's DESIGN.md, it is a file in the workspace that each stage's agent reads itself:
`prompts/shared/authentication.md`, staged at `.agentforge/auth/AUTHENTICATION.md`. It says how signing up,
signing in, sessions, role-based access and the signed-in and signed-out navigation work; the specification
still decides which roles and pages exist. A product with no sign-in gets no guide.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import prompts, reference_staging

PROMPT = "shared/authentication"
FOLDER = ".agentforge/auth"
NAME = "AUTHENTICATION.md"
PATH = f"{FOLDER}/{NAME}"


def needed(doc: Any) -> bool:
    """Whether the specification has anyone signing in."""
    if not isinstance(doc, dict):
        return False
    auth = doc.get("authentication_requirement")
    if isinstance(auth, dict) and auth.get("login_required"):
        return True
    pages = [p for p in (doc.get("public_pages") or []) + (doc.get("protected_pages") or []) if isinstance(p, dict)]
    return any(p.get("login_required") for p in pages)


def stage(workspace: Path) -> str:
    """Put the guide in the workspace, where an agent's read_file reaches it; returns its workspace path."""
    return reference_staging.stage(workspace, FOLDER, {NAME: prompts.load(PROMPT)})[0]


def staged_for(workspace: Path, doc: Any) -> str:
    """The guide's workspace path when the product has sign-in, staged fresh; "" when it has none."""
    return stage(workspace) if needed(doc) else ""
