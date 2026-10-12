"""A model service that does not answer: the "Try again" a person can press while the run waits.

A request the model service refuses (a 500, a dropped connection) is asked for again after a pause, up to a few times
(`session.RetryingClient`), and the chat shows that it is happening (`bus.connection`). Here is the other half: the person
presses "Try again", and the run asks again at once instead of waiting out the pause, or, when it has given up asking by
itself and is holding still for them, goes on from that very request.

A press is a count that goes up. A wait reads the count when it begins and ends when the count has moved, so one press
reaches every call of the project that is waiting (the lanes of a parallel step), and a press made while nothing was
waiting is never mistaken for an answer to a later wait.
"""
from __future__ import annotations

import threading

import httpx

# How long a request to the model service may go without a single byte coming back before it is given up on (and asked
# for again, `session.RetryingClient`). Without a bound a request the service never answers waits for ever and the run
# with it: a deployment sat for twenty minutes on one.
MODEL_READ_SECONDS = 900.0
MODEL_CONNECT_SECONDS = 30.0


def model_timeout() -> httpx.Timeout:
    return httpx.Timeout(MODEL_READ_SECONDS, connect=MODEL_CONNECT_SECONDS)


_lock = threading.Lock()
_pressed: dict[str, int] = {}


def retry(project: str) -> bool:
    """The person pressed "Try again" for `project`."""
    if not project:
        return False
    with _lock:
        _pressed[project] = _pressed.get(project, 0) + 1
    return True


def presses(project: str) -> int:
    """How many times "Try again" has been pressed for `project` so far."""
    with _lock:
        return _pressed.get(project, 0)
