"""The SRS journey artifact is the required, verifiable E2E contract."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "qa-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from qa_agent import build_evidence, evidence  # noqa: E402
from server_modules import journeys  # noqa: E402
from srs_agent import document as srs_document  # noqa: E402


DOCUMENT = {
    "roles": [{"role_key": "visitor", "role_name": "Visitor"}],
    "public_pages": [
        {"page_name": "Catalogue", "route": "/"},
        {"page_name": "Checkout", "route": "/checkout"},
    ],
    "protected_pages": [],
    "business_workflows": [
        {"workflow_name": "Visitor orders a cake", "who": "Visitor",
         "steps": ["Open Catalogue", "Add a cake to the basket", "Open Checkout", "Place the order"]},
        {"workflow_name": "Visitor checks an order", "who": "Visitor",
         "steps": ["Open Checkout", "Review the order"]},
    ],
}


ROLE_DOCUMENT = {
    "roles": [{"role_key": "visitor", "role_name": "Visitor"}, {"role_key": "member", "role_name": "Member"},
              {"role_key": "site_admin", "role_name": "Site Admin"}],
    "public_pages": [
        {"page_name": "Overview", "route": "/"},
        {"page_name": "Request Form", "route": "/request"},
        {"page_name": "Request Summary", "route": "/request/[id]/done"},
    ],
    "protected_pages": [
        {"page_name": "My Requests", "route": "/account/requests", "login_required": True, "allowed_roles": ["Member"]},
        {"page_name": "Contact Details", "route": "/account/contact", "login_required": True, "allowed_roles": "Member"},
        {"page_name": "Discount Codes", "route": "/admin/discounts", "login_required": True, "allowed_roles": ["site_admin"]},
    ],
    "business_workflows": [
        {"workflow_name": "Visitor sends a request", "who": "Visitor",
         "steps": ["Visitor opens the Request Form and enters their contact details",
                   "Visitor types a discount code and sees the new total",
                   "Visitor reaches the Request Summary"]},
        {"workflow_name": "Member reviews requests", "who": "Member",
         "steps": ["Member opens My Requests", "Member updates the contact details"],
         "step_routes": ["/account/requests", "/admin/discounts"]},
    ],
}


class JourneyContractTests(unittest.TestCase):
    def test_srs_writer_saves_the_contract_as_its_own_json_artifact(self):
        class Session:
            def __init__(self, root):
                self.root = root
                self.workspace = root

            def write_record(self, *parts, data):
                path = self.root.joinpath(".agentforge", *parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")
                return path

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(srs_document.bus, "file_written"), \
             mock.patch.object(srs_document.bus, "log"):
            session = Session(Path(folder))
            written = srs_document._write_user_journeys(session, "prj", DOCUMENT)
            saved = json.loads((Path(folder) / ".agentforge/srs/user-journeys.json").read_text(encoding="utf-8"))

        self.assertEqual(saved, written)
        self.assertEqual(saved["journeys"][0]["id"], "UJ-001")

    def test_contract_has_only_product_journeys_with_stable_ids(self):
        contract = journeys.journey_contract_for(DOCUMENT)

        self.assertEqual(set(contract), {"schema", "journeys"})
        self.assertEqual(contract["schema"], journeys.JOURNEY_SCHEMA)
        first, second = contract["journeys"]
        self.assertEqual((first["id"], second["id"]), ("UJ-001", "UJ-002"))
        self.assertEqual(set(first), {"id", "workflow_name", "who", "steps"})
        self.assertEqual(first["steps"][0], {
            "id": "UJ-001-S01", "step": "Open Catalogue", "route": "/", "named": True})
        # A step without a page name stays on the preceding concrete page.
        self.assertEqual(first["steps"][1]["route"], "/")
        self.assertEqual(first["steps"][2]["route"], "/checkout")
        self.assertEqual(first["steps"][3]["route"], "/checkout")

    def test_only_passing_journey_tests_cover_the_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            path = workspace / journeys.JOURNEY_ARTIFACT
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(journeys.journey_contract_for(DOCUMENT)), encoding="utf-8")
            coverage = journeys.e2e_coverage(workspace, [
                {"file": "e2e/orders.spec.js", "suite": "", "title": "[UJ-001] Visitor orders a cake", "status": "passed"},
                {"file": "e2e/orders.spec.js", "suite": "", "title": "[UJ-002] Visitor checks an order", "status": "failed"},
            ])

        self.assertEqual(coverage["required"], 2)
        self.assertEqual(coverage["covered"], 2)
        self.assertEqual(coverage["passed"], 1)
        self.assertEqual(coverage["missing"], [])
        self.assertEqual(coverage["failed"], ["UJ-002"])
        self.assertEqual(coverage["status"], "failed")

    def test_visual_or_smoke_tests_do_not_hide_a_missing_journey(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            path = workspace / journeys.JOURNEY_ARTIFACT
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(journeys.journey_contract_for(DOCUMENT)), encoding="utf-8")
            results = {
                "stats": {"duration": 1000},
                "suites": [{
                    "title": "journeys.spec.js", "file": "e2e/journeys.spec.js",
                    "specs": [{"title": "[UJ-001] Visitor orders a cake", "tests": [
                        {"projectName": "desktop", "results": [{"status": "passed"}]}
                    ]}], "suites": [],
                }, {
                    "title": "visual.spec.js", "file": "e2e/visual.spec.js",
                    "specs": [{"title": "[UJ-002] screenshot", "tests": [
                        {"projectName": "desktop", "results": [{"status": "passed"}]}
                    ]}], "suites": [],
                }],
            }
            target = workspace / "test-results" / "results.json"
            target.parent.mkdir()
            target.write_text(json.dumps(results), encoding="utf-8")
            derived = build_evidence.derive(workspace, {})

        coverage = derived["report"]["e2e"]["journeyCoverage"]
        self.assertEqual(coverage["passed"], 1)
        self.assertEqual(coverage["missing"], ["UJ-002"])
        self.assertEqual(coverage["status"], "failed")

    def test_runner_coverage_overrides_a_stale_agent_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            contract_path = workspace / journeys.JOURNEY_ARTIFACT
            contract_path.parent.mkdir(parents=True)
            contract_path.write_text(json.dumps(journeys.journey_contract_for(DOCUMENT)), encoding="utf-8")
            build = workspace / ".agentforge/build/report.json"
            build.parent.mkdir(parents=True)
            build.write_text(json.dumps({"project": "prj"}), encoding="utf-8")
            collected = evidence.collect(workspace, {
                "report": {"e2e": {"journeyCoverage": {"status": "passed", "required": 2}}}
            })

        coverage = collected["report"]["e2e"]["journeyCoverage"]
        self.assertEqual(coverage["missing"], ["UJ-001", "UJ-002"])
        self.assertEqual(coverage["status"], "failed")


if __name__ == "__main__":
    unittest.main()


class JourneyRouteTests(unittest.TestCase):
    """Each step on a page its role can open: from the SRS's own step_routes when they hold, else from the page it names."""

    def test_a_step_goes_to_the_page_it_names_never_a_page_its_role_cannot_open(self):
        visitor, member = journeys.user_journeys_for(ROLE_DOCUMENT)
        # "contact details" and "discount code" are shared words with signed-in pages a visitor cannot open
        self.assertEqual([s["route"] for s in visitor["steps"]], ["/request", "/request", "/request/[id]/done"])
        self.assertFalse(visitor["steps"][1]["named"])
        # a valid SRS route is kept; one the member cannot open is replaced
        self.assertEqual([s["route"] for s in member["steps"]], ["/account/requests", "/account/contact"])

    def test_wrong_step_routes_are_reported_and_filled(self):
        doc = json.loads(json.dumps(ROLE_DOCUMENT))
        problems = journeys.journey_problems(doc)
        self.assertIn('"Visitor sends a request" has 3 steps but 0 step_routes', problems)
        self.assertTrue(any("Member reviews requests" in p and "/admin/discounts" in p and "cannot open" in p for p in problems))
        self.assertEqual(journeys.fill_step_routes(doc), 4)
        self.assertEqual(journeys.journey_problems(doc), [])
        self.assertEqual(doc["business_workflows"][0]["step_routes"], ["/request", "/request", "/request/[id]/done"])

    def test_the_srs_fixes_journey_routes_with_the_model_and_never_fails_on_them(self):
        def corrected(**kwargs):
            answer = {"workflows": [{"workflow_name": "Visitor sends a request",
                                     "step_routes": ["/request", "/request", "/request/[id]/done"]},
                                    {"workflow_name": "Member reviews requests",
                                     "step_routes": ["/account/requests", "/account/contact"]}]}
            return kwargs["validator"](answer)

        with mock.patch.object(srs_document.llm, "complete_json", side_effect=corrected) as model, \
             mock.patch.object(srs_document.bus, "log"):
            envelope = srs_document._validate_journeys("prj", {"srs_document": json.loads(json.dumps(ROLE_DOCUMENT))})
        self.assertEqual(model.call_count, 1)
        self.assertIn("/admin/discounts", model.call_args.kwargs["user"])
        self.assertEqual(journeys.journey_problems(envelope["srs_document"]), [])

        # a model answer that is still wrong is rejected by the validator; the pages the steps name place them instead
        with mock.patch.object(srs_document.llm, "complete_json", side_effect=ValueError("still wrong")), \
             mock.patch.object(srs_document.bus, "log"):
            envelope = srs_document._validate_journeys("prj", {"srs_document": json.loads(json.dumps(ROLE_DOCUMENT))})
        flows = envelope["srs_document"]["business_workflows"]
        self.assertEqual(flows[1]["step_routes"], ["/account/requests", "/account/contact"])
        self.assertEqual(journeys.journey_problems(envelope["srs_document"]), [])

    def test_a_validator_rejects_a_route_the_role_cannot_open(self):
        check = srs_document._journey_routes_validator(ROLE_DOCUMENT, {"Visitor sends a request"})
        with self.assertRaisesRegex(ValueError, "cannot open"):
            check({"workflows": [{"workflow_name": "Visitor sends a request",
                                  "step_routes": ["/request", "/admin/discounts", "/request/[id]/done"]}]})

    def test_app_md_shows_the_page_of_each_step(self):
        from srs_agent import handoff

        doc = json.loads(json.dumps(ROLE_DOCUMENT))
        journeys.fill_step_routes(doc)
        text = handoff.app_md(doc)
        self.assertIn("1. Visitor opens the Request Form and enters their contact details — on `/request`", text)
