"""What the build itself proved, shaped for the Testing views.

The builder verifies its own work: it writes tests, runs them, repairs what they
find and records the outcome in `.agentforge/build/report.json`, next to the
artifacts its runners left (Vitest JSON, Playwright output, Lighthouse, a route
probe). The separate Testing stage may never run, so the Testing views read those
files directly instead of showing an empty screen.

Nothing here is invented. Every field comes from a file the build left, and a
value that cannot be read is left out — never defaulted to a pass. A saved QA
report always wins over what is derived here (see `evidence.collect`).
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server_modules import journeys as journey_contracts

BUILD_REPORT = ".agentforge/build/report.json"
HANDOFF = ".agentforge/srs/handoff.json"
QA_DIR = ".agentforge/qa"
LIGHTHOUSE_SUMMARY = ".lighthouseci/summary.json"
ROUTE_PROBE = ".agentforge/qa/routes.json"
ZAP_SUMMARY = ".agentforge/qa/zap/summary.json"
INVENTORY = ".agentforge/qa/coverage-inventory.json"
COVERAGE_SUMMARY = ".agentforge/qa/coverage/coverage-summary.json"
PLAYWRIGHT_JSON = "test-results/results.json"
# `scripts/with-server.mjs` keeps a copy of each run's Playwright JSON here, because the
# runner overwrites PLAYWRIGHT_JSON on every run (journeys, visual, accessibility, ...).
PLAYWRIGHT_RUNS = ".agentforge/qa/runs"
PREVIEW_RUNTIME = ".agentforge/preview-runtime.json"
VITEST_JSON = ".agentforge/qa/vitest.json"

# What PowerShell and Windows consoles do to UTF-8 on its way into a log file.
_MOJIBAKE = (("ΓÇ║", "›"), ("ΓÇö", "—"), ("ΓÇô", "–"), ("Â·", "·"),
             ("Â ", " "), ("Â ", " "), ("â€”", "—"), ("â€¢", "•"))

_A11Y = re.compile(r"a11y|accessib|axe|keyboard", re.I)
_VISUAL = re.compile(r"visual|looks as approved|screenshot", re.I)
_RUNNING = re.compile(r"Running\s+(\d+)\s+tests?\b")
_TEST_LINE = re.compile(
    r"^\[(\d+)/(\d+)\]\s+(?:\[([^\]]+)\]\s+›\s+)?(.+?):(\d+):(\d+)\s+›\s+(.+)$")
_SUMMARY = re.compile(
    r"^\s*(\d+)\s+(passed|failed|flaky|skipped|did not run|interrupted)\b"
    r"(?:\s+\(([\d.]+)\s*(ms|s|m)\))?")


def _clean(text: str) -> str:
    for bad, good in _MOJIBAKE:
        text = text.replace(bad, good)
    return text


def _read_text(path: Path) -> str:
    """UTF-8, or the UTF-16 that a PowerShell `>` redirect writes."""
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return _clean(data.decode("utf-16", errors="replace"))
    return _clean(data.decode("utf-8-sig", errors="replace"))


def _json(path: Path) -> Any:
    try:
        if not path.is_file() or path.stat().st_size > 20_000_000:
            return None
        return json.loads(_read_text(path))
    except (OSError, ValueError):
        return None


def _iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _rows(value: Any) -> list[dict]:
    return [r for r in (value or []) if isinstance(r, dict)] if isinstance(value, list) else []


# --- the browser runs ---------------------------------------------------------

def _spec_of(file: str) -> str:
    """The spec's file name. The JSON reporter says `a.spec.js`, a log says `e2e\a.spec.js`: same spec."""
    return str(file or "").replace("\\", "/").split("/")[-1]


