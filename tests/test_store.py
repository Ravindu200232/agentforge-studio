"""A new project gets a predictable, empty stage-folder skeleton immediately,
so a read tool can find its way around before any stage has run."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import config, store  # noqa: E402


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        patches = [
            mock.patch.object(config, "WORKSPACES", root / "workspaces"),
            mock.patch.object(config, "PROJECTS_FILE", root / ".agentforge-server" / "projects.json"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_creating_a_project_lays_out_the_whole_pipelines_empty_skeleton(self):
        record = store.create(idea="A shop")
        record_dir = config.record_dir(record["id"])
        for relative in config.SCAFFOLD_DIRS:
            folder = record_dir / relative
            self.assertTrue(folder.is_dir(), f"{relative} was not created")
            self.assertEqual(list(folder.iterdir()), [])

    def test_scaffolding_is_idempotent_and_never_clobbers_existing_content(self):
        record = store.create(idea="A shop")
        marker = config.record_dir(record["id"]) / "srs" / "srs.json"
        marker.write_text("{}", encoding="utf-8")

        config.scaffold_workspace(record["id"])   # called again, e.g. a duplicate create()

        self.assertEqual(marker.read_text(encoding="utf-8"), "{}")
        for relative in config.SCAFFOLD_DIRS:
            self.assertTrue((config.record_dir(record["id"]) / relative).is_dir())

    def test_a_new_project_can_use_the_empty_folder_the_customer_selected(self):
        selected = Path(self.temp.name) / "my-new-project"
        selected.mkdir()

        record = store.create(idea="A shop", workspace_path=str(selected))

        self.assertEqual(config.workspace_for(record["id"]), selected.resolve())
        self.assertTrue(config.has_custom_workspace(record["id"]))
        self.assertEqual(store.require(record["id"])["workspace_path"], str(selected.resolve()))
        self.assertTrue((selected / config.RECORD_DIR).is_dir())

    def test_a_selected_folder_with_existing_files_is_refused_before_a_project_is_created(self):
        selected = Path(self.temp.name) / "already-in-use"
        selected.mkdir()
        (selected / "important.txt").write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "empty folder"):
            store.create(idea="A shop", workspace_path=str(selected))

        self.assertEqual((selected / "important.txt").read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
