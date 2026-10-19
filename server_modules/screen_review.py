"""What the screenshot review of the end-to-end tests (`qa_agent/e2e_review.py`) is made of.

A vision model is shown pictures of a screen and answers with what is visibly wrong with it; the problems that matter are
written out for the agent to fix; what is found is told in the chat under the pictures.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import bus, vision

SYSTEM = ("You are a meticulous UI reviewer. You are shown screenshots of a web page and you report only what is visibly "
          "wrong with it, as the JSON object you are asked for. You never invent a problem you cannot see.")
MAX_DEFECTS = 8                      # per screen
MAX_TO_FIX = 40                      # across everything reviewed, high and medium first
FIX_SEVERITIES = ("high", "medium")
ORDER = {"high": 0, "medium": 1, "low": 2}


def clean(data: Any) -> dict[str, Any]:
    """The model's answer for one screen, as {"looks_ok", "summary", "defects": [...]}; an error says what to fix."""
    if not isinstance(data, dict):
        raise ValueError("the answer must be one JSON object")
    rows = data.get("defects")
    if not isinstance(rows, list):
        raise ValueError('"defects" must be a list (empty when the page looks right)')
    defects = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("problem") or "").strip():
            continue
        severity = str(row.get("severity") or "medium").strip().lower()
        viewport = str(row.get("viewport") or "both").strip().lower()
        defects.append({
            "severity": severity if severity in ORDER else "medium",
            "viewport": viewport if viewport in {"desktop", "mobile", "both"} else "both",
            "where": str(row.get("where") or "").strip()[:200],
            "problem": str(row.get("problem") or "").strip()[:400],
            "fix": str(row.get("fix") or "").strip()[:400],
        })
    defects.sort(key=lambda d: ORDER[d["severity"]])
    return {"looks_ok": bool(data.get("looks_ok")) and not defects,
            "summary": str(data.get("summary") or "").strip()[:300], "defects": defects[:MAX_DEFECTS]}


def can_review(model: str, need_browser: bool = False,
               cancelled: Callable[[], bool] | None = None) -> tuple[bool, str]:
    """Whether `model` can be shown screenshots (and, when the review takes them itself, there is a browser to take them
    with): (ok, why not). Ollama says whether a model reads images; the model picker marks the ones that do."""
    seen = vision.supports(model)
    if seen is None:
        return False, f"it could not be found out whether {model} can look at pictures"
    if not seen:
        return False, f"{model} cannot look at pictures; pick a model marked \"vision\" to have the screens checked"
    if need_browser:
        from ollama_terminal import screenshot

        if not screenshot.working_browser(cancelled=cancelled):
            return False, "no browser (Edge, Chrome or Chromium) could be used to take the screenshots"
    return True, ""


def tell(project: str, result: dict[str, Any], agent: str, kind: str = "visual_review") -> None:
    """One screen's finding, in the chat, under its pictures."""
    defects = result["defects"]
    if defects:
        lines = [f"- **{d['severity']}** · {d['viewport']} · {d['where'] or 'page'}: {d['problem']}" for d in defects]
        text = (result["summary"] + "\n\n" if result["summary"] else "") + "\n".join(lines)
    else:
        text = result["summary"] or "Looks right at desktop and mobile width."
    bus.agent_msg(project, text,
                  title=f"{result['name']} · {len(defects)} to fix" if defects else f"{result['name']} · looks right",
                  kind=kind, agent=agent, images=result["thumbs"])


def fix_request(findings: list[dict[str, Any]]) -> tuple[str, int]:
    """The problems worth fixing, written out screen by screen for the agent (each finding's `heading` opens its block).
    Returns the text and how many problems it holds."""
    pool = [(f, d) for f in findings for d in f["defects"] if d["severity"] in FIX_SEVERITIES]
    pool.sort(key=lambda pair: ORDER[pair[1]["severity"]])
    pool = pool[:MAX_TO_FIX]
    chosen = {id(f) for f, _ in pool}
    blocks = []
    for finding in findings:
        if id(finding) not in chosen:
            continue
        lines = [finding["heading"]]
        for number, (_page, defect) in enumerate(((f, d) for f, d in pool if f is finding), start=1):
            lines.append(f"{number}. [{defect['severity']} · {defect['viewport']}] {defect['where'] or 'the page'}: "
                         f"{defect['problem']}" + (f" Suggested: {defect['fix']}" if defect["fix"] else ""))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks), len(pool)


