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
        for stack in ("remix-mongo", "remix-mongo-only", "vite-mongo-only", "mern-microservices-only"):
            self.assertEqual(deployment_stacks()[stack]["targets"], ["aws_ec2", "aws_ecs", "azure"], stack)
        self.assertEqual(deployment_stacks()["nextjs-mongo-only"]["targets"], "all")

    def test_every_stack_has_a_template_a_guide_and_an_uploads_rule_where_it_needs_one(self):
        for stack in scaffold.STACK_GUIDES:
            with self.subTest(stack=stack):
                folder = scaffold.template_dir(stack)
                self.assertTrue(folder.is_dir(), folder)
                self.assertTrue(any((folder / name).is_file() for name in ("package.json", "package.json.tpl")))
                self.assertIn(scaffold.STACK_GUIDES[stack], scaffold.guide_files(stack))
                self.assertEqual(stack in scaffold.UPLOAD_GUIDES, scaffold.uses_mongodb(stack))

    def test_the_original_stack_ids_keep_their_templates_and_their_supabase_bucket(self):
        for stack in ("nextjs-mongo", "vite-mongo", "mern-microservices"):
            self.assertEqual(scaffold.template_dir(stack).name, stack)
            self.assertTrue(scaffold.uses_supabase(stack))
            self.assertEqual(scaffold.UPLOAD_GUIDES[stack], "uploads-supabase.md")

    def test_a_mongo_only_stack_installs_its_twins_template(self):
        for only in MONGO_ONLY:
            twin = only.removesuffix("-only")
            twin = {"mern-microservices": "mern-microservices"}.get(twin, twin)
            self.assertEqual(scaffold.template_dir(only), scaffold.template_dir(twin), only)

    def test_an_unknown_stack_is_still_refused(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "unsupported build stack"):
            scaffold.install(Path(folder), "nextjs-nosql")


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

    def test_no_mongodb_template_holds_any_supabase_code(self):
        for template in {scaffold.template_dir(stack) for stack in scaffold.STACK_GUIDES if scaffold.uses_mongodb(stack)}:
            for path in template.rglob("*"):
                if path.is_file():
                    self.assertNotIn("supabase", path.read_text(encoding="utf-8", errors="ignore").lower(),
                                     path.relative_to(scaffold.ROOT).as_posix())

    def test_a_mongo_only_project_installs_with_no_supabase_file_or_dependency(self):
        for stack in MONGO_ONLY:
            with self.subTest(stack=stack), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                result = scaffold.install(workspace, stack)
                self.assertTrue(result["scaffolded"])
                self.assertFalse((workspace / "supabase").exists())
                self.assertEqual([path for path in result["files"] if "supabase" in path.lower()], [])
                manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
                dependencies = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
                self.assertEqual([name for name in dependencies if "supabase" in name], [])


class RemixMongoTemplateTests(unittest.TestCase):
    def test_the_template_is_remix_on_mongodb(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            result = scaffold.install(workspace, "remix-mongo")
            self.assertTrue(result["scaffolded"])
            self.assertEqual(result["source"], "builder_agent/assets/templates/remix-mongo")
            for path in ("app/root.jsx", "app/routes/_index.jsx", "lib/db.js", "scripts/seed.mjs", "vite.config.js",
                         "test/helpers/db.js", "test/helpers/remix.js", "vitest.config.js", "vitest.env.js"):
                self.assertTrue((workspace / path).is_file(), path)
            manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
            for name in ("@remix-run/node", "@remix-run/react", "@remix-run/serve", "mongoose", "bcryptjs", "jose"):
                self.assertIn(name, manifest["dependencies"])
            self.assertEqual(manifest["scripts"]["start"], "remix-serve ./build/server/index.js")
            slug = scaffold.project_slug(workspace.name)
            self.assertIn(f"{slug}_test", (workspace / "vitest.env.js").read_text(encoding="utf-8"))
            self.assertIn(f"{slug}_test", (workspace / "test/helpers/db.js").read_text(encoding="utf-8"))
            self.assertNotIn("__APP_DB__", (workspace / "lib/db.js").read_text(encoding="utf-8"))


class BuildGateTests(StraightThroughCase):
    """`build.run` connects (or creates) the project's Supabase project only for a stack that uses Supabase."""

    def build_stack(self, stack: str) -> str:
        self.session.results.append({"status": "complete", "text": "done", "plan": "p"})
        with mock.patch.object(build.store, "require", return_value={"stack": stack, "name": "Shop"}), \
             mock.patch("builder_agent.scaffold.install", mock.Mock(return_value={"scaffolded": True, "files": []})):
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


if __name__ == "__main__":
    unittest.main()
