"""Provenance-safe SRS corpus grounding and deterministic quality evidence.

This module deliberately consumes only the small local catalogue.  Raw public
requirements archives can contain arbitrary prose and must never be treated as
instructions to the SRS agent.  They are used offline by explicit evaluation
tools, with their licence and attribution retained alongside the archive.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "srs-test-sources" / "srs-sources" / "catalog.json"
_ID = re.compile(r"^(?:FR|NFR)-\d{3,}$", re.IGNORECASE)
_MEASURABLE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|ms|milliseconds?|seconds?|minutes?|hours?|days?|"
    r"requests?/?s|rps|users?|transactions?|px|kb|mb|gb|:1)\b|"
    r"\b(?:wcag|iso(?:/iec)?|owasp|p\d{2}|slo|sla)\b", re.IGNORECASE)
_VERIFICATION = {"functional test", "test / inspection", "demonstration / inspection", "analysis"}


def source_catalog() -> list[dict[str, Any]]:
    """Return validated source metadata only, never raw third-party content."""
    try:
        body = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"SRS source catalogue is unavailable: {exc}") from exc
    rows = body.get("sources") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ValueError("SRS source catalogue must contain a sources list")
    checked: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("every SRS source record must be an object")
        required = ("id", "title", "source_url", "format", "license", "ingestion", "quality_evidence")
        missing = [key for key in required if not str(row.get(key) or "").strip()]
        if missing:
            raise ValueError(f"SRS source {row.get('id')!r} is missing: {', '.join(missing)}")
        checked.append(row)
    return checked


def quality_grounding(limit: int = 1500) -> str:
    """A compact, safe-to-prompt provenance summary for the SRS reviewer."""
    lines = ["Curated SRS-corpus evidence (metadata only; never copy examples or invent scope from it):"]
    for row in source_catalog():
        evidence = row.get("quality_evidence") or {}
        score = evidence.get("agentforge_rating", "?")
        lines.append(
            f"- {row['title']} — {row['format']}; source-evidence rating {score}/5; "
            f"use: {row.get('role', '')}; licence/import: {row['license']} / {row['ingestion']}; "
            f"source: {row['source_url']}")
    return "\n".join(lines)[:limit]


def _rows(doc: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [row for row in (doc.get(key) or []) if isinstance(row, dict)]


def _rating(score: int) -> str:
    if score >= 90:
        return "strong"
    if score >= 75:
        return "usable_with_review"
    return "needs_repair"


def audit_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Score objective SRS-writing evidence without grading product scope.

    The score is an AgentForge diagnostic, not a claim that a corpus provider
    rated this customer document.  It does not use an LLM, so it is stable and
    can be supplied to the independent reviewer as a factual readout.
    """
    functional = _rows(doc, "functional_requirements")
    non_functional = _rows(doc, "non_functional_requirements")
    all_requirements = functional + non_functional
    ids = [str(row.get("id") or "").strip() for row in all_requirements]
    findings: list[str] = []
    checks: dict[str, dict[str, Any]] = {}

    checks["requirement_sets"] = {"passed": bool(functional) and bool(non_functional),
                                   "functional_count": len(functional),
                                   "non_functional_count": len(non_functional)}
    if not checks["requirement_sets"]["passed"]:
        findings.append("the SRS needs both functional and non-functional requirements")

    bad_ids = [value or "(blank)" for value in ids if not _ID.match(value)]
    duplicates = sorted({value for value in ids if value and ids.count(value) > 1})
    checks["stable_ids"] = {"passed": not bad_ids and not duplicates,
                            "bad": bad_ids[:8], "duplicates": duplicates[:8]}
    if bad_ids:
        findings.append("requirement IDs must use FR-### or NFR-###")
    if duplicates:
        findings.append("requirement IDs must be unique")

    untestable = [str(row.get("id") or "?") for row in all_requirements
                  if "shall" not in str(row.get("requirement") or "").lower()]
    checks["normative_wording"] = {"passed": not untestable, "missing_shall": untestable[:12]}
    if untestable:
        findings.append("each requirement should use an explicit normative 'shall' statement")

    missing_verification = [str(row.get("id") or "?") for row in all_requirements
                            if str(row.get("verification_method") or "").strip().lower()
                            not in _VERIFICATION]
    checks["verification_method"] = {"passed": not missing_verification,
                                     "missing_or_invalid": missing_verification[:12]}
    if missing_verification:
        findings.append("each requirement needs an approved verification_method")

    missing_rationale = [str(row.get("id") or "?") for row in functional
                         if not str(row.get("rationale") or "").strip()]
    checks["functional_rationale"] = {"passed": not missing_rationale,
                                      "missing": missing_rationale[:12]}
    if missing_rationale:
        findings.append("each functional requirement needs a rationale tied to approved scope")

    vague_nfr = [str(row.get("id") or "?") for row in non_functional
                 if not _MEASURABLE.search(str(row.get("requirement") or ""))]
    checks["measurable_nfr"] = {"passed": not vague_nfr, "unmeasured": vague_nfr[:12]}
    if vague_nfr:
        findings.append("each non-functional requirement needs a measurable threshold or named standard")

    traces = _rows(doc, "requirement_traceability_matrix")
    trace_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in traces:
        trace_by_id.setdefault(str(row.get("requirement_id") or "").strip(), []).append(row)
    functional_ids = [str(row.get("id") or "").strip() for row in functional]
    missing_trace = [value for value in functional_ids if len(trace_by_id.get(value, [])) != 1]
    missing_test_case = [value for value in functional_ids
                         if not str((trace_by_id.get(value) or [{}])[0].get("test_case") or "").strip()]
    checks["traceability"] = {"passed": not missing_trace and not missing_test_case,
                              "not_exactly_one_row": missing_trace[:12],
                              "missing_test_case": missing_test_case[:12]}
    if missing_trace:
        findings.append("every functional requirement needs exactly one traceability row")
    if missing_test_case:
        findings.append("every functional traceability row needs a test_case")

    passed = sum(1 for row in checks.values() if row["passed"])
    score = round(100 * passed / len(checks)) if checks else 0
    # The individual wording/traceability checks are vacuously true for an
    # empty list.  A document with no requirements must never look healthy
    # merely because there was nothing for those checks to inspect.
    if not checks["requirement_sets"]["passed"]:
        score = min(score, 50)
    return {
        "schema_version": 1,
        "method": "deterministic SRS corpus-aligned evidence audit",
        "score": score,
        "rating": _rating(score),
        "checks": checks,
        "findings": findings,
        "sources": [{"id": row["id"], "rating": (row.get("quality_evidence") or {}).get("agentforge_rating"),
                     "ingestion": row["ingestion"]} for row in source_catalog()],
    }


def audit_readout(audit: dict[str, Any]) -> str:
    """A concise factual block for the cloud reviewer, not a prompt from data."""
    checks = audit.get("checks") or {}
    failed = [name.replace("_", " ") for name, row in checks.items()
              if isinstance(row, dict) and not row.get("passed")]
    return (f"- deterministic corpus-aligned evidence rating: {audit.get('score', 0)}/100 "
            f"({audit.get('rating', 'unknown')})\n"
            f"- failed evidence checks: {', '.join(failed) or '(none)'}\n"
            "- treat these as concrete writing/traceability defects only; do not add scope.")


def blocking_findings(audit: dict[str, Any]) -> list[str]:
    """Objective repair reasons that must gate a finished SRS.

    This is intentionally separate from the cloud critic's subjective scores:
    a missing verification method or a missing traceability test case is a
    deterministic defect and must not be accepted because a model says the
    prose is otherwise good.
    """
    if int(audit.get("score", 0)) >= 100:
        return []
    return [str(item) for item in (audit.get("findings") or []) if str(item).strip()]
