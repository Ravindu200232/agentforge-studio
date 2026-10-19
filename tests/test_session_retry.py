"""RetryingClient's retry-worthy exception coverage.

Found missing live: a real Ollama Cloud run hit `httpx.RemoteProtocolError`
("Server disconnected without sending a response") on turn 16 of a real
interview and the whole run died uncaught, despite Phase 0 raising
RETRY_ATTEMPTS specifically so a network blip gets more chances. httpx's own
transport exceptions are not subclasses of Python's ConnectionError/OSError/
TimeoutError, so `_transient()` never saw them as retryable.
"""
import ssl
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import session  # noqa: E402


class TransientClassificationTests(unittest.TestCase):
    def test_a_remote_protocol_error_is_transient(self):
        # Exactly the shape httpx raises for "server disconnected without
        # sending a response".
        self.assertTrue(session._transient(httpx.RemoteProtocolError("boom")))

    def test_every_httpx_transport_error_is_transient(self):
        for exc in (httpx.ConnectError("x"), httpx.ConnectTimeout("x"), httpx.ReadTimeout("x"),
                   httpx.WriteTimeout("x"), httpx.PoolTimeout("x"), httpx.ReadError("x"),
                   httpx.WriteError("x"), httpx.ProxyError("x"), httpx.LocalProtocolError("x")):
            self.assertTrue(session._transient(exc), type(exc).__name__)

    def test_a_non_transport_httpx_error_is_not_retried(self):
        # A malformed response body or a redirect loop is not something a
        # retry fixes.
        self.assertFalse(session._transient(httpx.DecodingError("bad body")))
        self.assertFalse(session._transient(httpx.TooManyRedirects("loop")))

    def test_application_json_errors_are_not_misclassified_as_connection_errors(self):
        self.assertFalse(session._transient(json.JSONDecodeError("Unterminated string", '{"model":"', 9)))
        self.assertTrue(session._transient(session.IncompleteModelStream("incomplete wire reply")))

    def test_the_original_built_in_exceptions_still_count(self):
        self.assertTrue(session._transient(ConnectionError("x")))
        self.assertTrue(session._transient(TimeoutError("x")))
        self.assertTrue(session._transient(OSError("x")))

    def test_a_retryable_status_code_still_counts(self):
        exc = Exception("rate limited")
        exc.status_code = 429
        self.assertTrue(session._transient(exc))

    def test_a_non_retryable_status_code_is_not_transient(self):
        exc = Exception("bad request")
        exc.status_code = 400
        self.assertFalse(session._transient(exc))

    def test_an_unrelated_exception_is_not_transient(self):
        self.assertFalse(session._transient(ValueError("not a network problem")))


