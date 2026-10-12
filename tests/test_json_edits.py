"""A repair changes only what it names: edits to the SRS JSON instead of a whole new document."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules.validation import json_edits  # noqa: E402

DOC = {
    "functional_requirements": [{"id": "FR-001", "requirement": "The system shall list items."},
                                {"id": "FR-002", "requirement": "The system shall be good."}],
    "protected_pages": [{"page_name": "Orders", "route": "/admin/orders", "sections": ["table"]}],
    "requirement_traceability_matrix": [{"requirement_id": "FR-001", "pages": ["/"]}],
    "app_summary": {"app_name": "Example"},
}


class JsonEditTests(unittest.TestCase):
    def test_set_add_and_remove_by_an_items_own_field(self):
        out = json_edits.apply_edits(DOC, {"edits": [
            {"op": "set", "path": "functional_requirements[id=FR-002].requirement",
             "value": "The system shall respond within 200 ms."},
            {"op": "add", "path": "requirement_traceability_matrix", "value": {"requirement_id": "FR-002", "pages": ["/"]}},
            {"op": "add", "path": "protected_pages[route=/admin/orders].sections", "value": "filters"},
            {"op": "set", "path": "app_summary.short_description", "value": "A short description."},
            {"op": "remove", "path": "functional_requirements[id=FR-001]"},
        ]})
        self.assertEqual([r["id"] for r in out["functional_requirements"]], ["FR-002"])
        self.assertEqual(out["functional_requirements"][0]["requirement"], "The system shall respond within 200 ms.")
        self.assertEqual(len(out["requirement_traceability_matrix"]), 2)
        self.assertEqual(out["protected_pages"][0]["sections"], ["table", "filters"])
        self.assertEqual(out["app_summary"]["short_description"], "A short description.")
        self.assertEqual(len(DOC["functional_requirements"]), 2)   # the original is never changed

    def test_an_edit_that_does_not_fit_is_reported_with_its_number(self):
        with self.assertRaises(json_edits.EditError) as caught:
            json_edits.apply_edits(DOC, [
                {"op": "set", "path": "functional_requirements[id=FR-009].requirement", "value": "x"},
                {"op": "rename", "path": "app_summary"},
                {"op": "remove", "path": "app_summary.missing"},
            ])
        message = str(caught.exception)
        self.assertIn("edit 1 (set functional_requirements[id=FR-009].requirement): no item in functional_requirements has id=FR-009", message)
        self.assertIn("edit 2", message)
        self.assertIn("edit 3", message)
        with self.assertRaisesRegex(json_edits.EditError, "at least one edit"):
            json_edits.apply_edits(DOC, {"edits": []})

    def test_the_srs_repair_keeps_only_edits_that_leave_a_valid_srs(self):
        from srs_agent import document as srs_document

        envelope = {"srs_document": {"functional_requirements": []}}
        with mock.patch.object(srs_document.srs_schema, "srs_validator", side_effect=lambda env: env) as validate:
            check = srs_document._repair_edits_validator(envelope)
            repaired, applied = check({"edits": [{"op": "add", "path": "functional_requirements",
                                                  "value": {"id": "FR-001", "requirement": "The system shall ..."}}]})
        self.assertEqual(applied, 1)
        self.assertEqual(repaired["srs_document"]["functional_requirements"][0]["id"], "FR-001")
        self.assertEqual(envelope["srs_document"]["functional_requirements"], [])
        validate.assert_called_once()

        with mock.patch.object(srs_document.srs_schema, "srs_validator",
                               side_effect=ValueError("the specification does not match the required shape")):
            with self.assertRaisesRegex(ValueError, "required shape"):
                srs_document._repair_edits_validator(envelope)(
                    {"edits": [{"op": "set", "path": "functional_requirements", "value": []}]})


if __name__ == "__main__":
    unittest.main()
