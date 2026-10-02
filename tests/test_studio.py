"""The studio backend's own rules.

These cover the parts that decide something: the prompt loader, the four
validation gates, and the event shapes the studio's reducer reads. The agents
themselves are not tested here — they are a model and a workspace, and what is
worth asserting about them is whether their output passes these gates.
"""
import json
import copy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent",
               "qa-agent", "deploy-agent", ".deps"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import prompts  # noqa: E402
from server_modules import store as project_store  # noqa: E402
from server_modules.session import extract_json  # noqa: E402
from server_modules.validation import completeness, plan_rules, review, srs_schema  # noqa: E402
from srs_agent import document as srs_document  # noqa: E402
from support import forget_project, isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


def a_plan(**patch):
    plan = {
        "product_intent": ("An online ordering site for a small bakery, so a visitor can "
                           "choose a cake, pick a collection date and pay a deposit, and "
                           "the owner can see the day's orders in one place."),
        "users": [{"role": "Owner", "can_do": ["see the day's orders", "edit the menu"]}],
        "screens": [{"name": "Home", "route": "/", "purpose": "show the cakes", "who": ["Visitor"]}],
        "records": [{"name": "Cake", "keeps": ["Name", "Price"]}],
        "workflows": [{"name": "Ordering a cake", "who": "Visitor",
                       "steps": ["open Home", "choose a cake", "pay the deposit"]}],
        "features": ["A visitor can order a cake for collection"],
        "account_policy": {"accounts_required": True, "registration_mode": "admin_created",
                           "provisioning_role": "Owner"},
        "open_questions": [],
    }
    plan.update(patch)
    return plan


def a_document(**patch):
    doc = {
        "project_name": "Bakery",
        "system_category": "Web Application",
        "app_summary": {"app_name": "Bakery", "short_description": "cakes",
                        "business_goal": "sell cakes", "target_users": ["Visitor"]},
        "app_type": {"primary_type": "web"},
        "roles": [{"role_key": "owner", "role_name": "Owner", "description": "runs it"}],
        "public_pages": [{"page_name": "Home", "route": "/", "sections": ["hero", "list"],
                          "functions": ["browse"]}],
        "database_design": {"tables": [{"table_name": "cakes", "fields": []}]},
        "functional_requirements": [
            {"id": "FR-001", "module": "Ordering",
             "requirement": "The system shall let a visitor order a cake for collection."},
            {"id": "FR-002", "module": "Menu",
             "requirement": "The system shall let the Owner edit the menu."},
            {"id": "FR-003", "module": "Orders",
             "requirement": "The system shall show the Owner the day's orders."},
        ],
        "non_functional_requirements": [
            {"id": "NFR-001", "category": "Performance", "requirement": "under 200ms"},
            {"id": "NFR-002", "category": "Security", "requirement": "hashed passwords"},
            {"id": "NFR-003", "category": "Accessibility", "requirement": "WCAG 2.1 AA"},
        ],
        "business_workflows": [{"workflow_name": "Ordering a cake", "who": "Visitor",
                                "steps": ["open Home", "choose", "pay"]}],
        "requirement_traceability_matrix": [
            {"requirement_id": "FR-001", "module": "Ordering", "pages": ["/"], "tables": ["cakes"]},
            {"requirement_id": "FR-002", "module": "Menu", "pages": ["/"], "tables": ["cakes"]},
            {"requirement_id": "FR-003", "module": "Orders", "pages": ["/"], "tables": ["cakes"]},
        ],
        "diagrams": [
            {"id": "D1", "kind": "erd", "title": "ERD", "source": "erDiagram"},
            {"id": "D2", "kind": "use_case", "title": "Use case", "source": "graph TD"},
            {"id": "D3", "kind": "system_context", "title": "Context", "source": "graph TD"},
            {"id": "D4", "kind": "activity", "title": "Activity", "source": "graph TD"},
            {"id": "D5", "kind": "sequence", "title": "Sequence", "source": "sequenceDiagram"},
            {"id": "D6", "kind": "dfd", "title": "DFD", "source": "graph TD"},
        ],
    }
    doc.update(patch)
    return doc


class PromptPackTests(unittest.TestCase):
    def test_every_stage_has_its_pack(self):
        for name in ("shared/engine", "interview/system", "interview/turn",
                     "plan/system", "plan/draft", "plan/revise",
                     "srs/system", "srs/document", "srs/review", "srs/repair",
                     "design/system", "design/draft",
                     "prototype/generate", "prototype/revise",
                     "builder/generate", "builder/update",
                     "testing/run", "deployment/plan", "deployment/execute", "chat/update"):
            self.assertTrue(prompts.exists(name), f"prompts/{name}.md is missing")

    def test_placeholders_are_filled_and_unknown_ones_are_left_visible(self):
        text = prompts.load("chat/update", message="add a field", stage="build",
                            artifacts="the app", language="English")
        self.assertIn("add a field", text)
        self.assertNotIn("{{message}}", text)
        # A value nobody passed stays on the page rather than becoming silence.
        self.assertIn("{{target}}", prompts.load("deployment/execute"))

    def test_skill_pages_come_from_the_pack(self):
        self.assertIn("requirement", prompts.skill("srs", "functional-requirements").lower())
        self.assertTrue({"aws", "vercel", "netlify"} <=
                        {row["slug"] for row in prompts.catalogue("deployment")})
        self.assertGreater(len(prompts.catalogue("design", kind="themes")), 20)

    def test_a_prompt_name_cannot_escape_the_pack(self):
        with self.assertRaises(prompts.MissingPrompt):
            prompts.load("../server_modules/config")

    def test_the_build_and_testing_prompts_point_at_web_tools_for_gaps_the_guides_leave(self):
        """Phase 8: the hand-maintained scaffold guides are never replaced,
        but a real gap in them (a current API detail) now has a named,
        explicit fallback — deployment/execute.md already had this."""
        for name in ("builder/generate", "testing/run", "deployment/execute"):
            text = prompts.load(name)
            self.assertIn("web_search", text, name)
            self.assertIn("web_fetch", text, name)
        builder = prompts.load("builder/generate")
        self.assertIn("Never edit a guide file", builder)


class BuildAvailabilityTests(unittest.TestCase):
    def test_completed_legacy_prototype_is_buildable_after_reload(self):
        # Older prototype runs persisted their status but not the new flag.
        self.assertTrue(project_store.build_available({
            "prototype_only": True,
            "status": "prototyped",
            "build_available": False,
        }))

    def test_in_progress_prototype_does_not_unlock_build(self):
        self.assertFalse(project_store.build_available({
            "prototype_only": True,
            "status": "planning",
            "build_available": False,
        }))

    def test_persisted_build_capability_is_preserved(self):
        self.assertTrue(project_store.build_available({"build_available": True}))


class InterviewShapeTests(unittest.TestCase):
    """The interview is a bounded requirements session, not an open conversation."""

    def test_the_first_answer_is_not_a_coverage_category(self):
        """`app_type` is the one catalogue-driven question; it must never
        collide with the coverage taxonomy the model reasons over afterward."""
        from server_modules import coverage
        from srs_agent import interview

        self.assertNotIn(interview.APP_TYPE_KEY, coverage.categories())

    def test_the_first_question_is_the_product_shape_and_costs_no_model_call(self):
        from srs_agent import interview

        question = interview._app_type_question("a hotel taking room bookings", 1, 25)
        self.assertEqual(question["id"], interview.APP_TYPE_KEY)
        self.assertEqual(question["answer_type"], "single_choice")
        values = {o["value"] for o in question["options"]}
        self.assertIn("booking", values)
        self.assertIn("other", values)
        self.assertEqual(question["total"], 25)

    def test_the_guess_ignores_the_words_every_idea_contains(self):
        from srs_agent import interview

        # "Subscription product with accounts" shares "with" and "product" with
        # almost any sentence; matching on those made everything look like SaaS.
        for idea, wanted in (
            ("a hotel that takes room bookings online with payment", "booking"),
            ("a shop till for a hardware store with stock and receipts", "pos"),
            ("a storefront with a cart and checkout for selling shoes", "ecommerce"),
            ("a calculator for converting currency", "utility"),
            ("a subscription tool with workspaces and billing plans", "saas"),
        ):
            self.assertEqual(interview._guess_app_type(idea), wanted, idea)

    def test_a_plural_in_the_idea_still_matches_a_singular_hint(self):
        from srs_agent import interview

        self.assertEqual(interview._guess_app_type("weekly classes members can book"),
                         "booking")

    def test_the_catalogue_is_a_file_not_a_constant(self):
        from srs_agent import interview

        pack = interview.catalogue()
        self.assertIn("types", pack)
        for key, entry in pack["types"].items():
            self.assertTrue(entry.get("label"), f"{key} has no label")
            self.assertTrue(entry.get("desc"), f"{key} has no description")

    def test_first_interview_question_is_written_to_the_shared_chat_once(self):
        from server_modules import config, store
        from server_modules.session import drop
        from srs_agent import interview

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                project = store.create("a boutique hotel booking site")["id"]
                with patch.object(interview.bus, "agent_msg") as announced:
                    first = interview.next_question(project)
                    again = interview.next_question(project)

                self.assertEqual(first["question"]["id"], interview.APP_TYPE_KEY)
                self.assertEqual(again["question"]["id"], interview.APP_TYPE_KEY)
                announced.assert_called_once_with(
                    project, first["question"]["question"], agent=interview.bus.DEVELOPER,
                    title="Interview question", kind="interview")
            finally:
                drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces


