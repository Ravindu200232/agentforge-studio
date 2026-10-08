"""The web search the specification's notation references use (the local Ollama search, no key)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import llm  # noqa: E402


class SearchTests(unittest.TestCase):
    def test_the_local_ollama_search_is_asked_without_a_key_and_its_results_are_trimmed(self):
        reply = mock.Mock()
        reply.json.return_value = {"results": [{"title": "A", "url": "https://a.example", "content": "x" * 5000}, "junk"]}
        with mock.patch.object(llm.config, "settings", lambda: {"cloud": False, "ollama_host": "http://localhost:11434"}), \
             mock.patch.object(llm.httpx, "post", return_value=reply) as post:
            rows = llm.web_search("  a   query ", 3)
        self.assertEqual(post.call_args.args[0], "http://localhost:11434/api/experimental/web_search")
        self.assertEqual(post.call_args.kwargs["json"], {"query": "a query", "max_results": 3})
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["content"]), 1500)

    def test_a_search_that_fails_is_an_empty_answer(self):
        with mock.patch.object(llm.config, "settings", lambda: {"cloud": False}), \
             mock.patch.object(llm.httpx, "post", side_effect=OSError("offline")):
            self.assertEqual(llm.web_search("anything"), [])
        self.assertEqual(llm.web_search("   "), [])


if __name__ == "__main__":
    unittest.main()
