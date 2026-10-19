"""The Studio's bridge goes into every page of a built app's preview, so picking an element works across sites.

The preview of a built app is another site than the Studio (http://127.0.0.1:PORT framed in localhost:3000 or agentforge://app), so
the Studio cannot reach into its page: picking an element, the page's address and its console go through a bridge script in the
page. Nothing put it there, and picking an element in the build did nothing. The preview's hook (`frame-headers.cjs`, loaded into
the preview process only) now serves the bridge and adds it to each page, whatever server sends it.
"""
from __future__ import annotations

import gzip
import shutil
import subprocess
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "server_modules" / "preview_hooks" / "frame-headers.cjs"
TAG = b'<script src="/__agentforge/preview-bridge.js" defer></script>'

SERVER = r"""
const http = require('http')
const zlib = require('zlib')
const page = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Shop</title></head><body><header>héllo</header></body></html>'
const server = http.createServer((req, res) => {
  if (req.url === '/sized') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    res.setHeader('Content-Length', Buffer.byteLength(page))
    res.setHeader('X-Frame-Options', 'DENY')
    return res.end(page)
  }
  if (req.url === '/streamed') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Length': '9999' })
    res.write(Buffer.from('<!DOCTYPE html><html lang="en"><head>'))
    return setTimeout(() => res.end('<title>x</title></head><body>streamed</body></html>'), 20)
  }
  if (req.url === '/compressed') {
    const gzipped = /gzip/.test(req.headers['accept-encoding'] || '')
    res.writeHead(200, { 'Content-Type': 'text/html', ...(gzipped ? { 'Content-Encoding': 'gzip' } : {}) })
    return res.end(gzipped ? zlib.gzipSync(page) : page)
  }
  if (req.url === '/header-only') {
    res.setHeader('Content-Type', 'text/html')
    return res.end('<html><body><header>no head of its own</header></body></html>')
  }
  res.setHeader('Content-Type', 'application/json')
  res.end('{"html": "<head></head>"}')
})
server.listen(0, '127.0.0.1', () => console.log(server.address().port))
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed")
class TheBridgeIsInEveryPreviewPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = subprocess.Popen(["node", "--require", str(HOOK), "-e", SERVER], stdout=subprocess.PIPE, text=True)
        cls.port = int(cls.server.stdout.readline().strip())

    @classmethod
    def tearDownClass(cls):
        cls.server.kill()
        cls.server.wait(timeout=10)

    def get(self, path: str, accept: str = "text/html,application/xhtml+xml", **headers: str):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         headers={"Accept": accept, "Accept-Encoding": "gzip", **headers})
        with urllib.request.urlopen(request, timeout=10) as answer:
            body = answer.read()
            if answer.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return answer, body

    def test_a_page_gets_the_bridge_first_in_its_head_and_a_length_that_fits(self):
        answer, body = self.get("/sized")
        self.assertTrue(body.startswith(b'<!DOCTYPE html><html><head>' + TAG + b'<meta charset="utf-8">'), body[:120])
        self.assertIn("héllo".encode("utf-8"), body)                       # the page's own bytes are untouched
        self.assertNotEqual(answer.headers.get("Content-Length"), str(len(body) - len(TAG)))
        self.assertIsNone(answer.headers.get("X-Frame-Options"))           # what the hook already did still holds

    def test_a_streamed_page_gets_it_in_the_chunk_that_opens_its_head(self):
        _answer, body = self.get("/streamed")
        self.assertEqual(body.count(TAG), 1)
        self.assertTrue(body.startswith(b'<!DOCTYPE html><html lang="en"><head>' + TAG), body[:100])
        self.assertTrue(body.endswith(b"streamed</body></html>"))

    def test_a_page_is_asked_for_uncompressed_so_it_can_carry_the_bridge(self):
        answer, body = self.get("/compressed")
        self.assertIsNone(answer.headers.get("Content-Encoding"))
        self.assertIn(TAG, body)

    def test_data_a_client_navigation_and_a_header_that_is_not_a_head_are_left_alone(self):
        self.assertNotIn(TAG, self.get("/data", accept="application/json")[1])
        self.assertNotIn(TAG, self.get("/sized", rsc="1")[1])
        _answer, body = self.get("/header-only")
        self.assertEqual(body, b"<html><body><header>no head of its own</header></body></html>")

    def test_the_bridge_itself_is_served(self):
        answer, body = self.get("/__agentforge/preview-bridge.js", accept="*/*")
        self.assertIn("javascript", answer.headers.get("Content-Type"))
        self.assertIn(b"agentforge:command", body)
        self.assertIn(b"agentforge:preview", body)


class TheBridgeAnswersWhatTheStudioAsksTests(unittest.TestCase):
    """The messages the Studio's preview pane sends and waits for (`studio/components/PreviewPane.jsx`)."""

    def test_every_command_the_pane_sends_and_every_answer_it_reads_is_in_the_bridge(self):
        pane = (ROOT / "studio" / "components" / "PreviewPane.jsx").read_text(encoding="utf-8")
        bridge = (ROOT / "server_modules" / "preview_hooks" / "preview-bridge.js").read_text(encoding="utf-8")
        for command in ("init", "pick"):
            self.assertIn(f"bridgeSend('{command}'", pane)
            self.assertIn(f"message.kind === '{command}'", bridge)
        for answer in ("ready", "route", "console", "picked"):
            self.assertIn(f"message.kind === '{answer}'", pane)
            self.assertIn(f"'{answer}'", bridge)


if __name__ == "__main__":
    unittest.main()