class InterviewTurnTests(unittest.TestCase):
    """The per-turn contract: validated, merged as deltas, never a fixed queue."""

    def _validator(self):
        from server_modules import coverage
        from srs_agent import interview
        return interview._turn_validator(set(coverage.categories()))

    def test_an_unknown_category_in_coverage_updates_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown categories"):
            self._validator()({"stage": "gathering",
                               "coverage_updates": {"not_a_real_category": {"status": "KNOWN"}},
                               "next": {"question": "Who uses it?"}})

    def test_gathering_with_no_next_question_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "next.question is empty"):
            self._validator()({"stage": "gathering", "next": {"question": ""}})

    def test_confirming_with_no_summary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "confirmation_summary is empty"):
            self._validator()({"stage": "confirming", "confirmation_summary": ""})

    def test_a_well_formed_turn_of_either_stage_passes(self):
        check = self._validator()
        gathering = check({"stage": "gathering", "coverage_updates": {"auth": {"status": "KNOWN"}},
                           "next": {"question": "Who uses it?"}})
        self.assertEqual(gathering["stage"], "gathering")
        confirming = check({"stage": "confirming", "confirmation_summary": "Here is what I understood..."})
        self.assertEqual(confirming["stage"], "confirming")

    def test_apply_turn_only_changes_the_categories_the_turn_named(self):
        from server_modules import coverage
        from srs_agent import interview

        data = {"coverage": coverage.blank_coverage(), "contradictions": [], "assumptions": []}
        interview._apply_turn(data, {
            "stage": "gathering",
            "coverage_updates": {"auth": {"status": "KNOWN", "confidence": "high",
                                          "facts": ["email/password login"]}},
        }, source="turn:2")
        self.assertEqual(data["coverage"]["auth"]["status"], "KNOWN")
        self.assertEqual(data["coverage"]["auth"]["facts"], ["email/password login"])
        # Every other category is untouched by a turn that never mentioned it.
        for key, entry in data["coverage"].items():
            if key not in ("auth", "deployment"):
                self.assertEqual(entry["status"], "UNKNOWN", key)

    def test_a_found_contradiction_is_recorded_unresolved(self):
        from server_modules import coverage
        from srs_agent import interview

        data = {"coverage": coverage.blank_coverage(), "contradictions": [], "assumptions": []}
        interview._apply_turn(data, {
            "stage": "gathering",
            "contradiction": {"found": True, "category": "permissions",
                              "statement_a": {"quote": "only admins approve"},
                              "statement_b": {"quote": "staff can too"}},
        }, source="turn:5")
        self.assertEqual(len(data["contradictions"]), 1)
        self.assertFalse(data["contradictions"][0]["resolved"])
        self.assertEqual(data["contradictions"][0]["category"], "permissions")

    def test_question_from_turn_produces_the_view_compatible_shape(self):
        from srs_agent import interview

        question = interview._question_from_turn({
            "question": "Do people sign in with email, Google, or both?",
            "answer_type": "single_choice", "topic": "auth_method",
            "options": [{"label": "Email and password", "value": "email"},
                       {"label": "Google", "value": "google"}],
            "recommended": "email", "coverage": ["auth"],
        }, index=3, total=8)
        self.assertEqual(question["id"], "auth_method:3")
        self.assertEqual(question["answer_type"], "single_choice")
        self.assertEqual(question["kind"], "single")
        self.assertEqual({o["value"] for o in question["options"]}, {"email", "google"})
        self.assertEqual(question["coverage_areas"], ["auth"])

    def test_confirmation_question_offers_confirm_or_correct(self):
        from srs_agent import interview

        question = interview._confirmation_question("Here is what I understood...", index=9, total=9)
        self.assertEqual(question["answer_type"], "single_choice")
        self.assertEqual({o["value"] for o in question["options"]}, {"confirmed", "correct"})
        self.assertIn("understood", question["question"])

    def test_clicking_yes_thats_right_ends_the_interview_with_no_model_call(self):
        # Found live: the interview looped forever on the confirmation screen.
        # Interview.jsx's submitAnswer() always sends `text` as the picked
        # option's own label ("Yes, that's right") even on a bare click - only
        # `custom` (what the customer typed themselves) is empty then. The old
        # guard required `not text` too, so it never matched a real click, fell
        # through to a full model turn every time, and the model - nothing new
        # to extract, still told stage="confirming" - handed back the same
        # summary again. Reproduces record_answer() with a payload shaped
        # exactly like that real click.
        from server_modules import config, store
        from server_modules.session import session_for, drop
        from srs_agent import interview

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                record = store.create("a boutique hotel booking site")
                project = record["id"]
                session = session_for(project)
                data = interview.state(session)
                data["stage"] = "confirming"
                question = interview._confirmation_question("Here is what I understood...", 9, 9)
                data["transcript"].append(question)
                data["order"].append(question["id"])
                data["pending"] = question
                interview.save(session, data)

                with patch.object(interview.llm, "complete_json",
                                  side_effect=AssertionError("must not call the model")):
                    result = interview.record_answer(project, {
                        "key": question["id"], "value": "confirmed",
                        "text": "Yes, that's right", "selected": ["confirmed"], "custom": "",
                    })

                self.assertTrue(result["done"])
                self.assertEqual(store.get(project)["stage"], "plan")
            finally:
                drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces

    def test_retrying_an_already_saved_answer_is_idempotent(self):
        """A lost browser response must not overwrite the next question or 500."""
        from server_modules import config, store
        from server_modules.session import session_for, drop
        from srs_agent import interview

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                project = store.create("a boutique hotel booking site")["id"]
                session = session_for(project)
                data = interview.state(session)
                first = interview._app_type_question("hotel booking", 1, 8)
                next_one = interview._question_from_turn({
                    "topic": "auth_method", "question": "How should guests sign in?",
                    "answer_type": "single_choice",
                    "options": [{"label": "Email", "value": "email"}],
                }, index=2, total=8)
                data["transcript"] = [first, next_one]
                data["answers"][first["id"]] = {
                    "question_id": first["id"], "value": "booking",
                    "text": "Booking site", "selected_values": ["booking"],
                    "custom_text": "", "attachments": [],
                }
                data["order"] = [first["id"]]
                data["pending"] = next_one
                interview.save(session, data)

                result = interview.record_answer(project, {
                    "key": first["id"], "value": "booking", "text": "Booking site",
                    "selected": ["booking"], "custom": "",
                })

                self.assertEqual(result["question"]["id"], next_one["id"])
                self.assertEqual(len(result["answers"]), 1)
            finally:
                drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces

    def test_stale_answer_is_a_clear_client_error_not_a_state_corruption(self):
        from server_modules import config, store
        from server_modules.session import session_for, drop
        from srs_agent import interview

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                project = store.create("a boutique hotel booking site")["id"]
                session = session_for(project)
                data = interview.state(session)
                question = interview._app_type_question("hotel booking", 1, 8)
                data["transcript"] = [question]
                data["pending"] = question
                interview.save(session, data)

                with self.assertRaisesRegex(ValueError, "no longer awaiting"):
                    interview.record_answer(project, {"key": "old-question", "text": "late"})

                self.assertEqual(interview.snapshot(project)["question"]["id"], question["id"])
            finally:
                drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces

    def test_overlapping_answer_retries_share_one_interview_transition(self):
        """A retry cannot race the first save and create a second mutation."""
        from server_modules import config, store
        from server_modules.session import session_for, drop
        from srs_agent import interview

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                project = store.create("a boutique hotel booking site")["id"]
                session = session_for(project)
                data = interview.state(session)
                question = interview._app_type_question("hotel booking", 1, 8)
                data["transcript"] = [question]
                data["pending"] = question
                interview.save(session, data)

                first_at_save = threading.Event()
                release_first = threading.Event()
                second_started = threading.Event()
                second_finished = threading.Event()
                errors = []
                saves = [0]
                original_save = interview.save

                def delayed_save(current_session, current_data):
                    saves[0] += 1
                    if saves[0] == 1:
                        first_at_save.set()
                        self.assertTrue(release_first.wait(1))
                    return original_save(current_session, current_data)

                payload = {"key": question["id"], "value": "booking",
                           "text": "Booking site", "selected": ["booking"], "custom": ""}

                def submit(second=False):
                    try:
                        if second:
                            second_started.set()
                        interview.record_answer(project, payload)
                    except Exception as exc:  # pragma: no cover - failure is asserted below
                        errors.append(exc)
                    finally:
                        if second:
                            second_finished.set()

                with patch.object(interview, "save", side_effect=delayed_save):
                    first = threading.Thread(target=submit)
                    first.start()
                    self.assertTrue(first_at_save.wait(1))
                    second = threading.Thread(target=lambda: submit(second=True))
                    second.start()
                    self.assertTrue(second_started.wait(1))
                    self.assertFalse(second_finished.wait(0.1))
                    release_first.set()
                    first.join(1)
                    second.join(1)

                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                self.assertFalse(errors)
                self.assertEqual(len(interview.snapshot(project)["answers"]), 1)
            finally:
                drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces

    def test_malformed_legacy_interview_state_is_normalized_before_answering(self):
        from server_modules import config, store
        from server_modules.session import session_for, drop
        from srs_agent import interview

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                project = store.create("a boutique hotel booking site")["id"]
                session = session_for(project)
                question = interview._app_type_question("hotel booking", 1, 8)
                session.write_record("interview.json", data={
                    "transcript": [question, "broken row"],
                    "answers": {"broken": "row"}, "order": [None, question["id"]],
                    "pending": question, "coverage": {"auth": "broken"},
                    "contradictions": ["broken"], "assumptions": "broken",
                })

                result = interview.record_answer(project, {
                    "key": question["id"], "value": "booking", "text": "Booking site",
                    "selected": ["booking"], "custom": "",
                })

                self.assertEqual(result["answers"][0]["question_id"], question["id"])
                self.assertIsNone(result["question"])
            finally:
                drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces


