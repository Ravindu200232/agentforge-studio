"""The cloud reviewer may only receive paths its read-only tool can use."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", ".deps"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from srs_agent import document  # noqa: E402


class DiagramReviewContextTests(unittest.TestCase):
    def _document(self):
        return {
            "app_summary": {"app_name": "Shop"},
            "roles": [{"role_name": "Shopper", "description": "Places orders"}],
            "main_modules": ["Checkout"],
            "business_workflows": [{
                "workflow_name": "Buy product", "who": "Shopper",
                "steps": ["Choose product", "Place order"],
            }],
            "database_design": {
                "tables": [
                    {"table_name": "accounts", "fields": [
                        {"name": "id", "type": "uuid", "primary_key": True},
                    ]},
                    {"table_name": "orders", "fields": [
                        {"name": "id", "type": "uuid", "primary_key": True},
                        {"name": "account_id", "type": "reference", "references": "accounts.id"},
                        {"name": "status", "type": "enum(open,paid,cancelled)"},
                    ]},
                ],
                "relationships": [{
                    "from": "accounts.id", "to": "orders.account_id", "type": "one_to_many",
                    "description": "An account places orders.",
                }],
            },
        }

    def test_context_path_is_relative_to_the_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            context = workspace / ".agentforge" / "srs" / "diagram-context" / "class_object.json"
            context.parent.mkdir(parents=True)
            context.write_text("{}", encoding="utf-8")
            self.assertEqual(document._workspace_relative(context, workspace),
                             ".agentforge/srs/diagram-context/class_object.json")

    def test_staged_relative_string_is_anchored_before_it_is_resolved(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            relative = ".agentforge/srs/diagram-context/system_context.json"
            path = workspace / relative
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(document._workspace_relative(relative, workspace), relative)

    def test_outside_path_is_never_presented_as_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            context = Path(other) / "secret.json"
            context.write_text("{}", encoding="utf-8")
            self.assertEqual(document._workspace_relative(context, Path(temp)), "secret.json")

    def test_erd_context_keeps_compact_schema_and_relationship_evidence(self):
        context = document._diagram_context(self._document(), "erd")
        schema = context["database_design"]
        self.assertEqual({row["table_name"] for row in schema["tables"]}, {"accounts", "orders"})
        self.assertEqual(schema["relationships"][0]["to"], "orders.account_id")

    def test_state_context_exposes_enum_lifecycle_candidates(self):
        context = document._diagram_context(self._document(), "state_machine")
        self.assertIn(
            {"table": "orders", "field": "status", "states": "enum(open,paid,cancelled)"},
            context["lifecycle_candidates"],
        )

    def test_sequence_context_keeps_workflow_steps(self):
        context = document._diagram_context(self._document(), "sequence")
        self.assertEqual(context["business_workflows"][0]["steps"], ["Choose product", "Place order"])
