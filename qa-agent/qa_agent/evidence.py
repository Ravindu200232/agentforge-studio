"""Expose runner-owned evidence to the Testing UI without inventing results."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from server_modules.qa_report import summary_counts

from . import build_evidence


_TEST_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json"}
_TEST_FOLDERS = (("test", "unit"), ("tests", "unit"), ("__tests__", "unit"), ("e2e", "e2e"))
_TEST_SETUP = ("playwright.config.js", "playwright.config.ts", "vitest.config.js", "vitest.config.ts",
               "vitest.env.js", "vitest.env.ts")
_RESULT_HISTORY = (".agentforge", "qa", "history")


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


def test_sources(workspace: Path) -> list[dict]:
    """Every readable unit/E2E source file for the Coder tab, grouped by role."""
    seen: set[Path] = set()
    rows: list[dict] = []
    for folder, kind in _TEST_FOLDERS:
        root = workspace / folder
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path in seen or not path.is_file() or path.suffix.lower() not in _TEST_SUFFIXES:
                continue
            seen.add(path)
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                code = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rows.append({"path": path.relative_to(workspace).as_posix(), "kind": kind, "code": code})
    for name in _TEST_SETUP:
        path = workspace / name
        if path in seen or not path.is_file():
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            code = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rows.append({"path": name, "kind": "support", "code": code})
    return sorted(rows, key=lambda row: (row["kind"], row["path"]))


def _result_paths(workspace: Path) -> list[Path]:
    """Machine-readable results only; screenshots remain where their gallery serves them."""
    paths = [workspace / ".agentforge/build/report.json", workspace / ".agentforge/qa/report.json",
             workspace / "test-results/results.json", workspace / ".lighthouseci/summary.json"]
    qa = workspace / ".agentforge/qa"
    if qa.is_dir():
        paths.extend(path for path in qa.rglob("*.json") if "history" not in path.relative_to(qa).parts)
    seen: set[Path] = set()
    return [path for path in paths if path.is_file() and not (path in seen or seen.add(path))]


def archive_results(workspace: Path, label: str, kind: str) -> dict | None:
    """Save a test-result snapshot before a run can replace the live artifacts."""
    sources = _result_paths(workspace)
    if not sources:
        return None
    stamp = int(time.time() * 1000)
    snapshot_id = f"run-{stamp}-{uuid.uuid4().hex[:6]}"
    target = workspace.joinpath(*_RESULT_HISTORY, snapshot_id)
    metadata = {"id": snapshot_id, "at": stamp, "label": label, "kind": kind, "source": "testing"}
    try:
        for source in sources:
            copy = target / source.relative_to(workspace)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy)
        target.mkdir(parents=True, exist_ok=True)
        (target / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        shutil.rmtree(target, ignore_errors=True)
        return None
    return metadata


def _counts(root: Path) -> dict:
    out = {}
    unit = _json(root / ".agentforge/qa/vitest.json")
    if isinstance(unit, dict) and isinstance(unit.get("numTotalTests"), int):
        out["unit"] = {"total": unit["numTotalTests"], "passed": int(unit.get("numPassedTests") or 0),
                       "failed": int(unit.get("numFailedTests") or 0)}
    browser = _json(root / "test-results/results.json")
    stats = browser.get("stats") if isinstance(browser, dict) else None
    if isinstance(stats, dict):
        passed, failed = int(stats.get("expected") or 0), int(stats.get("unexpected") or 0)
        flaky, skipped = int(stats.get("flaky") or 0), int(stats.get("skipped") or 0)
        out["browser"] = {"total": passed + failed + flaky + skipped, "passed": passed, "failed": failed}
    return out


def result_history(workspace: Path) -> list[dict]:
    """Historic records from test runs and approved chat changes, newest first."""
    rows = []
    history = workspace.joinpath(*_RESULT_HISTORY)
    if history.is_dir():
        for folder in history.iterdir():
            metadata = _json(folder / "metadata.json") if folder.is_dir() else None
            counts = _counts(folder) if isinstance(metadata, dict) else {}
            if metadata and counts:
                rows.append({**metadata, "counts": counts})
    versions = workspace / ".agentforge/versions"
    if versions.is_dir():
        for path in versions.glob("v*.json"):
            version = _json(path)
            snapshot = versions / path.stem / "results-before"
            counts = _counts(snapshot)
            if not isinstance(version, dict) or not counts:
                continue
            rows.append({"id": path.stem, "at": version.get("created"), "kind": "before-change", "source": "version",
                         "label": f"Before {path.stem} — {version.get('title') or 'approved change'}", "counts": counts,
                         "request": version.get("request") or ""})
    return sorted(rows, key=lambda row: int(row.get("at") or 0), reverse=True)


def collect(workspace: Path, saved: dict) -> dict:
    result = dict(saved)
    if "summary" in result and not isinstance(result["summary"], dict):
        # A sentence where the screen reads {pass, fail, warn}: keep the words, count the layers.
        result["summaryText"] = result.pop("summary")
        counts = summary_counts(saved)
        if any(counts.values()):
            result["summary"] = counts
    sources = test_sources(workspace)
    if sources:
        result["testSources"] = sources
    history = result_history(workspace)
    if history:
        result["resultHistory"] = history
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
