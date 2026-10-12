"""Before a build is planned, what it needs is checked, and what is missing is asked for until it is there.

Node.js, npm, a browser, and the stack's own services (a MongoDB that is connected and answers, a Supabase account). Missing
ones are listed in one Yes/No card; Yes checks again and asks again while something is still missing; No stops the build
before it has done anything.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent", "tests"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from builder_agent import build, preflight  # noqa: E402
from server_modules import bus  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402
from test_build import RUN_PROJECT, StraightThroughCase  # noqa: E402

MONGO = "nextjs-mongo-only"
SUPABASE = "nextjs-supabase"


class WhatIsMissingTests(unittest.TestCase):
    def setUp(self):
        self.tools = {"node": "/bin/node", "npm": "/bin/npm"}
        self.browser = ("edge", "chromium")
        self.state = {"saved": True, "atlas": False}
        self.answers = (True, "")
        self.linked = {}
        self.supabase = {"connected": True}
        self.cli = "/bin/supabase"
        from ollama_terminal import screenshot
        from server_modules import cli_signin

        for patch in (mock.patch.object(preflight.shutil, "which", lambda name: self.tools.get(name)),
                      mock.patch.object(screenshot, "working_browser", lambda *a, **k: self.browser),
                      mock.patch.object(preflight.deploy_vars, "database_state", lambda: dict(self.state)),
                      mock.patch.object(preflight.mongo_connect, "verify_or_repair", lambda log=None: self.answers),
                      mock.patch.object(preflight.supabase_connect, "record", lambda project: self.linked),
                      mock.patch.object(preflight.supabase_connect, "token_status", lambda: dict(self.supabase)),
                      mock.patch.object(cli_signin, "_where", lambda name: self.cli)):
            self.enterContext(patch)

    def what(self, stack=MONGO):
        return [gap["what"] for gap in preflight.missing("p", stack)]

    def test_everything_ready_is_nothing_missing(self):
        self.assertEqual(self.what(MONGO), [])
        self.assertEqual(self.what(SUPABASE), [])

    def test_no_node_npm_or_browser_on_this_computer(self):
        self.tools = {}
        self.browser = None
        self.assertEqual(self.what(), ["Node.js", "npm", "A browser"])

    def test_a_mongodb_stack_with_nothing_connected(self):
        self.state = {"saved": False, "atlas": False}
        gaps = preflight.missing("p", MONGO)
        self.assertEqual([g["what"] for g in gaps], ["MongoDB"])
        self.assertIn("Settings, Integrations", gaps[0]["how"])

    def test_a_signed_in_atlas_account_is_enough_the_build_makes_the_cluster(self):
        self.state = {"saved": False, "atlas": True}
        self.assertEqual(self.what(), [])

    def test_a_connected_cluster_that_does_not_answer(self):
        self.answers = (False, "The cluster is paused.")
        gaps = preflight.missing("p", MONGO)
        self.assertEqual([g["what"] for g in gaps], ["The MongoDB cluster"])
        self.assertIn("The cluster is paused.", gaps[0]["why"])

    def test_a_supabase_stack_with_no_account_and_no_cli(self):
        self.supabase = {"connected": False}
        self.cli = ""
        self.assertEqual(self.what(SUPABASE), ["Supabase", "The Supabase command line tool"])

    def test_a_project_already_linked_to_its_supabase_project_needs_nothing_more(self):
        self.linked = {"ref": "abc"}
        self.supabase = {"connected": False}
        self.assertEqual(self.what(SUPABASE), [])

    def test_a_mongodb_only_stack_is_never_asked_about_supabase(self):
        self.supabase = {"connected": False}
        self.assertEqual(self.what(MONGO), [])


class AskingUntilItIsReadyTests(unittest.TestCase):
    def setUp(self):
        self.looks: list[list[dict]] = []
        self.replies: list = []
        self.asked: list[str] = []
        self.said: list[str] = []

        def wait(project, kind, question, **kwargs):
            self.asked.append(question)
            self.kwargs = kwargs
            return self.replies.pop(0)

        for patch in (mock.patch.object(preflight, "missing", lambda project, stack, say=None: self.looks.pop(0)),
                      mock.patch.object(bus, "ask_and_wait", wait), mock.patch.object(bus, "phase"),
                      mock.patch.object(bus, "agent_msg", lambda project, text, **kw: self.said.append(text))):
            self.enterContext(patch)

    def gap(self, what="MongoDB"):
        return {"what": what, "why": "no MongoDB is connected", "how": "sign in under Settings, Integrations"}

    def test_nothing_is_asked_when_everything_is_ready(self):
        self.looks = [[]]
        self.assertEqual(preflight.ensure("p", MONGO, cancelled=lambda: False), [])
        self.assertEqual(self.asked, [])

    def test_yes_checks_again_and_the_build_goes_on_once_it_is_connected(self):
        self.looks = [[self.gap()], []]
        self.replies = ["Yes"]
        self.assertEqual(preflight.ensure("p", MONGO, cancelled=lambda: False), [{"missing": ["MongoDB"]}])
        self.assertEqual(len(self.asked), 1)
        self.assertIn("MongoDB", self.asked[0])
        self.assertIn("answer Yes to check again", self.asked[0])
        self.assertEqual([o["label"] for o in self.kwargs["options"]], ["Yes", "No"])
        self.assertTrue(self.kwargs["quick"])
        self.assertIn("ready now", self.said[-1])

    def test_still_not_connected_after_yes_is_asked_again(self):
        self.looks = [[self.gap(), self.gap("Node.js")], [self.gap()], []]
        self.replies = ["Yes", "Yes"]
        preflight.ensure("p", MONGO, cancelled=lambda: False)
        self.assertEqual(len(self.asked), 2)
        self.assertIn("Still not ready after checking again", self.asked[1])
        self.assertNotIn("Node.js", self.asked[1])                       # only what is still missing

    def test_no_or_leaving_it_to_the_agent_stops_the_build_saying_what_is_missing(self):
        for reply in ("No", ""):
            self.looks = [[self.gap()]]
            self.replies = [reply]
            with self.assertRaisesRegex(ValueError, "The build needs MongoDB"):
                preflight.ensure("p", MONGO, cancelled=lambda: False)

    def test_stop_while_waiting_stops_the_run(self):
        self.looks = [[self.gap()]]
        self.replies = [None]
        with self.assertRaises(RunCancelled):
            preflight.ensure("p", MONGO, cancelled=lambda: False)


class TheBuildChecksFirstTests(StraightThroughCase):
    def setUp(self):
        super().setUp()
        self.install = mock.Mock(return_value={"scaffolded": True, "files": ["package.json"]})
        self.enterContext(mock.patch("builder_agent.scaffold.install", self.install))

    def test_a_no_stops_the_build_before_anything_is_asked_provisioned_or_planned(self):
        self.enterContext(mock.patch.object(build.preflight, "missing",
                                            return_value=[{"what": "Supabase", "why": "not connected", "how": "sign in"}]))
        self.enterContext(mock.patch.object(build.bus, "ask_and_wait", return_value="No"))
        with self.assertRaisesRegex(ValueError, "The build needs Supabase"):
            build.run(RUN_PROJECT)
        self.assertEqual(self.session.before_plan, [])
        self.ensure_project.assert_not_called()
        self.install.assert_not_called()
        self.assertEqual(self.session.requests, [])


if __name__ == "__main__":
    unittest.main()
