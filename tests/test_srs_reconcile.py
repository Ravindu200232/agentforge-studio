"""After a change to the specification: the open decisions it settles and the review findings it puts right are taken off the overview."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, routes_srs  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402
from srs_agent import document  # noqa: E402

REQUEST = "Delivery address is only needed when the shopper chooses delivery; collection needs no address. Show exactly 6 phones on the Home page."
SUMMARY = "Made the delivery address optional for collection orders in FR-004 and set the Home page to six phones in FR-032."


AUDIT_PROBLEM = "each non-functional requirement needs a measurable threshold or named standard"


def decision(ident, area="Checkout", assumed="assumed"):
    return {"id": ident, "area": area, "description": f"{ident} is unclear.", "assumption_made": assumed, "needs_clarification": True}


def finding(rid="FR-001", severity="major", problem="not testable"):
    return {"requirement_id": rid, "severity": severity, "skill": "functional-requirements", "rule": "testable", "problem": problem}


def envelope(ambiguities=None, findings_=None):
    return {"srs_document": {
        "functional_requirements": [
            {"id": "FR-001", "requirement": "The system shall list the phones.", "rationale": "browse"},
            {"id": "FR-004", "requirement": "The system shall ask for a delivery address only when the shopper chooses delivery."},
            {"id": "FR-032", "requirement": "The system shall show exactly six phones on the Home page."}],
        "non_functional_requirements": [{"id": "NFR-001", "requirement": "Pages answer within 2 seconds for 95% of requests."}],
        "ambiguities": ambiguities if ambiguities is not None else [decision("AMB-001"), decision("AMB-002", "Reviews")],
        "requirements_quality_review": {"coverage_gaps": [], "reviewer": {
            "status": "capped", "iterations_used": 1, "stopped_because": "the 0-round review limit was reached",
            "final_scores": {"functional": 4}, "unresolved_findings": findings_ if findings_ is not None else [
                finding("FR-032", problem='"show a few phones" states no countable number'),
                finding("FR-001", "minor", "the list has no order"),
                {**finding(None, "blocker", AUDIT_PROBLEM), "skill": "corpus-evidence"}]}}}}


def said(ident="AMB-001", decision_="Delivery address is required only for delivery.",
         evidence="Delivery address is only needed when the shopper chooses delivery"):
    return {"id": ident, "decision": decision_, "evidence": evidence}


def put_right(number="F1", evidence="show exactly six phones on the Home page"):
    return {"finding": number, "evidence": evidence}


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.saved: list[dict] = []
        self.messages: list[dict] = []
        self.logs: list[tuple] = []
        self.states: list[tuple] = []
        self.calls: list[dict] = []
        self.envelope = envelope()
        self.audit_reports = [AUDIT_PROBLEM]

        def write_record(*parts, data=None):
            if parts == document.DOCUMENT:
                self.saved.append(copy.deepcopy(data))
            return Path(self.temp.name).joinpath(*parts)

        self.session = SimpleNamespace(record=Path(self.temp.name), cancelled=False, write_record=write_record)
        for patch in (
            mock.patch.object(document, "has_document", return_value=True),
            mock.patch.object(document, "document", side_effect=lambda project: copy.deepcopy(self.envelope)),
            mock.patch.object(document, "session_for", lambda project: self.session),
            mock.patch.object(document.corpus_rules, "audit_document", return_value={}),
            mock.patch.object(document.corpus_rules, "blocking_findings", side_effect=lambda audit: list(self.audit_reports)),
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.messages.append({"text": text, "title": title, "kind": kind})),
            mock.patch.object(bus, "log", lambda project, level, text, **k: self.logs.append((level, text))),
            mock.patch.object(bus, "sync_state", lambda project, status, detail="", **extra: self.states.append((status, detail, extra))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def model(self, settled=None, resolved=None, decisions_error=None, findings_error=None):
        """The model's answers: which decisions were settled, and which findings are put right."""
        def complete_json(system, user, validator=None, label="", project="", **_):
            self.calls.append({"label": label, "user": user})
            if label == "srs_reconcile":
                if decisions_error:
                    raise decisions_error
                return validator({"settled": settled or []})
            if label == "srs_reconcile_findings":
                if findings_error:
                    raise findings_error
                return validator({"resolved": resolved or []})
            raise AssertionError(f"unexpected model call: {label}")

        patcher = mock.patch("server_modules.llm.complete_json", side_effect=complete_json)
        patcher.start()
        self.addCleanup(patcher.stop)

    def labels(self):
        return [c["label"] for c in self.calls]

    def asked(self, label):
        return next(c["user"] for c in self.calls if c["label"] == label)

    def reconcile(self, request=REQUEST, summary=SUMMARY):
        return document.reconcile("p", request, summary, self.session)

    def final(self):
        return self.saved[-1]["srs_document"]

    def reviewer(self):
        return self.final()["requirements_quality_review"]["reviewer"]


