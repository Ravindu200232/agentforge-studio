"""The prototype agent.

Owns the design contract and the clickable prototype: the first time the customer
sees the product rather than reads about it. Runs in the project's one shared
model context, so the specification it is drawing is the one it helped write.
"""

from . import design, prototype  # noqa: F401

__all__ = ["design", "prototype"]
