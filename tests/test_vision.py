"""Which models can look at a picture: what Ollama says of each, remembered, and offered to the model picker."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import config, httpd, vision  # noqa: E402


class VisionCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patch = mock.patch.object(vision, "FILE", Path(self.temp.name) / "model-capabilities.json")
        patch.start()
        self.addCleanup(patch.stop)
        vision.forget()
        self.addCleanup(vision.forget)


class WhatOllamaSaysTests(unittest.TestCase):
    def test_a_model_that_lists_vision_among_its_capabilities_reads_images(self):
        self.assertTrue(vision.from_show(SimpleNamespace(capabilities=["completion", "tools", "vision"])))
        self.assertTrue(vision.from_show({"capabilities": ["vision", "thinking"]}))

    def test_a_model_that_lists_capabilities_without_vision_does_not(self):
        self.assertFalse(vision.from_show(SimpleNamespace(capabilities=["completion", "tools", "thinking"])))
        self.assertFalse(vision.from_show(SimpleNamespace(capabilities=[])))

    def test_an_older_ollama_without_capabilities_is_read_by_the_image_encoder_it_names(self):
        families = SimpleNamespace(capabilities=None, details=SimpleNamespace(families=["llama", "clip"]), modelinfo=None)
        self.assertTrue(vision.from_show(families))
        info = SimpleNamespace(capabilities=None, details=SimpleNamespace(families=["llama"]),
                               modelinfo={"llama.context_length": 8192, "mllama.vision.block_count": 32})
        self.assertTrue(vision.from_show(info))
        plain = SimpleNamespace(capabilities=None, details=SimpleNamespace(families=["llama"]),
                                modelinfo={"llama.context_length": 8192})
        self.assertFalse(vision.from_show(plain))

    def test_an_answer_that_says_nothing_either_way_is_unknown_not_no(self):
        self.assertIsNone(vision.from_show(SimpleNamespace(capabilities=None, details=None, modelinfo=None)))


class RememberingTests(VisionCase):
    def test_a_model_is_asked_once_and_then_remembered(self):
        with mock.patch.object(vision, "_ask", return_value=True) as ask:
            self.assertTrue(vision.supports("gemma4:31b-cloud"))
            self.assertTrue(vision.supports("gemma4:31b-cloud"))
        ask.assert_called_once_with("gemma4:31b-cloud")

    def test_a_model_that_cannot_be_asked_is_unknown_and_asked_again_next_time(self):
        with mock.patch.object(vision, "_ask", side_effect=[None, False]) as ask:
            self.assertIsNone(vision.supports("m"))
            self.assertFalse(vision.supports("m"))
        self.assertEqual(ask.call_count, 2)

    def test_no_model_is_unknown(self):
        self.assertIsNone(vision.supports(""))

    def test_answers_survive_a_restart_and_go_stale_after_a_week(self):
        with mock.patch.object(vision, "_ask", return_value=True):
            vision.supports("m")
        vision._known.clear()
        vision._loaded = False
        with mock.patch.object(vision, "_ask", side_effect=AssertionError("asked again")):
            self.assertTrue(vision.supports("m"))                     # read back from disk
        vision._known["m"]["at"] = time.time() - vision.TTL_SECONDS - 5
        with mock.patch.object(vision, "_ask", return_value=False) as ask:
            self.assertFalse(vision.supports("m"))                    # a week on: asked again
        ask.assert_called_once()

    def test_ask_reads_what_the_client_says_and_a_failing_client_is_unknown(self):
        client = mock.Mock()
        client.show.return_value = SimpleNamespace(capabilities=["vision"])
        with mock.patch("server_modules.llm.client", return_value=client):
            self.assertTrue(vision._ask("m"))
        client.show.assert_called_once_with("m")
        client.show.side_effect = RuntimeError("down")
        with mock.patch("server_modules.llm.client", return_value=client):
            self.assertIsNone(vision._ask("m"))


class ForThePickerTests(VisionCase):
    def wait_for(self, models, answered):
        for _ in range(100):
            result = vision.capabilities(models)
            if not result["pending"]:
                return result
            time.sleep(0.05)
        self.fail("the background asking never finished")

    def test_it_answers_at_once_with_what_is_known_and_fills_in_the_rest_in_the_background(self):
        gate = threading.Event()

        def ask(model):
            gate.wait(5)
            return model.startswith("v")
        with mock.patch.object(vision, "_ask", side_effect=ask):
            first = vision.capabilities(["vision-a", "plain-b"])
            self.assertEqual((first["capabilities"], first["pending"]), ({}, 2))
            gate.set()
            done = self.wait_for(["vision-a", "plain-b"], 2)
        self.assertEqual(done["capabilities"], {"vision-a": {"vision": True}, "plain-b": {"vision": False}})

    def test_a_model_is_not_asked_about_twice_while_an_answer_is_awaited(self):
        gate = threading.Event()
        calls = []

        def ask(model):
            calls.append(model)
            gate.wait(5)
            return True
        with mock.patch.object(vision, "_ask", side_effect=ask):
            vision.capabilities(["m"])
            vision.capabilities(["m"])
            vision.capabilities(["m"])
            gate.set()
            self.wait_for(["m"], 1)
        self.assertEqual(calls, ["m"])

    def test_a_model_that_could_not_be_asked_is_left_alone_for_a_couple_of_minutes_and_not_reported_pending(self):
        with mock.patch.object(vision, "_ask", return_value=None) as ask:
            self.wait_for(["m"], 1)
            result = vision.capabilities(["m"])
            self.assertEqual((result["capabilities"], result["pending"]), ({}, 0))   # the picker stops waiting
            vision.capabilities(["m"])
        ask.assert_called_once()
        vision._failed["m"] = time.time() - vision.RETRY_SECONDS - 1
        with mock.patch.object(vision, "_ask", return_value=True):
            self.wait_for(["m"], 1)
        self.assertEqual(vision.capabilities(["m"])["capabilities"], {"m": {"vision": True}})

    def test_duplicates_and_blanks_are_ignored(self):
        with mock.patch.object(vision, "_ask", return_value=False):
            self.wait_for(["a", "a", "", " a "], 1)
        self.assertEqual(vision.capabilities(["a", "a", ""])["capabilities"], {"a": {"vision": False}})

    def test_the_route_lists_every_model_the_picker_shows(self):
        listing = {"local_models": [{"id": "llama3.2-vision:11b"}, {"id": "phi4:14b"}],
                   "cloud": [{"id": "gemma4:31b-cloud", "tag": "cloud"}]}
        with mock.patch.object(httpd, "models", return_value=listing), \
                mock.patch.object(vision, "capabilities", return_value={"capabilities": {}, "pending": 3}) as caps:
            answer = httpd.dispatch("GET", "/models/capabilities", {}, {})
        caps.assert_called_once_with(["llama3.2-vision:11b", "phi4:14b", "gemma4:31b-cloud"])
        self.assertEqual(answer, {"capabilities": {}, "pending": 3})


if __name__ == "__main__":
    unittest.main()