class CoverageTests(unittest.TestCase):
    """The coverage taxonomy is hardcoded categories, not questions or order —
    what gets asked, in what order, is the model's decision each turn."""

    def test_every_category_carries_a_label_ask_about_and_importance(self):
        from server_modules import coverage

        cats = coverage.categories()
        self.assertGreaterEqual(len(cats), 15)
        for key, entry in cats.items():
            self.assertTrue(entry.get("label"), f"{key} has no label")
            self.assertTrue(entry.get("ask_about"), f"{key} has no ask_about")
            self.assertIn(entry.get("importance"), ("critical", "high", "normal"), key)

    def test_deployment_starts_not_applicable_everything_else_starts_unknown(self):
        from server_modules import coverage

        blank = coverage.blank_coverage()
        self.assertEqual(blank["deployment"]["status"], "NOT_APPLICABLE")
        others = [k for k in blank if k != "deployment"]
        self.assertTrue(others)
        for key in others:
            self.assertEqual(blank[key]["status"], "UNKNOWN", key)


class JsonExtractionTests(unittest.TestCase):
    def test_reads_json_however_the_model_wrapped_it(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('Here you go:\n{"a": 1}\nHope that helps.'), {"a": 1})
        with self.assertRaises(ValueError):
            extract_json("no object here")


class PlanRuleTests(unittest.TestCase):
    def test_a_complete_plan_passes(self):
        plan_rules.plan_validator(plan_rules.archetype_pack(a_plan()))(a_plan())

    def test_a_one_line_intent_is_not_something_to_approve(self):
        with self.assertRaisesRegex(ValueError, "product_intent"):
            plan_rules.plan_validator({})(a_plan(product_intent="A bakery site."))

    def test_a_screen_needs_a_purpose(self):
        with self.assertRaisesRegex(ValueError, "purpose"):
            plan_rules.plan_validator({})(
                a_plan(screens=[{"name": "Home", "route": "/", "who": []}]))

    def test_a_record_that_keeps_one_thing_is_not_a_record(self):
        with self.assertRaisesRegex(ValueError, "keep only one thing"):
            plan_rules.plan_validator({"archetype": "record-based"})(
                a_plan(records=[{"name": "Cake", "keeps": ["Name"]}]))

    def test_public_signup_cannot_create_a_privileged_role(self):
        with self.assertRaisesRegex(ValueError, "privileged"):
            plan_rules.plan_validator({"auth_policy": "required"})(
                a_plan(account_policy={"accounts_required": True,
                                       "registration_mode": "open",
                                       "registration_role": "Store Manager"}))

    def test_invite_mode_needs_someone_to_do_the_inviting(self):
        with self.assertRaisesRegex(ValueError, "provisioning_role"):
            plan_rules.plan_validator({"auth_policy": "required"})(
                a_plan(account_policy={"accounts_required": True,
                                       "registration_mode": "invite"}))


class SrsSchemaTests(unittest.TestCase):
    def test_a_complete_document_validates_either_wrapped_or_bare(self):
        self.assertIn("srs_document", srs_schema.srs_validator(a_document()))
        self.assertIn("srs_document",
                      srs_schema.srs_validator({"srs_document": a_document()}))

    def test_the_floors_are_enforced_with_a_message_a_model_can_act_on(self):
        with self.assertRaises(ValueError) as caught:
            srs_schema.srs_validator(a_document(functional_requirements=[]))
        self.assertIn("functional_requirements", str(caught.exception))

    def test_summary_counts_what_the_inspector_shows(self):
        counts = srs_schema.summarize_srs({"srs_document": a_document()})
        self.assertEqual(counts["functional"], 3)
        self.assertEqual(counts["tables"], 1)
        self.assertEqual(counts["roles"], 1)


class ReviewRuleTests(unittest.TestCase):
    def test_a_finding_against_a_requirement_that_does_not_exist_is_rejected(self):
        check = review.review_validator(a_document())
        with self.assertRaisesRegex(ValueError, "FR-999"):
            check({"verdict": "revise",
                   "scores": dict.fromkeys(review.SCORES, 4),
                   "findings": [{"requirement_id": "FR-999", "severity": "major",
                                 "problem": "vague"}]})

    def test_python_decides_whether_the_draft_passed_not_the_model(self):
        # The model says accept; a blocker says otherwise.
        self.assertFalse(review.satisfied({
            "verdict": "accept", "scores": dict.fromkeys(review.SCORES, 5),
            "findings": [{"severity": "blocker", "problem": "untestable"}]}))
        # And a thin section blocks even with no finding to pin it on.
        thin = dict.fromkeys(review.SCORES, 5)
        thin["security"] = 1
        self.assertFalse(review.satisfied({"verdict": "accept", "scores": thin}))
        self.assertTrue(review.satisfied({"verdict": "revise",
                                          "scores": dict.fromkeys(review.SCORES, 3)}))

    def test_findings_become_repair_instructions(self):
        text = review.findings_text({
            "scores": dict.fromkeys(review.SCORES, 4),
            "findings": [{"requirement_id": "FR-001", "severity": "major",
                          "problem": "no threshold", "suggested_rewrite": "within 200ms"}],
            "missing_requirements": [{"kind": "security", "topic": "rate limiting",
                                      "why": "OWASP"}]})
        self.assertIn("FR-001", text)
        self.assertIn("within 200ms", text)
        self.assertIn("rate limiting", text)

    def test_stamp_records_the_structural_readout_alongside_the_verdict(self):
        doc = a_document()
        review.stamp(doc, "accepted", 1, "the draft met the standards",
                     {"scores": dict.fromkeys(review.SCORES, 5)},
                     structural={"sections": {"ratio": 0.25}, "ambiguity": {"rate": 1.0}})
        readout = doc["requirements_quality_review"]["reviewer"]["structural_readout"]
        self.assertEqual(readout["sections"]["ratio"], 0.25)
        self.assertEqual(readout["ambiguity"]["rate"], 1.0)

    def test_stamp_without_a_structural_readout_omits_the_key(self):
        doc = a_document()
        review.stamp(doc, "skipped", 0, "there was nothing to review")
        self.assertNotIn("structural_readout", doc["requirements_quality_review"]["reviewer"])


