"""The SRS agent.

Owns the first half of a project: the interview, the approval plan, and the
specification itself — the document, its diagrams, its wireframes and the handoff
the builder consumes. It runs in the project's one shared model context, so
everything it learns here is still in front of the agents that come after it.
"""

from . import document, interview, plan  # noqa: F401

__all__ = ["interview", "plan", "document"]