def _from_line_log(text: str) -> dict | None:
    """A Playwright `line`/`list` reporter log: every test title, and the totals."""
    total = 0
    tests: list[dict] = []
    counts: dict[str, int] = {}
    seconds: float | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        running = _RUNNING.search(line)
        if running:
            total = int(running.group(1))
            continue
        found = _TEST_LINE.match(line)
        if found:
            parts = [p.strip() for p in found.group(7).split(" › ")]
            tests.append({"index": int(found.group(1)), "project": found.group(3) or "",
                          "file": _spec_of(found.group(4)),
                          "suite": " › ".join(parts[:-1]), "title": parts[-1]})
            continue
        summary = _SUMMARY.match(line)
        if summary:
            counts[summary.group(2)] = int(summary.group(1))
            if summary.group(3):
                seconds = float(summary.group(3)) * {"ms": .001, "s": 1, "m": 60}[summary.group(4)]
    if not total or not counts:
        return None
    failed = counts.get("failed", 0) + counts.get("interrupted", 0)
    clean = not failed and not counts.get("flaky") and not counts.get("skipped") \
        and not counts.get("did not run")
    for row in tests:
        # The line reporter names a test as it finishes; only a clean run says
        # every one of them passed. Otherwise the per-test result is not known.
        row["status"] = "passed" if clean else "unknown"
    return {"total": total, "passed": counts.get("passed", 0), "failed": failed,
            "flaky": counts.get("flaky", 0), "skipped": counts.get("skipped", 0),
            "seconds": seconds, "tests": tests}


def _screenshot_of(result: dict, workspace: Path | None) -> str:
    """The screenshot Playwright attached to a test result, workspace-relative, if it still exists."""
    if workspace is None:
        return ""
    root = workspace.resolve()
    for attachment in _rows(result.get("attachments")):
        if attachment.get("name") != "screenshot" or not attachment.get("path"):
            continue
        path = Path(str(attachment["path"]))
        path = (path if path.is_absolute() else workspace / path).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path.relative_to(root).as_posix()
    return ""


def _api_calls_of(result: dict, workspace: Path | None) -> list[dict]:
    """The app's own API calls this test's page made: `e2e/fixtures.js` attaches them as `api-calls`."""
    for attachment in _rows(result.get("attachments")):
        if attachment.get("name") != "api-calls":
            continue
        try:
            if attachment.get("body"):
                raw = base64.b64decode(str(attachment["body"])).decode("utf-8")
            elif attachment.get("path") and workspace is not None:
                raw = _read_text(workspace / str(attachment["path"]))
            else:
                return []
            lines = json.loads(raw)
        except (OSError, ValueError):
            return []
        calls = []
        for line in lines if isinstance(lines, list) else []:
            method, _, rest = str(line).partition(" ")
            path, _, status = rest.rpartition(" ")
            if method and path.startswith("/api"):
                calls.append({"method": method.upper(), "path": path,
                              "status": int(status) if status.isdigit() else None})
        return calls
    return []


def _from_playwright_json(data: Any, workspace: Path | None = None) -> dict | None:
    if not isinstance(data, dict):
        return None
    tests: list[dict] = []

    def walk(suite: dict, trail: list[str], file: str) -> None:
        file = suite.get("file") or file
        here = trail + ([suite["title"]] if suite.get("title") and not str(suite["title"]).endswith((".js", ".ts")) else [])
        for spec in _rows(suite.get("specs")):
            for test in _rows(spec.get("tests")):
                results = _rows(test.get("results"))
                last = results[-1].get("status") if results else test.get("status")
                status = {"passed": "passed", "expected": "passed", "failed": "failed",
                          "unexpected": "failed", "timedOut": "failed", "skipped": "skipped",
                          "flaky": "flaky"}.get(str(last or test.get("status")), "unknown")
                final = results[-1] if results else {}
                duration = final.get("duration")
                tests.append({"index": len(tests) + 1, "project": test.get("projectName") or "",
                              "file": _spec_of(spec.get("file") or file),
                              "suite": " › ".join(here), "title": spec.get("title") or "",
                              "status": status,
                              "seconds": round(duration / 1000, 1) if isinstance(duration, (int, float)) else None,
                              "screenshot": _screenshot_of(final, workspace),
                              "api_calls": _api_calls_of(final, workspace)})
        for child in _rows(suite.get("suites")):
            walk(child, here, file)

    for suite in _rows(data.get("suites")):
        walk(suite, [], suite.get("file") or "")
    if not tests:
        return None
    count = lambda s: sum(1 for t in tests if t["status"] == s)  # noqa: E731
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    return {"total": len(tests), "passed": count("passed"), "failed": count("failed"),
            "flaky": count("flaky"), "skipped": count("skipped"),
            "seconds": (stats.get("duration") or 0) / 1000 or None, "tests": tests}