class QuotingTests(unittest.TestCase):
    def test_words_that_are_in_the_text_are_a_quote_whatever_their_case_or_punctuation(self):
        text = "The system shall show exactly six phones, taken from the phones marked as shown."
        self.assertTrue(document._quoted("show exactly six phones", text))
        self.assertTrue(document._quoted("SHOW  EXACTLY six phones.", text))
        self.assertTrue(document._quoted("shall show exactly six phones taken from the phones", text))

    def test_a_quote_that_differs_by_a_word_still_counts_but_other_words_do_not(self):
        text = "The system shall reject a sign-up password shorter than 8 characters or longer than 64 characters."
        self.assertTrue(document._quoted("reject a password shorter than 8 characters or longer than 64 characters", text))
        self.assertFalse(document._quoted("accept passwords of any length without any limit at all", text))

    def test_nothing_or_something_too_short_to_mean_anything_is_not_a_quote(self):
        self.assertFalse(document._quoted("", "some text here"))
        self.assertFalse(document._quoted("six", "six phones"))
        self.assertFalse(document._quoted("a long enough quote", ""))


class SettleDecisionTests(Harness):
    def test_the_decisions_the_request_settles_are_marked_settled_with_what_was_decided(self):
        self.model(settled=[said()])
        result = self.reconcile()
        rows = {a["id"]: a for a in self.final()["ambiguities"]}
        self.assertFalse(rows["AMB-001"]["needs_clarification"])
        self.assertEqual(rows["AMB-001"]["resolution"], "Delivery address is required only for delivery.")
        self.assertEqual(rows["AMB-001"]["resolved_by"], "customer request")
        self.assertEqual(rows["AMB-001"]["assumption_made"], "assumed")                  # what was assumed is still on record
        self.assertTrue(rows["AMB-002"]["needs_clarification"])                          # the other was not decided
        self.assertNotIn("resolution", rows["AMB-002"])
        self.assertEqual((result["status"], result["open_decisions"], [s["id"] for s in result["settled"]]), ("done", 1, ["AMB-001"]))

    def test_the_model_is_given_the_customers_words_the_summary_and_only_the_open_decisions(self):
        self.envelope["srs_document"]["ambiguities"].append({**decision("AMB-003"), "needs_clarification": False})
        self.model(settled=[said()])
        self.reconcile()
        asked = self.asked("srs_reconcile")
        self.assertIn(REQUEST, asked)
        self.assertIn(SUMMARY, asked)
        self.assertIn("AMB-001", asked)
        self.assertIn("AMB-002", asked)
        self.assertNotIn("AMB-003", asked)                                               # already settled: nothing to ask

    def test_a_decision_is_only_settled_by_words_the_customer_really_said(self):
        self.model(settled=[said(evidence="the customer clearly wants collection orders to skip the address")])
        self.reconcile()
        self.assertEqual(self.saved, [])                                                  # nothing was shown to be settled: nothing written
        self.model(settled=[said(evidence="chooses delivery; collection needs no address")])      # from the request itself
        self.calls.clear()
        self.reconcile()
        self.assertFalse(self.final()["ambiguities"][0]["needs_clarification"])

    def test_words_from_the_agents_summary_can_settle_one_too(self):
        self.model(settled=[said("AMB-002", evidence="set the Home page to six phones in FR-032")])
        self.reconcile()
        self.assertFalse(self.final()["ambiguities"][1]["needs_clarification"])

    def test_an_unknown_id_or_an_empty_decision_settles_nothing_and_a_decision_named_twice_once(self):
        self.model(settled=[said("AMB-099"), said("AMB-002", decision_="")])
        self.reconcile()
        self.assertEqual(self.saved, [])
        self.model(settled=[said(), said(decision_="something else", evidence="collection needs no address")])
        self.reconcile()
        self.assertEqual(self.final()["ambiguities"][0]["resolution"], "Delivery address is required only for delivery.")

    def test_nothing_is_asked_when_no_decision_is_open_or_nothing_was_said(self):
        self.envelope = envelope(ambiguities=[{**decision("AMB-001"), "needs_clarification": False}], findings_=[])
        self.model()
        self.reconcile()
        self.assertEqual(self.calls, [])
        self.envelope = envelope(findings_=[])
        self.reconcile(request="   ")
        self.assertEqual(self.calls, [])

    def test_a_model_that_cannot_say_leaves_every_decision_open_and_the_findings_are_still_looked_at(self):
        self.model(decisions_error=ValueError("no JSON"), resolved=[put_right()])
        result = self.reconcile()
        self.assertTrue(all(a["needs_clarification"] for a in self.final()["ambiguities"]))
        self.assertTrue(any("stay open" in text for _, text in self.logs))
        self.assertEqual(result["cleared"], 1)
        self.assertEqual(self.labels(), ["srs_reconcile", "srs_reconcile_findings"])


