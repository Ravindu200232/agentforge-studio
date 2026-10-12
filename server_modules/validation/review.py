"""The specification review's own rules.

Ported from RP-SE-009 `srs-agent/srs_agent/app/agents/reviewer.py`.

Two things are load-bearing here and both are deliberate:

* A finding against a requirement id that is not in the document cannot be
  fixed, so the verdict is rejected and asked for again. A round spent on a
  phantom requirement is a round the cap has already spent.
* Python decides whether the draft passed, not the model. A reviewer asked to
  judge its own judgement tends to accept, so `verdict` is kept for the record
  and `satisfied()` is what actually gates the stage.
"""
from __future__ import annotations

from typing import Any, Callable

SEVERITIES = ("blocker", "major", "minor")
SCORES = ("functional", "non_functional", "security", "ambiguity", "traceability")

# A score below this is a blocking judgement even when no single requirement was
# named — "the security section is thin" is a real finding without a culprit.
FLOOR = 3

AUDIT_SKILLS = ("functional-requirements", "non-functional-quality", "security-architecture")


def requirement_ids(doc: dict) -> set[str]:
    found: set[str] = set()
    for key in ("functional_requirements", "non_functional_requirements"):
        for item in (doc.get(key) or []):
            if isinstance(item, dict) and item.get("id"):
                found.add(str(item["id"]))
    return found


def review_validator(doc: dict) -> Callable[[Any], dict]:
    """Reject a verdict that is not actionable."""
    known = requirement_ids(doc)

    def check(body: Any) -> dict:
        if not isinstance(body, dict):
            raise ValueError("The review must be a JSON object.")

        scores = body.get("scores") or {}
        if not isinstance(scores, dict):
            raise ValueError("`scores` must be an object.")
        for key in SCORES:
            value = scores.get(key)
            if not isinstance(value, (int, float)) or not 0 <= float(value) <= 5:
                raise ValueError(f"`scores.{key}` must be a number from 0 to 5.")

        findings = body.get("findings") or []
        if not isinstance(findings, list):
            raise ValueError("`findings` must be a list.")
        for finding in findings:
            if not isinstance(finding, dict):
                raise ValueError("Each finding must be an object.")
            if str(finding.get("severity", "")).lower() not in SEVERITIES:
                raise ValueError(f"`severity` must be one of {', '.join(SEVERITIES)}.")
            rid = str(finding.get("requirement_id") or "").strip()
            if rid and known and rid not in known:
                raise ValueError(
                    f"`requirement_id` {rid!r} is not in the document. "
                    f"Use one of: {', '.join(sorted(known)[:12])}.")
            if not str(finding.get("problem") or "").strip():
                raise ValueError("Each finding needs a `problem`.")
        return body

    return check


def blockers(verdict: dict) -> list[dict]:
    return [f for f in (verdict.get("findings") or [])
            if str(f.get("severity", "")).lower() == "blocker"]


def satisfied(verdict: dict) -> bool:
    """Whether the draft passed. The model's own `verdict` string is not obeyed."""
    if blockers(verdict):
        return False
    scores = verdict.get("scores") or {}
    return all(float(scores.get(key, 0)) >= FLOOR for key in SCORES)


def digest(doc: dict, limit: int = 24000) -> str:
    """The parts of the document a reviewer needs, without the parts it does not."""
    import json

    keep = ("project_name", "app_summary", "functional_requirements",
            "non_functional_requirements", "security_requirements", "roles",
            "business_workflows", "acceptance_criteria", "ambiguities",
            "requirement_traceability_matrix", "validation_rules")
    return json.dumps({k: doc.get(k) for k in keep if doc.get(k)},
                      ensure_ascii=False)[:limit]


def findings_text(verdict: dict) -> str:
    """The verdict as repair instructions the SRS agent can act on."""
    lines: list[str] = []
    for finding in (verdict.get("findings") or []):
        rid = str(finding.get("requirement_id") or "").strip()
        lines.append(
            f"- [{str(finding.get('severity', 'minor')).lower()}]"
            f"{' ' + rid if rid else ''}: {finding.get('problem', '')}"
            + (f"\n  Rewrite as: {finding['suggested_rewrite']}"
               if finding.get("suggested_rewrite") else ""))
    for missing in (verdict.get("missing_requirements") or []):
        lines.append(f"- [missing {missing.get('kind', 'requirement')}] "
                     f"{missing.get('topic', '')}: {missing.get('why', '')}")
    scores = verdict.get("scores") or {}
    low = [f"{key} scored {scores.get(key)}" for key in SCORES
           if float(scores.get(key, 5)) < FLOOR]
    if low:
        lines.append("- [thin] " + "; ".join(low)
                     + " — strengthen these areas without widening scope.")
    return "\n".join(lines) or "(no findings)"


def stamp(doc: dict, status: str, rounds: int, detail: str,
          verdict: dict | None = None, structural: dict | None = None) -> None:
    """Record the outcome on the document itself, where the studio reads it."""
    review = doc.setdefault("requirements_quality_review", {})
    if isinstance(review, dict):
        review["reviewer"] = {
            "status": status,
            "iterations_used": int(rounds),
            "stopped_because": detail,
            "final_scores": (verdict or {}).get("scores") or {},
            "unresolved_findings": (verdict or {}).get("findings") or [],
        }
        if structural is not None:
            review["reviewer"]["structural_readout"] = structural