def a_wireframe(body: str = "", pad: int = 8000) -> str:
    """A complete HTML document of roughly the size a real page has."""
    return ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Page</title><style>body{font-family:system-ui}"
            ".shell{display:flex}</style></head><body>"
            f"{body}<!--{'x' * pad}--></body></html>")


class CompletenessTests(unittest.TestCase):
    def test_a_covered_specification_has_no_gaps(self):
        pages = [("/", a_wireframe("<main><h1>Our Cakes</h1></main>"))]
        self.assertEqual(completeness.check_document(a_document(), a_plan()), [])
        self.assertEqual(completeness.wireframe_depth(pages, a_document()), [])

    def test_a_screen_the_plan_promised_and_the_document_dropped(self):
        plan = a_plan(screens=[
            {"name": "Home", "route": "/", "purpose": "show the cakes", "who": ["Visitor"]},
            {"name": "Basket", "route": "/basket", "purpose": "review the order",
             "who": ["Visitor"]}])
        gaps = completeness.page_coverage(a_document(), plan)
        self.assertTrue(any("Basket" in gap for gap in gaps))

    def test_a_record_the_plan_promised_and_the_schema_dropped(self):
        plan = a_plan(records=[{"name": "Cake", "keeps": ["Name", "Price"]},
                               {"name": "Order", "keeps": ["When", "Total"]}])
        gaps = completeness.table_coverage(a_document(), plan)
        self.assertTrue(any("Order" in gap for gap in gaps))

    def test_irregular_singular_record_names_match_conventional_plural_tables(self):
        plan = a_plan(records=[{"name": "Booking History Entry", "keeps": ["Booking"]},
                               {"name": "Message Log Entry", "keeps": ["Type"]}])
        doc = a_document(database_design={"tables": [
            {"table_name": "booking_history_entries"},
            {"table_name": "message_log_entries"},
        ]})
        self.assertEqual(completeness.table_coverage(doc, plan), [])

    def test_main_srs_gate_does_not_require_diagrams_before_they_are_drawn(self):
        doc = a_document(diagrams=[])
        self.assertEqual(completeness.check_document(doc, a_plan()), [])

    def test_plan_synchronization_fills_missing_workflows_screens_and_trace_rows(self):
        plan = a_plan(
            screens=[{"name": "Home", "route": "/", "purpose": "show the cakes",
                      "who": ["Visitor"]},
                     {"name": "Bookings", "route": "/bookings", "purpose": "manage stays",
                      "who": ["Owner"]}],
            records=[{"name": "Cake", "keeps": ["Name", "Price"]},
                     {"name": "Booking History Entry", "keeps": ["Booking", "Changed date"]}],
            workflows=[{"name": "Ordering a cake", "who": "Visitor",
                         "steps": ["open Home", "choose a cake", "pay the deposit"]},
                        {"name": "Managing bookings", "who": "Owner",
                         "steps": ["open Bookings", "inspect an order"]}],
        )
        envelope = {"srs_document": a_document(requirement_traceability_matrix=[],
                                               business_workflows=[])}
        added = srs_document._synchronize_plan_contract(envelope, plan)
        doc = envelope["srs_document"]

        self.assertEqual(added["workflows"], 2)
        self.assertEqual(added["pages"], 1)
        self.assertEqual(added["tables"], 1)
        self.assertEqual(added["traceability"], 3)
        self.assertEqual(completeness.check_document(doc, plan), [])

    def test_a_feature_nobody_wrote_a_requirement_for(self):
        plan = a_plan(features=["A visitor can order a cake for collection",
                                "The owner can export monthly revenue to a spreadsheet"])
        gaps = completeness.requirement_coverage(a_document(), plan)
        self.assertTrue(any("revenue" in gap for gap in gaps))

    def test_the_wireframe_floor_is_sized_to_the_page(self):
        # A sign-in screen is a finished screen at the floor; a page the
        # specification says carries eight things is not.
        sign_in = a_wireframe("<form><label>Email</label><input></form>", pad=7000)

        small = a_document(public_pages=[{"page_name": "Sign in", "route": "/login",
                                          "sections": ["form"], "functions": ["sign in"]}])
        self.assertEqual(completeness.wireframe_depth([("/login", sign_in)], small), [])

        big = a_document(public_pages=[{"page_name": "Dashboard", "route": "/login",
                                        "sections": ["a", "b", "c", "d"],
                                        "functions": ["e", "f", "g", "h"]}])
        self.assertTrue(completeness.wireframe_depth([("/login", sign_in)], big))

    def test_a_wireframe_that_is_only_a_fragment(self):
        """The old section-fragment shape renders as unstyled text in the studio."""
        fragment = '<section class="wf-header">Bakery</section>' + "x" * 9000
        gaps = completeness.wireframe_depth([("/", fragment)], a_document())
        self.assertTrue(any("complete HTML document" in gap for gap in gaps))

    def test_a_wireframe_with_no_stylesheet_of_its_own(self):
        naked = ("<!DOCTYPE html><html><head><title>x</title></head><body>"
                 + "y" * 9000 + "</body></html>")
        gaps = completeness.wireframe_depth([("/", naked)], a_document())
        self.assertTrue(any("<style>" in gap for gap in gaps))


class StructuralRubricTests(unittest.TestCase):
    """The Phase 3 readouts a real review call is grounded against: which
    optional sections carry content, and how many self-flagged ambiguities
    the document actually resolved."""

    def test_every_structural_section_starts_empty_on_the_bare_fixture(self):
        readout = completeness.section_completeness(a_document())
        self.assertEqual(readout["populated"], [])
        self.assertEqual(len(readout["empty"]), len(completeness.STRUCTURAL_SECTIONS))
        self.assertEqual(readout["ratio"], 0.0)

    def test_a_populated_section_moves_from_empty_to_populated(self):
        doc = a_document(security_requirements=["passwords are hashed"],
                         acceptance_criteria=[{"criterion": "an order can be placed"}])
        readout = completeness.section_completeness(doc)
        self.assertIn("security requirements", readout["populated"])
        self.assertIn("acceptance criteria", readout["populated"])
        self.assertNotIn("security requirements", readout["empty"])
        self.assertGreater(readout["ratio"], 0)

    def test_no_ambiguities_is_a_fully_resolved_rate(self):
        readout = completeness.ambiguity_resolution(a_document(ambiguities=[]))
        self.assertEqual(readout, {"total": 0, "resolved": 0, "rate": 1.0})

    def test_an_open_ambiguity_lowers_the_resolution_rate(self):
        doc = a_document(ambiguities=[
            {"id": "A1", "area": "payment", "description": "deposit amount",
             "assumption_made": "20% of the order", "needs_clarification": False},
            {"id": "A2", "area": "refunds", "description": "refund window",
             "assumption_made": "no refunds after collection", "needs_clarification": True},
        ])
        readout = completeness.ambiguity_resolution(doc)
        self.assertEqual(readout, {"total": 2, "resolved": 1, "rate": 0.5})


