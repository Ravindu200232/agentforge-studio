"""The Testing views' evidence as one readable document (Markdown, printed to PDF by `server_modules.pdf`).

It reads only what `verify.report()` already collected - the saved QA report merged with the
runner files (`evidence.collect`) - and writes down what is there. A section with nothing
recorded says so instead of being left out, so a missing layer stays visible in print too.
"""
from __future__ import annotations

from typing import Any


def _rows(value: Any) -> list[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _cell(value: Any) -> str:
    return " ".join(str("" if value is None else value).split()).replace("|", "\\|") or "—"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip() or '_Nothing was recorded for this layer._'}\n"


def _layers(report: dict) -> str:
    layers = _rows(report.get("layers"))
    if layers:
        return _table(["Layer", "Status", "Result", "Command", "Exit"],
                      [[row.get("layer"), row.get("status"), row.get("result"), row.get("command"),
                        row.get("exit_code")] for row in layers])
    timeline = _rows(report.get("timeline"))
    return _table(["Kind", "Status", "What it showed", "Command", "Exit"],
                  [[row.get("kind"), row.get("status"), row.get("suite"), row.get("command"),
                    row.get("exitCode")] for row in timeline]) if timeline else ""


def _unit(report: dict) -> str:
    vitest = report.get("vitest") if isinstance(report.get("vitest"), dict) else {}
    suites = _rows(vitest.get("testResults"))
    if not suites:
        return ""
    rows, failed = [], []
    for suite in suites:
        cases = _rows(suite.get("assertionResults"))
        passed = sum(1 for case in cases if case.get("status") == "passed")
        rows.append([str(suite.get("name") or "").replace("\\", "/").split("/")[-1], f"{passed}/{len(cases)}",
                     suite.get("status")])
        failed += [" › ".join([*map(str, case.get("ancestorTitles") or []), str(case.get("title") or "")])
                   for case in cases if case.get("status") == "failed"]
    head = (f"{vitest.get('numPassedTests', 0)}/{vitest.get('numTotalTests', 0)} test cases passed "
            f"across {len(suites)} files.")
    body = head + "\n\n" + _table(["File", "Passed", "Status"], rows)
    if failed:
        body += "\n\n**Failed:**\n\n" + "\n".join(f"- {_cell(name)}" for name in failed)
    return body


def _e2e(report: dict) -> str:
    e2e = (report.get("report") or {}).get("e2e") if isinstance(report.get("report"), dict) else None
    e2e = e2e if isinstance(e2e, dict) else {}
    parts = []
    coverage = e2e.get("journeyCoverage") if isinstance(e2e.get("journeyCoverage"), dict) else {}
    journeys = _rows(coverage.get("journeys"))
    if journeys:
        parts.append(f"{coverage.get('passed', 0)}/{coverage.get('required', len(journeys))} required user "
                     f"journeys passed.")
        for journey in journeys:
            who = f" — as {journey['who']}" if journey.get("who") else ""
            parts.append(f"### {journey.get('id')} {journey.get('workflow_name') or ''}{who} "
                         f"({journey.get('status')})")
            steps = [str(step) for step in journey.get("steps") or [] if str(step).strip()]
            if steps:
                parts.append("\n".join(f"{number}. {_cell(step)}" for number, step in enumerate(steps, 1)))
            tests = _rows(journey.get("tests"))
            if tests:
                parts.append("Proved by: " + "; ".join(f"{_cell(t.get('title'))} ({t.get('status')})" for t in tests))
    for flow in _rows(e2e.get("flows")):
        stages = _rows(flow.get("stages"))
        parts.append(f"### {flow.get('title') or 'Browser tests'} — "
                     f"{flow.get('stage_passed', 0)}/{flow.get('stage_total', len(stages))} passed")
        parts.append(_table(["#", "Stage", "Status", "Seconds"],
                            [[stage.get("index"), stage.get("label"), stage.get("status"), stage.get("seconds")]
                             for stage in stages]))
    return "\n\n".join(parts)