def _runs_found(workspace: Path) -> list[dict]:
    """Every browser run the build left: Playwright's JSON reporter and each log."""
    found: list[dict] = []
    exact = _from_playwright_json(_json(workspace / PLAYWRIGHT_JSON), workspace)
    if exact:
        found.append({**exact, "source": PLAYWRIGHT_JSON,
                      "at": _iso(workspace / PLAYWRIGHT_JSON), "rank": 1})
    kept = workspace / PLAYWRIGHT_RUNS
    for path in sorted(kept.glob("*.json")) if kept.is_dir() else []:
        run = _from_playwright_json(_json(path), workspace)
        if run:
            found.append({**run, "source": path.relative_to(workspace).as_posix(),
                          "at": _iso(path), "rank": 1})
    qa = workspace / QA_DIR
    for log in sorted(qa.glob("*.log")) if qa.is_dir() else []:
        try:
            run = _from_line_log(_read_text(log))
        except OSError:
            continue
        if run:
            found.append({**run, "source": log.relative_to(workspace).as_posix(),
                          "at": _iso(log), "rank": 0})
    return found


def browser_runs(workspace: Path) -> dict | None:
    """What the build's browser runs proved, one answer per spec file and browser.

    A build runs its layers separately (journeys, accessibility, visual, once per
    browser) and repeats them while it repairs things, and Playwright's JSON reporter is
    overwritten by every run. So no single run is "the" run. For each (browser, spec file)
    the newest run that covered it fully speaks for it: a later re-run of just a few of its
    tests does not shrink it, and an earlier failing attempt does not count once a later
    run replaced it.
    """
    runs = _runs_found(workspace)
    if not runs:
        return None
    options: dict[tuple, list] = {}
    for run in runs:
        groups: dict[tuple, list] = {}
        for test in run["tests"]:
            groups.setdefault((test["project"], test["file"]), []).append(test)
        for key, rows in groups.items():
            options.setdefault(key, []).append((run, rows))
    tests: list[dict] = []
    used: dict[str, dict] = {}
    for key in sorted(options):
        biggest = max(len(rows) for _, rows in options[key])
        run, rows = max((o for o in options[key] if len(o[1]) >= 0.6 * biggest),
                        key=lambda o: (o[0]["at"], o[0]["rank"]))
        used[run["source"]] = run
        tests.extend({**row, "source": run["source"]} for row in sorted(rows, key=lambda r: r["index"]))
    for at, row in enumerate(tests, 1):
        row["index"] = at
    count = lambda s: sum(1 for t in tests if t["status"] == s)  # noqa: E731
    seconds = [r["seconds"] for r in used.values() if r.get("seconds")]
    return {"total": len(tests), "passed": count("passed"), "failed": count("failed"),
            "flaky": count("flaky"), "skipped": count("skipped"),
            "seconds": round(sum(seconds), 1) if seconds else None, "tests": tests,
            "source": ", ".join(sorted(used)), "sources": sorted(used),
            "at": max(r["at"] for r in used.values())}


# --- the other runner artifacts ------------------------------------------------

def lighthouse(workspace: Path) -> dict | None:
    data = _json(workspace / LIGHTHOUSE_SUMMARY)
    if not isinstance(data, dict) or not _rows(data.get("results")):
        return None
    return data


def route_probe(workspace: Path) -> dict | None:
    data = _json(workspace / ROUTE_PROBE)
    return data if isinstance(data, dict) and _rows(data.get("results")) else None


def runtime_status(workspace: Path) -> dict | None:
    """The Studio-managed preview's current state, never a claimed test result."""
    data = _json(workspace / PREVIEW_RUNTIME)
    if not isinstance(data, dict) or not data.get("status"):
        return None
    return {key: data[key] for key in ("status", "url", "port", "detail", "revision") if key in data}


def unit_inventory(workspace: Path) -> dict | None:
    """`npm run qa:inventory`: every page, route and component, and the unit tests that use it."""
    data = _json(workspace / INVENTORY)
    return data if isinstance(data, dict) and isinstance(data.get("units"), list) else None


