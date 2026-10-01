"""The report shape the Testing views read, checked against what a build actually wrote.

`prompts/builder/report-template.json` is the one place that shape is written down. The
builder is handed a copy of it to fill (`stage_template`), and the same file is what
`problems()` checks the result against, so the prompt and the check cannot disagree.

Only the shape is checked - keys present, a list of objects still a list of objects, a
number still a number - never what a value claims. Whether a layer really passed is the
runner's own output file to prove, not this module's.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import prompts, reference_staging

TEMPLATE = "builder/report-template"
STAGED_DIR = ".agentforge/build/report-template"
STAGED_NAME = "report.template.json"
# section -> (record folder, file name), as ProjectSession.read_record() takes them
SECTIONS = {"build": ("build", "report.json"), "qa": ("qa", "report.json")}
# A row that is wrong is usually wrong the same way in every row; a few say enough.
_ROWS_REPORTED = 3


def template() -> dict[str, Any]:
    return prompts.data(TEMPLATE)


def stage_template(workspace: Path) -> str:
    """Copy the template into the workspace, where the agent's read_file can reach it."""
    body = json.dumps(template(), ensure_ascii=False, indent=2)
    return reference_staging.stage(workspace, STAGED_DIR, {STAGED_NAME: body})[0]


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return "empty"


def _check(name: str, value: Any, example: Any, out: list[str]) -> None:
    # null is an honest answer for a single value nothing measured (an unavailable layer's exit
    # code); a list or an object the screen iterates over has no such stand-in.
    if value is None and not isinstance(example, (list, dict)):
        return
    if _kind(value) != _kind(example):
        out.append(f"`{name}` must be {_kind(example)}, not {_kind(value)}")
        return
    if isinstance(example, dict):
        for key, sub in example.items():
            if key not in value:
                out.append(f"`{name}.{key}` is missing")
            else:
                _check(f"{name}.{key}", value[key], sub, out)
    elif isinstance(example, list) and example:
        wrong = 0
        for at, row in enumerate(value):
            before = len(out)
            _check(f"{name}[{at}]", row, example[0], out)
            if len(out) > before:
                wrong += 1
                if wrong >= _ROWS_REPORTED:
                    break


def problems(report: Any, section: str) -> list[str]:
    """What keeps `report` from being the shape the Testing views read, or [] when it is."""
    spec = template()[section]
    if not isinstance(report, dict):
        return [f"the {section} report is not a JSON object"]
    out = [f"`{key}` is missing" for key in spec["required"] if key not in report]
    for key, example in spec["example"].items():
        if key in report:
            _check(key, report[key], example, out)
    return out
