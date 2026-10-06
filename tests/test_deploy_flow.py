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
        self.fresh: list[str] = []      # the notes a deployment started from a small conversation with

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

    def shed_history(self, note="", keep_tokens=0):
        self.fresh.append(note)
        return 0

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
                      mock.patch.object(deploy, "_pause", lambda seconds: None),
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
MONGO_STACKS = ("nextjs-mongo", "vite-mongo", "remix-mongo", "mern-microservices")
# The same MongoDB applications without Supabase (uploaded files in MongoDB itself).
MONGO_ONLY_STACKS = ("nextjs-mongo-only", "vite-mongo-only", "remix-mongo-only", "mern-microservices-only")
ALL_STACKS = SUPABASE_STACKS + MONGO_STACKS + MONGO_ONLY_STACKS
# vite-mongo's Express server, remix-mongo's server and mern-microservices' gateway/services need a real,
# long-running process - never a static or serverless-functions-only target.
RESTRICTED_STACKS = ("vite-mongo", "remix-mongo", "mern-microservices",
                     "vite-mongo-only", "remix-mongo-only", "mern-microservices-only")


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
        for stack in (*SUPABASE_STACKS, "nextjs-mongo", "nextjs-mongo-only"):
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
                     "stack-nextjs-mongo", "stack-vite-mongo", "stack-remix-mongo", "stack-mern-microservices"):
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

    def test_planning_and_carrying_out_each_start_from_a_small_conversation(self):
        self.session.replies = [plan()]
        result = self.start()
        self.assertEqual(self.session.fresh, [deploy.FRESH_NOTE])               # the plan
        self.session.runs = [self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            changes.decide(PROJECT, result["change"], "approve")
            self.settle(result["change"])
        self.assertEqual(self.session.fresh, [deploy.FRESH_NOTE, deploy.FRESH_NOTE])   # and the run

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

    def test_the_planner_may_ask_only_a_few_questions_and_the_answer_reaches_the_next_plan(self):
        self.assertEqual(deploy.MAX_QUESTIONS, 3)                  # a deployment is fast: the rest are defaults in the plan
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
        broken = httpx.Response(500, request=httpx.Request("GET", "https://app.example.com"))
        fine = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", side_effect=[broken, broken, fine, fine]):
            self.approve(result)
        self.assertEqual(len(self.session.executed), 2)
        self.assertIn("did not hold", self.session.executed[1])
        self.assertIn("answered 500", self.session.executed[1])
        self.assertIn("one repair round", self.session.executed[1])
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
        with mock.patch.object(deploy, "_pause", lambda seconds: None), \
                mock.patch.object(deploy.httpx, "get", side_effect=httpx.ConnectError("certificate verify failed")):
            failures, evidence = deploy.probe(run)
        self.assertEqual(len(failures), 1)
        self.assertIn("did not answer", failures[0])
        self.assertEqual(evidence, [])

    def response(self, status):
        return httpx.Response(status, request=httpx.Request("GET", "https://app.example.com"))

    def test_a_host_that_is_only_waking_up_is_waited_for_not_handed_to_the_agent(self):
        run = {"url": "https://app.example.com", "checks": []}
        waits: list[float] = []
        with mock.patch.object(deploy, "_pause", waits.append), \
                mock.patch.object(deploy.httpx, "get", side_effect=[self.response(503), self.response(502),
                                                                       self.response(200)]) as get:
            failures, evidence = deploy.probe(run)
        self.assertEqual(failures, [])
        self.assertEqual(get.call_count, 3)
        self.assertEqual(waits, list(deploy.PROBE_PATIENCE))
        self.assertIn("-> 200", evidence[0]["detail"])

    def test_a_connection_that_is_refused_at_first_is_tried_again(self):
        run = {"url": "https://app.example.com", "checks": []}
        with mock.patch.object(deploy, "_pause", lambda seconds: None), \
                mock.patch.object(deploy.httpx, "get", side_effect=[httpx.ConnectTimeout("slow"), self.response(200)]):
            failures, _evidence = deploy.probe(run)
        self.assertEqual(failures, [])

    def test_a_gateway_error_that_never_clears_is_a_failure_after_the_waits_and_a_real_error_is_not_waited_for(self):
        run = {"url": "https://app.example.com", "checks": []}
        with mock.patch.object(deploy, "_pause", lambda seconds: None), \
                mock.patch.object(deploy.httpx, "get", return_value=self.response(502)) as get:
            failures, _evidence = deploy.probe(run)
        self.assertEqual(get.call_count, len(deploy.PROBE_PATIENCE) + 1)
        self.assertIn("answered 502", failures[0])
        with mock.patch.object(deploy.httpx, "get", return_value=self.response(500)) as get:
            deploy.probe(run)
        self.assertEqual(get.call_count, 1)                       # a 500 is the application's own answer: no waiting
        with mock.patch.object(deploy.httpx, "get", return_value=self.response(404)) as get:
            deploy.probe(run)
        self.assertEqual(get.call_count, 1)


class QuestionWordingTests(unittest.TestCase):
    def test_an_assumption_that_repeats_the_cards_own_words_is_not_shown_twice(self):
        for said, shown in (("No answer: it will deploy without a database", "deploy without a database"),
                            ("deploy it", "deploy it"), ("", "")):
            checked = changes.check_question({"question": "Which?", "assumption": said}, True)
            self.assertEqual(checked["assumption"], shown)


class FastDeploymentTests(unittest.TestCase):
    """A deployment is a delivery, not another test run: no re-testing, one pass, a smoke proof, one repair round."""

    TARGETS = ("vercel", "netlify", "github", "aws", "aws-ec2", "aws-ecs", "azure")
    STACKS = ("stack-nextjs-supabase", "stack-nextjs-mongo", "stack-remix-supabase", "stack-remix-mongo",
              "stack-vite-supabase", "stack-vite-mongo", "stack-mern-microservices")

    def page(self, slug):
        return prompts.skill("deployment", slug)

    def test_the_shared_page_opens_with_the_speed_contract(self):
        core = self.page("core")
        self.assertLess(core.index("## 0. The speed contract"), core.index("## 1. Read before anything else"))
        for rule in ("Do not test again", "Build once, where it is cheapest", "Decide, do not interview", "One pass",
                     "A smoke proof, not a test campaign", "One repair round", "A wait has a budget", "Reuse"):
            self.assertIn(rule, core)
        self.assertIn("at most six read-only requests", core)
        self.assertIn("at most three\n   questions in total", core.replace("Ask at most three questions", "at most three\n   questions"))
        self.assertIn("Time targets", core)

    def test_nothing_in_the_pages_still_asks_for_a_test_gate_a_journey_or_a_loop(self):
        for slug in ("core", "deployment-repair", *self.TARGETS, *self.STACKS):
            page = self.page(slug)
            for old in ("Local gate", "write/read-back", "full round trip", "fresh clone builds", "Stop after three",
                        "run every check again from the start", "Run the local gate"):
                self.assertNotIn(old, page, f"{slug}: {old}")

    def test_every_target_gives_its_fast_path_before_the_reference_sections(self):
        for slug in self.TARGETS:
            page = self.page(slug)
            self.assertEqual(page.count("## Fast path"), 1, slug)
            self.assertLess(page.index("## Fast path"), page.index("## 1."), slug)
            if slug != "aws":                                                      # (the shared page lists no skips)
                self.assertIn("Skip:", page.split("## 1.")[0], slug)              # what is left out is said
            self.assertIn("Take these as defaults, not as questions", page, slug)

    def test_the_fast_paths_name_the_commands_that_make_each_target_quick(self):
        for slug, words in {"vercel": ("vercel deploy --prod --yes", "No local install, test or build"),
                            "netlify": ("netlify deploy --build --prod", "No draft deploy first"),
                            "github": ("gh repo create", "git ls-remote origin main"),
                            "aws": ("create-stack", "One stack that holds everything", "wait stack-create-complete"),
                            "aws-ec2": ("create-stack", "While it creates", "smoke proof"),
                            "aws-ecs": ("desired count 0", "While it creates", "ECS bills by the hour"),
                            "azure": ("az webapp deploy", "cold start")}.items():
            page = " ".join(self.page(slug).split("## 1.")[0].split())
            for word in words:
                self.assertIn(word, page, f"{slug}: {word}")

    def test_the_stack_pages_say_live_means_the_smoke_proof(self):
        for slug in self.STACKS:
            page = self.page(slug)
            self.assertIn("Within the smoke proof of `core` section 10", page, slug)
            self.assertIn("no sign-in, no write, no test data", page, slug)

    def test_the_repair_is_one_round_and_the_studio_hands_a_failure_back_once(self):
        self.assertEqual(deploy.REPAIR_ROUNDS, 1)
        repair = self.page("deployment-repair")
        self.assertIn("## The round (there is one)", repair)
        self.assertIn("Never try a third\n   time", repair)
        failed = prompts.load("deployment/verify-failed", failures="- x").strip()
        self.assertIn("one repair round", failed)
        self.assertIn("there is no further round", failed)

    def test_the_planning_and_run_prompts_ask_for_a_delivery_not_a_test_run(self):
        plan_prompt = prompts.load("deployment/plan", target_label="Vercel", skills="S", machine="M", previous_run="",
                                   artifacts="A", history="", stack_label="Next.js", questions_left="Q", language="English",
                                   previous_plan="")
        text = " ".join(plan_prompt.split())
        for needle in ("This deployment is fast", "at most three questions are asked in the whole deployment",
                       "There is no test run and no gate", "at most six read-only requests", "Never the database"):
            self.assertIn(needle, text)
        self.assertNotIn("Install, tests and the production build on this computer first", text)
        self.assertNotIn("{{", plan_prompt)
        execute = " ".join(prompts.load("deployment/execute", request="r", plan="P", target="vercel", target_label="Vercel",
                                        project="p", run_id="r1", skills="S", machine="M", artifacts="A", language="English",
                                        resume="").split())
        for needle in ("Be fast: this is a delivery, not another test run", "No tests, no audits, no lint, no second gate",
                       "One repair round", "not more than twice in the whole run", "## The smoke proof"):
            self.assertIn(needle, execute)
        self.assertNotIn("Prove it live, then prove it again", execute)
        self.assertNotIn("{{", execute)

    def test_the_pages_a_planner_must_read_do_not_grow_past_what_they_were(self):
        # The speed contract was added to the shared page without making it longer than it was (20.5 KB).
        self.assertLess(len(self.page("core")), 20500)
        self.assertLess(len(self.page("deployment-repair")), 4500)


class MongoDeploymentTests(DeployFlowCase):
    """A MongoDB application is deployed on the database the build used: provided by the studio, never asked for in the chat."""

    SHOP_BUILD = "mongodb+srv://u:p4ssw0rd-long@c.mongodb.net/shop_build?retryWrites=true"

    def setUp(self):
        super().setUp()
        self.state = {"saved": True, "atlas": True}
        self.found = {"status": "ready", "database": "shop_build", "reason": ""}
        self.made: list[str] = []
        for patch in (mock.patch.object(deploy, "stack_of", lambda project: "nextjs-mongo-only"),
                      mock.patch.object(deploy.deploy_vars, "database_state", lambda: dict(self.state)),
                      mock.patch.object(deploy.deploy_vars, "build_databases", lambda project="": (self.SHOP_BUILD, "")),
                      mock.patch.object(deploy.mongo_connect, "ensure_for_project",
                                        lambda project, log=None: self.made.append(project) or self.found)):
            patch.start()
            self.addCleanup(patch.stop)
        self.session.reads = [f"{SKILLS}/{slug}/SKILL.md" for slug in ("core", "vercel", "stack-nextjs-mongo")]

    def approve(self, result):
        changes.decide(PROJECT, result["change"], "approve")
        self.settle(result["change"])

    def asks_for_the_string(self, request):
        self.session.write_record(*deploy.QUESTION, data={
            "question": "What is your MongoDB connection string?", "why": "the app needs a real database", "options": [],
            "variable": "MONGODB_URI", "secret": True, "check": "mongodb", "assumption": ""})
        run = deploy.run_state(PROJECT)
        run["state"] = "NEEDS_INPUT"
        self.session.write_record(*deploy.RUN, data=run)
        return {"status": "blocked", "text": "need the connection string", "rounds": 1}

    def test_with_nothing_connected_a_deployment_is_refused_before_anything_is_planned_or_asked(self):
        self.state = {"saved": False, "atlas": False}
        with self.assertRaisesRegex(ValueError, "Connect MongoDB before deploying") as refused:
            deploy.start(PROJECT, "vercel")
        self.assertIn("Settings, Integrations", str(refused.exception))
        self.assertEqual(self.session.prompts, [])
        self.assertIsNone(changes.active(PROJECT))

    def test_a_saved_string_or_a_signed_in_atlas_account_is_enough_to_start(self):
        self.session.replies = [plan()] * 2
        for state in ({"saved": True, "atlas": False}, {"saved": False, "atlas": True}):
            self.state = state
            result = deploy.start(PROJECT, "vercel")
            self.settle(result["change"])
            self.assertEqual(changes.active(PROJECT)["status"], "proposed", state)
            changes.decide(PROJECT, result["change"], "cancel")

    def test_a_stack_without_mongodb_is_never_asked_to_connect_it(self):
        self.state = {"saved": False, "atlas": False}
        with mock.patch.object(deploy, "stack_of", lambda project: "nextjs-supabase"):
            deploy._require_mongodb(PROJECT, "nextjs-supabase")
            self.assertEqual(deploy._mongodb_fact(PROJECT), "not used - this stack has no MongoDB")

    def test_the_machine_facts_say_what_is_connected_and_that_nothing_about_it_is_asked(self):
        saved = deploy._mongodb_fact(PROJECT)
        self.assertIn("`shop_build`", saved)
        self.assertIn("MONGODB_URI", saved)
        self.assertIn("Never ask the customer for a connection string", saved)
        self.assertNotIn("p4ssw0rd", saved)                                  # the database is named, the string never is
        self.state = {"saved": False, "atlas": True}
        self.assertIn("the Studio makes the cluster", deploy._mongodb_fact(PROJECT))
        self.assertIn("Never ask the customer for a connection string", deploy._mongodb_fact(PROJECT))
        self.state = {"saved": False, "atlas": False}
        self.assertIn("not connected", deploy._mongodb_fact(PROJECT))

    def test_the_machine_facts_prompt_has_a_place_for_it(self):
        text = prompts.load("deployment/machine", stack="s", tools="t", database="d", mongodb="MONGO-FACT", variables="v",
                            shell="sh", git="g", tests="x")
        self.assertIn("This project's MongoDB: MONGO-FACT", text)
        self.assertNotIn("{{", text)

    def test_the_database_is_made_before_the_run_starts_and_the_run_goes_on_when_it_is_ready(self):
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = [self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            self.approve(result)
        self.assertEqual(self.made, [PROJECT])
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")

    def test_a_database_that_cannot_be_made_fails_the_deployment_with_the_reason_and_asks_nothing(self):
        self.found = {"status": "failed", "database": "", "reason": "the cluster is paused"}
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = []
        self.approve(result)
        self.assertEqual(deploy.run_state(PROJECT)["state"], "FAILED")
        self.assertIn("the cluster is paused", deploy.run_state(PROJECT)["error"])
        self.assertEqual(self.session.executed, [])
        self.assertEqual([e for e in self.events if e.get("type") == "approval"], [])

    def test_a_run_that_asks_for_the_connection_string_is_answered_by_the_studio_and_goes_on(self):
        self.session.replies = [plan()]
        result = self.start()
        self.session.runs = [self.asks_for_the_string, self.live_run]
        answered = httpx.Response(200, request=httpx.Request("GET", "https://app.example.com"))
        with mock.patch.object(deploy.httpx, "get", return_value=answered):
            self.approve(result)
        self.assertEqual(len(self.session.executed), 2)
        self.assertIn("What is your MongoDB connection string?", self.session.executed[1])
        self.assertIn("not the customer's to give", self.session.executed[1])
        self.assertEqual([e for e in self.events if e.get("type") == "approval"
                          and "connection string" in str(e.get("question"))], [])      # the customer was never asked
        self.assertEqual(deploy.run_state(PROJECT)["state"], "LIVE")
        self.assertFalse(deploy.pending_question(PROJECT))

    def test_any_other_question_a_run_asks_is_still_asked(self):
        self.session.replies = [plan()]
        result = self.start()

        def blocked(request):
            self.session.write_record(*deploy.QUESTION, data={
                "question": "Should www and the bare domain both work?", "why": "a custom domain", "options": [{"label": "Both"}],
                "assumption": "both"})
            return {"status": "blocked", "text": "need a domain decision", "rounds": 1}

        self.session.runs = [blocked]
        self.approve(result)
        self.assertEqual(changes.active(PROJECT)["status"], "asking")
        self.assertEqual([e for e in self.events if e.get("type") == "approval"][-1]["question"],
                         "Should www and the bare domain both work?")

    def test_the_stack_pages_no_longer_tell_the_model_to_ask_for_the_connection(self):
        for slug in ("stack-nextjs-mongo", "stack-vite-mongo", "stack-remix-mongo", "stack-mern-microservices"):
            page = prompts.skill("deployment", slug)
            self.assertIn("`MONGODB_URI` is **not asked for**", page, slug)
            self.assertNotIn('"variable": "MONGODB_URI"', page, slug)
            self.assertNotIn("Is there already a MongoDB Atlas cluster connected", page, slug)
            self.assertIn("The database is not a question", page, slug)


if __name__ == "__main__":
    unittest.main()
