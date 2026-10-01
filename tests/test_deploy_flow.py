"""A deployment is planned first, asked about, approved, carried out and checked from the outside."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

import httpx  # noqa: E402
from deploy_agent import deploy  # noqa: E402
from server_modules import bus, changes, config, prompts  # noqa: E402
from support import forget_project  # noqa: E402

PROJECT = "prj_deploy_flow_test"
SKILLS = deploy.SKILLS_DIR


class FakeAgent:
    def set_mode(self, mode):
        pass


class FakeSession:
    """Stands in for the model and the engine. `replies` answer the planner; `runs` are what the agent does."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.lock = threading.RLock()
        self.replies: list = []
        self.prompts: list[str] = []
        self.executed: list[str] = []
        self.runs: list = []            # callables(request) -> result dict, one per execute_approved
        self.finished: list[str] = []
        self.failed: list[str] = []
        self.stages: list[str] = []
        self.notes: list[str] = []
        self.reads: list[str] = []      # skill pages "read" by the planner before it answers

    def begin(self, stage, role=None, run_id=""):
        self.stages.append(stage)

    def finish(self, text=""):
        self.finished.append(text)

    def fail(self, text):
        self.failed.append(text)

    def note(self, text, role=""):
        self.notes.append(text)

    def agent(self, model=""):
        return FakeAgent()

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        if not path.is_file():
            return fallback
        return json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else path.read_text()

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if path.suffix == ".json" else str(data), encoding="utf-8")
        return path

    def ask_json(self, prompt, validator=None, model="", attempts=3):
        self.prompts.append(prompt)
        for name in self.reads:
            bus.file_read(PROJECT, name, "page")
        reply = self.replies.pop(0)
        return validator(reply) if validator else reply

    def execute_approved(self, request, plan, model=""):
        self.executed.append(request)
        return self.runs.pop(0)(request)

    def cancel(self):
        pass


def plan(**over) -> dict:
    base = {"kind": "plan", "title": "Deploy to Vercel", "summary": "Live on Vercel with a repository.",
            "requirements": ["Vercel signed in"],
            "impact": [{"stage": "GitHub repository", "affected": True, "why": "the code is published"}],
            "steps": [{"id": "repo", "stage": "Repository", "title": "Publish the repository",
                       "commands": ["gh repo create"]},
                      {"id": "release", "stage": "Vercel", "title": "Release", "commands": ["vercel deploy --prod"]}],
            "assumptions": ["private repository"], "risks": [], "verification": ["home page answers 200"],
            "rollback": ["vercel rollback"], "cost": ["free"]}
    base.update(over)
    return base


class DeployFlowCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / ".agentforge").mkdir()
        (self.workspace / "package.json").write_text("{}")
        self.session = FakeSession(self.workspace)
        self.events: list[dict] = []
        bus._pending_decisions.clear()
        changes._threads.clear()
        for patch in (mock.patch.object(changes, "session_for", lambda project: self.session),
                      mock.patch.object(deploy, "session_for", lambda project: self.session),
                      mock.patch.object(config, "record_dir", lambda project: self.workspace / ".agentforge"),
                      mock.patch.object(deploy, "machine_facts", lambda *args: "FACTS"),
                      mock.patch.object(deploy, "_require_cli", lambda target: None),
                      mock.patch.object(deploy.store, "get", lambda project: {"language": "English"}),
                      mock.patch.object(deploy.store, "update", lambda *a, **k: None),
                      mock.patch.object(deploy.store, "advance", lambda *a, **k: None)):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(bus.subscribe(self.events.append))
        self.addCleanup(forget_project, PROJECT)
        self.session.reads = [f"{SKILLS}/{slug}/SKILL.md" for slug in ("core", "vercel", "stack-nextjs-supabase")]

    def settle(self, change_id):
        thread = changes._threads.get(change_id)
        if thread:
            thread.join(15)

    def start(self, target="vercel", **kw):
        result = deploy.start(PROJECT, target)
        self.settle(result["change"])
        return result

    def of_type(self, kind):
        return [e for e in self.events if e.get("type") == kind]

    def live_run(self, request):
        """What a good agent leaves behind: the record says LIVE at a public address."""
        run = deploy.run_state(PROJECT)
        run.update(state="LIVE", url="https://app.example.com",
                   checks=[{"name": "health", "url": "https://app.example.com/health", "expect": "200"}])
        self.session.write_record(*deploy.RUN, data=run)
        return {"status": "complete", "text": "Live at https://app.example.com", "rounds": 2}


