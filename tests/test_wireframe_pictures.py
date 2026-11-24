"""Picture overlays persist in the authored HTML together with local assets."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import wireframe_pictures  # noqa: E402


PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII="


class WireframePictureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.page = self.root / "wireframe-html" / "home.html"
        self.page.parent.mkdir()
        self.source = "<!doctype html><html><body><h1>Home</h1></body></html>"
        self.page.write_text(self.source, encoding="utf-8")
        self.session = SimpleNamespace(record=self.root, lock=threading.RLock(), write_record=self.write)

    def write(self, *parts, data):
        self.root.joinpath(*parts).write_text(data, encoding="utf-8")

    def save(self, pictures, uploads=None, revision=None):
        return wireframe_pictures.save(self.session, self.page, {
            "pictures": pictures, "uploads": uploads or {},
            "revision": revision or wireframe_pictures.read(self.page)["revision"],
        })

    def test_saves_triangle_crop_and_asset_without_interpreting_text(self):
        row = {"id": "first", "asset": "new-picture", "shape": "triangle", "x": 40, "y": 60,
               "w": 220, "h": 120, "fit": "fit", "zoom": 2, "panX": 12, "rotation": 30,
               "naturalW": 7, "naturalH": 5, "flipX": True, "opacity": 75,
               "border": 4, "color": "#666666", "group": "group-1", "alt": '"><script>bad()</script>'}
        saved = self.save([row], {"new-picture": PIXEL})
        self.assertEqual(wireframe_pictures.read(self.page), saved)
        asset = saved["pictures"][0]["asset"]
        self.assertTrue((self.page.parent / "assets" / "pictures" / asset).is_file())
        page = self.page.read_text(encoding="utf-8")
        for expected in (f'assets/pictures/{asset}', '<polygon ', 'stroke-width="8"', 'rotate(30deg)',
                         'opacity:0.75', 'scale(-1 1)', '<h1>Home</h1>', '&lt;script&gt;'):
            self.assertIn(expected, page)
        self.assertNotIn('<script>bad()', page)
        self.assertEqual(page.count("agentforge-pictures:start"), 1)
        reordered = self.save([{**saved["pictures"][0], "shape": "circle", "w": 90, "h": 60}])
        self.assertEqual(reordered["pictures"][0]["h"], 90)
        self.assertIn("<ellipse ", self.page.read_text(encoding="utf-8"))

    def test_rejects_stale_or_invalid_saves_and_restores_page_when_removed(self):
        original = wireframe_pictures.read(self.page)["revision"]
        saved = self.save([{"id": "pic", "asset": "uploaded"}], {"uploaded": PIXEL})
        with self.assertRaisesRegex(ValueError, "wireframe changed"):
            self.save([], revision=original)
        with self.assertRaisesRegex(ValueError, "choose a PNG"):
            self.save([{"id": "pic", "asset": "fake"}], {"fake": "PHN2Zy8+"})
        self.assertEqual(wireframe_pictures.read(self.page), saved)
        self.assertEqual(self.save([])["pictures"], [])
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.source)

    def test_picture_icon_is_saved_as_a_shaped_placeholder_without_an_upload(self):
        saved = self.save([{"id": "icon", "asset": "placeholder", "shape": "triangle", "x": 15, "y": 25,
                            "name": "Picture placeholder", "w": 120, "h": 90, "border": 1}])
        page = self.page.read_text(encoding="utf-8")
        self.assertIn('aria-label="Picture placeholder"', page)
        self.assertIn('<polygon points="60.0,0 120,90 0,90"', page)
        self.assertIn('<path d="m3 17', page)
        self.assertNotIn("<image href", page)
        self.assertEqual(wireframe_pictures.read(self.page), saved)
