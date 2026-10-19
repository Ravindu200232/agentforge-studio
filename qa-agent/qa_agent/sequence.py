"""The order the Studio tests a built application in, in a build and in a Testing run.

1. The pages first. Every page is photographed whole, at desktop and mobile width, and looked at by a model that can see
   pictures; what looks wrong is fixed and only those pages are photographed again (`e2e_review`, `kind="pages"`). The
   journeys are never run to take pictures.
2. The journeys, once (`e2e_run.run`). While some still fail, the person is asked before each further round: Yes has the
   failing ones fixed and runs only them again; No moves on. Nothing is asked once every journey passes.
3. The other checks (accessibility, performance, security, dependencies), by the agent. A change made there is checked with
   the runtime test - the build, then every page opens (`e2e_run.runtime_check`) - never with the journeys, and the
   journeys' run stays the app's (`e2e_run.carry_over`). A runtime test that fails is asked about the same way: Yes has it
   fixed and runs it again; No moves on.

Every round after the first is a question in the chat (`screen_review.next_round`), so nothing here ever loops by itself.
"""
from __future__ import annotations

import time
from typing import Any

from server_modules import bus, prompts, screen_review
from server_modules.session import RunCancelled

from . import e2e_review, e2e_run

AFTER_JOURNEYS = "accessibility, security and the other final checks"


def _stopped(session: Any) -> None:
    if getattr(session, "cancelled", False):
        raise RunCancelled(session.project)


def screens_then_journeys(project: str, session: Any, reason: str = "build", force: bool = False) -> dict[str, Any]:
    """Steps 1 and 2: every page looked at and fixed, round by round; then the journeys one by one, each fixed as soon as
    it fails (`journeys_one_by_one`). Returns the journeys' run."""
    e2e_review.run(project, session, kind="pages", continue_plan=True)
    _stopped(session)
    return journeys_one_by_one(project, session, reason=reason, force=force)


MAX_JOURNEY_FIXES = 2         # fixes of one journey before the run goes on to the next


def journeys_one_by_one(project: str, session: Any, reason: str = "build", force: bool = False, model: str = "") -> dict[str, Any]:
    """Each journey on its own, at desktop width: run it; when it fails, have it fixed and run it again (at most
    MAX_JOURNEY_FIXES times); then the next. A fix made for one journey (a shared helper, the seed) is in place before the
    journeys after it run, and the app is built again only when a fix changed it. Running all of them first and fixing
    them together afterwards took an hour and a half on a 31-page store. Returns {"status": "passed" | "failed" | ...}."""
    workspace = session.workspace
    ids = e2e_run.journey_ids(workspace)
    if not ids or not e2e_run.runnable(workspace):
        ran = e2e_run.run(project, session, reason=reason, force=force)
        journey_rounds(project, session, ran, model)
        return ran
    if not force and e2e_run.current(workspace):
        return e2e_run.run(project, session, reason=reason)             # says the results are reused and returns them
    passed, failed, fixed = [], [], []
    # The journeys, then the requirement tests the build wrote for the pages no journey goes through, each the same way.
    items = [{**j, "grep": [j["id"]], "ask": lambda j=j: e2e_run.fix_one_request(workspace, j["id"]), "what": "Journey"}
             for j in ids]
    items += [{**s, "ask": lambda s=s: e2e_run.fix_spec_request(workspace, s), "what": "Requirement test"}
              for s in e2e_run.requirement_specs(workspace)]
    for number, item in enumerate(items, start=1):
        _stopped(session)
        bus.agent_msg(project, f"{item['what']} {number} of {len(items)}: {item['id']} {item['name']}.", title="Journeys",
                      kind="narration", agent=bus.DEVELOPER)
        ran = e2e_run.run(project, session, grep=item["grep"], reason=f"{reason}: {item['id']}", desktop=True)
        tries = 0
        while ran.get("status") in {"failed", "build_failed"} and tries < MAX_JOURNEY_FIXES:
            tries += 1
            request = (item["ask"]() if ran.get("status") == "failed" else
                       prompts.load("testing/fix-runtime", output=str(ran.get("output") or "")[-3000:]))
            if not request:
                break
            bus.agent_msg(project, f"{item['id']} failed: fixing it ({tries} of {MAX_JOURNEY_FIXES}), then running it again.",
                          title="Journeys", kind="narration", agent=bus.DEVELOPER)
            _fix(project, session, request, model, "Journeys")
            _stopped(session)
            ran = e2e_run.run(project, session, grep=item["grep"], reason=f"{reason}: {item['id']} fix {tries}", desktop=True)
        if ran.get("status") == "passed":
            passed.append(item["id"])
            if tries:
                fixed.append(item["id"])
        else:
            failed.append(item["id"])
    ids = items
    status = "passed" if not failed else "failed"
    e2e_run.record_full(workspace, {"at": time.time(), "reason": f"{reason} (one by one)", "grep": [],
                                    "exit_code": 0 if not failed else 1, "passed": len(passed), "failed": len(failed),
                                    "total": len(ids), "one_by_one": True})
    text = (f"{len(passed)} of {len(ids)} journeys and requirement tests pass" + (f" ({', '.join(fixed)} after a fix)" if fixed else "")
            + (f". Still failing after {MAX_JOURNEY_FIXES} fixes each: {', '.join(failed)}." if failed else "."))
    bus.agent_msg(project, text, title="Journeys", kind="narration", agent=bus.DEVELOPER)
    return {"status": status, "passed": len(passed), "failed": len(failed), "failing": failed, "total": len(ids)}