SUPABASE_STACKS = ("nextjs-supabase", "vite-supabase", "remix-supabase")
MONGO_STACKS = ("nextjs-mongo", "vite-mongo", "mern-microservices")
ALL_STACKS = SUPABASE_STACKS + MONGO_STACKS
# vite-mongo's Express server and mern-microservices' gateway/services need a real, long-running
# process - never a static or serverless-functions-only target.
RESTRICTED_STACKS = ("vite-mongo", "mern-microservices")


class StackTests(DeployFlowCase):
    def test_every_target_has_its_pages_and_every_stack_a_page_of_its_own(self):
        for target in deploy.SKILLS_FOR:
            for stack in ALL_STACKS:
                with mock.patch.object(deploy, "stack_of", lambda project, s=stack: s):
                    paths = deploy.stage_skills(PROJECT, target)
                    self.assertEqual(paths[0], f"{SKILLS}/core/SKILL.md")
                    self.assertIn(f"{SKILLS}/{deploy.stack_info(stack)['skill']}/SKILL.md", paths)
                    for path in paths:
                        self.assertGreater(len((self.workspace / path).read_text(encoding="utf-8")), 400, path)

    def test_every_supabase_and_nextjs_mongo_stack_can_go_to_every_target(self):
        # These render their own server-rendered or serverless routes (or, for the Supabase SPA, need
        # no server at all) - nothing about them needs a fixed address or a long-running process only
        # some targets provide, so every one of them can go anywhere.
        for stack in (*SUPABASE_STACKS, "nextjs-mongo"):
            self.assertEqual(set(deploy.allowed_targets(stack)), set(deploy.SKILLS_FOR))

    def test_server_backed_mongo_stacks_are_restricted_to_real_server_hosting(self):
        for stack in RESTRICTED_STACKS:
            allowed = set(deploy.allowed_targets(stack))
            self.assertEqual(allowed, {"aws_ec2", "aws_ecs", "azure"} & set(deploy.SKILLS_FOR))
            self.assertNotIn("vercel", allowed)
            self.assertNotIn("netlify", allowed)
            self.assertNotIn("github", allowed)

    def test_the_microservices_stack_page_says_how_to_deploy_separate_instances(self):
        page = " ".join(prompts.skill("deployment", "stack-mern-microservices").split())
        for words in ("cloud map", "one fargate task definition per package", "only the gateway"):
            self.assertIn(words.lower(), page.lower())

    def test_every_skill_page_carries_the_questions_the_customer_may_decide(self):
        for slug in ("core", "vercel", "netlify", "aws", "aws-ec2", "aws-ecs", "azure", "github",
                     "stack-nextjs-supabase", "stack-remix-supabase", "stack-vite-supabase",
                     "stack-nextjs-mongo", "stack-vite-mongo", "stack-mern-microservices"):
            self.assertRegex(prompts.skill("deployment", slug), r"(?i)questions? to ask|how to ask", slug)


class CliAvailabilityTests(unittest.TestCase):
    """The target's CLI is checked before anything is planned, not discovered
    later as a raw 'command not found' deep inside a run."""

    def test_a_missing_target_cli_is_refused_before_any_planning_starts(self):
        with mock.patch.object(deploy.cli_signin.SIGNINS, "available",
                               lambda only="", fresh=False:
                               {"vercel": {"installed": False, "title": "Vercel", "install": "npm i -g vercel"}}):
            with self.assertRaisesRegex(ValueError, r"Vercel is not installed.*npm i -g vercel"):
                deploy._require_cli("vercel")

    def test_an_installed_target_cli_is_not_blocked(self):
        with mock.patch.object(deploy.cli_signin.SIGNINS, "available",
                               lambda only="", fresh=False: {"vercel": {"installed": True}}):
            deploy._require_cli("vercel")  # does not raise


