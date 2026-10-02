"""A build that stops to ask is answered, wherever the answer is typed and even after a restart; and when the
account cannot take a new database, the way forward is the model's to offer and the customer's to choose — a
project of theirs is paused or deleted only when they chose that for it."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent", "tests"):
    sys.path.insert(0, str(ROOT / folder))

import support  # noqa: E402
from builder_agent import build, setup  # noqa: E402
from server_modules import bus, httpd, runs, supabase_connect  # noqa: E402


def setUpModule():
    support.isolate_workspaces()


ACCOUNT = {"connected": True, "organizations": [{"id": "org1", "name": "Mine", "plan": "free"}],
           "projects": [{"ref": "refshop", "name": "ShopApp", "status": "ACTIVE_HEALTHY", "organization_id": "org1"},
                        {"ref": "refblog", "name": "BlogApp", "status": "ACTIVE_HEALTHY", "organization_id": "org1"}]}
FOUND = {"supabase": {"this_project": None, "account": ACCOUNT}}


def ready(room: dict | None) -> dict:
    supabase = {"use": "new", "organization": "org1", "region": "ap-south-1"}
    if room:
        supabase["make_room"] = room
    return {"kind": "ready", "database": {"supabase": supabase}, "decisions": ["a new project"]}


class MakeRoomCheckTests(unittest.TestCase):
    def test_a_project_is_paused_or_deleted_only_when_the_customer_was_asked_about_it(self):
        with self.assertRaisesRegex(ValueError, "has not been asked about ShopApp"):
            setup.check(ready({"action": "delete", "project": "refshop"}), True, "nextjs-supabase", FOUND, [])
        asked = [{"question": "Your free plan is full. Pause ShopApp, delete ShopApp, or go Pro?", "answer": "delete"}]
        settled = setup.check(ready({"action": "delete", "project": "refshop"}), True, "nextjs-supabase", FOUND, asked)
        self.assertEqual(settled["database"]["supabase"]["make_room"],
                         {"action": "delete", "project": "refshop", "name": "ShopApp"})

    def test_only_a_real_other_project_and_only_with_a_new_one(self):
        asked = [{"question": "Pause ShopApp?", "answer": "yes"}]
        with self.assertRaisesRegex(ValueError, "one of the account's projects"):
            setup.check(ready({"action": "pause", "project": "nope"}), True, "nextjs-supabase", FOUND, asked)
        with self.assertRaisesRegex(ValueError, '"pause" or "delete"'):
            setup.check(ready({"action": "wipe", "project": "refshop"}), True, "nextjs-supabase", FOUND, asked)
        own = {"supabase": {"this_project": {"ref": "refshop", "name": "ShopApp"}, "account": ACCOUNT}}
        with self.assertRaisesRegex(ValueError, "own Supabase project"):
            setup.check(ready({"action": "pause", "project": "refshop"}), True, "nextjs-supabase", own, asked)
        reply = ready({"action": "pause", "project": "refshop"})
        reply["database"]["supabase"]["use"] = "this"
        with self.assertRaisesRegex(ValueError, 'only goes with "use": "new"'):
            setup.check(reply, True, "nextjs-supabase", own, asked)

    def test_without_make_room_nothing_changes(self):
        settled = setup.check(ready(None), True, "nextjs-supabase", FOUND, [])
        self.assertNotIn("make_room", settled["database"]["supabase"])

    def test_room_is_made_before_the_new_project(self):
        calls = []
        with mock.patch.object(setup.supabase_connect, "make_room", side_effect=lambda *a, **k: calls.append("room")), \
             mock.patch.object(setup.supabase_connect, "ensure_project", side_effect=lambda *a, **k: calls.append("new")), \
             mock.patch.object(setup.supabase_connect, "record", return_value={}):
            setup.apply("prj_new", "Hotel", ready({"action": "pause", "project": "refshop"})["database"], say=print)
        self.assertEqual(calls, ["room", "new"])


class MakeRoomTests(unittest.TestCase):
    def _answer(self, status: int, body: dict | None = None):
        return SimpleNamespace(status_code=status, text=json.dumps(body or {}), json=lambda: body or {})

    def test_pause_waits_until_the_project_is_down(self):
        states = iter([self._answer(200, {"status": "ACTIVE_HEALTHY"}), self._answer(200, {"status": "PAUSING"}),
                       self._answer(200, {"status": "INACTIVE"})])
        with mock.patch.object(supabase_connect, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(supabase_connect.httpx, "get", side_effect=lambda *a, **k: next(states)), \
             mock.patch.object(supabase_connect.httpx, "post", return_value=self._answer(200)) as post, \
             mock.patch.object(supabase_connect.time, "sleep"):
            supabase_connect.make_room("refshop", "pause")
        self.assertTrue(post.call_args.args[0].endswith("/v1/projects/refshop/pause"))

    def test_a_project_already_paused_is_left_alone(self):
        with mock.patch.object(supabase_connect, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(supabase_connect.httpx, "get", return_value=self._answer(200, {"status": "INACTIVE"})), \
             mock.patch.object(supabase_connect.httpx, "post") as post:
            supabase_connect.make_room("refshop", "pause")
        post.assert_not_called()

    def test_delete_forgets_the_agentforge_project_that_used_it(self):
        saved = {"prj_shop": {"ref": "refshop"}, "prj_other": {"ref": "refother"}}
        states = iter([self._answer(200, {"status": "ACTIVE_HEALTHY"}), self._answer(404)])
        with mock.patch.object(supabase_connect, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(supabase_connect.httpx, "get", side_effect=lambda *a, **k: next(states)), \
             mock.patch.object(supabase_connect.httpx, "delete", return_value=self._answer(200)) as delete, \
             mock.patch.object(supabase_connect.time, "sleep"), \
             mock.patch.object(supabase_connect, "_read_all", return_value=dict(saved)), \
             mock.patch.object(supabase_connect, "_write_all") as wrote:
            supabase_connect.make_room("refshop", "delete")
        self.assertTrue(delete.call_args.args[0].endswith("/v1/projects/refshop"))
        self.assertEqual(wrote.call_args.args[0], {"prj_other": {"ref": "refother"}})

    def test_a_refusal_comes_back_as_the_reason(self):
        with mock.patch.object(supabase_connect, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(supabase_connect.httpx, "get", return_value=self._answer(200, {"status": "ACTIVE_HEALTHY"})), \
             mock.patch.object(supabase_connect.httpx, "delete", return_value=self._answer(403, {"message": "no access"})):
            with self.assertRaisesRegex(ValueError, "would not delete project refshop: no access"):
                supabase_connect.make_room("refshop", "delete")


class AnswerRoutingTests(unittest.TestCase):
    def test_typed_into_the_chat_while_a_build_waits_it_is_the_builds_answer(self):
        with mock.patch.object(runs.builder, "waiting", return_value={"question": {"question": "Pause ShopApp?"}}), \
             mock.patch.object(runs, "answer_build", return_value={"ok": True}) as answered, \
             mock.patch.object(runs.changes, "submit") as planned, \
             mock.patch.object(runs.bus, "user_msg"):
            runs.agent_update({"project": "prj_wait", "prompt": "pause it"})
        answered.assert_called_once_with("prj_wait", "pause it")
        planned.assert_not_called()

    def test_a_card_from_before_a_restart_still_answers_the_waiting_build(self):
        with mock.patch.object(httpd.runs.builder, "waiting", return_value={"question": {"question": "?"}}), \
             mock.patch.object(httpd.runs, "answer_build", return_value={"ok": True}) as answered:
            out = httpd.decide({"id": "ask-1", "project": "prj_wait", "decision": "answer", "reply": "Pro"})
        self.assertEqual(out, {"ok": True})
        answered.assert_called_once_with("prj_wait", "Pro")

    def test_question_ids_never_repeat_across_restarts(self):
        first = bus.ask("prj_ids", "question", "a?")
        second = bus.ask("prj_ids", "question", "b?")
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^ask-\d+-[0-9a-f]{8}$")
        bus.resolve(first)
        bus.resolve(second)


class RestoreTests(unittest.TestCase):
    def test_a_build_waiting_when_the_server_restarted_asks_again_once(self):
        with tempfile.TemporaryDirectory() as folder:
            record = Path(folder) / ".agentforge"
            (record / "build").mkdir(parents=True)
            question = {"question": "Pause ShopApp to make room?", "options": [], "why": "", "assumption": ""}
            (record / "build" / "pending.json").write_text(json.dumps({"mode": "setup", "question": question}),
                                                           encoding="utf-8")
            with mock.patch.object(build.store, "listing", return_value=[{"name": "prj_restored"}]), \
                 mock.patch.object(build.config, "record_dir", return_value=record):
                first = build.restore_questions()
                second = build.restore_questions()
        self.assertEqual([q["question"] for q in first], ["Pause ShopApp to make room?"])
        self.assertEqual(second, [])
        shown = [d for d in bus.pending_decisions() if d.get("project") == "prj_restored"]
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0]["flow"], "build")
        bus.resolve_project("prj_restored", "build")


if __name__ == "__main__":
    unittest.main()