class EventStreamTests(unittest.TestCase):
    def test_a_long_conversation_keeps_older_durable_turns_after_restart(self):
        """The Studio may page older rows visually, but it must never trim them."""
        from server_modules import bus, config

        with tempfile.TemporaryDirectory() as directory:
            original = config.WORKSPACES
            config.WORKSPACES = Path(directory)
            project = "prj_long_conversation"
            try:
                bus.project_created(project)
                for index in range(4001):
                    bus.user_msg(project, f"request {index}")

                # A process restart has no in-memory rows. Reloading must
                # restore both the first and newest customer message.
                bus.forget(project)
                bus.project_created(project)
                replayed = [event for event in bus.history(project)
                            if event.get("type") == "user_msg"]
                text = {event.get("text") for event in replayed}
                self.assertIn("request 0", text)
                self.assertIn("request 4000", text)
            finally:
                config.WORKSPACES = original
                forget_project(project)

    def test_the_durable_events_survive_a_restart(self):
        from server_modules import bus, config

        with tempfile.TemporaryDirectory() as directory:
            original = config.WORKSPACES
            config.WORKSPACES = Path(directory)
            try:
                bus.forget("prj_test")
                bus.project_created("prj_test")
                bus.log("prj_test", "INFO", "started")
                bus.agent_msg("prj_test", "the plan is ready")
                bus.stream("prj_test", "a token")        # live only
                bus.done("prj_test", "finished")

                # Drop the memory the way a restart does, and read it back.
                bus.forget("prj_test")
                bus.project_created("prj_test")
                replayed = bus.history("prj_test")
                kinds = [event["type"] for event in replayed]
                self.assertIn("log", kinds)
                self.assertIn("agent_msg", kinds)
                self.assertIn("done", kinds)
                self.assertNotIn("stream", kinds)

                stream = bus.saved_stream("prj_test")
                self.assertEqual(stream["chat"][0]["text"], "the plan is ready")
                self.assertEqual(stream["logs"][0]["text"], "started")
            finally:
                config.WORKSPACES = original
                forget_project("prj_test")

    def test_events_carry_what_the_studio_reducer_reads(self):
        from server_modules import bus, config

        seen = []
        cancel = bus.subscribe(seen.append)
        # Durable events write into the project's workspace, so point that
        # somewhere disposable rather than leaving a `prj_shape` folder behind.
        original = config.WORKSPACES
        with tempfile.TemporaryDirectory() as directory:
            config.WORKSPACES = Path(directory)
            try:
                bus.phase("prj_shape", "srs", "Writing", detail="the document")
                bus.run_state("prj_shape", "running", run_id="r1")
                bus.file_written("prj_shape", "a.txt", "new", old="old")
            finally:
                cancel()
                config.WORKSPACES = original
                forget_project("prj_shape")

        by_type = {event["type"]: event for event in seen}
        self.assertEqual(by_type["phase"]["title"], "Writing")
        self.assertEqual(by_type["run_state"]["status"], "running")
        self.assertEqual(by_type["file"]["old_content"], "old")
        for event in seen:
            self.assertIn("event_id", event)
            self.assertIn("at", event)
            self.assertIn("project", event)


class StreamWriterTests(unittest.TestCase):
    """Phase 6's token batching: a fast model's deltas are coalesced before
    they reach the bus, so one page does not flood the shared event history."""

    def _own_role_events(self, seen):
        # MIRROR_ROLES files every event under both roles; count the one the
        # writer was actually created for ("developer", StreamWriter's default).
        return [e for e in seen if e["agent"] == "developer"]

    def test_small_bursts_under_the_thresholds_are_not_flushed_yet(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=10, min_chars=1000)
            writer.start("a.html")
            writer.token("a")
            writer.token("bit")
            writer.token("more")
        finally:
            cancel()
            forget_project("prj_stream")
        # start() itself emits stream_start; no stream (token) event yet.
        self.assertNotIn("stream", [e["type"] for e in self._own_role_events(seen)])

    def test_crossing_the_character_threshold_flushes_once(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=10, min_chars=5)
            writer.start("a.html")
            writer.token("hel")
            writer.token("lo!")   # 6 characters buffered, over the 5-character threshold
        finally:
            cancel()
            forget_project("prj_stream")
        tokens = [e for e in self._own_role_events(seen) if e["type"] == "stream"]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["token"], "hello!")

    def test_crossing_the_time_threshold_flushes_even_a_short_buffer(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=0, min_chars=1000)
            writer.start("a.html")
            writer.token("x")
        finally:
            cancel()
            forget_project("prj_stream")
        tokens = [e for e in self._own_role_events(seen) if e["type"] == "stream"]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["token"], "x")

    def test_an_empty_token_is_ignored(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=0, min_chars=1)
            writer.start("a.html")
            writer.token("")
        finally:
            cancel()
            forget_project("prj_stream")
        self.assertEqual([e for e in self._own_role_events(seen) if e["type"] == "stream"], [])

    def test_end_flushes_a_buffered_tail_that_never_crossed_a_threshold(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=10, min_chars=1000)
            writer.start("a.html")
            writer.token("just a few characters")
            own = self._own_role_events(seen)
            self.assertEqual([e for e in own if e["type"] == "stream"], [])   # not flushed yet
            writer.end("a.html", "just a few characters")
        finally:
            cancel()
            forget_project("prj_stream")
        own = self._own_role_events(seen)
        tokens = [e for e in own if e["type"] == "stream"]
        ends = [e for e in own if e["type"] == "stream_end"]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["token"], "just a few characters")
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["content"], "just a few characters")

    def test_a_second_start_clears_a_still_unflushed_tail_from_the_first_round(self):
        """The bug a naive per-call sink had: a draft round's small,
        never-flushed leftover text used to bleed into the repair round that
        replaced it, because the two rounds shared one buffer with nothing
        resetting it in between. `start()` now owns that reset itself."""
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=10, min_chars=1000)
            writer.start("a.html")
            writer.token("draft round narration, never long enough to flush")
            # A new round begins (e.g. a validation repair) without the first
            # round ever having flushed or ended.
            writer.start("a.html")
            writer.token("the real page")
            writer.end("a.html", "the real page")
        finally:
            cancel()
            forget_project("prj_stream")
        tokens = [e for e in self._own_role_events(seen) if e["type"] == "stream"]
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["token"], "the real page")

    def test_end_with_nothing_buffered_still_ends_the_stream(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            writer = bus.StreamWriter("prj_stream", min_interval=10, min_chars=1000)
            writer.start("a.html")
            writer.end("a.html", "")
        finally:
            cancel()
            forget_project("prj_stream")
        own = self._own_role_events(seen)
        self.assertEqual([e for e in own if e["type"] == "stream"], [])
        self.assertEqual(len([e for e in own if e["type"] == "stream_end"]), 1)


class LiveUsageMeterTests(unittest.TestCase):
    def test_memory_event_carries_exact_current_turn_usage(self):
        from server_modules import bus

        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            bus.memory("prj_usage", "test", 120, 4096, 2,
                       turn_started_at=1234, turn_input_tokens=41,
                       turn_output_tokens=9)
        finally:
            cancel()
            forget_project("prj_usage")
        event = next(e for e in seen if e["type"] == "memory" and e["agent"] == "developer")
        self.assertEqual(event["turn_started_at"], 1234)
        self.assertEqual(event["sent"], 41)
        self.assertEqual(event["received"], 9)
        self.assertEqual(event["turn_tokens"], 9)


class PlanningStreamTests(unittest.TestCase):
    def test_planning_shows_activity_without_publishing_the_generated_plan(self):
        from server_modules import bus
        from server_modules.session import ProjectSession

        class Result:
            status = "complete"
            text = "done"
            rounds = 1

        class Agent:
            def set_mode(self, _mode):
                pass

            def ask(self, _request):
                return "1. Read the contract\n2. Build every route\n3. Verify the app"

            def execute_plan(self, _request, _plan, **_kwargs):
                return Result()

        session = ProjectSession.__new__(ProjectSession)
        session.project = "prj_plan"
        session.role = bus.DEVELOPER
        session.stage = "build"
        session.lock = threading.RLock()
        session._cancel = threading.Event()
        session.agent = lambda _model="": Agent()
        session.report_memory = lambda: None
        session.save_context = lambda: None

        with patch.object(bus, "agent_state"), patch.object(bus, "log") as logged, \
             patch.object(bus, "agent_msg") as published:
            result = session.run_task("build it")

        self.assertEqual(result["status"], "complete")
        published.assert_not_called()
        messages = [str(call.args[2]) for call in logged.call_args_list]
        self.assertTrue(any("reviewing the project context" in line for line in messages))
        self.assertTrue(any("Plan ready" in line for line in messages))

    def test_build_plans_are_saved_in_output_app_and_a_new_run_replans(self):
        from server_modules import bus
        from server_modules.session import ProjectSession

        class Result:
            status = "complete"
            text = "done"
            rounds = 1

        with tempfile.TemporaryDirectory() as directory:
            session = ProjectSession.__new__(ProjectSession)
            session.project = "prj_plan_record"
            session.role = bus.DEVELOPER
            session.stage = "build"
            session.workspace = Path(directory)
            session.lock = threading.RLock()
            session._cancel = threading.Event()
            session.report_memory = lambda: None
            session.save_context = lambda: None
            plans = iter(("Milestone 1: first plan", "Milestone 1: revised plan"))

            class Agent:
                def set_mode(self, _mode):
                    pass

                def ask(self, _request):
                    return next(plans)

                def execute_plan(self, request, plan, **_kwargs):
                    name = "developmentplan1.md" if "first" in plan else "developmentplan2.md"
                    assert (session.workspace / "plan" / name).read_text(encoding="utf-8") == plan
                    assert f"plan/{name}" in request
                    return Result()

            session.agent = lambda _model="": Agent()
            with patch.object(bus, "agent_state"), patch.object(bus, "log"):
                first = session.run_task("build", plan_directory="plan")
                second = session.run_task("build again", plan_directory="plan")

            self.assertEqual(first["plan"], "Milestone 1: first plan")
            self.assertEqual(second["plan"], "Milestone 1: revised plan")
            self.assertEqual(first["plan_file"], "plan/developmentplan1.md")
            self.assertEqual(second["plan_file"], "plan/developmentplan2.md")
            self.assertEqual((session.workspace / first["plan_file"]).read_text(encoding="utf-8"), first["plan"])

    def test_file_reads_get_a_visible_expandable_chat_activity(self):
        from server_modules import bus
        from server_modules.session import StudioTools

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "handoff.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
            tools = StudioTools(root, None, lambda _question: True,
                                project="prj_plan", role_of=lambda: bus.DEVELOPER)
            dormant = type("Dormant", (), {"_agent": None})()
            with patch("server_modules.session.session_for", return_value=dormant), \
                 patch.object(bus, "file_read") as file_read, \
                 patch.object(bus, "log") as logged:
                result = tools.execute("read_file", {"path": "handoff.md"})

        self.assertIn("1: one", result)
        file_read.assert_called_once()
        self.assertIn("Read handoff.md (3 lines)", logged.call_args.args[2])

    def test_a_failed_tool_call_names_itself_in_the_warn_log(self):
        # Found live: a model calling list_files on a path that turned out to
        # be a file got a WARN log that just said "Tool error: Not a
        # directory" — no way to tell from the studio's activity feed which
        # call produced it, even though the model recovers on its own right
        # after. The log line now names the call.
        from server_modules import bus
        from server_modules.session import StudioTools

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "handoff.md").write_text("one\n", encoding="utf-8")
            tools = StudioTools(root, None, lambda _question: True,
                                project="prj_plan", role_of=lambda: bus.DEVELOPER)
            dormant = type("Dormant", (), {"_agent": None})()
            with patch("server_modules.session.session_for", return_value=dormant), \
                 patch.object(bus, "log") as logged:
                result = tools.execute("list_files", {"path": "handoff.md"})

        self.assertIn("is a file, not a directory", result)
        warn_calls = [call for call in logged.call_args_list if call.args[1] == "WARN"]
        self.assertEqual(len(warn_calls), 1)
        self.assertIn("list_files(handoff.md)", warn_calls[0].args[2])
        self.assertIn("is a file, not a directory", warn_calls[0].args[2])

    def test_running_a_command_posts_one_clean_output_card_not_a_line_per_line_echo(self):
        # Found live: every line of a real npm build's output streamed into the
        # chat as its own separate, unformatted bus.log entry (readable fine in
        # a terminal, choppy and symbol-mangled as individual chat bubbles) -
        # and then the *same* complete output was posted again as one block
        # once the command finished. A wall of raw lines followed by a full
        # duplicate, instead of the one clean card Claude Code/Codex show.
        from server_modules import bus, config, store
        from server_modules.session import StudioTools, drop

        with tempfile.TemporaryDirectory() as folder:
            original_projects, original_workspaces = config.PROJECTS_FILE, config.WORKSPACES
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            config.WORKSPACES = Path(folder) / "workspaces"
            project = None
            try:
                record = store.create("a test idea")
                project = record["id"]
                workspace = config.workspace_for(project)
                (workspace / "emit.py").write_text(
                    "print('line one')\nprint('line two')\nprint('line three')\n", encoding="utf-8")
                tools = StudioTools(workspace, None, lambda _q: True,
                                    project=project, role_of=lambda: bus.DEVELOPER)
                events = []
                self.addCleanup(bus.subscribe(events.append))
                result = tools.execute("run_command", {"command": f"{sys.executable} emit.py"})
            finally:
                if project:
                    drop(project)
                config.PROJECTS_FILE, config.WORKSPACES = original_projects, original_workspaces

        self.assertIn("line one", result)
        # No per-line "› ..." echo at all anymore.
        echoes = [e for e in events if e.get("type") == "log" and str(e.get("text", "")).startswith("›")]
        self.assertEqual(echoes, [])
        # Exactly one clean card with the whole output, posted once.
        cards = [e for e in events if e.get("type") == "agent_msg" and e.get("kind") == "command_output"]
        self.assertTrue(cards)
        for card in cards:
            self.assertIn("line one", card["text"])
            self.assertIn("line three", card["text"])


