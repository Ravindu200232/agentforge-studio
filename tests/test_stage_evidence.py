"""The uniform per-stage crash checkpoint every stage gets for free through
ProjectSession.begin()/finish()/fail() (server_modules/session.py)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent",
               "qa-agent", "deploy-agent", ".deps"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import bus, config, stage_evidence  # noqa: E402
from server_modules.session import ProjectSession  # noqa: E402


class StageEvidenceTests(unittest.TestCase):
    def test_a_stage_that_never_ran_has_no_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                self.assertIsNone(stage_evidence.last("prj", "srs"))
                self.assertFalse(stage_evidence.was_interrupted("prj", "srs"))

    def test_begin_then_finish_leaves_a_complete_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                stage_evidence.begin("prj", "srs")
                self.assertTrue(stage_evidence.was_interrupted("prj", "srs"))
                stage_evidence.finish("prj", "srs", "wrote the specification")
                record = stage_evidence.last("prj", "srs")
                self.assertEqual(record["status"], "complete")
                self.assertEqual(record["detail"], "wrote the specification")
                self.assertFalse(stage_evidence.was_interrupted("prj", "srs"))

    def test_begin_then_fail_leaves_a_failed_checkpoint_not_interrupted(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                stage_evidence.begin("prj", "build")
                stage_evidence.fail("prj", "build", "npm install failed")
                record = stage_evidence.last("prj", "build")
                self.assertEqual(record["status"], "failed")
                self.assertEqual(record["error"], "npm install failed")
                # A recorded failure is a known outcome, not an unfinished run.
                self.assertFalse(stage_evidence.was_interrupted("prj", "build"))

    def test_a_begin_with_no_matching_finish_or_fail_reads_as_interrupted(self):
        """What a crash actually looks like: begin() wrote "running" and
        nothing ever overwrote it."""
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                stage_evidence.begin("prj", "build")
                self.assertTrue(stage_evidence.was_interrupted("prj", "build"))

    def test_stages_are_independent_checkpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                stage_evidence.begin("prj", "srs")
                stage_evidence.finish("prj", "srs")
                stage_evidence.begin("prj", "build")
                self.assertFalse(stage_evidence.was_interrupted("prj", "srs"))
                self.assertTrue(stage_evidence.was_interrupted("prj", "build"))


class ProjectSessionCheckpointTests(unittest.TestCase):
    """Every stage calls begin()/finish()/fail() already — this confirms the
    checkpoint really is wired in there, not something each stage must
    remember to call itself."""

    def test_begin_finish_leaves_a_complete_checkpoint_for_that_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                session = ProjectSession("prj")
                session.begin("srs", role=bus.DEVELOPER)
                self.assertTrue(stage_evidence.was_interrupted("prj", "srs"))
                session.finish("done")
                self.assertFalse(stage_evidence.was_interrupted("prj", "srs"))
                self.assertEqual(stage_evidence.last("prj", "srs")["status"], "complete")

    def test_a_crash_mid_stage_is_reported_as_a_warning_on_the_next_begin(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                events = []
                unsubscribe = bus.subscribe(events.append)
                try:
                    session = ProjectSession("prj")
                    session.begin("build", role=bus.DEVELOPER)
                    # No finish()/fail() — simulates the process dying mid-build.
                    session2 = ProjectSession("prj")
                    session2.begin("build", role=bus.DEVELOPER)
                finally:
                    unsubscribe()
                warnings = [e for e in events if e.get("type") == "log"
                           and e.get("level") == "WARN" and "did not finish" in e.get("text", "")]
                self.assertTrue(warnings, "expected a did-not-finish warning on the second begin()")

    def test_fail_does_not_read_as_interrupted_on_the_next_begin(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(config, "workspace_for", return_value=Path(temp)):
                events = []
                unsubscribe = bus.subscribe(events.append)
                try:
                    session = ProjectSession("prj")
                    session.begin("build", role=bus.DEVELOPER)
                    session.fail("out of disk space")
                    session2 = ProjectSession("prj")
                    session2.begin("build", role=bus.DEVELOPER)
                finally:
                    unsubscribe()
                warnings = [e for e in events if e.get("type") == "log"
                           and e.get("level") == "WARN" and "did not finish" in e.get("text", "")]
                self.assertFalse(warnings, "a recorded failure should not be reported as a crash")


if __name__ == "__main__":
    unittest.main()