class PlanFirstTests(DeployFlowCase):
    def test_pressing_deploy_plans_and_deploys_nothing(self):
        self.session.replies = [plan()]
        result = self.start()
        self.assertEqual(self.session.executed, [])
        self.assertEqual(deploy.run_state(PROJECT)["state"], "AWAITING_APPROVAL")
        card = self.of_type("change")[-1]
        self.assertEqual((card["status"], card["flow"], card["target"]), ("proposed", "deploy", "vercel"))
        self.assertEqual(deploy.plan_of(PROJECT)["steps"][0]["id"], "repo")
        self.assertEqual(deploy.results(PROJECT)["change"]["id"], result["change"])

    def test_the_planning_prompt_is_the_packs_and_names_the_skill_pages_and_the_stack(self):
        self.session.replies = [plan()]
        self.start()
        prompt = " ".join(self.session.prompts[0].split())
        self.assertIn("The customer chose **Vercel**", prompt)
        for path in (f"{SKILLS}/core/SKILL.md", f"{SKILLS}/vercel/SKILL.md", f"{SKILLS}/stack-nextjs-supabase/SKILL.md"):
            self.assertIn(path, prompt)
        self.assertIn("Next.js + Supabase", prompt)
        self.assertIn("FACTS", prompt)
        self.assertIn("Collect all that apply from the pages you read", prompt)
        self.assertIn("prompts to think with, not a script", prompt)          # the lists are not a fixed set of questions
        self.assertIn("this must work for any project", prompt.lower())
        self.assertNotIn("{{", prompt)

    def test_the_planner_that_did_not_read_the_pages_is_sent_back_to_read_them(self):
        check = deploy.validator(PROJECT, {"target": "vercel", "created": 0})
        self.session.reads = []
        with self.assertRaisesRegex(ValueError, "read the skill pages"):
            check(plan(), True)
        for slug in ("core", "vercel", "stack-nextjs-supabase"):
            bus.file_read(PROJECT, f"{SKILLS}/{slug}/SKILL.md", "page")
        checked = check(plan(), True)
        self.assertEqual(len(checked["skills"]), 3)              # what it really read, not what it claims

    def test_a_plan_needs_live_checks_and_a_way_back_and_step_ids_are_unique(self):
        for slug in ("core", "vercel", "stack-nextjs-supabase"):
            bus.file_read(PROJECT, f"{SKILLS}/{slug}/SKILL.md", "page")
        check = deploy.validator(PROJECT, {"target": "vercel", "created": 0})
        with self.assertRaisesRegex(ValueError, "verification"):
            check(plan(verification=[]), True)
        with self.assertRaisesRegex(ValueError, "rollback"):
            check(plan(rollback=[]), True)
        checked = check(plan(steps=[{"title": "Same"}, {"title": "Same"}]), True)
        self.assertEqual([s["id"] for s in checked["steps"]], ["same", "same_2"])

    def test_the_planner_asks_many_questions_and_the_answer_reaches_the_next_plan(self):
        self.assertGreaterEqual(deploy.MAX_QUESTIONS, 8)
        self.session.replies = [{"kind": "question", "question": "How many instances?", "why": "cost",
                                 "options": [{"label": "One", "hint": "cheapest"}, "One each"],
                                 "assumption": "use one"}, plan()]
        result = self.start()
        self.assertEqual(deploy.run_state(PROJECT)["state"], "NEEDS_INPUT")
        ask = next(e for e in self.events if e.get("type") == "approval")
        self.assertEqual((ask["kind"], ask["change_id"]), ("question", result["change"]))
        changes.answer(PROJECT, result["change"], "One")
        self.settle(result["change"])
        self.assertIn("How many instances?", self.session.prompts[1])
        self.assertEqual(deploy.run_state(PROJECT)["state"], "AWAITING_APPROVAL")

    def test_typing_in_the_chat_revises_the_deployment_plan(self):
        self.session.replies = [plan(), plan(title="Deploy to Vercel, public repo")]
        result = self.start()
        changes.submit(PROJECT, "make the repository public")
        self.settle(result["change"])
        self.assertEqual(deploy.plan_of(PROJECT)["title"], "Deploy to Vercel, public repo")
        self.assertIn("make the repository public", self.session.prompts[1])

    def test_a_second_deploy_while_one_is_open_is_refused(self):
        self.session.replies = [plan()]
        self.start()
        with self.assertRaisesRegex(ValueError, "still open"):
            deploy.start(PROJECT, "vercel")

    def test_cancelling_the_plan_ends_the_run_record(self):
        self.session.replies = [plan()]
        result = self.start()
        changes.decide(PROJECT, result["change"], "cancel")
        self.assertEqual(deploy.run_state(PROJECT)["state"], "CANCELLED")
        self.assertIsNone(changes.active(PROJECT))


