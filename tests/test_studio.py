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
        for name in ("shared/engine", "interview/system", "interview/next-question",
                     "plan/system", "plan/draft", "plan/revise",
                     "srs/system", "srs/generate", "srs/review", "srs/repair",
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
        self.assertIn("wireframe", prompts.skill("srs", "wireframe-generation").lower())
        self.assertTrue({"aws", "vercel", "netlify"} <=
                        {row["slug"] for row in prompts.catalogue("deployment")})
        self.assertGreater(len(prompts.catalogue("design", kind="themes")), 20)

    def test_a_prompt_name_cannot_escape_the_pack(self):
        with self.assertRaises(prompts.MissingPrompt):
            prompts.load("../server_modules/config")


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

    def test_the_first_answer_satisfies_the_catalogue_topic_it_answers(self):
        """Stored under any other key, `app_type` looks unasked and is asked twice."""
        from server_modules import topics
        from srs_agent import interview

        self.assertIn(interview.APP_TYPE_KEY, topics.by_key())
        answers = {interview.APP_TYPE_KEY: {"selected_values": ["booking"],
                                            "value": "booking"}}
        queue = topics.build_queue(answers, "booking",
                                   interview.catalogue().get("types") or {})
        self.assertTrue(queue, "the queue emptied immediately")
        self.assertNotEqual(queue[0]["topic"], "app_type",
                            "app_type was queued again after being answered")
        self.assertEqual(queue[0]["topic"], "app_name")

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


class TopicQueueTests(unittest.TestCase):
    """The catalogue decides what is asked, in what order, and when to stop."""

    @staticmethod
    def _answer(answers, key, value):
        answers[key] = {"selected_values": value if isinstance(value, list) else [value],
                        "value": value}

    def _types(self):
        from srs_agent import interview
        return interview.catalogue().get("types") or {}

    def _walk(self, profile, picks=None):
        from server_modules import topics

        picks = picks or {}
        answers, asked = {}, []
        self._answer(answers, "app_type", profile)
        for _ in range(60):
            queue = topics.build_queue(answers, profile, self._types())
            if not queue:
                break
            item = queue[0]
            asked.append(item["key"])
            self._answer(answers, item["key"], picks.get(item["topic"], "something"))
        return asked

    def test_the_catalogue_carries_every_topic_with_its_intent(self):
        from server_modules import topics

        rows = topics.catalogue().get("topics") or []
        self.assertGreaterEqual(len(rows), 40)
        for row in rows:
            self.assertTrue(row.get("key"))
            self.assertTrue(row.get("intent"), f"{row.get('key')} has no intent")
        self.assertEqual(topics.max_questions(), 25)

    def test_every_app_type_finishes_inside_the_budget(self):
        from server_modules import topics

        for profile in self._types():
            asked = self._walk(profile, {"auth_roles": ["admin", "customer"],
                                         "data_tables": ["bookings", "rooms"],
                                         "account_creation": "open",
                                         "images": "true", "lead_capture": "true"})
            self.assertLessEqual(len(asked), topics.max_questions(),
                                 f"{profile} asks {len(asked)} questions")
            self.assertGreater(len(asked), 5, f"{profile} asks almost nothing")

    def test_a_repeating_topic_asks_once_per_subject(self):
        asked = self._walk("booking", {"auth_roles": ["admin", "customer"],
                                       "data_tables": ["bookings", "rooms"],
                                       "account_creation": "open"})
        self.assertIn("role_functions:admin", asked)
        self.assertIn("role_functions:customer", asked)
        self.assertIn("table_entities:bookings", asked)
        self.assertIn("table_entities:rooms", asked)

    def test_a_conditional_topic_stays_shut_until_its_condition_holds(self):
        # `signup_role` exists only where the public may sign themselves up.
        opened = self._walk("saas", {"auth_roles": ["admin"], "data_tables": ["items"],
                                     "account_creation": "open"})
        closed = self._walk("saas", {"auth_roles": ["admin"], "data_tables": ["items"],
                                     "account_creation": "admin_created"})
        self.assertIn("signup_role", opened)
        self.assertNotIn("signup_role", closed)

    def test_a_landing_page_is_never_asked_about_records_or_roles(self):
        asked = self._walk("landing", {"lead_capture": "true"})
        for unwanted in ("data_tables", "auth_roles", "table_entities"):
            self.assertFalse(any(k.startswith(unwanted) for k in asked),
                             f"a landing page was asked about {unwanted}")
        self.assertIn("sections", asked)
        self.assertIn("cta", asked)

    def test_a_tool_is_asked_about_its_job_not_about_a_storefront(self):
        asked = self._walk("utility")
        self.assertIn("tool_job", asked)
        self.assertIn("tool_inputs", asked)
        self.assertFalse(any(k.startswith("store_") for k in asked))


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
        self.assertEqual(completeness.check(a_document(), a_plan(), pages), [])

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
        self.assertTrue(completeness.diagram_coverage(doc))

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

    def test_a_diagram_skipped_while_its_evidence_is_in_the_document(self):
        doc = a_document()
        doc["diagrams"][0]["applicable"] = False   # the ERD, with a table present
        gaps = completeness.diagram_coverage(doc)
        self.assertTrue(any("erd" in gap for gap in gaps))

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

    def test_a_prototype_link_that_goes_nowhere(self):
        routes = [{"route": "/", "file": "index.html", "name": "Home"}]
        pages = {"index.html": '<a href="_basket.html">Basket</a>' + "x" * 2000}
        gaps = completeness.prototype_coverage(a_document(), routes, pages)
        self.assertTrue(any("_basket.html" in gap for gap in gaps))

    def test_a_prototype_that_ignored_the_approved_tokens(self):
        routes = [{"route": "/", "file": "index.html", "name": "Home"}]
        pages = {"index.html": "x" * 3000, "assets/app.css": "body { color: red }"}
        gaps = completeness.prototype_coverage(
            a_document(), routes, pages, {"light": {"accent": "#c2410c", "bg": "#fffaf5"}})
        self.assertTrue(any("design tokens" in gap for gap in gaps))


class EventStreamTests(unittest.TestCase):
    def test_the_durable_events_survive_a_restart(self):
        from server_modules import bus, config

        with tempfile.TemporaryDirectory() as directory:
            original = config.WORKSPACES
            config.WORKSPACES = Path(directory)
            try:
                bus.forget("prj_test")
                bus.log("prj_test", "INFO", "started")
                bus.agent_msg("prj_test", "the plan is ready")
                bus.stream("prj_test", "a token")        # live only
                bus.done("prj_test", "finished")

                # Drop the memory the way a restart does, and read it back.
                bus.forget("prj_test")
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
                bus.forget("prj_test")

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
                bus.forget("prj_shape")

        by_type = {event["type"]: event for event in seen}
        self.assertEqual(by_type["phase"]["title"], "Writing")
        self.assertEqual(by_type["run_state"]["status"], "running")
        self.assertEqual(by_type["file"]["old_content"], "old")
        for event in seen:
            self.assertIn("event_id", event)
            self.assertIn("at", event)
            self.assertIn("project", event)


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

            def execute_plan(self, _request, _plan):
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

                def execute_plan(self, request, plan):
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

            def draw(_session, _project, _doc, page, _docs, _request, system):
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
    def test_every_approved_route_uses_its_html_and_handoff(self):
        from prototype_agent import prototype as prototyper
        from srs_agent import document as srs_document

        doc = a_document()
        approved = a_plan(screens=[
            {"name": "Home", "route": "/", "purpose": "Browse", "who": ["Visitor"]},
            {"name": "Checkout", "route": "/checkout", "purpose": "Pay", "who": ["Visitor"]},
        ])
        captured = []

        class Session:
            cancelled = False

            def __init__(self, root):
                self.record = root / ".agentforge"

        def complete_html(_system, user, **_kwargs):
            captured.append(json.loads(user))
            return "<!DOCTYPE html><html><style>body{color:red}</style><body>Ready</body></html>"

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(prototyper, "session_for", return_value=Session(Path(folder))), \
             patch.object(prototyper.design_stage, "approved_customization", return_value={
                 "design_md_path": "prompts/design/themes/terracotta/DESIGN.md",
                 "design_md": "SELECTED_DESIGN_MARKDOWN",
                 "customizer_prompt": "CUSTOMIZER_EXTRA_PROMPT",
                 "customizer_spec": {"mode": "theme", "theme": {"slug": "terracotta"}},
             }), \
             patch.object(srs_document, "document", return_value={"srs_document": doc}), \
             patch.object(srs_document.plan_stage, "approved_plan", return_value=approved), \
             patch.object(srs_document, "handoff_docs", return_value={"app.md": "FINAL_HANDOFF_DETAIL"}), \
             patch.object(prototyper.llm, "complete_html", side_effect=complete_html), \
             patch.object(prototyper.llm, "in_lanes", side_effect=lambda items, fn, **_kw: [fn(item) for item in items]), \
             patch.object(prototyper.bus, "file_written"), \
             patch.object(prototyper.bus, "progress"), \
             patch.object(prototyper.bus, "agent_msg") as messages:
            rows = prototyper._draw_focused(
                "test", {"tokens": {}}, "Make a realistic prototype",
                wireframe_source={"/": "HOME_WIREFRAME", "/checkout": "CHECKOUT_WIREFRAME"},
                approved_execution_plan="APPROVED_EXECUTION_PLAN")

        self.assertEqual([row["route"] for row in rows], ["/", "/checkout"])
        self.assertEqual([call.kwargs.get("title") for call in messages.call_args_list],
                         ["Prototype screen", "Prototype screen"])
        self.assertEqual([item["source_wireframe_html"] for item in captured],
                         ["HOME_WIREFRAME", "CHECKOUT_WIREFRAME"])
        self.assertTrue(all(item["srs_handoff_files"]["app.md"] == "FINAL_HANDOFF_DETAIL"
                            and item["approved_prototype_plan"] == "APPROVED_EXECUTION_PLAN"
                            and item["selected_design_md"] == "SELECTED_DESIGN_MARKDOWN"
                            and item["customizer_prompt"] == "CUSTOMIZER_EXTRA_PROMPT"
                            for item in captured))

    def test_missing_wireframes_block_approval_before_starting_a_run(self):
        from prototype_agent import prototype as prototyper
        from srs_agent import document as srs_document

        with patch.object(srs_document, "has_document", return_value=True), \
             patch.object(prototyper.design_stage, "current", return_value={"approved": True}), \
             patch.object(srs_document, "wireframes", return_value={"pages": [
                 {"route": "/", "has_html": True},
                 {"route": "/checkout", "has_html": False},
             ]}), \
             patch.object(prototyper, "session_for") as session:
            with self.assertRaisesRegex(ValueError, "/checkout"):
                prototyper.generate_from_wireframes("test", "direction")
            session.return_value.begin.assert_not_called()

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