class RetryingClientTests(unittest.TestCase):
    def test_an_incomplete_nonstreaming_wire_reply_is_retried_without_connection_cards(self):
        calls, notices = [], []

        class Inner:
            def chat(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    raise json.JSONDecodeError("Unterminated string", '{"message":"', 11)
                return "complete"

        client = session.RetryingClient(Inner(), on_connection=lambda state, fields: notices.append(state))
        with patch.object(session.time, "sleep"):
            self.assertEqual(client.chat(model="m", messages=[]), "complete")
        self.assertEqual(len(calls), 2)
        self.assertEqual(notices, [])

    def test_a_remote_protocol_error_is_retried_until_it_succeeds(self):
        calls = []

        class Inner:
            def chat(self, **kwargs):
                calls.append(1)
                if len(calls) < 3:
                    raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
                return "ok"

        with patch.object(session.time, "sleep"):
            client = session.RetryingClient(Inner())
            result = client.chat(model="m", messages=[])
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_a_remote_protocol_error_that_never_clears_is_eventually_raised(self):
        class Inner:
            def chat(self, **kwargs):
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

        with patch.object(session.time, "sleep"), \
             patch.object(session, "RETRY_ATTEMPTS", 3):
            client = session.RetryingClient(Inner())
            with self.assertRaises(httpx.RemoteProtocolError):
                client.chat(model="m", messages=[])


BAD_MAC = ssl.SSLError(1, "[SSL: SSLV3_ALERT_BAD_RECORD_MAC] sslv3 alert bad record mac (_ssl.c:2580)")


def _opening_fails(error, then):
    """An Ollama-style stream: nothing is sent until the first chunk is read, which is where the error comes out."""
    def stream():
        raise error
        yield  # pragma: no cover - makes this a generator
    return stream() if error is not None else iter(then)


class StreamedReplyTests(unittest.TestCase):
    """Cloud calls are streamed, and a stream's connection fails when it is read, not when `chat()` returns."""

    def _client(self, streams, **kwargs):
        calls = []

        class Inner:
            def chat(self, **kw):
                calls.append(kw)
                return streams[min(len(calls), len(streams)) - 1]()

        return session.RetryingClient(Inner(), **kwargs), calls

    def test_a_bad_tls_record_before_the_first_chunk_is_asked_for_again(self):
        # The live failure: the agent's next request after a tool ran, answered with a bad_record_mac alert.
        client, calls = self._client([lambda: _opening_fails(BAD_MAC, None), lambda: _opening_fails(BAD_MAC, None),
                                      lambda: iter(["a", "b"])])
        with patch.object(session.time, "sleep"):
            self.assertEqual(list(client.chat(model="m", messages=[], stream=True)), ["a", "b"])
        self.assertEqual(len(calls), 3)

    def test_a_malformed_stream_line_before_the_first_chunk_is_asked_for_again(self):
        broken = json.JSONDecodeError("Unterminated string", '{"model":"', 9)
        client, calls = self._client([lambda: _opening_fails(broken, None), lambda: iter(["complete"])])
        notices = []
        client._on_connection = lambda state, fields: notices.append(state)
        with patch.object(session.time, "sleep"):
            self.assertEqual(list(client.chat(model="m", messages=[], stream=True)), ["complete"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(notices, [])

    def test_the_agent_retries_an_incomplete_model_reply_without_duplicating_words(self):
        broken = json.JSONDecodeError("Unterminated string", '{"model":"', 9)

        def partial():
            yield SimpleNamespace(message=SimpleNamespace(content="partial", thinking=None, tool_calls=None))
            raise broken

        def complete():
            yield SimpleNamespace(message=SimpleNamespace(content="complete", thinking=None, tool_calls=None),
                                  done=True)

        client, calls = self._client([partial, complete])
        agent = session.Agent.__new__(session.Agent)
        agent.cloud = True
        agent.model = "m"
        agent.client = client
        with patch.object(session.time, "sleep"):
            reply = agent._chat_response({"model": "m", "messages": []})
        self.assertEqual(reply.message.content, "complete")
        self.assertEqual(len(calls), 2)

    def test_a_malformed_line_after_a_chunk_does_not_show_false_reconnections(self):
        broken = json.JSONDecodeError("Unterminated string", '{"model":"', 9)

        def partial():
            yield SimpleNamespace(message=SimpleNamespace(content="partial", thinking=None, tool_calls=None), done=False)
            raise broken

        def complete():
            yield SimpleNamespace(message=SimpleNamespace(content="whole", thinking=None, tool_calls=None), done=True)

        client, calls = self._client([partial, partial, complete])
        notices = []
        client._on_connection = lambda state, fields: notices.append(state)
        agent = session.Agent.__new__(session.Agent)
        agent.cloud = True
        agent.model = "m"
        agent.client = client
        with patch.object(session.time, "sleep"):
            reply = agent._chat_response({"model": "m", "messages": []})
        self.assertEqual(reply.message.content, "whole")
        self.assertEqual(len(calls), 3)
        self.assertEqual(notices, [])

    def test_persistently_malformed_replies_stop_after_the_bounded_retry_count(self):
        broken = json.JSONDecodeError("Unterminated string", '{"model":"', 9)

        def partial():
            yield SimpleNamespace(message=SimpleNamespace(content="partial", thinking=None, tool_calls=None), done=False)
            raise broken

        client, calls = self._client([partial])
        notices = []
        client._on_connection = lambda state, fields: notices.append(state)
        agent = session.Agent.__new__(session.Agent)
        agent.cloud = True
        agent.model = "m"
        agent.client = client
        with patch.object(session.time, "sleep"), patch.object(session, "RETRY_ATTEMPTS", 3):
            with self.assertRaisesRegex(RuntimeError, "model reply stayed incomplete"):
                agent._chat_response({"model": "m", "messages": []})
        self.assertEqual(len(calls), 3)
        self.assertEqual(notices, [])

    def test_a_connection_is_only_marked_restored_after_the_complete_reply(self):
        def starts_then_drops():
            yield SimpleNamespace(done=False)
            raise httpx.ReadError("connection reset")

        def complete():
            yield SimpleNamespace(done=False)
            yield SimpleNamespace(done=True)

        client, calls = self._client([starts_then_drops, complete])
        notices = []
        client._on_connection = lambda state, fields: notices.append(state)
        with patch.object(session.time, "sleep"):
            with self.assertRaises(httpx.ReadError):
                list(client.chat(model="m", messages=[], stream=True))
            client._next_attempt(httpx.ReadError("connection reset"), 0)
            stream = client.chat(model="m", messages=[], stream=True)
            self.assertEqual(next(stream).done, False)
            self.assertEqual(notices, ["retrying"])
            self.assertEqual(next(stream).done, True)
            self.assertEqual(notices, ["retrying"])
            with self.assertRaises(StopIteration):
                next(stream)
        self.assertEqual(notices, ["retrying", "ok"])

    def test_an_error_status_on_opening_the_stream_is_asked_for_again(self):
        busy = httpx.HTTPStatusError("bad gateway", request=httpx.Request("POST", "http://x"),
                                     response=httpx.Response(502))
        busy.status_code = 502
        client, calls = self._client([lambda: _opening_fails(busy, None), lambda: iter(["ok"])])
        with patch.object(session.time, "sleep"):
            self.assertEqual(list(client.chat(stream=True)), ["ok"])
        self.assertEqual(len(calls), 2)

    def test_a_failure_after_words_were_handed_on_is_raised_not_repeated(self):
        def drops_midway():
            yield "first words"
            raise httpx.ReadError("connection reset")

        client, calls = self._client([drops_midway, lambda: iter(["again"])])
        got = []
        with patch.object(session.time, "sleep"), self.assertRaises(httpx.ReadError):
            for chunk in client.chat(stream=True):
                got.append(chunk)
        self.assertEqual(got, ["first words"])
        self.assertEqual(len(calls), 1)

    def test_an_error_a_retry_cannot_fix_is_raised_at_once(self):
        client, calls = self._client([lambda: _opening_fails(ValueError("not a network problem"), None)])
        with patch.object(session.time, "sleep") as sleep, self.assertRaises(ValueError):
            list(client.chat(stream=True))
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_a_stream_that_never_clears_is_eventually_raised(self):
        client, calls = self._client([lambda: _opening_fails(BAD_MAC, None)])
        with patch.object(session.time, "sleep"), patch.object(session, "RETRY_ATTEMPTS", 3), \
             self.assertRaises(ssl.SSLError):
            list(client.chat(stream=True))
        self.assertEqual(len(calls), 3)

    def test_a_reply_that_is_not_a_stream_is_handed_back_as_it_is(self):
        reply = object()
        client, calls = self._client([lambda: reply])
        self.assertIs(client.chat(stream=True), reply)
        self.assertEqual(len(calls), 1)

    def test_it_retries_on_the_thread_that_lets_stop_end_a_wait(self):
        client, calls = self._client([lambda: _opening_fails(BAD_MAC, None), lambda: iter(["a"])],
                                     cancelled=lambda: False, wait_for_cancel=lambda seconds: False)
        self.assertEqual(list(client.chat(stream=True)), ["a"])
        self.assertEqual(len(calls), 2)

    def test_stop_during_the_wait_ends_the_retries(self):
        client, calls = self._client([lambda: _opening_fails(BAD_MAC, None)],
                                     cancelled=lambda: False, wait_for_cancel=lambda seconds: True)
        with self.assertRaises(session.RunCancelled):
            list(client.chat(stream=True))
        self.assertEqual(len(calls), 1)

    def test_the_retry_is_announced(self):
        said = []
        client, _ = self._client([lambda: _opening_fails(BAD_MAC, None), lambda: iter(["a"])], announce=said.append)
        with patch.object(session.time, "sleep"):
            list(client.chat(stream=True))
        self.assertEqual(len(said), 1)
        self.assertIn("[retry]", said[0])
        self.assertIn("BAD_RECORD_MAC", said[0])


if __name__ == "__main__":
    unittest.main()