class OneContextTests(unittest.TestCase):
    """One project, one context, across all six stages."""

    def _session(self, directory):
        from server_modules import config
        from server_modules.session import ProjectSession

        original = config.WORKSPACES
        config.WORKSPACES = Path(directory)
        try:
            return ProjectSession("prj_ctx"), original
        except Exception:
            config.WORKSPACES = original
            raise

    def test_a_note_taken_before_the_agent_exists_is_not_lost(self):
        """The interview runs long before any tool-using stage opens the agent."""
        from server_modules import config

        with tempfile.TemporaryDirectory() as directory:
            session, original = self._session(directory)
            try:
                session.note("Interview — who uses it? Members and an instructor.")
                session.note("The customer approved the plan.")
                self.assertIn("instructor", session.memory_digest())
                self.assertIn("approved the plan", session.memory_digest())
            finally:
                config.WORKSPACES = original

    def test_context_checkpoint_keeps_the_project_model_preference(self):
        from server_modules import config

        with tempfile.TemporaryDirectory() as directory:
            session, original = self._session(directory)
            try:
                session._context_file().write_text(json.dumps({
                    "model": "cloud-model-a",
                    "thinking_level": "xhigh",
                    "messages": [],
                }), encoding="utf-8")
                self.assertEqual(session._saved_context_preferences(), ("cloud-model-a", "xhigh"))
            finally:
                config.WORKSPACES = original

    def test_the_memory_carries_every_stage_into_the_focused_calls(self):
        from server_modules import config

        with tempfile.TemporaryDirectory() as directory:
            session, original = self._session(directory)
            try:
                for stage in ("Interview — pickup is 4 hours before",
                              "The specification is written",
                              "7 wireframe(s) are drawn",
                              "The prototype is built",
                              "The application is built",
                              "Verification finished"):
                    session.note(stage)
                digest = session.memory_digest()
                for stage in ("4 hours", "specification", "wireframe",
                              "prototype", "application", "Verification"):
                    self.assertIn(stage, digest, f"{stage} fell out of the memory")
            finally:
                config.WORKSPACES = original

    def test_the_digest_is_bounded_so_a_long_project_still_fits_a_prompt(self):
        from server_modules import config

        with tempfile.TemporaryDirectory() as directory:
            session, original = self._session(directory)
            try:
                for index in range(200):
                    session.note(f"Stage note number {index} " + "x" * 200)
                digest = session.memory_digest(limit=4000)
                self.assertLessEqual(len(digest), 4000)
                # The most recent stages are the ones that survive.
                self.assertIn("number 199", digest)
            finally:
                config.WORKSPACES = original