class SettleFindingTests(Harness):
    def test_a_finding_the_requirement_no_longer_has_comes_off_the_quality_review(self):
        self.model(resolved=[put_right("F1")])
        result = self.reconcile()
        reviewer = self.reviewer()
        self.assertEqual([f["requirement_id"] for f in reviewer["unresolved_findings"]], ["FR-001", None])
        self.assertEqual(reviewer["unresolved_findings"][1]["skill"], "corpus-evidence")
        cleared = reviewer["resolved_findings"]
        self.assertEqual(len(cleared), 1)
        self.assertEqual((cleared[0]["requirement_id"], cleared[0]["resolved_by"]), ("FR-032", "customer change"))
        self.assertEqual(cleared[0]["evidence"], "show exactly six phones on the Home page")
        self.assertIn("countable number", cleared[0]["problem"])                          # what it said is kept with it
        self.assertEqual((result["cleared"], result["findings"]), (1, 2))

    def test_the_scores_and_the_verdict_of_the_review_itself_are_left_alone(self):
        self.model(resolved=[put_right("F1")])
        self.reconcile()
        reviewer = self.reviewer()
        self.assertEqual((reviewer["status"], reviewer["iterations_used"], reviewer["final_scores"]), ("capped", 1, {"functional": 4}))

    def test_a_finding_is_only_cleared_when_the_words_that_fix_it_are_really_in_the_requirement(self):
        self.model(resolved=[put_right("F1", evidence="the Home page shows a fixed count of phones chosen by the shop owner")])
        self.reconcile()
        self.assertEqual(self.saved, [])                                                  # a made-up quote clears nothing
        self.assertEqual(len(self.envelope["srs_document"]["requirements_quality_review"]["reviewer"]["unresolved_findings"]), 3)

    def test_the_requirement_text_it_is_judged_against_is_the_text_as_it_reads_now(self):
        self.model()
        self.reconcile()
        asked = self.asked("srs_reconcile_findings")
        self.assertIn("The system shall show exactly six phones on the Home page.", asked)            # F1: FR-032
        self.assertIn("The system shall list the phones.", asked)                                     # F2: FR-001
        self.assertNotIn("F3", asked)                                                                 # the audit's own finding is not asked
        self.assertNotIn('"rationale"', asked)
        self.assertIn(SUMMARY, asked)

    def test_another_requirement_a_finding_mentions_is_shown_as_well(self):
        self.envelope = envelope(findings_=[finding("FR-001", problem="FR-004 caps the quantity but nothing says what FR-001 lists")])
        self.model()
        self.reconcile()
        asked = self.asked("srs_reconcile_findings")
        self.assertIn("The system shall ask for a delivery address only when", asked)

    def test_the_review_is_never_run_again_so_it_cannot_find_new_things_to_say(self):
        self.model(resolved=[put_right("F1")])
        self.reconcile()
        self.assertEqual(set(self.labels()), {"srs_reconcile", "srs_reconcile_findings"})
        self.assertEqual(len(self.final()["functional_requirements"]), 3)                  # and nothing is rewritten

    def test_a_model_that_cannot_say_leaves_every_finding_where_it_was(self):
        self.model(findings_error=RuntimeError("the model service is down"))
        result = self.reconcile()
        self.assertEqual(self.saved, [])
        self.assertTrue(any("they stay" in text for _, text in self.logs))
        self.assertEqual((result["status"], result["cleared"], result["findings"]), ("done", 0, 3))

    def test_with_no_findings_there_is_nothing_to_ask(self):
        self.envelope = envelope(findings_=[])
        self.model()
        self.reconcile()
        self.assertNotIn("srs_reconcile_findings", self.labels())

    def test_a_finding_of_the_evidence_audit_is_never_a_models_to_clear_and_stays_while_the_audit_reports_it(self):
        self.model(resolved=[put_right("F3", "Pages answer within 2 seconds for 95% of requests")])    # a model's opinion of it
        self.reconcile()
        self.assertNotIn("each non-functional requirement", self.asked("srs_reconcile_findings"))
        self.assertEqual(len(self.envelope["srs_document"]["requirements_quality_review"]["reviewer"]["unresolved_findings"]), 3)
        self.assertEqual(self.saved, [])

    def test_a_finding_of_the_evidence_audit_comes_off_when_the_audit_no_longer_reports_it(self):
        self.audit_reports = []
        self.model()
        result = self.reconcile()
        cleared = self.reviewer()["resolved_findings"]
        self.assertEqual((len(cleared), cleared[0]["skill"]), (1, "corpus-evidence"))
        self.assertIn("evidence audit no longer reports it", cleared[0]["evidence"])
        self.assertEqual(result["cleared"], 1)
        self.assertEqual(set(self.labels()), {"srs_reconcile", "srs_reconcile_findings"})

    def test_an_audit_that_cannot_run_clears_nothing(self):
        with mock.patch.object(document.corpus_rules, "blocking_findings", side_effect=RuntimeError("no audit")):
            self.model()
            self.reconcile()
        self.assertEqual(self.saved, [])

    def test_a_finding_that_names_no_requirement_of_the_document_is_not_asked_and_stays(self):
        self.envelope = envelope(findings_=[finding("FR-777", problem="FR-888 is vague"), finding(None, problem="the spec is thin")])
        self.model()
        self.reconcile()
        self.assertNotIn("srs_reconcile_findings", self.labels())                          # nothing to judge either against
        self.assertEqual(self.saved, [])

    def test_the_requirements_a_finding_names_are_shown_in_full_but_never_more_than_three(self):
        doc = self.envelope["srs_document"]
        doc["functional_requirements"] += [{"id": f"FR-{n}", "requirement": f"Requirement number {n}."} for n in range(100, 106)]
        shown = document._requirement_texts(doc, finding("FR-100", problem="FR-101, FR-102, FR-103 and FR-104 disagree, as FR-100 says"))
        self.assertEqual([line.split(":")[0] for line in shown.splitlines()], ["FR-100", "FR-101", "FR-102"])

    def test_a_finding_put_right_twice_over_two_changes_is_kept_in_both_records(self):
        self.model(resolved=[put_right("F1")])
        self.reconcile()
        self.envelope = self.saved[-1]
        self.calls.clear()
        self.model(resolved=[put_right("F1", evidence="The system shall list the phones")])
        self.reconcile()
        self.assertEqual([f["requirement_id"] for f in self.reviewer()["resolved_findings"]], ["FR-032", "FR-001"])
        self.assertEqual([f["requirement_id"] for f in self.reviewer()["unresolved_findings"]], [None])
        self.assertEqual(self.reviewer()["unresolved_findings"][0]["skill"], "corpus-evidence")


