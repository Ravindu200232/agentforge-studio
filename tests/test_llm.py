"""server_modules.llm's context-window sizing for the one-shot calls.

A focused SRS/wireframe/prototype call has no `Agent` to remember a model's
real context window between turns the way the tool-using conversation does —
`_num_ctx()` is what gives it the same sizing anyway, without asking the
server on every single call.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import config, llm  # noqa: E402


class FakeShowClient:
    def __init__(self):
        self.show_calls: list[str] = []

    def show(self, model):
        self.show_calls.append(model)
        return SimpleNamespace(modelinfo={"llama.context_length": 32768})


class NumCtxTests(unittest.TestCase):
    def setUp(self):
        llm._context_cache.clear()
        self.addCleanup(llm._context_cache.clear)

    def test_a_manual_setting_wins_and_never_asks_the_server(self):
        client = FakeShowClient()
        with mock.patch.object(config, "settings",
                               lambda: {**config.DEFAULTS, "context": 4096}), \
             mock.patch.object(llm, "client", return_value=client):
            self.assertEqual(llm._num_ctx("some-model"), 4096)
        self.assertEqual(client.show_calls, [])

    def test_with_no_override_the_models_own_context_is_learned_and_cached(self):
        client = FakeShowClient()
        with mock.patch.object(config, "settings",
                               lambda: {**config.DEFAULTS, "context": 0}), \
             mock.patch.object(llm, "client", return_value=client):
            self.assertEqual(llm._num_ctx("big-model"), 32768)
            self.assertEqual(llm._num_ctx("big-model"), 32768)
        self.assertEqual(client.show_calls, ["big-model"])   # learned once, reused

    def test_a_model_the_server_cannot_describe_gets_no_options_at_all(self):
        class SilentClient:
            def show(self, model):
                raise RuntimeError("unknown model")

        with mock.patch.object(config, "settings",
                               lambda: {**config.DEFAULTS, "context": 0}), \
             mock.patch.object(llm, "client", return_value=SilentClient()):
            self.assertIsNone(llm._num_ctx("mystery-model"))

    def test_cloud_mode_never_sends_num_ctx_even_with_a_learnable_model(self):
        calls: list[dict] = []

        class ChatClient(FakeShowClient):
            def chat(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(message=SimpleNamespace(content="ok", thinking=""))

        with mock.patch.object(config, "settings",
                               lambda: {**config.DEFAULTS, "cloud": True, "model": "cloud-model",
                                       "ollama_api_key": "k", "context": 0}), \
             mock.patch.object(llm, "client", return_value=ChatClient()), \
             mock.patch.object(llm, "_tools_for", return_value=None):
            llm.complete("sys", "usr")
        self.assertNotIn("options", calls[0])


if __name__ == "__main__":
    unittest.main()
