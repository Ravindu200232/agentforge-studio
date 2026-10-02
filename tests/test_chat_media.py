"""Chat uploads must land in the output app and remain safe across name collisions."""

import base64
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import httpd  # noqa: E402
from prototype_agent import prototype  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


class ChatMediaTests(unittest.TestCase):
    def test_upload_saves_media_announces_path_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(httpd.store, "exists", return_value=True), \
             patch.object(httpd.config, "workspace_for", return_value=Path(temporary)), \
             patch.object(httpd.bus, "agent_msg") as message:
            request = {"project": "prj_example", "filename": "../photo.png",
                       "mode": "image", "data_base64": base64.b64encode(b"image-data").decode()}
            first = httpd.attach_to_chat(request)
            second = httpd.attach_to_chat(request)

            self.assertEqual(first["path"], "media/photo.png")
            self.assertEqual(second["path"], "media/photo-2.png")
            self.assertEqual((Path(temporary) / first["path"]).read_bytes(), b"image-data")
            self.assertEqual((Path(temporary) / second["path"]).read_bytes(), b"image-data")
            self.assertEqual(message.call_args.kwargs["kind"], "attachment")
            self.assertEqual(message.call_args.args[1], second["path"])

    def test_invalid_content_is_rejected(self):
        with patch.object(httpd.store, "exists", return_value=True):
            with self.assertRaises(httpd.HttpError) as raised:
                httpd.attach_to_chat({"project": "prj_example", "filename": "bad.txt",
                                     "data_base64": "!"})
        self.assertEqual(raised.exception.status, 400)

    def test_design_image_upload_note_preview_and_remove_share_media_folder(self):
        class Session:
            def __init__(self, workspace):
                self.workspace = workspace
                self.record = workspace / ".agentforge"
                self.rows = []

            def read_record(self, *parts, fallback=None):
                return self.rows

            def write_record(self, *parts, data):
                self.rows = data

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            session = Session(workspace)
            with patch.object(httpd.store, "exists", return_value=True), \
                 patch.object(httpd.config, "workspace_for", return_value=workspace), \
                 patch.object(httpd, "session_for", return_value=session), \
                 patch.object(httpd.bus, "agent_msg") as message:
                payload = {"project": "prj_example", "filename": "../logo.png", "purpose": "Brand logo",
                           "data_base64": base64.b64encode(b"png-image").decode()}
                first = httpd.site_image_save(payload)
                second = httpd.site_image_save(payload)
                self.assertEqual(first["image"]["path"], "media/logo.png")
                self.assertEqual(second["image"]["path"], "media/logo-2.png")
                self.assertEqual(len(second["images"]), 2)
                self.assertEqual(message.call_args.kwargs["kind"], "attachment")
                manifest = (workspace / "media/IMAGES.md")
                self.assertIn("media/logo.png", manifest.read_text(encoding="utf-8"))
                self.assertIn("Brand logo", manifest.read_text(encoding="utf-8"))

                match = re.match(r"/site-image/(?P<project>[^/]+)/(?P<name>.+)",
                                 "/site-image/prj_example/logo.png")
                preview = httpd.site_image({"_match": match})
                self.assertEqual(preview.body, b"png-image")
                self.assertEqual(preview.content_type, "image/png")

                noted = httpd.site_image_describe({"project": "prj_example", "file": "logo.png",
                                                   "purpose": "Header identity"})
                self.assertEqual(noted["images"][0]["purpose"], "Header identity")
                self.assertIn("Header identity", manifest.read_text(encoding="utf-8"))
                dropped = httpd.site_image_drop({"project": "prj_example", "file": "logo.png"})
                self.assertEqual(len(dropped["images"]), 1)
                self.assertFalse((workspace / "media/logo.png").exists())
                self.assertTrue((workspace / "media/logo-2.png").exists())
                self.assertNotIn("media/logo.png", manifest.read_text(encoding="utf-8"))

    def test_design_image_rejects_non_image_and_preserves_existing_upload(self):
        with patch.object(httpd.store, "exists", return_value=True):
            with self.assertRaises(httpd.HttpError) as raised:
                httpd.site_image_save({"project": "prj_example", "filename": "notes.txt",
                                       "data_base64": base64.b64encode(b"text").decode()})
        self.assertEqual(raised.exception.status, 400)

    def test_prototype_stages_selected_media_without_moving_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            image = workspace / "media/logo.png"
            image.parent.mkdir()
            image.write_bytes(b"logo")
            session = SimpleNamespace(
                workspace=workspace,
                read_record=lambda *args, **kwargs: [
                    {"path": "media/logo.png", "purpose": "Brand logo"},
                    {"path": "media/../other.png", "purpose": "Unsafe"}])
            staged = prototype._uploaded_site_images(session, workspace / ".agentforge/prototype")
            self.assertEqual(staged, [{"name": "logo.png", "usage": "Brand logo",
                                       "source": "media/logo.png",
                                       "prototype_url": "assets/uploads/logo.png"}])
            self.assertEqual((workspace / ".agentforge/prototype/assets/uploads/logo.png").read_bytes(), b"logo")
            self.assertEqual(image.read_bytes(), b"logo")


if __name__ == "__main__":
    unittest.main()
