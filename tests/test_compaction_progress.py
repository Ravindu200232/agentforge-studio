"""The studio's side of compaction: the engine's progress becomes a live state the chat can draw."""
from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, config  # noqa: E402
from server_modules.session import ProjectSession  # noqa: E402


class CompactionProgressTests(unittest.TestCase):
    def setUp(self):
        # A project of its own per test: `bus.forget` retires a project, and a retired one emits nothing.
        self.project = f"prj_compacting_{uuid.uuid4().hex[:8]}"
        # Its events land in a scratch folder, not beside the real projects.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(config, "WORKSPACES", Path(folder.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        self.addCleanup(bus.forget, self.project)
        self.session = SimpleNamespace(project=self.project, role=bus.DEVELOPER, cancelled=False, _agent=None)

    def mine(self, kind: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == kind and e.get("agent") == bus.DEVELOPER]

    def test_each_part_and_the_merge_are_a_state_with_how_far_along_it_is(self):
        for line in ("[compacting] 0/35", "[compacting] 12/35", "[compacting] merging 35"):
            ProjectSession._announce(self.session, line)
        states = [(e["state"], e.get("detail")) for e in self.mine("agent_state")]
        self.assertEqual(states, [("compacting", "0/35"), ("compacting", "12/35"), ("compacting", "merging 35")])
        self.assertTrue(all(e["thinking"] for e in self.mine("agent_state")))

    def test_the_start_of_compaction_is_written_to_the_log(self):
        ProjectSession._announce(self.session, "[context] Compacting 766 earlier messages into memory: 35 parts, up to 4 at a time.")
        self.assertTrue(any("35 parts" in e["text"] for e in self.mine("log")))

    def test_a_state_without_detail_carries_no_detail_field(self):
        bus.agent_state(self.project, "thinking", thinking=True)
        self.assertNotIn("detail", self.mine("agent_state")[-1])


if __name__ == "__main__":
    unittest.main()