def code_coverage(workspace: Path) -> dict | None:
    """`npm run test:coverage`: what the unit tests execute, in total and per file (lowest first)."""
    data = _json(workspace / COVERAGE_SUMMARY)
    total = data.get("total") if isinstance(data, dict) else None
    if not isinstance(total, dict) or not isinstance(total.get("lines"), dict):
        return None

    def pct(block: Any, key: str) -> float | None:
        value = (block.get(key) or {}).get("pct") if isinstance(block, dict) else None
        return float(value) if isinstance(value, (int, float)) else None

    root = str(workspace.resolve()).replace("\\", "/").rstrip("/") + "/"
    files = []
    for name, block in data.items():
        if name == "total" or not isinstance(block, dict):
            continue
        rel = str(name).replace("\\", "/")
        files.append({"file": rel[len(root):] if rel.startswith(root) else rel,
                      **{k: pct(block, k) for k in ("lines", "statements", "functions", "branches")},
                      "linesTotal": (block.get("lines") or {}).get("total")})
    files.sort(key=lambda f: (f["lines"] is None, f["lines"] if f["lines"] is not None else 0, f["file"]))
    return {**{k: pct(total, k) for k in ("lines", "statements", "functions", "branches")},
            "files": files[:300], "fileCount": len(files), "at": _iso(workspace / COVERAGE_SUMMARY)}


# --- mapping onto what the Testing views read ---------------------------------

def _kind(command: str) -> str:
    c = command.lower()
    for kind, needles in (("install", ("npm install", "npm ci")), ("audit", ("npm audit",)),
                          ("security", ("zap",)), ("performance", ("lighthouse", "lhci", "run-perf")),
                          ("a11y", ("a11y", "axe")), ("visual", ("visual",)),
                          ("unit", ("vitest", "npm test")), ("build", ("npm run build", "next build")),
                          ("seed", ("seed",)), ("routes", ("verify-routes",)),
                          ("e2e", ("playwright", "run-e2e", "e2e"))):
        if any(n in c for n in needles):
            return kind
    return "check"


def _requirement_text(workspace: Path) -> dict[str, str]:
    data = _json(workspace / HANDOFF)
    out: dict[str, str] = {}
    if isinstance(data, dict):
        for row in _rows(data.get("requirements")) + _rows(data.get("non_functional")):
            if row.get("id"):
                out[str(row["id"])] = str(row.get("requirement") or "")
    return out


def _evidence_kinds(text: str) -> list[str]:
    t = text.lower()
    kinds = [k for k, needles in (("unit", ("test/", "vitest", "unit")),
                                  ("e2e", ("journey", "e2e", "playwright")),
                                  ("a11y", ("axe", "keyboard", "a11y")),
                                  ("visual", ("visual", "screenshot")),
                                  ("seed", ("seed",))) if any(n in t for n in needles)]
    return kinds or ["report"]


def _group(tests: list[dict], keep) -> list[dict]:
    """One flow per (spec file, project), with a stage per test."""
    flows: dict[tuple, dict] = {}
    for t in tests:
        if not keep(t):
            continue
        key = (t["file"], t["project"])
        flow = flows.setdefault(key, {"title": f"{t['file'].split('/')[-1]}" + (f" · {t['project']}" if t["project"] else ""),
                                      "role": t["project"], "stages": []})
        status = {"passed": "pass", "failed": "fail"}.get(t["status"], "not_reached")
        label = f"{t['suite']} › {t['title']}" if t["suite"] else t["title"]
        flow["stages"].append({"index": len(flow["stages"]) + 1, "label": label, "status": status,
                               "seconds": t.get("seconds"), "screenshot": t.get("screenshot") or ""})
    for flow in flows.values():
        st = [s["status"] for s in flow["stages"]]
        flow.update(stage_total=len(st), stage_passed=st.count("pass"),
                    stage_failed=st.count("fail"), stage_not_reached=st.count("not_reached"))
    return list(flows.values())


def _test_sources(vitest: Any) -> list[dict]:
    """The test files that are safe to link to a handler inventory."""
    files = []
    for suite in _rows((vitest or {}).get("testResults") if isinstance(vitest, dict) else []):
        name = str(suite.get("name") or "")
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        except OSError:
            text = ""
        files.append({"file": name.replace("\\", "/").split("/")[-1],
                      "status": suite.get("status") or "recorded", "text": text})
    return files


def _api_handlers(workspace: Path) -> list[dict]:
    """Read the API handlers that actually exist, without guessing an HTTP result."""
    roots = ((workspace / "app/api", "app/api"), (workspace / "src/app/api", "src/app/api"))
    rows = []
    for root, prefix in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("route.*"):
            if path.suffix.lower() not in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            relative = path.relative_to(root).parent.as_posix()
            route = "/api" + ("" if relative == "." else f"/{relative}")
            methods = sorted(set(re.findall(r"\bexport\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b", text)))
            rows.append({"route": route, "handler": f"{prefix}/{path.relative_to(root).as_posix()}",
                         "methods": methods, "tests": []})
    return rows


