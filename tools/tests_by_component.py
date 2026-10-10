"""The automated tests, grouped by the component (and so the team member) whose behaviour they verify.

    python tools/tests_by_component.py            every group
    python tools/tests_by_component.py c3         one group (c1, c2, c3, c4 or shared)

Prints the result of each group and writes it to tools/tests_by_component.json.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent", "tests", ".deps/py312"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

GROUPS = {
    "c1": ("Requirements interview, specification, diagrams and wireframes", "Gunasena R M K N (IT22078582)", [
        "all_diagram_notation", "class_diagram_standard", "diagram_drawing", "diagram_look", "diagram_renderer",
        "diagram_review_context", "handoff", "interview_skip", "journey_contract", "json_edits", "spec_resume",
        "srs_corpus", "srs_corpus_fetch", "srs_reconcile", "use_case_layout", "wireframe", "wireframe_html"]),
    "c2": ("Generative engine, prototype, app builder, context memory and data layer", "Subasinha P A R B (IT22098450)", [
        "agent", "app_text", "auth_guide", "build", "changes", "chat_media", "cli", "cloud_streaming",
        "compaction_progress", "connection_notice", "database_panel", "failure_echo", "fast_stop", "fresh_context",
        "hidden_start_process", "journey_walk", "llm_tools", "mcp_client", "model_choice", "mongo_check", "mongo_connect",
        "ollama_cloud", "permissions", "phases", "preflight", "preview_live", "preview_runtime", "preview_stale_build",
        "prompt_too_long", "prototype", "pty_process", "run_command", "session_retry", "supabase_connect",
        "thinking_level", "vision", "web_app"]),
    "c3": ("Multi-layer verification of the built application", "Hamna R H F (IT22516916)", [
        "browser_inspect", "build_report", "e2e_once", "e2e_review", "qa_report", "qa_report_project", "qa_report_provenance",
        "scaffold_qa", "screenshot", "screenshot_tool", "visual_review"]),
    "c4": ("Autonomous multi-target deployment", "Bandara R M M P (IT22249166)", [
        "cli_monitor", "cli_signin", "deploy_accounts_refresh", "deploy_asks_midway", "deploy_flow", "deploy_vars", "stacks"]),
    "shared": ("Shared platform and integration", "the whole team", [
        "availability", "desktop_backend", "plugins", "privacy", "reliability", "stage_evidence", "store", "studio",
        "versions", "wsd_slow_client"]),
}


def run(key: str) -> dict:
    title, owner, names = GROUPS[key]
    suite = unittest.TestSuite()
    counts = {}
    for name in names:
        loaded = unittest.defaultTestLoader.loadTestsFromName(f"test_{name}")
        counts[f"tests/test_{name}.py"] = loaded.countTestCases()
        suite.addTests(loaded)
    started = time.time()
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    failed = [str(t[0]) for t in result.failures + result.errors]
    return {"group": key, "component": title, "owner": owner, "modules": [f"tests/test_{n}.py" for n in names], "per_module": counts,
            "tests": result.testsRun, "passed": result.testsRun - len(failed) - len(result.skipped),
            "failed": len(failed), "skipped": len(result.skipped), "seconds": round(time.time() - started, 1),
            "failures": failed[:20]}


def main(keys: list[str]) -> None:
    rows = [run(k) for k in keys]
    out = pathlib.Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for r in rows:
        print(f"{r['group']:7} {r['component']:34} {r['owner']:24} modules {len(r['modules']):3}  tests {r['tests']:4}  "
              f"passed {r['passed']:4}  failed {r['failed']}  skipped {r['skipped']}  ({r['seconds']}s)")
        for f in r["failures"]:
            print("        failed:", f)


if __name__ == "__main__":
    main(sys.argv[1:] or list(GROUPS))
