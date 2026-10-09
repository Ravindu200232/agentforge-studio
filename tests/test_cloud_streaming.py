"""A model served from ollama.com is streamed: one long response is cut off by the service's edge (Cloudflare "524")."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", ".deps/py312"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal.agent import Agent, served_from_cloud  # noqa: E402
from server_modules import config, llm, llm_tools  # noqa: E402


class NameTests(unittest.TestCase):
    def test_a_model_is_served_from_the_cloud_by_its_name(self):
        for name in ("deepseek-v4.1-flash:cloud", "kimi-k2.7-code:cloud", "gpt-oss:120b-cloud", "deepseek-v4-pro:0813-cloud", " GLM-5.3:CLOUD "):
            self.assertTrue(served_from_cloud(name), name)
        for name in ("llama3:8b", "qwen3:30b", "gemma3", "", None):
            self.assertFalse(served_from_cloud(name), name)


class AskedAsStreamTests(unittest.TestCase):
    def setUp(self):
        self.asked: list[dict] = []

        def run_chat(chat, kwargs, tools, **_):
            self.asked.append(dict(kwargs))
            return SimpleNamespace(content='{"ok": true}', thinking="")

        for patch in (mock.patch.object(llm_tools, "run_chat", run_chat),
                      mock.patch.object(llm, "_tools_for", return_value=None),
                      mock.patch.object(llm, "_context_for", return_value=0),
                      mock.patch.object(llm, "client", return_value=SimpleNamespace(chat=None)),
                      mock.patch.object(config, "thinking_enabled", return_value=False)):
            patch.start()
            self.addCleanup(patch.stop)

    def settings(self, **values):
        return mock.patch.object(config, "setting", lambda name, fallback=None: values.get(name, fallback))

    def test_a_cloud_model_reached_through_the_local_ollama_is_asked_for_as_a_stream(self):
        with self.settings(cloud=False):
            llm.complete("system", "user", model="deepseek-v4.1-flash:cloud")
            llm.complete_json("system", "user", lambda value: value, model="deepseek-v4.1-flash:cloud")
        self.assertEqual([row["stream"] for row in self.asked], [True, True])

    def test_a_model_on_this_computer_is_not_streamed_as_before(self):
        with self.settings(cloud=False):
            llm.complete("system", "user", model="llama3:8b")
            llm.complete_json("system", "user", lambda value: value, model="llama3:8b")
        self.assertEqual([row["stream"] for row in self.asked], [False, False])

    def test_the_cloud_setting_still_streams_every_model(self):
        with self.settings(cloud=True):
            llm.complete("system", "user", model="llama3:8b")
        self.assertEqual([row["stream"] for row in self.asked], [True])


class AgentStreamTests(unittest.TestCase):
    def agent(self, model, cloud=False):
        agent = Agent.__new__(Agent)
        agent.model, agent.cloud = model, cloud
        agent.calls = []

        class Client:
            def chat(inner, **kwargs):
                agent.calls.append(kwargs)
                if kwargs.get("stream"):
                    return iter([SimpleNamespace(message=SimpleNamespace(content="hel", thinking=None, tool_calls=None)),
                                 SimpleNamespace(message=SimpleNamespace(content="lo", thinking=None, tool_calls=None))])
                return SimpleNamespace(message=SimpleNamespace(content="hello", thinking=None, tool_calls=None))
        agent.client = Client()
        return agent

    def test_the_agent_streams_a_cloud_model_and_puts_the_reply_back_together(self):
        agent = self.agent("deepseek-v4.1-flash:cloud")
        answer = agent._chat_response({"model": agent.model, "messages": [], "stream": False})
        self.assertTrue(agent.calls[0]["stream"])
        self.assertEqual(answer.message.content, "hello")

    def test_the_agent_keeps_the_single_response_for_a_model_on_this_computer(self):
        agent = self.agent("llama3:8b")
        agent._chat_response({"model": agent.model, "messages": [], "stream": False})
        self.assertFalse(agent.calls[0]["stream"])


class CutOffReplyTests(unittest.TestCase):
    """A streamed reply that is cut off part-way is asked for again, whole: nothing was shown, so nothing is said twice."""

    def agent(self):
        agent = Agent.__new__(Agent)
        agent.model, agent.cloud = "deepseek-v4.1-flash:cloud", False
        agent.asked = 0
        agent.retries: list[tuple] = []
        outer = agent

        class Cut(Exception):
            pass

        def chunk(text):
            return SimpleNamespace(message=SimpleNamespace(content=text, thinking=None, tool_calls=None))

        def broken():
            yield chunk("hel")
            raise Cut("peer closed connection without sending complete message body (incomplete chunked read)")

        class Client:
            def chat(inner, **kwargs):
                outer.asked += 1
                return broken() if outer.asked == 1 else iter([chunk("hello"), chunk(" again")])

            def _next_attempt(inner, exc, attempt):
                outer.retries.append((type(exc).__name__, attempt))
                return attempt + 1
        agent.client = Client()
        return agent

    def test_a_reply_cut_off_part_way_is_asked_for_again_and_comes_back_whole(self):
        agent = self.agent()
        answer = agent._chat_response({"model": agent.model, "messages": []})
        self.assertEqual(answer.message.content, "hello again")          # not "helhello again"
        self.assertEqual(agent.asked, 2)
        self.assertEqual(agent.retries, [("Cut", 0)])

    def test_a_client_that_does_not_retry_lets_the_failure_through_as_before(self):
        agent = self.agent()
        del type(agent.client)._next_attempt
        with self.assertRaises(Exception) as caught:
            agent._chat_response({"model": agent.model, "messages": []})
        self.assertIn("peer closed connection", str(caught.exception))
        self.assertEqual(agent.asked, 1)



if __name__ == "__main__":
    unittest.main()
