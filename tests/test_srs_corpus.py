"""Tests for the provenance-safe SRS evaluation corpus metadata and audit."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "srs_corpus_validation", ROOT / "server_modules" / "validation" / "corpus.py")
assert SPEC and SPEC.loader
corpus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus)


def good_document():
    functional = [
        {"id": f"FR-00{number}", "requirement": "The system shall record a booking.",
         "verification_method": "Functional Test", "rationale": "Approved booking flow"}
        for number in range(1, 4)
    ]
    non_functional = [
        {"id": f"NFR-00{number}", "requirement": "The system shall respond within 200 ms.",
         "verification_method": "Analysis"}
        for number in range(1, 4)
    ]
    return {
        "functional_requirements": functional,
        "non_functional_requirements": non_functional,
        "requirement_traceability_matrix": [
            {"requirement_id": row["id"], "test_case": f"TC-{index:03d}"}
            for index, row in enumerate(functional, 1)
        ],
    }


class SrsCorpusTests(unittest.TestCase):
    def test_every_catalogue_record_has_provenance_and_an_ingestion_boundary(self):
        rows = corpus.source_catalog()
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            self.assertTrue(row["source_url"].startswith("https://"))
            self.assertIn(row["ingestion"], {
                "allowed_with_attribution", "allowed_with_attribution_and_share_alike", "reference_only"})
            self.assertIn("agentforge_rating", row["quality_evidence"])

    def test_catalogue_grounding_is_metadata_not_raw_corpus_content(self):
        note = corpus.quality_grounding()
        self.assertIn("metadata only", note)
        self.assertIn("PURE", note)
        self.assertLessEqual(len(note), 1500)

    def test_a_complete_document_receives_a_strong_rating(self):
        audit = corpus.audit_document(good_document())
        self.assertEqual(audit["score"], 100)
        self.assertEqual(audit["rating"], "strong")

    def test_the_audit_explains_testability_and_traceability_gaps(self):
        doc = good_document()
        doc["functional_requirements"][0].pop("verification_method")
        doc["non_functional_requirements"][0]["requirement"] = "The system shall be fast."
        doc["requirement_traceability_matrix"][0].pop("test_case")
        audit = corpus.audit_document(doc)
        self.assertEqual(audit["rating"], "needs_repair")
        self.assertIn("verification_method", audit["checks"])
        self.assertFalse(audit["checks"]["measurable_nfr"]["passed"])
        self.assertFalse(audit["checks"]["traceability"]["passed"])

    def test_an_empty_specification_cannot_receive_a_high_rating(self):
        audit = corpus.audit_document({})
        self.assertEqual(audit["rating"], "needs_repair")
        self.assertFalse(audit["checks"]["requirement_sets"]["passed"])

    def test_any_objective_gap_becomes_a_required_repair_finding(self):
        doc = good_document()
        self.assertEqual(corpus.blocking_findings(corpus.audit_document(doc)), [])
        doc["functional_requirements"][0].pop("rationale")
        findings = corpus.blocking_findings(corpus.audit_document(doc))
        self.assertIn("rationale", findings[0])
