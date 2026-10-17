"""The personal data kept from the model comes back in what the model writes, so the specification and the app use real values.

The privacy filter used to replace a name, an email address or a phone number with a placeholder and keep nothing else, so the
specification and the built application were made with `<PERSON>` and `<EMAIL_ADDRESS>` in them, and a shop called "Sunil
Hardware" or a town like Kandy became a person too. Now each value is kept for its project under a placeholder numbered for the
whole project; the one place every model call goes through hides the values on the way out and puts them back on the way in.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import config, privacy, privacy_vault, session  # noqa: E402

PROJECT = "prj_vault"


class VaultCase(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.TemporaryDirectory()
        self.addCleanup(self.state.cleanup)
        self.enterContext(mock.patch.object(config, "STATE", Path(self.state.name)))
        privacy_vault._cache.clear()
        self.addCleanup(privacy_vault._cache.clear)
        privacy_vault.remember(PROJECT, [("PERSON", "Nimal Perera"), ("EMAIL_ADDRESS", "nimal@shop.lk"),
                                         ("PHONE_NUMBER", "0771234567")])


class TheVaultTests(VaultCase):
    def test_a_value_keeps_its_placeholder_for_the_whole_project_and_a_new_one_is_numbered_on(self):
        again = privacy_vault.remember(PROJECT, [("PERSON", "nimal  perera"), ("PERSON", "Kamala Silva")])
        self.assertEqual(again, {"nimal perera": "<PERSON_1>", "Kamala Silva": "<PERSON_2>"})
        self.assertEqual(privacy_vault.remember("prj_other", [("PERSON", "Kamala Silva")]), {"Kamala Silva": "<PERSON_1>"})

    def test_the_values_are_kept_encrypted_and_go_with_a_deleted_project(self):
        kept = Path(self.state.name) / "privacy" / f"{PROJECT}.vault"
        self.assertNotIn(b"nimal", kept.read_bytes().lower())
        privacy_vault._cache.clear()
        self.assertEqual(len(privacy_vault.entries(PROJECT)), 3)            # read back from disk
        from server_modules import store
        with mock.patch.object(store, "_read", return_value={}), mock.patch.object(store, "_write"):
            store.delete(PROJECT)
        self.assertFalse(kept.exists())
        self.assertEqual(privacy_vault.entries(PROJECT), [])

    def test_hiding_finds_a_name_as_a_whole_word_in_any_case_and_revealing_puts_it_back(self):
        text = "Owner Nimal Perera (nimal@shop.lk, 0771234567); NIMAL PERERA signs. nimalperera stays."
        hidden = privacy_vault.hide(PROJECT, text)
        self.assertEqual(hidden, "Owner <PERSON_1> (<EMAIL_ADDRESS_1>, <PHONE_NUMBER_1>); <PERSON_1> signs. nimalperera stays.")
        self.assertEqual(privacy_vault.reveal(PROJECT, hidden),
                         "Owner Nimal Perera (nimal@shop.lk, 0771234567); Nimal Perera signs. nimalperera stays.")

    def test_a_placeholder_written_into_html_comes_back_too_and_an_unknown_one_is_left(self):
        self.assertEqual(privacy_vault.reveal(PROJECT, "<p>Mail &lt;EMAIL_ADDRESS_1&gt; or <PERSON_9></p>"),
                         "<p>Mail nimal@shop.lk or <PERSON_9></p>")


def reply(content="", thinking="", calls=()):
    return SimpleNamespace(message=SimpleNamespace(content=content, thinking=thinking, tool_calls=list(calls)))


def call(name, **arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


class EveryModelCallTests(VaultCase):
    """`session.RetryingClient.chat`: the values never leave in a request, and come back in the answer."""

    def client(self, inner):
        return session.RetryingClient(inner, project=PROJECT)

    def test_a_request_carries_placeholders_in_its_messages_tool_results_and_earlier_tool_calls(self):
        sent = {}
        inner = SimpleNamespace(chat=lambda **kw: sent.update(kw) or reply("ok"))
        with mock.patch.object(session, "accounts", create=True), mock.patch("server_modules.accounts.check"), \
                mock.patch("server_modules.accounts.record"):
            self.client(inner).chat(model="m", messages=[
                {"role": "user", "content": "Build a shop for Nimal Perera, nimal@shop.lk"},
                {"role": "assistant", "content": "", "tool_calls": [call("write_file", path="a.txt", content="Nimal Perera")]},
                {"role": "tool", "content": "a.txt: Call 0771234567", "images": ["picture"]},
            ])
        messages = sent["messages"]
        self.assertEqual(messages[0]["content"], "Build a shop for <PERSON_1>, <EMAIL_ADDRESS_1>")
        self.assertEqual(messages[1]["tool_calls"][0].function.arguments["content"], "<PERSON_1>")
        self.assertEqual(messages[2]["content"], "a.txt: Call <PHONE_NUMBER_1>")
        self.assertEqual(messages[2]["images"], ["picture"])

    def test_an_answer_gets_the_real_values_in_its_text_and_local_tools_but_not_in_a_web_search(self):
        answer = reply("Hello <PERSON_1>", "about <EMAIL_ADDRESS_1>",
                       [call("write_file", path="about.jsx", content="<p><PERSON_1> - <PHONE_NUMBER_1></p>"),
                        call("web_search", query="<PERSON_1> shop reviews")])
        inner = SimpleNamespace(chat=lambda **kw: answer)
        with mock.patch("server_modules.accounts.check"), mock.patch("server_modules.accounts.record"):
            got = self.client(inner).chat(model="m", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(got.message.content, "Hello Nimal Perera")
        self.assertEqual(got.message.thinking, "about nimal@shop.lk")
        self.assertEqual(got.message.tool_calls[0].function.arguments["content"], "<p>Nimal Perera - 0771234567</p>")
        self.assertEqual(got.message.tool_calls[1].function.arguments["query"], "<PERSON_1> shop reviews")

    def test_a_placeholder_split_across_streamed_chunks_comes_back_whole(self):
        chunks = [reply("Owner: <PER"), reply("SON_1> and &lt;EMAIL"), reply("_ADDRESS_1&gt; end <")]
        inner = SimpleNamespace(chat=lambda **kw: iter(chunks))
        with mock.patch("server_modules.accounts.check"), mock.patch("server_modules.accounts.record"):
            stream = self.client(inner).chat(model="m", messages=[{"role": "user", "content": "hi"}], stream=True)
            text = "".join(chunk.message.content for chunk in stream)
        self.assertEqual(text, "Owner: Nimal Perera and nimal@shop.lk end <")

    def test_with_the_filter_off_or_nothing_kept_nothing_is_swapped(self):
        sent = {}
        inner = SimpleNamespace(chat=lambda **kw: sent.update(kw) or reply("<PERSON_1>"))
        with mock.patch("server_modules.accounts.check"), mock.patch("server_modules.accounts.record"), \
                mock.patch.object(privacy, "enabled", return_value=False):
            got = self.client(inner).chat(model="m", messages=[{"role": "user", "content": "Nimal Perera"}])
        self.assertEqual((sent["messages"][0]["content"], got.message.content), ("Nimal Perera", "<PERSON_1>"))
        with mock.patch("server_modules.accounts.check"), mock.patch("server_modules.accounts.record"):
            got = session.RetryingClient(inner, project="prj_nothing_kept").chat(
                model="m", messages=[{"role": "user", "content": "Nimal Perera"}])
        self.assertEqual(sent["messages"][0]["content"], "Nimal Perera")


class NotEveryNameIsAPersonTests(unittest.TestCase):
    """What the small English model takes for a person's name but is a business, a product or a town is left as it is."""

    def keep(self, value, text="", keep=()):
        start = text.find(value) if text else 0
        return privacy._keep("PERSON", value, text, max(start, 0), keep)

    def test_a_business_a_product_and_a_town_are_not_people(self):
        self.assertTrue(self.keep("Sunil Hardware"))
        self.assertTrue(self.keep("Kandy"))
        self.assertTrue(self.keep("Nuwara Eliya"))
        self.assertTrue(self.keep("Sunil", "Sunil Hardware inventory app"))          # the business word right after it
        self.assertTrue(self.keep("Clean Mate", "an app called Clean Mate for cleaning"))
        self.assertTrue(self.keep("Kamal", "App name: Kamal for the shop"))

    def test_a_word_the_person_listed_and_the_project_name_are_kept(self):
        self.assertTrue(self.keep("Bramble Hill", keep=["Bramble Hill Tool Library"]))
        with mock.patch.object(config, "setting", lambda name, fallback=None: ["Lotus Rise"] if name == "privacy_keep" else fallback), \
                mock.patch("server_modules.store.get", return_value={"name": "Kamal Stores POS"}):
            terms = privacy.keep_terms(PROJECT)
        self.assertEqual(terms, ["Lotus Rise", "Kamal Stores POS"])

    def test_a_real_person_is_still_hidden(self):
        self.assertFalse(self.keep("Nimal Perera", "Manager Nimal Perera approves orders"))
        self.assertFalse(self.keep("Dilani Fernando", "Kasun went to Colombo with Dilani Fernando."))


if __name__ == "__main__":
    unittest.main()
