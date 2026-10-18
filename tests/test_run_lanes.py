"""`ProjectSession.run_lanes`: several parts of a stage at once, each by its own agent in a conversation of its own."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import config, session as sessions  # noqa: E402
from server_modules.session import ProjectSession, RunCancelled  # noqa: E402


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.session = ProjectSession.__new__(ProjectSession)
        self.session.project = "prj_lanes"
        self.session._cancel = threading.Event()
        self.session._thinking_level = "low"
        self.archived: list[list] = []
        self.session._archive_summary = lambda old: self.archived.append(old)
        main = SimpleNamespace(model="m", memory_summary="what the project knows")
        self.session.agent = lambda model="": main
        self.running = 0
        self.most = 0
        self.lock = threading.Lock()
        self.made: list = []

        def make(model, level, saved, mcp=True):
            test = self

            class Agent:
                memory_summary = ""
                messages = [{"role": "system", "content": ""}]

                def _system_message(self):
                    return "system + " + self.memory_summary

                def execute_plan(self, request, plan, audit=True, parallel_write_limit=1):
                    with test.lock:
                        test.running += 1
                        test.most = max(test.most, test.running)
                    time.sleep(0.05)
                    with test.lock:
                        test.running -= 1
                    if "boom" in request:
                        raise RuntimeError("the model service is down")
                    self.messages = self.messages + [{"role": "user", "content": request}]
                    return SimpleNamespace(status="complete", text=f"did {plan}", rounds=1)

            agent = Agent()
            self.made.append((agent, mcp))
            return agent

        self.session._make_agent = make
        patcher = mock.patch.object(config, "settings", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_parts_run_at_once_each_in_a_new_conversation_and_are_archived(self):
        results = self.session.run_lanes([(f"part {n}", f"plan {n}") for n in range(5)], parallel_write_limit=4)
        self.assertEqual([r["text"] for r in results], [f"did plan {n}" for n in range(5)])
        self.assertEqual(self.most, sessions.LANES)                          # at most LANES at once, and that many
        self.assertEqual(len(self.made), 5)
        self.assertTrue(all(mcp is False for _, mcp in self.made))            # no MCP servers started for a part
        self.assertTrue(all(agent.messages[0]["content"] == "system + what the project knows" for agent, _ in self.made))
        self.assertEqual(len(self.archived), 5)

    def test_a_part_that_fails_is_reported_and_the_others_still_finish(self):
        results = self.session.run_lanes([("part 1", "p1"), ("boom", "p2"), ("part 3", "p3")])
        self.assertEqual([r["status"] for r in results], ["complete", "failed", "complete"])
        self.assertIn("model service is down", results[1]["text"])

    def test_stop_before_or_during_ends_with_cancelled(self):
        self.session._cancel.set()
        with self.assertRaises(RunCancelled):
            self.session.run_lanes([("part", "p")])


if __name__ == "__main__":
    unittest.main()
