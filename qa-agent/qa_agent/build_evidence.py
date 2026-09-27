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

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BUILD_REPORT = ".agentforge/build/report.json"
HANDOFF = ".agentforge/srs/handoff.json"
QA_DIR = ".agentforge/qa"
LIGHTHOUSE_SUMMARY = ".lighthouseci/summary.json"
ROUTE_PROBE = ".agentforge/qa/routes.json"
ZAP_SUMMARY = ".agentforge/qa/zap/summary.json"
INVENTORY = ".agentforge/qa/coverage-inventory.json"
COVERAGE_SUMMARY = ".agentforge/qa/coverage/coverage-summary.json"
PLAYWRIGHT_JSON = "test-results/results.json"

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


def _from_playwright_json(data: Any) -> dict | None:
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
                tests.append({"index": len(tests) + 1, "project": test.get("projectName") or "",
                              "file": _spec_of(spec.get("file") or file),
                              "suite": " › ".join(here), "title": spec.get("title") or "",
                              "status": status})
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
    exact = _from_playwright_json(_json(workspace / PLAYWRIGHT_JSON))
    if exact:
        found.append({**exact, "source": PLAYWRIGHT_JSON,
                      "at": _iso(workspace / PLAYWRIGHT_JSON), "rank": 1})
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
        flow["stages"].append({"index": len(flow["stages"]) + 1, "label": label, "status": status})
    for flow in flows.values():
        st = [s["status"] for s in flow["stages"]]
        flow.update(stage_total=len(st), stage_passed=st.count("pass"),
                    stage_failed=st.count("fail"), stage_not_reached=st.count("not_reached"))
    return list(flows.values())


def _contracts(workspace: Path, build: dict, vitest: Any) -> list[dict]:
    files = []
    for suite in _rows((vitest or {}).get("testResults") if isinstance(vitest, dict) else []):
        name = str(suite.get("name") or "")
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        except OSError:
            text = ""
        files.append({"file": name.replace("\\", "/").split("/")[-1], "status": suite.get("status") or "", "text": text})
    rows: dict[str, dict] = {}
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
        base = re.sub(r"/\{\w+\}$", "", row["route"])
        for f in files:
            if base in f["text"] or row["handler"].rsplit("/route.", 1)[0] in f["text"]:
                row["tests"].append({"file": f["file"], "status": f["status"] or "recorded"})
    return list(rows.values())


def derive(workspace: Path, have: dict) -> dict:
    """Everything the Testing views can read from what the build left behind."""
    build = _json(workspace / BUILD_REPORT)
    build = build if isinstance(build, dict) else {}
    runs = browser_runs(workspace)
    lh = lighthouse(workspace)
    probe = route_probe(workspace)
    zap_summary = _json(workspace / ZAP_SUMMARY)
    zap_summary = zap_summary if isinstance(zap_summary, dict) and zap_summary.get("engine") else None
    inventory = unit_inventory(workspace)
    coverage = code_coverage(workspace)
    if not (build or runs or lh or probe or zap_summary or inventory or coverage):
        return {}

    out: dict[str, Any] = {}
    if inventory:
        out["unitInventory"] = inventory
    if coverage:
        out["codeCoverage"] = coverage
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
    if runs:
        said = lambda t: f"{t['file']} {t['suite']} {t['title']}"  # noqa: E731
        a11y = [t for t in tests if _A11Y.search(said(t))]
        visual = [t for t in tests if t not in a11y and _VISUAL.search(said(t))]
        journeys = [t for t in tests if t not in a11y and t not in visual]
        flows = _group(journeys, lambda t: True)
        total = sum(f["stage_total"] for f in flows)
        e2e = {"ran": True, "flows": flows, "stage_total": total,
               "stage_passed": sum(f["stage_passed"] for f in flows),
               "stage_failed": sum(f["stage_failed"] for f in flows),
               "stage_not_reached": sum(f["stage_not_reached"] for f in flows),
               "failures": [], "source": runs["source"]}
        if a11y:
            bad = sum(1 for t in a11y if t["status"] == "failed")
            out["accessibility"] = {
                "status": "failed" if bad else "passed" if all(t["status"] == "passed" for t in a11y) else "recorded",
                "audited": len(a11y), "totalRoutes": len(a11y), "passed": len(a11y) - bad, "failed": bad,
                "pages": [{"route": (f"{t['suite']} › " if t["suite"] else "") + t["title"] + (f" [{t['project']}]" if t["project"] else ""),
                           "status": t["status"] if t["status"] in ("passed", "failed") else "recorded"} for t in a11y]}
        out.setdefault("report", {})["e2e"] = e2e
        out["visualRuns"] = {"tests": len(visual), "passed": sum(1 for t in visual if t["status"] == "passed")}

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

    contracts = _contracts(workspace, build, have.get("vitest"))
    if contracts:
        out["contracts"] = contracts

    if build:
        out["provenance"] = ("Recorded by the build's own verification — the builder's report and the "
                             "runner artifacts it saved. The separate Testing stage has not run.")
        out["evidenceSource"] = "build"
    return out
