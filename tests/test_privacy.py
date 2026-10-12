"""What the person types goes through Microsoft Presidio before any model sees it: personal data is replaced by placeholders."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", ".deps/py312"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, config, httpd, permissions, privacy, routes_srs, runs  # noqa: E402
from support import forget_project, isolate_workspaces  # noqa: E402

PROJECT = "prj_privacy_test"


def setUpModule():
    isolate_workspaces()


def have_presidio() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
        import presidio_anonymizer  # noqa: F401
        import spacy.util

        return spacy.util.is_package(privacy.MODEL)
    except ImportError:
        return False


def settings(**values):
    return mock.patch.object(config, "setting", lambda name, fallback=None: values.get(name, fallback))


@unittest.skipUnless(have_presidio(), "Microsoft Presidio and its spaCy model are not installed")
class PresidioTests(unittest.TestCase):
    """The real analyzer and anonymizer."""

    def test_an_email_address_and_phone_numbers_are_replaced_in_any_language(self):
        done = privacy.scrub("mail ravin.silva@gmail.com or call +94 77 123 4567 / 0771234567")
        self.assertNotIn("gmail", done.text)
        self.assertNotIn("123 4567", done.text)
        self.assertNotIn("0771234567", done.text)
        self.assertEqual(done.found, {"EMAIL_ADDRESS": 1, "PHONE_NUMBER": 2})
        sinhala = privacy.scrub("මගේ email එක kamal@yahoo.com සහ අංකය 077 765 4321")
        self.assertNotIn("kamal@yahoo.com", sinhala.text)
        self.assertNotIn("765 4321", sinhala.text)
        self.assertIn("මගේ", sinhala.text)                      # the rest of the message is left as it was

    def test_a_name_a_card_a_bank_account_and_a_public_ip_address_are_replaced(self):
        done = privacy.scrub("I am Kamal Perera, card 4111 1111 1111 1111, iban GB82 WEST 1234 5698 7654 32, server 8.8.8.8")
        for gone in ("Kamal", "Perera", "4111", "GB82", "8.8.8.8"):
            self.assertNotIn(gone, done.text)
        self.assertEqual(set(done.found), {"PERSON", "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS"})

    def test_a_sri_lankan_national_identity_number_is_found_in_both_forms(self):
        done = privacy.scrub("NIC 199012345678 and the old one 901234567V")
        self.assertNotIn("199012345678", done.text)
        self.assertNotIn("901234567V", done.text)
        self.assertEqual(done.found, {"LK_NIC": 2})

    def test_the_same_value_is_the_same_placeholder_and_different_ones_are_numbered(self):
        done = privacy.scrub("a@gmail.com, b@gmail.com, a@gmail.com again")
        self.assertEqual(done.text, "<EMAIL_ADDRESS_1>, <EMAIL_ADDRESS_2>, <EMAIL_ADDRESS_1> again")
        alone = privacy.scrub("write to a@gmail.com")
        self.assertEqual(alone.text, "write to <EMAIL_ADDRESS>")

    def test_sample_data_and_addresses_of_this_computer_are_left_alone(self):
        text = "add a test user admin@example.com, the api is on 127.0.0.1 and the router on 192.168.1.5, a clinic in Colombo"
        done = privacy.scrub(text)
        self.assertEqual(done.text, text)
        self.assertFalse(done.changed)

    def test_an_ordinary_request_comes_back_exactly_as_it_was(self):
        text = "add a due date to every task and show the overdue ones in red"
        self.assertEqual(privacy.scrub(text).text, text)

    def test_what_was_hidden_is_not_found_again_when_the_text_goes_through_a_second_time(self):
        once = privacy.scrub("I am Nimal Silva, mail nimal@gmail.com, NIC 901234567V, phone 0771234567")
        self.assertTrue(once.changed)
        again = privacy.scrub(once.text)
        self.assertEqual(again.text, once.text)
        self.assertFalse(again.changed)

    def test_a_long_message_is_read_in_pieces_and_every_piece_is_covered(self):
        filler = "please keep the page simple. " * 3000
        done = privacy.scrub("first a@gmail.com " + filler + " last b@gmail.com")
        self.assertNotIn("gmail", done.text)
        self.assertEqual(done.found, {"EMAIL_ADDRESS": 2})

    def test_only_the_kinds_chosen_in_the_settings_are_hidden(self):
        with settings(privacy_entities=["EMAIL_ADDRESS"]):
            done = privacy.scrub("I am Kamal Perera, mail kamal@gmail.com")
        self.assertEqual(done.found, {"EMAIL_ADDRESS": 1})
        self.assertIn("Kamal Perera", done.text)

    def test_the_status_says_presidio_is_ready_and_what_it_hides(self):
        status = privacy.status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["engine"], "Microsoft Presidio")
        self.assertIn("PERSON", status["entities"])

    def test_without_the_spacy_model_the_patterns_still_work(self):
        saved = dict(privacy._ready)
        privacy._ready.clear()
        try:
            with settings(privacy_model="no_such_model"):
                done = privacy.scrub("I am Kamal Perera, mail kamal@gmail.com, phone 0771234567")
                self.assertEqual(privacy.status()["model"], "")
            self.assertEqual(done.found, {"EMAIL_ADDRESS": 1, "PHONE_NUMBER": 1})
            self.assertIn("Kamal Perera", done.text)                       # names need the model
        finally:
            privacy._ready.clear()
            privacy._ready.update(saved)


class FilterTests(unittest.TestCase):
    def test_a_filter_that_is_turned_off_leaves_the_text_alone_and_loads_nothing(self):
        with settings(privacy_filter=False), mock.patch.object(privacy, "_engines", side_effect=AssertionError("loaded")):
            self.assertEqual(privacy.screen(PROJECT, "mail a@gmail.com"), "mail a@gmail.com")
            self.assertFalse(privacy.status()["enabled"])

    def test_a_filter_that_cannot_run_holds_the_message_back_instead_of_letting_it_through(self):
        with mock.patch.object(privacy, "_engines", side_effect=privacy.NotSent("Presidio is not installed")):
            with self.assertRaises(privacy.NotSent) as caught:
                privacy.screen(PROJECT, "mail a@gmail.com")
        self.assertIsInstance(caught.exception, ValueError)             # a route answers it as a plain error
        with mock.patch.object(privacy, "_engines", side_effect=privacy.NotSent("x")):
            self.assertEqual(privacy.screen(PROJECT, "   "), "   ")      # nothing to read, nothing to hold

    def test_the_line_in_the_chat_says_how_many_of_which_kind_and_never_the_values(self):
        events: list[dict] = []
        with mock.patch.object(bus, "agent_msg", lambda project, text, **k: events.append({"text": text, **k})):
            privacy.tell(PROJECT, {"EMAIL_ADDRESS": 2, "PERSON": 1, "PHONE_NUMBER": 1})
            privacy.tell(PROJECT, {})
        self.assertEqual(len(events), 1)
        self.assertIn("2 email addresses", events[0]["text"])
        self.assertIn("1 name", events[0]["text"])
        self.assertEqual(events[0]["title"], "Privacy filter")
        self.assertEqual(privacy.describe({"PERSON": 1}), "1 name")


def fake_scrub(text):
    clean = str(text).replace("kamal@gmail.com", "<EMAIL_ADDRESS>")
    return privacy.Scrubbed(clean, {"EMAIL_ADDRESS": 1} if clean != text else {})


class EntryPointTests(unittest.TestCase):
    """Everything typed reaches the next step with its personal data already hidden."""

    def setUp(self):
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        self.addCleanup(forget_project, PROJECT)
        for patch in (mock.patch.object(privacy, "scrub", fake_scrub),
                      mock.patch.object(permissions, "start_project", return_value="plan")):      # the projects here are not in the store
            patch.start()
            self.addCleanup(patch.stop)

    def said(self, title):
        """What the chat was told under this title (the subscriber hears each event twice: once live, once from the log)."""
        return sorted({e["text"] for e in self.events if e.get("title") == title})

    def test_a_chat_message_is_planned_without_the_address_and_the_chat_says_so(self):
        with mock.patch.object(runs.changes, "applies", return_value=True), \
                mock.patch.object(runs.changes, "submit", return_value={"ok": True}) as submit:
            runs.agent_update({"project": PROJECT, "prompt": "mail kamal@gmail.com when it is done"})
        self.assertEqual(submit.call_args.args[1], "mail <EMAIL_ADDRESS> when it is done")
        self.assertEqual(len(self.said("Privacy filter")), 1)
        self.assertNotIn("kamal@gmail.com", json.dumps(self.events))

    def test_a_direct_change_reaches_the_agent_with_the_address_hidden(self):
        with mock.patch.object(runs, "_in_background") as started, \
                mock.patch.object(runs.builder, "built", return_value=True), \
                mock.patch.object(runs, "_spec_pending", return_value=False), \
                mock.patch.object(runs, "_answer_held", return_value=None):
            runs.agent_update_direct({"project": PROJECT, "prompt": "send it to kamal@gmail.com"})
        self.assertEqual(started.call_args.args[5], "send it to <EMAIL_ADDRESS>")

    def test_in_a_pointed_edit_only_what_was_typed_is_filtered_not_the_description_of_the_page(self):
        elements = [{"tag": "h2", "text": "kamal@gmail.com's orders"}]
        with mock.patch.object(runs.changes, "applies", return_value=True),                 mock.patch.object(runs.changes, "submit", return_value={"ok": True}) as submit:
            runs.element_edit({"project": PROJECT, "prompt": "mail kamal@gmail.com here", "route": "/orders", "elements": elements})
        sent = submit.call_args.args[1]
        self.assertTrue(sent.startswith("mail <EMAIL_ADDRESS> here"))
        self.assertIn("kamal@gmail.com's orders", sent)                  # the agent still finds the heading by its own words

    def test_a_message_the_filter_could_not_read_is_not_sent_and_says_why(self):
        with mock.patch.object(privacy, "scrub", side_effect=privacy.NotSent("Presidio is not installed")), \
                mock.patch.object(runs.changes, "submit") as submit:
            answer = runs.agent_update({"project": PROJECT, "prompt": "mail kamal@gmail.com"})
        submit.assert_not_called()
        self.assertFalse(answer["ok"])
        self.assertIn("not installed", answer["detail"])
        self.assertEqual(len(self.said("Not sent")), 1)

    def test_a_build_started_from_the_first_box_hides_the_data_in_the_idea_too(self):
        created: list[str] = []

        def create(idea="", **_):
            created.append(idea)
            return {"id": PROJECT, "name": "x", "stack": "", "language": "", "status": "new"}
        with mock.patch.object(runs.store, "create", create), mock.patch.object(runs, "_in_background"), \
                mock.patch.object(runs, "_remember_model"):
            runs.agent_build({"prompt": "a shop for kamal@gmail.com"})
        self.assertEqual(created, ["a shop for <EMAIL_ADDRESS>"])
        self.assertEqual(len(self.said("Privacy filter")), 1)

    def test_a_new_project_keeps_only_the_hidden_idea(self):
        saved: list[str] = []

        def create(idea="", **_):
            saved.append(idea)
            return {"id": PROJECT, "name": "x", "stack": "", "language": "", "status": "new"}
        with mock.patch.object(routes_srs.store, "create", create):
            routes_srs.dispatch("POST", "/projects", {"idea": "a clinic for kamal@gmail.com"})
        self.assertEqual(saved, ["a clinic for <EMAIL_ADDRESS>"])
        self.assertEqual(len(self.said("Privacy filter")), 1)

    def test_an_interview_answer_a_plan_revision_and_a_wireframe_request_are_hidden_before_they_are_used(self):
        seen: dict[str, object] = {}
        with mock.patch.object(routes_srs.interview, "record_answer", lambda project, body: seen.update(answer=body)), \
                mock.patch.object(routes_srs.plan, "draft", lambda project, revision="", answers=None: seen.update(plan=(revision, answers))), \
                mock.patch.object(routes_srs.wireframer, "edit", lambda project, prompt, route, elements: seen.update(wire=prompt)), \
                mock.patch.object(routes_srs.prototyper, "revise", lambda project, prompt, elements: seen.update(proto=prompt)):
            routes_srs.dispatch("POST", f"/projects/{PROJECT}/interview/answer",
                                {"key": "a", "text": "mail kamal@gmail.com", "custom": "kamal@gmail.com", "selected": ["x"]})
            routes_srs.dispatch("POST", f"/projects/{PROJECT}/plan",
                                {"revision": "ask kamal@gmail.com", "answers": {"Who?": "kamal@gmail.com"}})
            routes_srs.dispatch("POST", f"/projects/{PROJECT}/wireframes/edit", {"prompt": "show kamal@gmail.com", "route": "/"})
            routes_srs.dispatch("POST", f"/projects/{PROJECT}/prototype/edit", {"prompt": "show kamal@gmail.com"})
        self.assertEqual(seen["answer"]["text"], "mail <EMAIL_ADDRESS>")
        self.assertEqual(seen["answer"]["custom"], "<EMAIL_ADDRESS>")
        self.assertEqual(seen["answer"]["selected"], ["x"])
        self.assertEqual(seen["plan"], ("ask <EMAIL_ADDRESS>", {"Who?": "<EMAIL_ADDRESS>"}))
        self.assertEqual((seen["wire"], seen["proto"]), ("show <EMAIL_ADDRESS>", "show <EMAIL_ADDRESS>"))

    def test_a_reply_to_a_question_and_feedback_on_a_plan_are_hidden(self):
        asked = bus.ask(PROJECT, "question", "Who should be told?", options=[{"id": "1", "label": "Someone"}])
        with mock.patch.object(httpd.runs, "agent_update_direct") as direct:
            httpd.decide({"id": asked, "decision": "answer", "reply": "tell kamal@gmail.com"})
        self.assertEqual(direct.call_args.args[0]["prompt"], "tell <EMAIL_ADDRESS>")
        with mock.patch.object(httpd.changes, "decide", return_value={"ok": True}) as decide,                 mock.patch.object(httpd, "_project", return_value=PROJECT):
            httpd.change_decide({"project": PROJECT, "decision": "revise", "feedback": "also kamal@gmail.com",
                                 "_match": mock.Mock(group=lambda name: "chg-1")})
        self.assertEqual(decide.call_args.args[3], "also <EMAIL_ADDRESS>")

    def test_a_private_value_typed_into_a_question_is_not_touched_by_the_filter(self):
        """A password the person was asked for is saved by name and never reaches a model: the filter must not alter it."""
        asked = {"id": "d1", "variable": "ADMIN_PASSWORD", "project": PROJECT}
        with mock.patch.object(bus, "pending_decisions", return_value=[asked]), \
                mock.patch.object(httpd.deploy_vars, "accept", return_value="") as accept, \
                mock.patch.object(bus, "resolve", return_value=None):
            httpd.decide({"id": "d1", "decision": "answer", "reply": "kamal@gmail.com"})
        self.assertEqual(accept.call_args.args[1], "kamal@gmail.com")


class InstallTests(unittest.TestCase):
    def test_the_dependency_lists_name_presidio_spacy_and_its_model(self):
        for name in ("pyproject.toml", "studio.ps1", "release/build.ps1"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for expected in ("presidio-analyzer", "presidio-anonymizer", "spacy"):
                self.assertIn(expected, text, f"{name}: {expected}")
        for name in ("studio.ps1", "release/build.ps1"):
            self.assertIn("en_core_web_sm", (ROOT / name).read_text(encoding="utf-8"))

    def test_the_backend_loads_presidio_in_the_background_when_it_starts(self):
        self.assertIn("privacy.warm_up()", (ROOT / "server.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