class ReportTests(Harness):
    def test_the_customer_is_told_where_things_stand_and_the_overview_is_told_to_reload(self):
        self.model(settled=[said()], resolved=[put_right("F1"), put_right("F2", "The system shall list the phones")])
        self.reconcile()
        text = self.messages[-1]["text"]
        self.assertEqual(self.messages[-1]["title"], "Specification review")
        self.assertIn("1 of 2 open decisions settled (AMB-001)", text)
        self.assertIn("2 of 3 quality-review findings put right", text)
        status, detail, extra = self.states[-1]
        self.assertEqual((status, extra.get("source"), extra.get("srs_status")), ("clean", "srs", "completed"))
        self.assertEqual(len(self.saved), 1)

    def test_only_what_happened_is_said(self):
        self.model(resolved=[put_right("F1")])
        self.reconcile()
        self.assertNotIn("decision", self.messages[-1]["text"])
        self.assertIn("1 of 3 quality-review findings put right", self.messages[-1]["text"])

    def test_when_the_change_settled_and_cleared_nothing_nothing_is_written_said_or_reloaded(self):
        self.model()
        result = self.reconcile()
        self.assertEqual((self.saved, self.messages, self.states), ([], [], []))
        self.assertEqual((result["status"], result["open_decisions"], result["findings"]), ("done", 2, 3))


