"""RetryingClient's retry-worthy exception coverage.

Found missing live: a real Ollama Cloud run hit `httpx.RemoteProtocolError`
("Server disconnected without sending a response") on turn 16 of a real
interview and the whole run died uncaught, despite Phase 0 raising
RETRY_ATTEMPTS specifically so a network blip gets more chances. httpx's own
transport exceptions are not subclasses of Python's ConnectionError/OSError/
TimeoutError, so `_transient()` never saw them as retryable.
"""
import ssl
import sys
import unittest
from pathlib import Path
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