def _route_pattern(route: str) -> tuple[re.Pattern[str], int]:
    """A handler's URL as a pattern, and how many dynamic segments it has (fewer = more specific)."""
    parts = [p for p in route.strip("/").split("/") if p and not (p.startswith("(") and p.endswith(")"))]
    regex, dynamic = [], 0
    for part in parts:
        if re.fullmatch(r"\[\[?\.\.\.[^\]]+\]\]?", part):
            regex.append(".+")
            dynamic += 2
        elif re.fullmatch(r"\[[^\]]+\]", part):
            regex.append("[^/]+")
            dynamic += 1
        else:
            regex.append(re.escape(part))
    return re.compile("^/" + "/".join(regex) + "/?$"), dynamic


def _link_e2e(rows: dict[str, dict], tests: list[dict]) -> None:
    """Each API call an E2E test's page made, linked to the one handler that answered it - the most
    specific match, the way Next.js picks `/api/orders/new` before `/api/orders/[id]`."""
    patterns = {handler: _route_pattern(row["route"]) for handler, row in rows.items()}
    for test in tests:
        linked: dict[str, dict] = {}
        for call in test.get("api_calls") or []:
            matches = [(dynamic, handler) for handler, (pattern, dynamic) in patterns.items()
                       if pattern.match(call["path"])]
            if not matches:
                continue
            handler = min(matches)[1]
            entry = linked.setdefault(handler, {"kind": "e2e", "file": test.get("file") or "",
                                                "title": test.get("title") or "",
                                                "status": test.get("status") or "recorded", "calls": []})
            said = f"{call['method']} {call['status'] if call['status'] is not None else ''}".strip()
            if said not in entry["calls"]:
                entry["calls"].append(said)
        for handler, entry in linked.items():
            rows[handler]["tests"].append(entry)


def _contracts(workspace: Path, build: dict, vitest: Any, tests: list[dict] | None = None) -> list[dict]:
    files = _test_sources(vitest)
    rows: dict[str, dict] = {}
    for row in _api_handlers(workspace):
        rows[row["handler"]] = row
    for r in _rows(build.get("routes")):
        route = str(r.get("route") or "")
        if not route.startswith("/api/"):
            continue
        folder = re.sub(r"\{(\w+)\}", r"[\1]", route)
        handler = next((f"app{folder}/route.{ext}" for ext in ("js", "jsx", "ts", "tsx", "mjs")
                        if (workspace / f"app{folder}/route.{ext}").is_file()), f"app{folder}/route.js")
        row = rows.setdefault(handler, {"route": route, "handler": handler, "methods": [], "tests": []})
        if r.get("method") and r["method"] not in row["methods"]:
            row["methods"].append(r["method"])
    for row in rows.values():
        handler_root = row["handler"].rsplit("/route.", 1)[0]
        for f in files:
            if handler_root in f["text"].replace("\\", "/"):
                row["tests"].append({"kind": "unit", "file": f["file"], "status": f["status"] or "recorded"})
    _link_e2e(rows, tests or [])
    return sorted(rows.values(), key=lambda row: row["route"])


def _declared_layer(build: dict, kind: str, qa: dict | None = None) -> dict | None:
    """A build or QA report may retain an aggregate after detailed runner output is overwritten."""
    phases = [build, build.get("phase_3") if isinstance(build.get("phase_3"), dict) else {},
              qa if isinstance(qa, dict) else {}]
    for phase in phases:
        for layer in _rows(phase.get("layers")):
            name = str(layer.get("layer") or "")
            if kind == "a11y" and not _A11Y.search(name):
                continue
            if kind == "visual" and not _VISUAL.search(name):
                continue
            detail = str(layer.get("result") or "")
            match = re.search(r"\b(\d+)\s+(?:[a-z-]+\s+)?passed\b", detail, re.I)
            count = int(match.group(1)) if match else 0
            status = "passed" if layer.get("exit_code") == 0 or "passed" in detail.lower() else "recorded"
            return {"status": status, "count": count, "detail": detail}
    return None


