"""RetryingClient's retry-worthy exception coverage.

Found missing live: a real Ollama Cloud run hit `httpx.RemoteProtocolError`
("Server disconnected without sending a response") on turn 16 of a real
interview and the whole run died uncaught, despite Phase 0 raising
RETRY_ATTEMPTS specifically so a network blip gets more chances. httpx's own
transport exceptions are not subclasses of Python's ConnectionError/OSError/
TimeoutError, so `_transient()` never saw them as retryable.
"""
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


if __name__ == "__main__":
    unittest.main()