class CarryingOutTests(DeployFlowCase):
    def approve(self, result):
        changes.decide(PROJECT, result["change"], "approve")
        self.settle(result["change"])

    def test_an_approved_plan_is_carried_out_then_checked_from_outside(self):
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = [self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered) as get:
            self.approve(result)
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")
        self.assertEqual({call.args[0] for call in get.call_args_list},
                         {"https://app.example.com", "https://app.example.com/health"})
        self.assertTrue(any(row["kind"] == "studio re-check" for row in deploy.run_state(PROJECT)["evidence"]))
        self.assertEqual(changes.active(PROJECT), None)
        self.assertEqual(self.session.stages[-1], deploy.STAGE_RUN)
        request = self.session.executed[0]
        self.assertIn("Publish the repository", request)          # the approved plan
        self.assertIn(f"{SKILLS}/vercel/SKILL.md", request)
        self.assertNotIn("{{", request)

    def test_an_address_that_does_not_hold_goes_back_to_the_agent_and_then_holds(self):
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = [self.live_run, self.live_run]
        broken = httpx.Response(502, request=httpx.Request("GET", "https://app.example.com"))
        fine = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", side_effect=[broken, broken, fine, fine]):
            self.approve(result)
        self.assertEqual(len(self.session.executed), 2)
        self.assertIn("did not hold", self.session.executed[1])
        self.assertIn("answered 502", self.session.executed[1])
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")

    def test_an_address_that_never_holds_ends_failed_not_live(self):
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = [self.live_run] * (deploy.REPAIR_ROUNDS + 1)
        broken = httpx.Response(500, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=broken):
            self.approve(result)
        self.assertEqual(deploy.run_state(PROJECT)["state"], "FAILED")
        self.assertIn("did not hold", deploy.run_state(PROJECT)["error"])
        self.assertEqual(len(self.session.executed), deploy.REPAIR_ROUNDS + 1)

    def test_a_run_that_stops_on_a_question_asks_it_and_resumes_with_the_answer(self):
        self.session.replies = [plan()]
        result = self.start()

        def blocked(request):
            self.session.write_record(*deploy.QUESTION, data={
                "question": "Which database?", "why": "no reachable database", "options": [{"label": "Use Atlas"}],
                "assumption": "skip it"})
            return {"status": "blocked", "text": "need a database", "rounds": 1}

        self.session.runs = [blocked, self.live_run]
        self.approve(result)
        self.assertEqual(changes.active(PROJECT)["status"], "asking")
        self.assertEqual(deploy.run_state(PROJECT)["state"], "NEEDS_INPUT")
        ask = [e for e in self.events if e.get("type") == "approval"][-1]
        self.assertEqual(ask["question"], "Which database?")

        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            changes.submit(PROJECT, "Use Atlas")               # typing in the chat answers it
            self.settle(result["change"])
        self.assertEqual(len(self.session.executed), 2)
        self.assertIn("Which database?", self.session.executed[1])
        self.assertIn("Use Atlas", self.session.executed[1])
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")

    def test_a_run_that_records_no_result_is_failed_with_the_reason(self):
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = [lambda request: {"status": "complete", "text": "done", "rounds": 1}]
        self.approve(result)
        self.assertEqual(deploy.run_state(PROJECT)["state"], "FAILED")
        self.assertIn("did not record", deploy.run_state(PROJECT)["error"])