def run_fix(project: str, session: Any, request: str, model: str, agent: str, title: str) -> str:
    """The agent's pass over the problems found. Returns "" when it finished, else why it stopped.

    A pass that stops partway (the model service stayed unreachable, say) has still changed files, so it is not a reason to
    end the review: the screens whose files changed are looked at again either way, and what is wrong is reported as it is.
    Only Stop ends the review."""
    from .session import RunCancelled

    try:
        session.run_direct(request, model=model)
        return ""
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - what the fix changed before it stopped is still looked at
        why = str(exc)[:200]
        bus.agent_msg(project, f"The fix stopped before it was finished: {why}. What it had changed so far is looked at anyway.",
                      title=title, kind="narration", agent=agent)
        return why


def rebuilt(project: str, rebuild: Any, agent: str, title: str) -> bool:
    """Bundle the app again after a fix (`rebuild`, which has the agent repair what does not bundle). A fix that breaks the
    bundle - one agent's fix of a crashing page took out a page's opening tag - is given one more go; when the app still does
    not bundle, the review stops fixing and says so, and keeps what it found, instead of ending: the stage bundles the app
    again, with its own repairs, when the review is over. Whether the app is bundled. Only Stop ends the review."""
    from .session import RunCancelled

    for attempt in (1, 2):
        try:
            rebuild()
            return True
        except RunCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - a bundle that fails is repaired again, then reported, never the end of the review
            why = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            if attempt == 1:
                bus.log(project, "WARN", f"The fix left the app not bundling ({why}); repairing it again.", agent=agent)
                continue
            bus.agent_msg(project, f"The fix left the app not bundling ({why}). No more fixes in this review: what it found is "
                                   "listed, and the app is bundled again, with its own repairs, when the stage finishes.",
                          title=title, kind="narration", agent=agent)
    return False


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


# The reviews go round by round: look, fix, look again. The first round runs by itself; every round after it is asked for,
# Yes or No, in the chat - nothing is asked once nothing is left to fix. This is the most rounds one review can have.
MAX_ROUNDS = 10
_YES = {"y", "yes", "yeah", "yep", "ok", "okay", "sure", "go", "continue", "ow", "ou", "owu", "හා", "ඔව්", "ඔව"}


def _first_word(text: str | None) -> str:
    words = re.split(r"[\s,.!?]+", str(text or "").strip().lower())
    return words[0] if words else ""


def said_yes(reply: str | None) -> bool:
    """Whether an answer to a Yes/No card is a yes (the button, or typed: "yes", "ok", "ow", "ඔව්")."""
    return _first_word(reply) in _YES


def next_round(project: str, session: Any, agent: str, done: int, remaining: int, where: str, title: str,
               continue_plan: bool = False, left: str = "") -> bool:
    """After round `done`, with `remaining` problems still on `where` (or what `left` says is still wrong): whether to run
    round `done + 1`. The run holds still for the answer on a Yes/No card in the chat (typing it works too). Yes runs the next
    round. No, "You decide" and reaching `MAX_ROUNDS` end the rounds: inside a build or a testing run (`continue_plan`) the
    run then goes on to its next step, else the review stops there. Stop ends the run."""
    from .session import RunCancelled

    if remaining <= 0:
        return False
    left = left or f"{plural(remaining, 'problem')} still {'shows' if remaining == 1 else 'show'} on {where}"
    after = "moving on to the next step" if continue_plan else "the review stops here"
    if done >= MAX_ROUNDS:
        bus.agent_msg(project, f"{title}: {left} after {done} rounds; {after}.", title=title, kind="narration", agent=agent)
        return False
    reply = bus.ask_and_wait(
        project, "question",
        f"{title}: round {done} is done and {left}. Run round {done + 1} (fix {'it' if remaining == 1 else 'them'} and check "
        f"again)?" + (" No moves on to the next step." if continue_plan else ""),
        options=[{"id": "1", "label": "Yes"}, {"id": "2", "label": "No"}], agent=agent,
        cancelled=lambda: bool(getattr(session, "cancelled", False)), quick=True,
        why="Each round fixes only what is still wrong, then checks only that again.",
        assumption="move on to the next step and list what is left" if continue_plan else "stop here and list what is left")
    if reply is None:
        raise RunCancelled(project)
    if said_yes(reply):
        return True
    bus.agent_msg(project, (f"After round {done}: {left}, listed below; {after}." if continue_plan
                            else f"Stopped after round {done}: {plural(remaining, 'problem')} left as they are, listed below."),
                  title=title, kind="narration", agent=agent)
    return False
