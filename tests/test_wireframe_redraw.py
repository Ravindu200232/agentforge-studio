"""A manual redraw stays a focused, silent wireframe operation."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", ".deps"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from srs_agent import document  # noqa: E402


class SilentWireframeRedrawTests(unittest.TestCase):
    def test_page_redraw_uses_the_focused_prompt_without_reopening_the_chat_run(self):
        session = SimpleNamespace()
        with patch.object(document, "session_for", return_value=session), \
             patch.object(document, "document", return_value={"srs_document": {"pages": []}}), \
             patch.object(document.plan_stage, "approved_plan", return_value={}), \
             patch.object(document, "_generate_wireframes", return_value=1) as generate, \
             patch.object(document, "wireframes", return_value={"pages": []}), \
             patch.object(document.bus, "agent_msg") as message, \
             patch.object(document.bus, "phase") as phase:
            result = document.redraw("prj_example", "/orders", quiet=True)

        self.assertEqual(result, {"pages": []})
        self.assertTrue(generate.call_args.kwargs["quiet"])
        self.assertIn("silent redraw", generate.call_args.kwargs["request"])
        self.assertIn("/orders", generate.call_args.kwargs["request"])
        message.assert_not_called()
        phase.assert_not_called()

    def test_normal_redraw_keeps_the_existing_stage_lifecycle(self):
        session = SimpleNamespace(begin=lambda *args, **kwargs: None,
                                  finish=lambda *args, **kwargs: None)
        with patch.object(document, "session_for", return_value=session), \
             patch.object(document, "document", return_value={"srs_document": {"pages": []}}), \
             patch.object(document.plan_stage, "approved_plan", return_value={}), \
             patch.object(document, "_generate_wireframes", return_value=1) as generate, \
             patch.object(document, "wireframes", return_value={"pages": []}):
            document.redraw("prj_example", "/orders")

        self.assertFalse(generate.call_args.kwargs["quiet"])


if __name__ == "__main__":
    unittest.main()
