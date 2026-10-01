"""Helpers shared by the tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server_modules import bus  # noqa: E402


def forget_project(project: str) -> None:
    """Clear a test project's events and let a later test use the same name again.

    `bus.forget` retires a project for good - a deleted project emits nothing more - which is right in the product
    and wrong between tests: every later test reusing the name would have its events silently dropped.
    """
    bus.forget(project)
    with bus._lock:  # noqa: SLF001 - test-only release of the tombstone
        bus._discarded.discard(project)  # noqa: SLF001
