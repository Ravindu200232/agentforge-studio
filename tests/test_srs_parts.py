"""The specification is written in parts at the same time and joined; a part that fails is asked for once more on its own,
and only a part that fails twice means the one-call path."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from srs_agent import document, interview  # noqa: E402

PLAN = {"app_name": "Corner Shop", "screens": [{"name": "Sign In", "route": "/login", "who": ["Visitor"]},
                                              {"name": "Products", "route": "/products", "who": ["Owner"]}],
        "records": [{"name": "Product", "keeps": ["Name", "Price"]}]}


def requirement(n):
    return {"id": f"FR-00{n}", "module": "Products", "requirement": f"The system shall do thing {n}.", "priority": "high",
            "allowed_roles": ["Owner"], "verification_method": "Functional Test", "rationale": "Selling products."}


PARTS = {
    "frame": {"document_title": "Software Requirements Specification", "project_name": "Corner Shop",
              "system_category": "Retail", "app_type": {"primary_type": "web app"},
              "app_summary": {"app_name": "Corner Shop", "short_description": "A till.", "business_goal": "Sell."},
              "roles": [{"role_key": "owner", "role_name": "Owner", "description": "Runs the shop."}],
              "public_pages": [{"page_name": "Sign In", "route": "/login"}],
              "protected_pages": [{"page_name": "Products", "route": "/products"}]},
    "tables": {"database_design": {"tables": [{"table_name": "products"}], "relationships": []}},
    "api": {"api_design": [], "validation_rules": []},
    "requirements": {"functional_requirements": [requirement(n) for n in (1, 2, 3)],
                     "requirement_traceability_matrix": [{"requirement_id": f"FR-00{n}", "module": "Products",
                                                          "pages": ["/products"], "tables": ["products"],
                                                          "test_case": f"TC-00{n}"} for n in (1, 2, 3)]},
    "quality": {"non_functional_requirements": [{"id": f"NFR-00{n}", "category": "Performance",
                                                 "requirement": "The system shall answer within 200 ms.",
                                                 "verification_method": "Analysis"} for n in (1, 2, 3)],
                "security_requirements": ["Passwords are hashed."], "business_workflows": []},
}


class PartsTests(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(memory_digest=lambda: "", workspace=Path("."))
        self.users: list[str] = []

    def model(self, fail="", times=99):
        left = {"failures": times}

        def complete_json(system="", user="", validator=None, label="", **kwargs):
            self.users.append(user)
            name = label.split(":", 1)[1] if ":" in label else ""
            if name and name == fail and left["failures"] > 0:
                left["failures"] -= 1
                raise ValueError("the part could not be written")
            data = PARTS[name] if name else {k: v for part in PARTS.values() for k, v in part.items()}
            return validator({"srs_document": {**data}})
        return complete_json

    def write(self, model):
        with mock.patch.object(document.llm, "complete_json", model), \
                mock.patch.object(interview, "full_transcript", return_value="Q: Who sells? A: The owner."), \
                mock.patch.object(document.bus, "phase"), mock.patch.object(document.bus, "log") as logged:
            envelope = document._write_document(self.session, "prj_parts", {"name": "Corner Shop", "stack": "nextjs"}, PLAN)
        return envelope, logged

    def test_the_parts_are_joined_into_one_valid_specification_with_the_same_names(self):
        self.assertEqual(set(document.PARTS), set(PARTS))
        envelope, _ = self.write(self.model())
        doc = envelope["srs_document"]
        self.assertEqual(len(self.users), len(document.PARTS))
        self.assertEqual(len(doc["functional_requirements"]), 3)
        self.assertEqual(doc["protected_pages"][0]["route"], "/products")
        for user in self.users:
            self.assertIn("- `/products` — Owner", user)
            self.assertIn("- `products` (Product)", user)
            self.assertIn("Q: Who sells? A: The owner.", user)

    def test_a_part_that_fails_once_is_written_again_on_its_own_and_the_parts_still_join(self):
        envelope, _ = self.write(self.model(fail="tables", times=1))
        self.assertEqual(len(self.users), len(document.PARTS) + 1)            # only the failed part again
        self.assertEqual(envelope["srs_document"]["database_design"]["tables"][0]["table_name"], "products")

    def test_a_part_that_fails_twice_means_the_whole_specification_is_written_in_one_call(self):
        envelope, logged = self.write(self.model(fail="tables"))
        self.assertIn("writing it in one call", logged.call_args.args[2])
        self.assertEqual(len(envelope["srs_document"]["functional_requirements"]), 3)
        self.assertEqual(len(self.users), len(document.PARTS) + 2)            # the parts, the failed one again, the one call


if __name__ == "__main__":
    unittest.main()