def _build_repairs(build: dict) -> dict | None:
    """Repairs recorded by the builder, kept distinct from a Testing-stage repair loop."""
    items = []
    phases = [build, build.get("phase_2") if isinstance(build.get("phase_2"), dict) else {},
              build.get("phase_3") if isinstance(build.get("phase_3"), dict) else {}]
    for phase in phases:
        for row in _rows(phase.get("defects_found_and_fixed")):
            where = str(row.get("where") or "Generated application")
            problem = str(row.get("defect") or row.get("cause") or "A defect was found")
            fix = str(row.get("fix") or row.get("resolution") or "Repaired and rechecked")
            items.append({"where": where, "problem": problem, "fix": fix})
        for row in phase.get("defects_found_by_phase_3_and_repaired", []) if isinstance(phase.get("defects_found_by_phase_3_and_repaired"), list) else []:
            if isinstance(row, str) and row.strip():
                items.append({"where": "Browser verification", "problem": row.strip(), "fix": "Repaired during the build"})
    if not items:
        return None
    return {"status": "fixed", "source": "build", "items": items}


def _as_template(build: dict) -> dict:
    """A report written before the template (`prompts/builder/report-template.json`) existed,
    read as the template's keys. Only shapes real builds wrote are mapped, and only where the
    template's own key is absent, so a report that follows the template passes through unchanged."""
    build = dict(build)
    routes = [{"route": r} if isinstance(r, str) else r for r in build.get("routes") or []] \
        if isinstance(build.get("routes"), list) else build.get("routes")
    if isinstance(routes, list) and isinstance(build.get("api"), list):
        for line in build["api"]:
            method, _, path = str(line).strip().partition(" ")
            if path.startswith("/"):
                routes.append({"route": path, "method": method})
    if routes is not None:
        build["routes"] = routes
    if isinstance(build.get("gaps"), list):
        build["gaps"] = [{**g, "item": g.get("area", ""), "status": g.get("severity") or "gap",
                          "reason": g.get("detail", "")}
                         if isinstance(g, dict) and "item" not in g and ("area" in g or "detail" in g) else g
                         for g in build["gaps"]]
    if "defects_found_and_fixed" not in build and isinstance(build.get("repairs"), list):
        build["defects_found_and_fixed"] = [
            {"where": str(r.get("phase") or ""), "defect": str(r.get("finding") or ""), "fix": str(r.get("fix") or "")}
            for r in build["repairs"] if isinstance(r, dict)]
    return build


def _unit_result(vitest: Any) -> dict | None:
    """The unit layer as the Testing screen's `unit` entry, from Vitest's own JSON."""
    if not isinstance(vitest, dict) or not isinstance(vitest.get("numTotalTests"), int):
        return None
    failed = int(vitest.get("numFailedTests") or 0)
    return {"status": "failed" if failed or vitest.get("success") is False else "passed",
            "total": vitest["numTotalTests"], "passed": int(vitest.get("numPassedTests") or 0),
            "failed": failed, "artifact": VITEST_JSON}


