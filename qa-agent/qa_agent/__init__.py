"""The QA agent.

Verifies the built application against its own specification and leaves the
evidence on disk. Runs in the project's one shared model context, so it tests
what was actually agreed rather than what a report says was agreed.
"""

from . import verify  # noqa: F401

__all__ = ["verify"]
