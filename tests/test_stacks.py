"""One list of stacks, said the same way everywhere - and a MongoDB-only stack never touches Supabase.

The stacks live in three places that must agree: `scaffold.py` (templates and guides), `prompts/deployment/stacks.json`
(how each deploys) and `studio/lib/stacks.js` (what the picker offers and which accounts a build waits for). The
MongoDB stacks come in two kinds: with a Supabase Storage bucket for uploaded files (the original ids) and MongoDB-only
(`-only`, no Supabase account, uploaded files in GridFS).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent", "tests"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build, scaffold  # noqa: E402
from deploy_agent import deploy  # noqa: E402
from server_modules import changes  # noqa: E402
from test_build import RUN_PROJECT, StraightThroughCase  # noqa: E402
from support import isolate_workspaces  # noqa: E402

SUPABASE_DATABASE = ("nextjs-supabase", "vite-supabase", "remix-supabase")
MONGO_BUCKET = ("nextjs-mongo", "vite-mongo", "remix-mongo", "mern-microservices")
MONGO_ONLY = ("nextjs-mongo-only", "vite-mongo-only", "remix-mongo-only", "mern-microservices-only")


def setUpModule():
    isolate_workspaces()


def studio_stacks() -> dict[str, list[str]]:
    """The ids and `needs` in studio/lib/stacks.js, read from its source."""
    text = (ROOT / "studio" / "lib" / "stacks.js").read_text(encoding="utf-8")
    rows = re.findall(r"id: '([a-z-]+)'.*?needs: \[([^\]]*)\]", text, re.DOTALL)
    return {stack: re.findall(r"'([a-z]+)'", needs) for stack, needs in rows}


def deployment_stacks() -> dict:
    return json.loads((ROOT / "prompts" / "deployment" / "stacks.json").read_text(encoding="utf-8"))


class RegistryTests(unittest.TestCase):
    def test_the_build_the_deployment_and_the_studio_list_the_same_stacks(self):
        built = set(scaffold.STACK_GUIDES)
        self.assertEqual(built, set(SUPABASE_DATABASE) | set(MONGO_BUCKET) | set(MONGO_ONLY))
        self.assertEqual(set(deployment_stacks()), built)
        self.assertEqual(set(studio_stacks()), built)

    def test_the_studio_waits_for_exactly_the_accounts_a_stack_uses(self):
        for stack, needs in studio_stacks().items():
            with self.subTest(stack=stack):
                self.assertEqual("supabase" in needs, scaffold.uses_supabase(stack))
                self.assertEqual("mongodb" in needs, scaffold.uses_mongodb(stack))

    def test_deployment_is_told_which_stacks_have_no_supabase(self):
        for stack, row in deployment_stacks().items():
            with self.subTest(stack=stack):
                self.assertEqual(row.get("supabase", True), stack not in MONGO_ONLY)
                self.assertEqual(row.get("supabase", True), scaffold.uses_supabase(stack))
                self.assertTrue((ROOT / "prompts" / "deployment" / "skills" / row["skill"] / "SKILL.md").is_file())

    def test_a_server_stack_is_only_offered_where_a_server_can_run(self):
        for stack in ("vite-mongo-only", "mern-microservices-only"):
            self.assertEqual(deployment_stacks()[stack]["targets"], ["aws_ec2", "aws_ecs", "azure"], stack)
        # Remix runs as one server, or as serverless functions on Vercel (its Vercel preset).
        for stack in ("remix-mongo", "remix-mongo-only"):
            self.assertEqual(deployment_stacks()[stack]["targets"], ["vercel", "aws_ec2", "aws_ecs", "azure"], stack)
        self.assertEqual(deployment_stacks()["nextjs-mongo-only"]["targets"], "all")

    def test_every_stack_has_a_creation_prompt_and_an_uploads_rule_where_needed(self):
        for stack in scaffold.STACK_GUIDES:
            with self.subTest(stack=stack):
                guides = scaffold.build_guide_files(stack)
                self.assertIn("Author ", guides[scaffold.STACK_GUIDES[stack]])
                self.assertIn("application.md", guides)
                self.assertEqual(stack in scaffold.UPLOAD_GUIDES, scaffold.uses_mongodb(stack))

    def test_mongo_only_and_bucket_stacks_share_framework_guidance(self):
        for only in MONGO_ONLY:
            twin = only.removesuffix("-only")
            self.assertEqual(scaffold.STACK_GUIDES[only], scaffold.STACK_GUIDES[twin])
            self.assertEqual(scaffold.UPLOAD_GUIDES[only], "uploads-gridfs.md")
            self.assertEqual(scaffold.UPLOAD_GUIDES[twin], "uploads-supabase.md")

    def test_an_unknown_stack_is_still_refused(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "unsupported build stack"):
            scaffold.describe_workspace(Path(folder), "nextjs-nosql")


class MongoOnlyNeverTouchesSupabaseTests(unittest.TestCase):
    @staticmethod
    def _without_the_no_supabase_rule(files: dict[str, str]) -> str:
        lines = []
        for body in files.values():
            lines += [line for line in body.splitlines() if "there is no Supabase project" not in line]
        return "\n".join(lines)

    def test_the_guides_a_mongo_only_build_reads_never_mention_supabase(self):
        for stack in MONGO_ONLY:
            with self.subTest(stack=stack):
                for files in (scaffold.build_guide_files(stack), scaffold.guide_files(stack)):
                    self.assertNotIn("supabase", self._without_the_no_supabase_rule(files).lower())

    def test_a_mongo_only_build_is_told_outright_that_there_is_no_supabase_and_where_files_go(self):
        for stack in MONGO_ONLY:
            guides = scaffold.build_guide_files(stack)
            self.assertIn("uploads-gridfs.md", guides, stack)
            self.assertNotIn("uploads-supabase.md", guides, stack)
            self.assertIn("none is to be added", guides["uploads-gridfs.md"])
            self.assertIn("GridFSBucket", guides["uploads-gridfs.md"])

    def test_the_bucket_stacks_keep_supabase_storage_for_uploads(self):
        for stack in MONGO_BUCKET:
            guides = scaffold.build_guide_files(stack)
            self.assertIn("uploads-supabase.md", guides, stack)
            self.assertNotIn("uploads-gridfs.md", guides, stack)
            self.assertIn("Supabase Storage", guides["uploads-supabase.md"])
            self.assertIn("@supabase/supabase-js", guides["uploads-supabase.md"])

    def test_the_supabase_pitfalls_go_only_to_the_stacks_that_use_supabase(self):
        for stack in SUPABASE_DATABASE + MONGO_BUCKET:
            self.assertIn("pitfalls-supabase.md", scaffold.build_guide_files(stack), stack)
            self.assertIn("pitfalls-supabase.md", scaffold.guide_files(stack), stack)
        for stack in MONGO_ONLY:
            self.assertNotIn("pitfalls-supabase.md", scaffold.build_guide_files(stack), stack)

    def test_the_shared_pitfalls_name_no_particular_database(self):
        self.assertNotIn("supabase", scaffold.build_guide_files("nextjs-mongo-only")["pitfalls.md"].lower())
        self.assertIn("## Test data", scaffold.build_guide_files("nextjs-mongo-only")["pitfalls.md"])


class RemixMongoPromptTests(unittest.TestCase):
    def test_the_stack_prompt_names_the_remix_entry_and_mongodb_contract(self):
        guide = scaffold.build_guide_files("remix-mongo")["remix-mongo.md"]
        for item in ("@remix-run/serve", "build/server/index.js", "Mongoose", "loaders and actions", "TEST_MONGODB_URI"):
            self.assertIn(item, guide)


class BuildGateTests(StraightThroughCase):
    """`build.run` connects (or creates) the project's Supabase project only for a stack that uses Supabase."""

    def setUp(self):
        super().setUp()
        # A MongoDB stack's database is not what these tests are about, and they must never reach a real cluster: with the
        # Studio's own settings they did, and a cluster that did not answer held the build on its "Try again?" card.
        self.enterContext(mock.patch.object(build.mongo_connect, "ensure_for_project",
                                            return_value={"status": "not_connected", "database": "", "reason": ""}))

    def build_stack(self, stack: str) -> str:
        self.session.results.append({"status": "complete", "text": "done", "plan": "p"})
        with mock.patch.object(build.store, "require", return_value={"stack": stack, "name": "Shop"}), \
             mock.patch("builder_agent.scaffold.describe_workspace", mock.Mock(return_value={"mode": "from_scratch", "existing": []})):
            build.run(RUN_PROJECT)
        return self.session.before_plan[0]

    def test_a_mongo_only_build_never_asks_for_or_creates_a_supabase_project(self):
        for stack in MONGO_ONLY:
            with self.subTest(stack=stack):
                self.ensure_project.reset_mock()
                self.session.before_plan.clear()
                prompt = self.build_stack(stack)
                self.ensure_project.assert_not_called()
                self.assertIn("This stack has no Supabase", prompt)
                self.assertNotIn("already connected", prompt)
                guides = self.session.workspace / ".agentforge" / "build" / "guides"
                self.assertTrue((guides / "uploads-gridfs.md").is_file())
                self.assertFalse((guides / "uploads-supabase.md").exists())

    def test_every_other_stack_still_gets_its_supabase_project(self):
        for stack in SUPABASE_DATABASE + MONGO_BUCKET:
            with self.subTest(stack=stack):
                self.ensure_project.reset_mock()
                self.session.before_plan.clear()
                prompt = self.build_stack(stack)
                self.ensure_project.assert_called_once()
                self.assertIn("Never ask for anything Supabase", prompt)