def derive(workspace: Path, have: dict) -> dict:
    """Everything the Testing views can read from what the build left behind."""
    build = _json(workspace / BUILD_REPORT)
    build = _as_template(build) if isinstance(build, dict) else {}
    runs = browser_runs(workspace)
    lh = lighthouse(workspace)
    probe = route_probe(workspace)
    zap_summary = _json(workspace / ZAP_SUMMARY)
    zap_summary = zap_summary if isinstance(zap_summary, dict) and zap_summary.get("engine") else None
    inventory = unit_inventory(workspace)
    coverage = code_coverage(workspace)
    runtime = runtime_status(workspace)
    unit = _unit_result(have.get("vitest"))
    if not (build or runs or lh or probe or zap_summary or inventory or coverage or runtime or unit):
        return {}

    out: dict[str, Any] = {}
    if unit:
        out["unit"] = unit
    if inventory:
        out["unitInventory"] = inventory
    if coverage:
        out["codeCoverage"] = coverage
    if runtime:
        out["runtimeStatus"] = runtime
    if build:
        out["build"] = build
    if runs:
        out["browserRuns"] = runs
    if lh:
        out["lighthouse"] = lh
    if probe:
        out["routeProbe"] = probe
    if zap_summary:
        out["zapSummary"] = zap_summary

    commands = _rows(build.get("commands"))
    gaps = _rows(build.get("gaps"))
    # The builder types `built_at` from memory (a local clock time labelled UTC,
    # in the run this was written against), so the file's own time is the record.
    report_file = workspace / BUILD_REPORT
    built_at = _iso(report_file) if report_file.is_file() else str(build.get("built_at") or "")
    if built_at:
        out["recordedAt"] = built_at
    rows = [{"at": built_at, "kind": _kind(str(c.get("command") or "")),
             "suite": str(c.get("note") or c.get("command") or ""), "command": str(c.get("command") or ""),
             "status": "passed" if c.get("exit_code") == 0 else "failed",
             "exitCode": c.get("exit_code"), "derived": True} for c in commands]
    if rows:
        out["timeline"] = rows
        out["stages"] = sorted({r["kind"] for r in rows})
        bad = [r for r in rows if r["status"] == "failed"]
        out["summary"] = {"pass": len(rows) - len(bad),
                          "fail": sum(1 for r in bad if r["kind"] != "audit"),
                          "warn": len(gaps) + sum(1 for r in bad if r["kind"] == "audit")}

    tests = (runs or {}).get("tests") or []
    journey_coverage = None
    if runs:
        said = lambda t: f"{t['file']} {t['suite']} {t['title']}"  # noqa: E731
        a11y = [t for t in tests if _A11Y.search(said(t))]
        visual = [t for t in tests if t not in a11y and _VISUAL.search(said(t))]
        journey_tests = [t for t in tests if t not in a11y and t not in visual]
        journey_coverage = journey_contracts.e2e_coverage(workspace, journey_tests)
        flows = _group(journey_tests, lambda t: True)
        total = sum(f["stage_total"] for f in flows)
        e2e = {"ran": True, "flows": flows, "stage_total": total,
               "stage_passed": sum(f["stage_passed"] for f in flows),
               "stage_failed": sum(f["stage_failed"] for f in flows),
               "stage_not_reached": sum(f["stage_not_reached"] for f in flows),
               "failures": [], "source": runs["source"]}
        if journey_coverage is not None:
            e2e["journeyCoverage"] = journey_coverage
        if a11y:
            bad = sum(1 for t in a11y if t["status"] == "failed")
            out["accessibility"] = {
                "status": "failed" if bad else "passed" if all(t["status"] == "passed" for t in a11y) else "recorded",
                "audited": len(a11y), "totalRoutes": len(a11y), "passed": len(a11y) - bad, "failed": bad,
                "pages": [{"route": (f"{t['suite']} › " if t["suite"] else "") + t["title"] + (f" [{t['project']}]" if t["project"] else ""),
                           "status": t["status"] if t["status"] in ("passed", "failed") else "recorded"} for t in a11y]}
            keyboard = [t for t in a11y if "keyboard" in said(t).lower()]
            if keyboard:
                out["accessibility"]["keyboard"] = "passed" if all(t["status"] == "passed" for t in keyboard) else "recorded"
        out.setdefault("report", {})["e2e"] = e2e
        out["visualRuns"] = {"tests": len(visual), "passed": sum(1 for t in visual if t["status"] == "passed")}

    declared_a11y = _declared_layer(build, "a11y", have)
    if declared_a11y:
        accessibility = out.setdefault("accessibility", {"status": declared_a11y["status"], "pages": []})
        accessibility["declaredAudited"] = declared_a11y["count"]
        accessibility["declaredPassed"] = declared_a11y["count"] if declared_a11y["status"] == "passed" else 0
        accessibility["declaredDetail"] = declared_a11y["detail"]
        accessibility.setdefault("manualReview", "not run")

    visual = _declared_layer(build, "visual", have)
    if visual:
        out["uiQualitySummary"] = visual

    # Still expose a missing journey run when the SRS contract exists but no
    # Playwright result was saved. A generic QA `complete: true` cannot hide it.
    if not runs:
        journey_coverage = journey_contracts.e2e_coverage(workspace, [])
    if journey_coverage is not None:
        out.setdefault("report", {}).setdefault("e2e", {})["journeyCoverage"] = journey_coverage

    if lh:
        results = _rows(lh.get("results"))
        cats = sorted({k for r in results for k in (r.get("scores") or {})})
        scores = {k: min(r["scores"][k] for r in results if k in (r.get("scores") or {})) for k in cats}
        first = (results[0].get("metrics") or {}) if results else {}
        out["performance"] = {"scores": scores, "metrics": {k.replace("_", " "): v for k, v in first.items()},
                              "measured_on": "Lighthouse · " + ", ".join(str(r.get("route")) for r in results)
                              + (f" · {lh['audited_at']}" if lh.get("audited_at") else "")}

    zap = next((g for g in gaps if "zap" in str(g.get("item", "")).lower()), None)
    audit = next((c for c in commands if _kind(str(c.get("command") or "")) == "audit"), None)
    known = [g for g in gaps if g is not zap and str(g.get("status")) == "known"]
    if zap or audit or known or zap_summary:
        security = {"zap": {"status": (zap or {}).get("status") or "not run",
                            "reason": (zap or {}).get("reason") or ""},
                    "findings": [{"severity": "known", "name": str(g.get("item")), "what": str(g.get("reason"))} for g in known]}
        if zap_summary:
            # The scan's own record supersedes what the builder said about it in prose.
            seen = [*_rows(zap_summary.get("failing")), *_rows(zap_summary.get("warnings"))]
            engine = str(zap_summary.get("engine"))
            security["zap"] = {
                "status": str(zap_summary.get("status") or "recorded"), "engine": engine,
                "reason": (f"[{engine}] " + str(zap_summary.get("reason") or zap_summary.get("note") or "")).strip(),
                "report": zap_summary.get("report"),
                "counts": zap_summary.get("counts") if isinstance(zap_summary.get("counts"), dict) else {},
                "scanMode": "passive baseline" if "passive" in str(zap_summary.get("note") or "").lower() else "baseline",
                "activeScan": False if "no active" in str(zap_summary.get("note") or "").lower() else None,
                "findings": [{"severity": a.get("risk"), "name": f"{a.get('id')} {a.get('name')}",
                              "what": a.get("description")} for a in seen]}
        if audit:
            security["audit"] = {"command": audit.get("command"), "exit_code": audit.get("exit_code"),
                                 "summary": audit.get("note")}
        out["security"] = security
        listed = [{**f, "path": f.get("name")} for f in [*security["findings"], *security["zap"].get("findings", [])]]
        out.setdefault("report", {})["security"] = {**security, "findings": listed,
                                                    "audit_status": "completed" if audit else "not run"}

    reqs = _rows(build.get("requirements"))
    if reqs or commands or gaps:
        text = _requirement_text(workspace)
        met = [r for r in reqs if r.get("status") == "met"]
        evidence = {
            "ready": not any(r["status"] == "failed" and r["kind"] != "audit" for r in rows)
                     and not any(str(g.get("status")) in ("unavailable", "untested", "unmeasured") for g in gaps)
                     and len(met) == len(reqs),
            "revision": built_at, "requiredKinds": sorted({r["kind"] for r in rows}),
            "suites": [{"kind": r["kind"], "suite": r["suite"], "status": r["status"],
                        "exitCode": r["exitCode"], "command": r["command"], "covers": []} for r in rows],
            "limitations": {str(g.get("item")): f"{g.get('status')}: {g.get('reason')}" for g in gaps},
        }
        if reqs:
            evidence["scope"] = {"requirements": [
                {"id": str(r.get("id")), "description": text.get(str(r.get("id")), "") or str(r.get("evidence") or ""),
                 "evidence": _evidence_kinds(str(r.get("evidence") or ""))} for r in reqs]}
            evidence["missingRequirements"] = [{"id": str(r.get("id")), "kind": _evidence_kinds(str(r.get("evidence") or ""))[0]}
                                               for r in reqs if r.get("status") != "met"]
            evidence["coverage"] = {"e2e": {"covered": len(met), "total": len(reqs),
                                            "percent": round(100 * len(met) / len(reqs)), "target": 100,
                                            "status": "passed" if len(met) == len(reqs) else "failed"}}
        report = out.setdefault("report", {})
        report["evidence"] = evidence
        report.setdefault("suite", {"unresolved": [], "suspects": [], "quarantined": [], "failures": []})

    contracts = _contracts(workspace, build, have.get("vitest"), tests)
    if contracts:
        out["contracts"] = contracts

    repairs = _build_repairs(build)
    if repairs:
        out["buildRepairs"] = repairs

    if build:
        out["provenance"] = ("Recorded by the build's own verification — the builder's report and the "
                             "runner artifacts it saved. The separate Testing stage has not run.")
        out["evidenceSource"] = "build"
    return out