class WireframeGenerationTests(unittest.TestCase):
    def test_page_prompt_points_at_the_handoff_files_and_carries_the_approved_plan(self):
        """The handoff is read by the model itself, not pasted into the prompt."""
        from srs_agent import document as srs_document

        class Session:
            def __init__(self, root):
                self.workspace = root
                self.record = root / ".agentforge"

            def record_path(self, *parts):
                path = self.record.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                return path

        html = "<!DOCTYPE html><html><head><style>body{color:#111;background:#fff}</style>" \
               "</head><body>" + "Detailed section. " * 420 + "</body></html>"
        handoff = "Contract " + "x" * 21000 + " FINAL_HANDOFF_DETAIL"
        captured = []

        def complete_html(**kwargs):
            captured.append(kwargs["user"])
            return html

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(srs_document.llm, "complete_html", side_effect=complete_html), \
             patch.object(srs_document.plan_stage, "markdown", return_value="# Approved /plan"), \
             patch.object(srs_document.bus, "file_written"), \
             patch.object(srs_document.bus, "log"):
            srs_document._draw_page(Session(Path(folder)), "test", a_document(),
                                    a_document()["public_pages"][0],
                                    {"app.md": handoff, "sitemap.md": "All routes"})

        self.assertNotIn("FINAL_HANDOFF_DETAIL", captured[0])
        self.assertIn(".agentforge/srs/handoff/app.md", captured[0])
        self.assertIn(".agentforge/srs/handoff/sitemap.md", captured[0])
        self.assertIn("# Approved /plan", captured[0])

    def test_every_plan_route_gets_a_grid_card_even_when_one_drawing_fails(self):
        from srs_agent import document as srs_document

        approved = a_plan(screens=[
            {"name": "Home", "route": "/", "purpose": "Browse", "who": ["Visitor"]},
            {"name": "Checkout", "route": "/checkout", "purpose": "Pay", "who": ["Visitor"]},
            {"name": "Orders", "route": "/orders", "purpose": "Review", "who": ["Owner"]},
        ])
        doc = a_document()

        class Session:
            stage = "srs"

            def __init__(self, root):
                self.workspace = root
                self.record = root / ".agentforge"
                self.saved = {}

            def read_record(self, *parts, fallback=None):
                return copy.deepcopy(self.saved.get(parts, fallback))

            def write_record(self, *parts, data):
                self.saved[parts] = copy.deepcopy(data)
                return self.record.joinpath(*parts)

        with tempfile.TemporaryDirectory() as folder:
            session = Session(Path(folder))

            systems = []

            def draw(_session, _project, _doc, page, _docs, _request, system, **_kwargs):
                systems.append(system)
                if page["route"] == "/checkout":
                    raise ValueError("model unavailable")
                slug = srs_document._slug(page["route"])
                relative = f".agentforge/srs/wireframes/{slug}.html"
                path = session.workspace / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("<!DOCTYPE html><html><style></style></html>", encoding="utf-8")
                return {"route": page["route"], "name": page["page_name"],
                        "slug": slug, "file": relative}

            with patch.object(srs_document, "handoff_docs", return_value={"app.md": "contract"}), \
                 patch.object(srs_document, "_draw_page", side_effect=draw), \
                 patch.object(srs_document, "_wireframe_system", return_value={"ideas": "IDEAS", "layout": "LAYOUT", "new": []}) as prepared, \
                 patch.object(srs_document, "session_for", return_value=session), \
                 patch.object(srs_document, "document", return_value={"srs_document": doc}), \
                 patch.object(srs_document.plan_stage, "approved_plan", return_value=approved), \
                 patch.object(srs_document.bus, "phase"), \
                 patch.object(srs_document.bus, "agent_msg") as messages, \
                 patch.object(srs_document.bus, "log"):
                self.assertEqual(srs_document._generate_wireframes(session, "test", doc, approved), 2)
                self.assertTrue(any(call.kwargs.get("title") == "Wireframe generation"
                                    for call in messages.call_args_list))
                grid = srs_document.wireframes("test")
                # the ideas and the shared layout are made once, before any page, and every page is given the same ones
                self.assertEqual(prepared.call_count, 1)
                self.assertTrue(prepared.call_args.kwargs["fresh"])            # every page again: a new pass
                self.assertEqual(len(systems), 3)
                self.assertTrue(all(s["layout"] == "LAYOUT" and s["ideas"] == "IDEAS" for s in systems))
                srs_document._generate_wireframes(session, "test", doc, approved, route="/orders")
                self.assertFalse(prepared.call_args.kwargs["fresh"])           # one page again: the kept ones are reused

            self.assertEqual([p["route"] for p in grid["pages"]],
                             ["/", "/checkout", "/orders"])
            self.assertEqual([p["has_html"] for p in grid["pages"]],
                             [True, False, True])
            self.assertIn("model unavailable", grid["pages"][1]["error"])
            self.assertFalse(grid["drawing"])


