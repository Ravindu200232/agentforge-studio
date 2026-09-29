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
    def test_context_path_is_relative_to_the_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            context = workspace / ".agentforge" / "srs" / "diagram-context" / "class_object.json"
            context.parent.mkdir(parents=True)
            context.write_text("{}", encoding="utf-8")
            self.assertEqual(document._workspace_relative(context, workspace),
                             ".agentforge/srs/diagram-context/class_object.json")

    def test_outside_path_is_never_presented_as_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as other:
            context = Path(other) / "secret.json"
            context.write_text("{}", encoding="utf-8")
            self.assertEqual(document._workspace_relative(context, Path(temp)), "secret.json")