class ResumeTests(DeployFlowCase):
    def interrupted(self):
        """A run that was carried out part of the way and then stopped (the server went away)."""
        self.session.replies = [plan()]
        result = self.start()

        def stopped(request):
            line = json.dumps({"stage": "repo", "status": "complete", "message": "9 commits"})
            (self.workspace / ".agentforge/deploy/events.jsonl").write_text(line + chr(10), encoding="utf-8")
            raise RuntimeError("the server stopped")

        self.session.runs = [stopped]
        changes.decide(PROJECT, result["change"], "approve")
        self.settle(result["change"])
        return result

    def test_an_interrupted_run_can_be_resumed_on_the_same_plan_and_carries_on(self):
        result = self.interrupted()
        self.assertEqual(deploy.run_state(PROJECT)["state"], "FAILED")
        retry = deploy.results(PROJECT)["retry"]
        self.assertEqual(retry["change"], result["change"])

        self.session.runs = [self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            self.assertTrue(changes.decide(PROJECT, result["change"], "retry")["ok"])
            self.settle(result["change"])
        again = self.session.executed[-1]
        self.assertIn("Continue from where you stopped", again)
        self.assertIn("interrupted", again)
        self.assertIn("Publish the repository", again)                # the same approved plan
        self.assertEqual(len(self.session.prompts), 1)                # nothing was planned again
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")
        self.assertIsNone(deploy.results(PROJECT)["retry"])

    def test_a_later_attempt_that_failed_to_plan_does_not_lose_the_run_that_can_be_resumed(self):
        first = self.interrupted()
        self.session.replies = []                                # the next Deploy fails while planning
        second = deploy.start(PROJECT, "vercel")
        self.settle(second["change"])
        self.assertNotEqual(deploy.run_state(PROJECT)["run_id"], first["run_id"])
        self.assertEqual(deploy.results(PROJECT)["retry"]["change"], first["change"])

        self.session.runs = [self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            changes.decide(PROJECT, first["change"], "retry")
            self.settle(first["change"])
        self.assertEqual(deploy.run_state(PROJECT)["run_id"], first["run_id"])     # its own record came back
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")
        self.assertIn("9 commits", " ".join(row.get("message", "") for row in deploy.events(PROJECT)))
        self.assertIsNone(deploy.results(PROJECT)["retry"])

    def test_a_finished_deployment_supersedes_an_older_one_that_stopped(self):
        first = self.interrupted()
        self.session.replies = [plan()]
        newer = self.start()
        self.session.runs = [self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            changes.decide(PROJECT, newer["change"], "approve")
            self.settle(newer["change"])
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")
        self.assertIsNone(deploy.results(PROJECT)["retry"])
        self.assertNotEqual(newer["change"], first["change"])

    def test_a_plan_that_never_ran_or_a_busy_project_has_nothing_to_resume(self):
        self.session.replies = [plan()]
        result = self.start()                                         # only a plan waiting for approval
        self.assertFalse(changes.decide(PROJECT, result["change"], "retry")["ok"])
        self.assertIsNone(deploy.results(PROJECT)["retry"])


class ProbeTests(unittest.TestCase):
    def test_expected_statuses(self):
        self.assertTrue(deploy._expected(200, "200"))
        self.assertTrue(deploy._expected(302, None))
        self.assertTrue(deploy._expected(404, "2xx|404"))
        self.assertTrue(deploy._expected(401, "401, 403"))
        self.assertFalse(deploy._expected(500, None))
        self.assertFalse(deploy._expected(200, "401"))

    def test_only_a_public_https_address_is_called(self):
        self.assertEqual(deploy._public_https("https://app.example.com"), "")
        for url in ("http://app.example.com", "https://localhost:3000", "https://127.0.0.1", "https://10.0.0.5/x",
                    "https://db.internal"):
            self.assertNotEqual(deploy._public_https(url), "", url)

    def test_a_certificate_or_network_failure_is_a_failed_check(self):
        run = {"url": "https://app.example.com", "checks": []}
        with mock.patch.object(deploy.httpx, "get", side_effect=httpx.ConnectError("certificate verify failed")):
            failures, evidence = deploy.probe(run)
        self.assertEqual(len(failures), 1)
        self.assertIn("did not answer", failures[0])
        self.assertEqual(evidence, [])


class QuestionWordingTests(unittest.TestCase):
    def test_an_assumption_that_repeats_the_cards_own_words_is_not_shown_twice(self):
        for said, shown in (("No answer: it will deploy without a database", "deploy without a database"),
                            ("deploy it", "deploy it"), ("", "")):
            checked = changes.check_question({"question": "Which?", "assumption": said}, True)
            self.assertEqual(checked["assumption"], shown)


if __name__ == "__main__":
    unittest.main()