def journey_rounds(project: str, session: Any, ran: dict[str, Any], model: str = "") -> int:
    """While journeys fail after a run that really happened, ask before each round: Yes fixes the failing ones and runs only
    them again, No moves on. Returns how many rounds ran after the first."""
    if ran.get("status") not in {"passed", "failed"}:
        return 0
    done = 1
    while True:
        request, failing = e2e_run.fix_request(session.workspace)
        left = f"{screen_review.plural(len(failing), 'journey')} still {'fails' if len(failing) == 1 else 'fail'}" + (
            f" ({', '.join(failing[:8])})" if failing else "")
        if not failing or not screen_review.next_round(project, session, bus.DEVELOPER, done, len(failing), "", "Journeys",
                                                       continue_plan=True, left=left):
            return done - 1
        _stopped(session)
        bus.agent_msg(project, f"Round {done + 1}: fixing {', '.join(failing)}, then running only "
                               f"{'that journey' if len(failing) == 1 else 'those journeys'} again.",
                      title="Journeys", kind="narration", agent=bus.DEVELOPER)
        _fix(project, session, request, model, "Journeys")
        e2e_run.run(project, session, grep=failing, reason=f"journeys round {done + 1}")
        _stopped(session)
        done += 1


def after_changes(project: str, session: Any, why: str = AFTER_JOURNEYS, model: str = "") -> dict[str, Any]:
    """Step 3's check: when the app changed since the journeys' run, the runtime test instead of the journeys - asked about,
    round by round, while it fails - and, once it passes, the journeys' run stays the app's."""
    workspace = session.workspace
    last = e2e_run.record(workspace).get("full") or {}
    if not last.get("fingerprint") or e2e_run.current(workspace):
        return {"status": "unchanged"}
    bus.agent_msg(project, "The app changed after the journeys ran, for " + why + ". Those changes are checked with the "
                           "runtime test (the build, then every page opens); the journeys are not run again for them.",
                  title="Runtime test", kind="narration", agent=bus.DEVELOPER)
    checked = e2e_run.runtime_check(project, session)
    done = 1
    while checked.get("status") != "passed" and screen_review.next_round(
            project, session, bus.DEVELOPER, done, 1, "", "Runtime test", continue_plan=True,
            left="the runtime test still fails"):
        _stopped(session)
        _fix(project, session, prompts.load("testing/fix-runtime", output=str(checked.get("output") or "")[-3000:]), model,
             "Runtime test")
        checked = e2e_run.runtime_check(project, session)
        _stopped(session)
        done += 1
    if checked.get("status") == "passed":
        e2e_run.carry_over(workspace, why)
    return checked


def _fix(project: str, session: Any, request: str, model: str, title: str) -> None:
    """One fix pass by the agent, with every tool (a journey's fix runs that journey's own spec file). A pass that stops
    part-way is said, and what it changed is checked all the same; only Stop ends the run."""
    try:
        session.run_unplanned(request, model)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        bus.agent_msg(project, f"The fix stopped before it was finished: {str(exc)[:200]}. What it changed is checked anyway.",
                      title=title, kind="narration", agent=bus.DEVELOPER)
