"""What a build needs from this computer and the person's accounts, checked before the build is planned.

Node.js and npm (every command of the build), a browser (the end-to-end tests and the screenshot reviews), and the stack's own
services: a MongoDB stack's database (connected, and its cluster answering) and a Supabase stack's Supabase account. A build
used to find out half-way: a MongoDB that was not connected was said in one line and the build went on against a database on
this computer that was not there, failing the seed and every journey hours later; a Supabase account that was not connected
failed the build after it had started. Now what is missing is listed at the start, in one Yes/No card - "connect them, then
answer Yes to check again" - and Yes looks again, as many times as it takes. No stops the build before it has done anything.
"""
from __future__ import annotations

import shutil
from typing import Any, Callable

from server_modules import bus, deploy_vars, mongo_connect, screen_review, supabase_connect
from server_modules.session import RunCancelled

from . import scaffold

SETTINGS = "Settings, Integrations"


def missing(project: str, stack: str, say: Callable[[str], None] | None = None) -> list[dict[str, str]]:
    """What the build needs that is not there now: [{"what", "why", "how"}], empty when everything is ready."""
    gaps: list[dict[str, str]] = []
    if not shutil.which("node"):
        gaps.append({"what": "Node.js", "why": "it is not installed on this computer (every build command runs on it)",
                     "how": "install Node.js 20 or newer from https://nodejs.org, then restart AgentForge"})
    if not (shutil.which("npm") or shutil.which("npm.cmd")):
        gaps.append({"what": "npm", "why": "it is not installed on this computer",
                     "how": "it comes with Node.js: install Node.js from https://nodejs.org, then restart AgentForge"})
    from ollama_terminal import screenshot

    if not screenshot.working_browser():
        gaps.append({"what": "A browser", "why": "no Edge, Chrome or Chromium on this computer could open a page "
                                                   "(the end-to-end tests and the screenshot reviews use one)",
                     "how": "install Microsoft Edge or Google Chrome"})
    if scaffold.uses_mongodb(stack):
        gaps += _mongodb(say)
    if scaffold.uses_supabase(stack):
        gaps += _supabase(project)
    return gaps


def _mongodb(say: Callable[[str], None] | None) -> list[dict[str, str]]:
    state = deploy_vars.database_state()
    if not (state["saved"] or state["atlas"]):
        return [{"what": "MongoDB", "why": "no MongoDB is connected (the build's seed, preview and tests run on it)",
                 "how": f"sign in to MongoDB Atlas, or save a connection string, under {SETTINGS}"}]
    if not state["saved"]:
        return []                     # an Atlas account is signed in: the build makes the cluster itself
    answers, why = mongo_connect.verify_or_repair(log=say)
    if answers:
        return []
    return [{"what": "The MongoDB cluster", "why": f"it does not answer: {why}".rstrip(),
             "how": f"resume it in MongoDB Atlas if it is paused, or fix the connection under {SETTINGS}"}]


def _supabase(project: str) -> list[dict[str, str]]:
    if supabase_connect.record(project):
        return []                     # this project's Supabase project is already linked
    gaps = []
    if not supabase_connect.token_status()["connected"]:
        gaps.append({"what": "Supabase", "why": "no Supabase account is connected (this stack keeps its data in a Supabase "
                                                "project the build creates)",
                     "how": f"sign in to Supabase under {SETTINGS}"})
    from server_modules import cli_signin

    if not cli_signin._where("supabase"):  # noqa: SLF001 - the same lookup supabase_connect uses to create the project
        gaps.append({"what": "The Supabase command line tool", "why": "it is not installed on this computer",
                     "how": "install it with `npm i -g supabase`"})
    return gaps


def card_text(gaps: list[dict[str, str]], again: bool) -> str:
    lines = [f"- **{gap['what']}**: {gap['why']}. To fix: {gap['how']}." for gap in gaps]
    head = ("Still not ready after checking again:" if again else
            "Before the build is planned, these need to be ready:")
    return head + "\n" + "\n".join(lines) + "\n\nConnect or install them, then answer Yes to check again."


def ensure(project: str, stack: str, cancelled: Callable[[], bool], agent: str = bus.DEVELOPER) -> list[dict[str, Any]]:
    """Hold the build until everything it needs is ready, asking the person each time something is still missing. Returns
    what was asked about (empty when everything was ready at once). Raises RunCancelled on Stop, ValueError on No."""
    def say(line: str) -> None:
        bus.agent_msg(project, line, title="Before the build", kind="narration", agent=agent)

    bus.phase(project, "build:check", "Checking what the build needs", agent=agent,
              detail="Node.js, a browser, and this stack's database and accounts.")
    asked: list[dict[str, Any]] = []
    while True:
        gaps = missing(project, stack, say)
        if not gaps:
            if asked:
                say("Everything the build needs is ready now.")
            bus.phase(project, "build:check", "Checking what the build needs", status="complete", agent=agent)
            return asked
        asked.append({"missing": [gap["what"] for gap in gaps]})
        reply = bus.ask_and_wait(
            project, "question", card_text(gaps, again=len(asked) > 1),
            options=[{"id": "1", "label": "Yes"}, {"id": "2", "label": "No"}], agent=agent, cancelled=cancelled, quick=True,
            why="A build without these fails part-way, hours later. Nothing has been built yet.",
            assumption="stop the build")
        if reply is None:
            raise RunCancelled(project)
        if not screen_review.said_yes(reply):
            bus.phase(project, "build:check", "Checking what the build needs", status="failed", agent=agent,
                      detail=", ".join(gap["what"] for gap in gaps))
            raise ValueError("The build needs " + "; ".join(f"{gap['what']} ({gap['why']})" for gap in gaps)
                             + ". Connect or install it, then press Build again.")
