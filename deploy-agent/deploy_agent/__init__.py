"""The deploy agent.

Takes the verified application to a real target and proves it answers there. Runs
in the project's one shared model context, so it deploys the application it
watched get built, with the environment contract it already knows about.
"""

from . import deploy  # noqa: F401

__all__ = ["deploy"]