class DeploymentFactTests(unittest.TestCase):
    def test_a_mongo_only_stack_is_not_told_to_connect_a_supabase_project(self):
        for stack in MONGO_ONLY:
            with mock.patch.object(deploy, "stack_of", return_value=stack), \
                 mock.patch.object(deploy.supabase_connect, "status", side_effect=AssertionError("asked Supabase")):
                fact = deploy._database_fact("prj_x")  # noqa: SLF001
            self.assertIn("no Supabase project", fact)
            self.assertNotIn("none linked", fact)

    def test_a_stack_with_a_supabase_project_is_still_asked_to_have_one(self):
        with mock.patch.object(deploy, "stack_of", return_value="nextjs-mongo"), \
             mock.patch.object(deploy.supabase_connect, "status", return_value={"connected": False}):
            self.assertIn("none linked", deploy._database_fact("prj_x"))  # noqa: SLF001


class ChangeGuidesFollowTheStackTests(unittest.TestCase):
    def guides(self, stack: str) -> str:
        with mock.patch.object(changes.store, "get", return_value={"stack": stack}):
            return changes._guides("prj_x")  # noqa: SLF001

    def test_a_change_to_a_mongo_only_app_is_given_no_supabase_guidance(self):
        self.assertNotIn("supabase", self.guides("nextjs-mongo-only").lower())

    def test_a_change_to_a_supabase_app_still_gets_it(self):
        self.assertIn("### pitfalls-supabase.md", self.guides("nextjs-supabase"))

    def test_a_change_with_no_project_keeps_the_guidance_it_always_had(self):
        self.assertIn("### pitfalls-supabase.md", changes._guides())  # noqa: SLF001


