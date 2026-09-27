"""A record of every update the customer approved in the chat: v1, v2, ...

Each finished update leaves one file pair under `<project>/.agentforge/versions/`: `v3.json` for the
studio and `v3.md` for a person reading the folder. The record says what was asked, what the plan
was, which files were added, changed or removed, and what the tests came to before and after. It
also keeps a copy of the test result records as they were before the update ran (`v3/results-before/`),
so an update can never cost the project the results it already had.

Nothing here interprets the update: it lists what the plan said and what the folder shows.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from . import config

VERSIONS = "versions"
_LIST_CAP = 300
_COPY_CAP = 8_000_000
_TEST_PATH = re.compile(r"(^|/)(tests?|e2e|__tests__)/|\.(test|spec)\.[cm]?[jt]sx?$")

# The records the Testing view reads, relative to the project's record folder or to the project.
_RECORDS = ((".agentforge/build/report.json"), (".agentforge/qa/report.json"), (".agentforge/qa/vitest.json"),
            ("test-results/results.json"))


def _dir(project: str) -> Path:
    return config.record_dir(project) / VERSIONS


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def next_number(project: str) -> int:
    numbers = [int(match.group(1)) for path in _dir(project).glob("v*.json")
               if (match := re.fullmatch(r"v(\d+)\.json", path.name))]
    return max(numbers, default=0) + 1


def result_records(workspace: Path) -> list[str]:
    """The test result records that exist in this project, by path."""
    found = [name for name in _RECORDS if (workspace / name).is_file()]
    qa = workspace / config.RECORD_DIR / "qa"
    if qa.is_dir():
        found += sorted(p.relative_to(workspace).as_posix() for p in qa.glob("*.json")
                        if p.relative_to(workspace).as_posix() not in found)
    return found


def preserve_results(project: str, number: int, workspace: Path) -> None:
    """Copy the result records as they are now, before an update can touch them."""
    target = _dir(project) / f"v{number}" / "results-before"
    for name in result_records(workspace):
        source = workspace / name
        try:
            if source.stat().st_size > _COPY_CAP:
                continue
            copy = target / name
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy)
        except OSError:
            continue


def test_counts(workspace: Path) -> dict[str, dict[str, int]]:
    """What the unit and browser test records hold right now."""
    out: dict[str, dict[str, int]] = {}
    unit = _json(workspace / config.RECORD_DIR / "qa" / "vitest.json")
    if isinstance(unit, dict) and isinstance(unit.get("numTotalTests"), int):
        out["unit"] = {"total": unit["numTotalTests"], "passed": int(unit.get("numPassedTests") or 0),
                       "failed": int(unit.get("numFailedTests") or 0)}
    browser = _json(workspace / "test-results" / "results.json")
    stats = browser.get("stats") if isinstance(browser, dict) else None
    if isinstance(stats, dict):
        passed, failed = int(stats.get("expected") or 0), int(stats.get("unexpected") or 0)
        flaky, skipped = int(stats.get("flaky") or 0), int(stats.get("skipped") or 0)
        out["browser"] = {"total": passed + failed + flaky + skipped, "passed": passed, "failed": failed}
    return out


def _diff(before: dict, after: dict) -> dict[str, list[str]]:
    added = sorted(path for path in after if path not in before)
    removed = sorted(path for path in before if path not in after)
    changed = sorted(path for path in after if path in before and before[path] != after[path])
    return {"added": added[:_LIST_CAP], "changed": changed[:_LIST_CAP], "removed": removed[:_LIST_CAP],
            "counts": {"added": len(added), "changed": len(changed), "removed": len(removed)}}


def record(project: str, number: int, change: dict, before: dict, after: dict,
           counts_before: dict, counts_after: dict, account: str) -> dict:
    """Write the version file for an update that has just finished, and return it."""
    plan = change.get("plan") or {}
    files = _diff(before, after)
    touched = [path for kind in ("added", "changed") for path in files[kind] if _TEST_PATH.search(path)]
    warnings = []
    for kind, label in (("unit", "unit-test"), ("browser", "browser-test")):
        if kind in counts_before and counts_after.get(kind, {}).get("total", 0) < counts_before[kind]["total"]:
            warnings.append(f"The {label} record holds {counts_after.get(kind, {}).get('total', 0)} tests now, "
                            f"it held {counts_before[kind]['total']} before: earlier results may have been "
                            f"overwritten. The record as it was is kept in versions/v{number}/results-before/.")
    version = {
        "number": number, "id": f"v{number}", "change_id": change.get("id"), "created": int(time.time() * 1000),
        "title": plan.get("title") or change.get("request", "")[:80], "summary": plan.get("summary", ""),
        "request": change.get("request", ""), "revisions": change.get("revision", 1),
        "impact": plan.get("impact", []), "steps": [{"stage": s.get("stage"), "title": s.get("title")}
                                                    for s in plan.get("steps", [])],
        "files": files, "tests": {"before": counts_before, "after": counts_after, "files": touched[:_LIST_CAP]},
        "warnings": warnings, "account": account,
    }
    folder = _dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"v{number}.json").write_text(json.dumps(version, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / f"v{number}.md").write_text(_markdown(version), encoding="utf-8")
    return version


def listing(project: str) -> list[dict]:
    """Every version, newest first."""
    rows = [row for path in _dir(project).glob("v*.json") if isinstance(row := _json(path), dict)]
    return sorted(rows, key=lambda row: row.get("number", 0), reverse=True)


def _tests_line(counts: dict) -> str:
    parts = []
    for kind, label in (("unit", "unit"), ("browser", "browser")):
        if kind in counts:
            row = counts[kind]
            parts.append(f"{label} {row['passed']}/{row['total']} passed")
    return ", ".join(parts) or "no test record"


def _markdown(version: dict) -> str:
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(version["created"] / 1000))
    lines = [f"# {version['id']}: {version['title']}", "", f"*{when} · request {version.get('change_id')}*", "",
             f"> {version['request']}", "", "## Summary", "", version["summary"] or "(no summary)", "",
             "## What it touched", ""]
    for row in version["impact"]:
        lines.append(f"- {row.get('stage')}: {'changed' if row.get('affected') else 'not changed'}"
                     f" — {row.get('why', '')}")
    files = version["files"]
    lines += ["", "## Files", ""]
    for kind in ("added", "changed", "removed"):
        counts = files["counts"][kind]
        if counts:
            lines.append(f"**{kind.capitalize()} ({counts})**")
            lines += [f"- {path}" for path in files[kind]]
            lines.append("")
    tests = version["tests"]
    lines += ["## Tests", "", f"Before: {_tests_line(tests['before'])}", f"After: {_tests_line(tests['after'])}"]
    if tests["files"]:
        lines += ["", "Test files created or edited:"] + [f"- {path}" for path in tests["files"]]
    for warning in version["warnings"]:
        lines += ["", f"**Warning:** {warning}"]
    lines += ["", "## Account", "", version["account"] or "(none)", ""]
    return "\n".join(lines)
