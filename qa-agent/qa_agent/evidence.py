"""Expose runner-owned evidence to the Testing UI without inventing results."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import build_evidence


def _json(path: Path) -> dict:
    try:
        if path.stat().st_size > 20_000_000:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _fill(into: dict, derived: dict) -> None:
    """Add what was derived without overwriting anything the saved report says."""
    for key, value in derived.items():
        if key not in into:
            into[key] = value
        elif isinstance(into[key], dict) and isinstance(value, dict):
            _fill(into[key], value)


def collect(workspace: Path, saved: dict) -> dict:
    result = dict(saved)
    vitest = _json(workspace / ".agentforge/qa/vitest.json")
    if vitest:
        result["vitest"] = vitest
    playwright = _json(workspace / "test-results/results.json")
    if playwright:
        result["playwright"] = {
            "stats": playwright.get("stats", {}),
            "suites": playwright.get("suites", []),
            "errors": playwright.get("errors", []),
        }

    seen = {str(row.get("path")) for row in result.get("screenshots", [])
            if isinstance(row, dict) and row.get("path")}
    shots = [dict(row) for row in result.get("screenshots", []) if isinstance(row, dict)]
    for folder in (workspace / "test-results", workspace / "e2e/__screenshots__",
                   workspace / ".agentforge/qa/shots"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not path.is_file():
                continue
            relative = path.relative_to(workspace).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            shots.append({"name": path.stem, "path": relative, "status": "captured",
                          "at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
    result["screenshots"] = shots
    # A project whose Testing stage has not run still has what its build proved.
    derived = build_evidence.derive(workspace, result)
    _fill(result, derived)
    # This is calculated from the SRS artifact and runner-owned Playwright
    # result, so it must not be masked by a stale or optimistic agent report.
    journey_coverage = (((derived.get("report") or {}).get("e2e") or {})
                        .get("journeyCoverage"))
    if isinstance(journey_coverage, dict):
        result.setdefault("report", {}).setdefault("e2e", {})["journeyCoverage"] = journey_coverage
    return result