class TheDatabaseIsTheStudiosToProvideTests(unittest.TestCase):
    """The model is told at the root that the MongoDB connection is provided: never asked for, never looked for on this computer."""

    def test_every_mongodb_stack_guide_says_the_database_is_already_connected_and_to_look_for_no_other(self):
        for stack in (*MONGO_BUCKET, *MONGO_ONLY):
            with self.subTest(stack=stack):
                for files in (scaffold.build_guide_files(stack), scaffold.guide_files(stack)):
                    guide = files[scaffold.STACK_GUIDES[stack]]
                    self.assertIn("The database is already connected - never ask for one, never look for another", guide)
                    for rule in ("Never ask the customer for the database", "Do not look for a MongoDB on this computer",
                                 "`mongod`, `mongosh`, Docker", "Never drop a database"):
                        self.assertIn(rule, guide)
                    # What used to make the model ask for it, or go and check a local one, is gone.
                    for old in ("value-only question", "asked for before the plan", "carry on with the local fallback",
                                "customer's to supply"):
                        self.assertNotIn(old, guide)

    def test_the_build_prompts_say_it_too(self):
        for name in ("builder/generate", "builder/update"):
            text = (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("never look for a MongoDB on this computer", text.replace("Never look", "never look"), name)
            self.assertIn("MONGODB_URI", text, name)
        wiring = (ROOT / "prompts" / "builder" / "phase-wiring.md").read_text(encoding="utf-8")
        self.assertIn("do not look for, start or test a MongoDB on this computer", wiring)
        self.assertIn("names only, no real value", wiring)

    def test_the_question_before_the_plan_no_longer_offers_a_connection_string_as_something_to_ask(self):
        text = (ROOT / "prompts" / "builder" / "decide.md").read_text(encoding="utf-8")
        self.assertNotIn("a provider account, a connection string", text)
        self.assertIn("{{database}}", text)


if __name__ == "__main__":
    unittest.main()
