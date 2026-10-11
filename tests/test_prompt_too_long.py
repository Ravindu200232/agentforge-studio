"""A request the model refuses for being longer than its window is compacted and asked again, not the end of the run.

Found live: a long project's shared context reached 1,643,388 tokens against a 1,048,576-token window, and the testing
stage failed at once with "The prompt is too long". The four-characters-a-token estimate had stayed under the compaction
threshold the whole time, because the history carried text that tokenizes far more densely than that.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import agent as agent_module  # noqa: E402
from ollama_terminal.agent import Agent, prompt_too_long  # noqa: E402

REFUSAL = ("The prompt is too long: 1643388, model maximum context length: 1048576 "
           "(ref: 28879320-f482-42cf-873c-68d5e12a996b) (status code: 400)")


class Message(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {"role": "assistant", "content": self.content}


class ParseTests(unittest.TestCase):
    def test_the_models_own_count_is_read_from_its_refusal(self):
        self.assertEqual(prompt_too_long(RuntimeError(REFUSAL)), 1643388)

    def test_any_other_failure_is_not_a_length_refusal(self):
        self.assertEqual(prompt_too_long(RuntimeError("500 Internal Server Error")), 0)
        self.assertEqual(prompt_too_long(RuntimeError("context deadline exceeded")), 0)


class CompactAndAskAgainTests(unittest.TestCase):
    def agent(self, refusals: int):
        agent = Agent.__new__(Agent)
        agent.model, agent.mode, agent.mcp, agent.think, agent.options = "m", "act", None, None, None
        agent.context, agent.max_steps = 1_048_576, 6
        agent.messages = [{"role": "system", "content": "sys"}]
        agent.last_terminal_signal = ""
        agent.last_prompt_tokens, agent.prompt_tokens, agent.completion_tokens = 0, 0, 0
        agent.token_scale = 1.0
        agent.said, agent.compactions, agent.asked = [], [], 0
        agent.announce = agent.said.append
        agent._system_message = lambda: "sys"

        def summarize():
            # Stands in for the real compaction: records what triggered it.
            estimate = int(agent_module._approx_tokens(agent.messages) * agent.token_scale)
            if max(estimate, agent.last_prompt_tokens) >= agent.context * 0.88:
                agent.compactions.append(agent.last_prompt_tokens)
                agent.last_prompt_tokens = 0
        agent._summarize_history = summarize

        def chat(kwargs):
            agent.asked += 1
            if agent.asked <= refusals:
                raise RuntimeError(REFUSAL)
            return SimpleNamespace(message=Message(content="done", thinking=None, tool_calls=None), prompt_eval_count=900)
        agent._chat_response = chat
        return agent

    def test_the_history_is_compacted_and_the_request_asked_again(self):
        agent = self.agent(refusals=1)
        self.assertEqual(agent.ask("run the tests"), "done")
        self.assertEqual(agent.asked, 2)
        self.assertEqual(agent.compactions, [1643388])
        self.assertTrue(any("1,643,388 tokens" in line for line in agent.said))

    def test_later_estimates_use_what_the_model_counted(self):
        agent = self.agent(refusals=1)
        agent.messages.append({"role": "user", "content": "x" * 400})
        agent.ask("run the tests")
        self.assertGreater(agent.token_scale, 1.0)

    def test_a_request_still_too_long_after_three_compactions_fails_as_before(self):
        agent = self.agent(refusals=10)
        with self.assertRaises(RuntimeError) as caught:
            agent.ask("run the tests")
        self.assertIn("prompt is too long", str(caught.exception))
        self.assertEqual(agent.asked, 4)


if __name__ == "__main__":
    unittest.main()