def _accessibility(report: dict) -> str:
    a11y = report.get("accessibility") if isinstance(report.get("accessibility"), dict) else {}
    if not a11y:
        return ""
    lines = [f"Status: **{a11y.get('status') or 'recorded'}**"]
    if a11y.get("audited") is not None:
        lines.append(f"Pages audited: {a11y.get('audited')} · passed {a11y.get('passed', 0)} · "
                     f"failed {a11y.get('failed', 0)}")
    if a11y.get("declaredDetail"):
        lines.append(f"Recorded by the build: {a11y['declaredDetail']}")
    body = "\n\n".join(lines)
    pages = _rows(a11y.get("pages"))
    if pages:
        body += "\n\n" + _table(["Page", "Status"], [[page.get("route"), page.get("status")] for page in pages])
    return body


def _performance(report: dict) -> str:
    perf = report.get("performance") if isinstance(report.get("performance"), dict) else {}
    scores = perf.get("scores") if isinstance(perf.get("scores"), dict) else {}
    if not scores:
        return ""
    return (_table(["Category", "Lowest score"], [[name, value] for name, value in scores.items()])
            + (f"\n\nMeasured on: {perf['measured_on']}" if perf.get("measured_on") else ""))


def _security(report: dict) -> str:
    security = report.get("security") if isinstance(report.get("security"), dict) else {}
    zap = security.get("zap") if isinstance(security.get("zap"), dict) else {}
    if not zap:
        return ""
    body = f"OWASP ZAP: **{zap.get('status') or 'recorded'}**" + (f" — {zap['reason']}" if zap.get("reason") else "")
    findings = _rows(zap.get("findings"))
    if findings:
        body += "\n\n" + _table(["Risk", "Finding"], [[row.get("severity"), row.get("name")] for row in findings])
    return body


def _api(report: dict) -> str:
    contracts = _rows(report.get("contracts"))
    if not contracts:
        return ""
    rows = []
    for row in contracts:
        tests = _rows(row.get("tests"))
        rows.append([row.get("route"), " · ".join(row.get("methods") or []),
                     "; ".join(f"{t.get('kind') or 'unit'} {t.get('title') or t.get('file')} ({t.get('status')})"
                               for t in tests) or "no linked test"])
    return _table(["Route", "Methods", "Linked tests"], rows)


def markdown_of(report: dict, title: str) -> str:
    """The whole test report, section by section, as Markdown."""
    build = report.get("build") if isinstance(report.get("build"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    head = [f"# Test report — {title}"]
    if report.get("recordedAt"):
        head.append(f"Recorded {report['recordedAt']}")
    if summary:
        head.append(f"**{summary.get('pass', 0)} passed · {summary.get('fail', 0)} failed · "
                    f"{summary.get('warn', 0)} warnings**")
    if report.get("summaryText"):
        head.append(str(report["summaryText"]))
    if report.get("provenance"):
        head.append(f"_{report['provenance']}_")
    sections = [
        _section("Layers", _layers(report)),
        _section("Unit & integration tests", _unit(report)),
        _section("End-to-end journeys", _e2e(report)),
        _section("Accessibility", _accessibility(report)),
        _section("Performance", _performance(report)),
        _section("Security", _security(report)),
        _section("API handlers", _api(report)),
        _section("Requirements", _table(["Id", "Status", "Evidence"],
                                        [[r.get("id"), r.get("status"), r.get("evidence")]
                                         for r in _rows(build.get("requirements"))])
                 if _rows(build.get("requirements")) else ""),
        _section("Not proven — recorded gaps",
                 "\n".join(f"- **{_cell(g.get('item'))}** ({g.get('status') or 'gap'}): {_cell(g.get('reason'))}"
                           for g in _rows(build.get("gaps")))),
        _section("Repairs during the build",
                 "\n".join(f"- **{_cell(r.get('where'))}** — {_cell(r.get('problem'))} → {_cell(r.get('fix'))}"
                           for r in _rows((report.get("buildRepairs") or {}).get("items")))),
    ]
    return "\n\n".join(head) + "\n\n" + "\n".join(sections)
