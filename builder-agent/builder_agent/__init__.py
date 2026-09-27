"""The builder agent.

Turns the approved specification, design contract and prototype into the real
application in the workspace root. Runs in the project's one shared model
context: it is the same session that wrote the specification and drew the
prototype, so the build is not an interpretation of a handoff document — it is
the same participant continuing.
"""

from . import build  # noqa: F401

__all__ = ["build"]
