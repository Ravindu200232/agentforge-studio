"""A deployment is not asked for inside the build's conversation, and a model call that never answers ends instead of waiting for ever."""
from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from deploy_agent import deploy  # noqa: E402
from server_modules import connection  # noqa: E402
from server_modules.session import ProjectSession  # noqa: E402


def conversation(turns: int, size: int = 4000) -> list[dict]:
    rows: list[dict] = [{"role": "system", "content": "SYSTEM"}]
    for number in range(turns):
        rows.append({"role": "user" if number % 2 == 0 else "assistant", "content": f"turn {number} " + "x" * size})
    return rows


class Session:
    """What `ProjectSession.shed_history` touches, as a stand-in: the agent, its lock, the archive and the saved context."""

    def __init__(self, messages, summary=""):
        self.agent = SimpleNamespace(messages=messages, memory_summary=summary, last_prompt_tokens=123,
                                     _system_message=lambda: "SYSTEM + memory")
        self._agent = self.agent
        self.lock = threading.RLock()
        self.archived: list[list[dict]] = []
        self.saved = 0
        self._archive_summary = self.archived.append
        self.save_context = self._save

    def _save(self):
        self.saved += 1


class SheddingTests(unittest.TestCase):
    def test_a_long_conversation_is_archived_whole_and_a_deployment_starts_from_the_memory_and_a_note(self):
        session = Session(conversation(200), summary="Earlier work, summarised.")
        old = list(session.agent.messages[1:])
        shed = ProjectSession.shed_history(session, "The record is in .agentforge/.")
        self.assertEqual(shed, 200)
        self.assertEqual(session.archived, [old])                                  # nothing is lost: every turn is kept verbatim
        self.assertEqual(session.agent.messages, [{"role": "system", "content": "SYSTEM + memory"}])
        self.assertEqual(session.agent.memory_summary, "Earlier work, summarised.\nThe record is in .agentforge/.")
        self.assertEqual(session.agent.last_prompt_tokens, 0)
        self.assertEqual(session.saved, 1)

    def test_a_small_conversation_is_left_alone(self):
        session = Session(conversation(4, size=100))
        self.assertEqual(ProjectSession.shed_history(session, "note"), 0)
        self.assertEqual((len(session.agent.messages), session.archived, session.saved), (5, [], 0))
        self.assertEqual(session.agent.memory_summary, "")

    def test_the_note_is_not_added_twice_and_the_memory_stays_bounded(self):
        session = Session(conversation(200), summary="m" * 11_990)
        ProjectSession.shed_history(session, "N" * 50)
        self.assertEqual(len(session.agent.memory_summary), 12_000)
        self.assertTrue(session.agent.memory_summary.endswith("N" * 50))
        again = Session(conversation(200), summary="Earlier.\nThe same note.")
        ProjectSession.shed_history(again, "The same note.")
        self.assertEqual(again.agent.memory_summary.count("The same note."), 1)

    def test_what_a_build_leaves_is_far_over_the_size_a_deployment_should_carry(self):
        # About 700K tokens (2.6 MB) was what the deployment of the generated app was sent with every answer.
        build = conversation(700, size=3700)
        self.assertGreater(len(json.dumps(build)), 2_400_000)
        session = Session(build)
        ProjectSession.shed_history(session, "note")
        self.assertLess(len(json.dumps(session.agent.messages)), 1_000)


class TheDeploymentAsksForItTests(unittest.TestCase):
    def test_the_deployments_own_hook_passes_its_note_and_tolerates_a_session_without_one(self):
        told: list[str] = []
        session = SimpleNamespace(shed_history=lambda note, keep_tokens=0: told.append(note) or 17)
        self.assertEqual(deploy.fresh_context(session), 17)
        self.assertEqual(told, [deploy.FRESH_NOTE])
        self.assertEqual(deploy.fresh_context(SimpleNamespace()), 0)

    def test_the_note_says_where_the_record_is(self):
        for needle in (".agentforge/build/report.json", ".agentforge/qa/report.json", ".agentforge/srs/handoff/",
                       ".agentforge/deploy/"):
            self.assertIn(needle, deploy.FRESH_NOTE)

    def test_both_the_plan_and_the_run_start_fresh(self):
        source = (ROOT / "deploy-agent" / "deploy_agent" / "deploy.py").read_text(encoding="utf-8")
        plan = source[source.index("def plan_prompt("):source.index("def _slug(")]
        run = source[source.index("def execute("):source.index("def _settle(")]
        self.assertIn("fresh_context(session)", plan)
        self.assertLess(run.index("fresh_context(session)"), run.index("machine_facts("))


class AModelThatNeverAnswersEndsTests(unittest.TestCase):
    def test_the_bound_is_long_enough_for_a_slow_answer_and_short_enough_to_end(self):
        timeout = connection.model_timeout()
        self.assertEqual((timeout.read, timeout.connect), (900.0, 30.0))

    def test_every_client_that_talks_to_the_model_service_has_it(self):
        for name in ("session.py", "llm.py", "ollama_cloud.py"):
            source = (ROOT / "server_modules" / name).read_text(encoding="utf-8")
            clients = [line for line in source.splitlines() if "ollama.Client(" in line]
            self.assertTrue(clients, name)
            for line in clients:
                self.assertIn("timeout=connection.model_timeout()", line, f"{name}: {line.strip()}")

    def test_a_timeout_is_a_transient_failure_so_it_is_asked_for_again_with_a_notice(self):
        import httpx
        from server_modules.session import _transient

        self.assertTrue(_transient(httpx.ReadTimeout("no bytes for 900 s")))
        self.assertTrue(_transient(httpx.ConnectTimeout("no answer")))


if __name__ == "__main__":
    unittest.main()