class SafetyTests(Harness):
    def test_a_project_without_a_specification_is_left_alone(self):
        self.model()
        with mock.patch.object(document, "has_document", return_value=False):
            self.assertEqual(self.reconcile(), {"status": "none"})
        self.assertEqual((self.calls, self.saved), ([], []))

    def test_a_stop_ends_it_and_nothing_is_saved(self):
        with mock.patch("server_modules.llm.complete_json", side_effect=RunCancelled("p")):
            with self.assertRaises(RunCancelled):
                self.reconcile()
        self.assertEqual(self.saved, [])

    def test_whatever_goes_wrong_never_fails_the_change_it_follows(self):
        with mock.patch.object(document, "document", side_effect=OSError("disk")):
            result = self.reconcile()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("could not be refreshed" in text for _, text in self.logs))


class CustomizeRouteTests(unittest.TestCase):
    def test_a_change_typed_into_the_specification_review_brings_its_overview_back_in_line_too(self):
        session = mock.Mock()
        session.run_task.return_value = {"text": "Made the address optional."}
        with mock.patch("server_modules.session.session_for", return_value=session), \
                mock.patch.object(routes_srs.store, "require", return_value={"language": "English"}), \
                mock.patch.object(bus, "user_msg"), mock.patch.object(document, "document", return_value={"srs_document": {}}), \
                mock.patch.object(document, "reconcile") as reconcile:
            routes_srs.dispatch("POST", "/projects/prj_x/customize", {"prompt": "address only for delivery"})
        reconcile.assert_called_once_with("prj_x", "address only for delivery", "Made the address optional.", session)
        session.finish.assert_called_once()


class ReviewLoopUnchangedTests(unittest.TestCase):
    def test_the_specifications_own_review_is_still_taken_exactly_as_before(self):
        source = Path(document.__file__).read_text(encoding="utf-8")
        self.assertIn('cap = max(0, int(config.setting("srs_review_max_iterations", 2)))', source)
        self.assertIn('f"round-{round_no + 1}.json"', source)


if __name__ == "__main__":
    unittest.main()