class PrototypeFromWireframesTests(unittest.TestCase):
    def test_the_agent_reads_the_three_inputs_plans_silently_and_writes_every_page(self):
        from prototype_agent import prototype as prototyper
        from srs_agent import document as srs_document

        doc = a_document(
            authentication_requirement={"login_required": True, "sign_in_route": "/login"},
            public_pages=[{"page_name": "Home", "route": "/", "sections": ["hero", "list"], "functions": ["browse"]},
                          {"page_name": "Sign in", "route": "/login", "sections": ["form"], "functions": ["sign in"]}])
        approved = a_plan(screens=[
            {"name": "Home", "route": "/", "purpose": "Browse", "who": ["Visitor"]},
            {"name": "Checkout", "route": "/checkout", "purpose": "Pay", "who": ["Visitor"]},
        ])
        runs = []

        class Session:
            cancelled = False

            def __init__(self, root):
                self.workspace = root
                self.record = root / ".agentforge"

            def run_task(self, request, **kwargs):
                runs.append((request, kwargs))
                pages = self.record / "prototype"
                (pages / "assets" / "app.css").write_text(":root{--accent:#c2410c}", encoding="utf-8")
                (pages / "index.html").write_text(
                    "<!DOCTYPE html><html><head></head><body><h1>Fresh cakes</h1></body></html>", encoding="utf-8")
                (pages / "login.html").write_text(
                    "<!DOCTYPE html><html><head></head><body><form data-sign-in></form>"
                    "<div data-demo-login></div></body></html>", encoding="utf-8")
                return {"plan": "THE SILENT PLAN", "status": "complete", "text": "done"}

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = root / ".agentforge" / "srs" / "handoff"
            handoff.mkdir(parents=True)
            (handoff / "app.md").write_text("FINAL_HANDOFF_DETAIL", encoding="utf-8")
            with patch.object(prototyper, "session_for", return_value=Session(root)), \
                 patch.object(prototyper.design_stage, "approved_customization", return_value={
                     "design_md_path": "prompts/design/themes/terracotta/DESIGN.md",
                     "design_md": "SELECTED_DESIGN_MARKDOWN",
                     "design_md_workspace_path": "design/theme.md",
                     "customizer_prompt": "CUSTOMIZER_EXTRA_PROMPT",
                     "customizer_spec": {"mode": "theme", "theme": {"slug": "terracotta"}},
                 }), \
                 patch.object(srs_document, "document", return_value={"srs_document": doc}), \
                 patch.object(srs_document.plan_stage, "approved_plan", return_value=approved), \
                 patch.object(prototyper.bus, "file_written"), \
                 patch.object(prototyper.bus, "progress"), \
                 patch.object(prototyper.bus, "log"), \
                 patch.object(prototyper.bus, "agent_msg") as messages:
                rows = prototyper._draw_with_agent(
                    "test", {"tokens": {"light": {"accent": "#c2410c"}}}, "Make a realistic prototype",
                    wireframe_source={"/": "<html><head><style>.box{}</style></head><body><h1 class='box'>HOME_WIREFRAME</h1></body></html>",
                                      "/checkout": "<html><body><form>CHECKOUT_WIREFRAME</form></body></html>"})

            prototype = root / ".agentforge" / "prototype"
            self.assertEqual([row["route"] for row in rows], ["/", "/login", "/checkout"])
            self.assertEqual(len(runs), 1)
            request, kwargs = runs[0]
            # the builder's own run: silent plan, then write; no audit pass
            self.assertFalse(kwargs["audit"])
            # only the three inputs: app.md, the wireframes and what Design Customize produced
            for expected in (".agentforge/srs/handoff/app.md", ".agentforge/prototype/input/design-spec.json",
                             "design/theme.md", ".agentforge/prototype/input/wireframes/index.html",
                             ".agentforge/prototype/input/wireframes/checkout.html",
                             "CUSTOMIZER_EXTRA_PROMPT", "Make a realistic prototype"):
                self.assertIn(expected, request)
            self.assertNotIn("SKILL", request)
            self.assertNotIn("premium-frontend", request.lower())
            # sample data, every piece of wireframe content, role-based demo login and no guards are asked for in the prompt
            for expected in ("realistic sample data", "Do not miss a single piece of wireframe content",
                             "**No guards.**", "data-demo-login", "owner@example.com"):
                self.assertIn(expected, request)
            blueprint = (prototype / "input" / "wireframes" / "index.html").read_text(encoding="utf-8")
            self.assertIn("HOME_WIREFRAME", blueprint)
            self.assertNotIn("<style", blueprint)
            # what the agent wrote is kept, only wired to the shared files
            home = (prototype / "index.html").read_text(encoding="utf-8")
            self.assertIn("Fresh cakes", home)
            self.assertIn("assets/flow.js", home)
            self.assertIn("assets/app.css", home)
            # a page the agent never wrote keeps its wireframe instead of stopping the run
            self.assertIn("CHECKOUT_WIREFRAME", (prototype / "checkout.html").read_text(encoding="utf-8"))
            self.assertTrue(any("/checkout" in call.args[1] for call in messages.call_args_list))
            flow = (prototype / "assets" / "flow.js").read_text(encoding="utf-8")
            self.assertIn("owner@example.com", flow)
            self.assertIn("P.loginAs", flow)
            self.assertNotIn("location.replace", flow)
            self.assertEqual((prototype / "plan.md").read_text(encoding="utf-8"), "THE SILENT PLAN")
            saved = json.loads((prototype / "routes.json").read_text(encoding="utf-8"))
            self.assertEqual([row["file"] for row in saved["routes"]], ["index.html", "login.html", "checkout.html"])
            self.assertTrue(json.loads((prototype / "generation.json").read_text(encoding="utf-8"))["complete"])

    def test_each_demo_role_opens_its_own_pages_and_lands_on_the_top_of_its_area(self):
        from prototype_agent import prototype_brief

        def protected(route, roles):
            return {"page_name": route.strip("/").title() or "Home", "route": route,
                    "login_required": True, "allowed_roles": roles}

        doc = {"authentication_requirement": {"login_required": True, "sign_in_route": "/login"},
               "roles": [{"role_key": "shopper", "role_name": "Shopper"},
                         {"role_key": "store_owner", "role_name": "Store Owner"},
                         {"role_key": "guest", "role_name": "Guest"}],
               # an access matrix that names the pages differently from the page list
               "role_access_matrix": [{"role": "Shopper", "allowed_pages": "Storefront and the account area"},
                                      {"role": "store_owner", "allowed_pages": "/admin/staff"}],
               "public_pages": [{"page_name": "Home", "route": "/"}, {"page_name": "Sign in", "route": "/login"}],
               "protected_pages": [protected("/account/orders", ["Shopper"]), protected("/account", ["Shopper"]),
                                   protected("/admin/products", "Store Owner"), protected("/admin", ["store_owner"]),
                                   protected("/admin/staff", [])]}
        routes = [{"route": p["route"], "file": "x.html", "name": p["page_name"]} for p in prototype_brief.pages_of(doc)]
        accounts = {a["role"]: a for a in prototype_brief.draw_accounts(doc, routes, {"journeys": [], "leads_to": {}}, "")}

        self.assertEqual(set(accounts), {"Shopper", "Store Owner"})
        self.assertEqual(accounts["Shopper"]["lands_on"], "/account")
        self.assertEqual(accounts["Store Owner"]["lands_on"], "/admin")
        owner = {p["route"] for p in accounts["Store Owner"]["can_open"]}
        self.assertTrue({"/admin", "/admin/products", "/admin/staff"} <= owner)
        self.assertNotIn("/account", owner)
        self.assertNotIn("/admin", {p["route"] for p in accounts["Shopper"]["can_open"]})

    def test_a_missing_wireframe_does_not_block_the_prototype(self):
        """A route whose wireframe is not drawn is prototyped from the SRS and handoff; the ready ones are honoured."""
        from prototype_agent import prototype as prototyper
        from srs_agent import document as srs_document

        drawn = {}

        def draw(project, spec, direction, *, wireframe_source=None):
            drawn["source"] = wireframe_source
            raise RuntimeError("stop after the draw was started")

        with patch.object(srs_document, "has_document", return_value=True), \
             patch.object(prototyper.design_stage, "current", return_value={"approved": True}), \
             patch.object(prototyper.design_stage, "approved_spec", return_value={"tokens": {}}), \
             patch.object(srs_document, "wireframes", return_value={"pages": [
                 {"route": "/", "has_html": True},
                 {"route": "/checkout", "has_html": False},
             ]}), \
             patch.object(srs_document, "wireframe_html", return_value="<html></html>"), \
             patch.object(prototyper, "_draw_with_agent", draw), \
             patch.object(prototyper, "session_for") as session:
            with self.assertRaisesRegex(RuntimeError, "stop after the draw"):
                prototyper.generate_from_wireframes("test", "direction")
        session.return_value.begin.assert_called_once()
        self.assertEqual(drawn["source"], {"/": "<html></html>"})

    def test_selected_design_md_is_read_only_from_the_chosen_theme(self):
        from prototype_agent import design as design_stage

        path, markdown = design_stage.selected_design_md({
            "theme": {"slug": "terracotta"}})
        self.assertEqual(path, "prompts/design/themes/terracotta/DESIGN.md")
        self.assertIn("Terracotta", markdown)
        self.assertEqual(design_stage.selected_design_md({
            "theme": {"slug": "../../private"}}), ("", ""))

    def test_customizer_selection_and_prompt_survive_design_approval(self):
        from prototype_agent import design as design_stage
        from srs_agent import plan as plan_stage

        prompts_seen = []

        class Session:
            def __init__(self, workspace):
                self.saved = {}
                self.role = ""
                self.workspace = workspace

            def read_record(self, *parts, fallback=None):
                return copy.deepcopy(self.saved.get(parts, fallback))

            def write_record(self, *parts, data):
                self.saved[parts] = copy.deepcopy(data)

            def ask_json(self, prompt):
                prompts_seen.append(prompt)
                return {"theme": "terracotta", "tokens": {"light": {"accent": "#c56a3c"}}}

        selection = {"mode": "theme", "theme": {"slug": "terracotta"}}
        with tempfile.TemporaryDirectory() as folder:
            session = Session(Path(folder))
            with patch.object(design_stage, "session_for", return_value=session), \
                 patch.object(design_stage.store, "require", return_value={"idea": "Hotel"}), \
                 patch.object(design_stage.store, "advance"), \
                 patch.object(plan_stage, "approved_plan", return_value=a_plan()), \
                 patch.object(design_stage.bus, "agent_state"), \
                 patch.object(design_stage.bus, "agent_msg"), \
                 patch.object(design_stage.bus, "log"):
                drafted = design_stage.draft("test", direction="Use calm motion", spec=selection)
                design_stage.approve("test", drafted["version"])
                material = design_stage.approved_customization("test")

        self.assertIn("prompts/design/themes/terracotta/DESIGN.md", prompts_seen[0])
        self.assertIn("Use calm motion", prompts_seen[0])
        self.assertIn("Terracotta", material["design_md"])
        self.assertTrue(material["design_md_workspace_path"])
        self.assertEqual(material["customizer_prompt"], "Use calm motion")
        self.assertEqual(material["customizer_spec"], selection)


class RouteTests(unittest.TestCase):
    def test_session_uses_focused_cloud_usage_when_no_shared_agent_exists(self):
        from server_modules import httpd

        class DormantSession:
            stage = "idle"
            _agent = None

        usage = {"model": "deepseek-v4.1-flash:cloud", "limit": 1_048_576,
                 "used": 5_261, "tools": 0}
        with patch.object(httpd, "_project", return_value="prj_context"), \
             patch.object(httpd, "session_for", return_value=DormantSession()), \
             patch.object(httpd.bus, "latest_memory", return_value=usage):
            status = httpd.project_session({"project": "prj_context"})

        self.assertEqual(status["model"], usage["model"])
        self.assertEqual(status["context"], usage["limit"])
        self.assertEqual(status["used"], usage["used"])

    def test_the_job_endpoints_are_not_shadowed_by_the_catch_alls(self):
        from server_modules import httpd

        # `/srs/(.+)` and `/deploy/(.+)` would otherwise swallow every job poll.
        self.assertEqual(httpd.dispatch("GET", "/srs/jobs/nope")["status"], "unknown")
        self.assertEqual(httpd.dispatch("GET", "/deploy/jobs/nope")["status"], "unknown")
        self.assertEqual(httpd.dispatch("GET", "/jobs/nope")["status"], "unknown")

    def test_a_runtime_answer_always_carries_what_the_reducer_compares(self):
        from server_modules import httpd

        runtime = httpd._runtime_state("prj_x")
        self.assertIn("serverId", runtime)
        self.assertIn("revision", runtime)

    def test_an_unknown_route_is_a_404_not_a_crash(self):
        from server_modules import httpd

        with self.assertRaises(httpd.HttpError) as caught:
            httpd.dispatch("GET", "/nothing/here")
        self.assertEqual(caught.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
