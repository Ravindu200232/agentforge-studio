"""The builder copies a selected scaffold without replacing existing work."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "builder-agent", "qa-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import scaffold  # noqa: E402
from qa_agent.evidence import archive_results, collect  # noqa: E402

SUPABASE_STACKS = {"nextjs-supabase", "vite-supabase", "remix-supabase"}
# The sets below name template folders: a Mongo-only stack installs its Supabase-bucket twin's folder.
MONGO_STACKS = {"nextjs-mongo", "vite-mongo", "remix-mongo", "mern-microservices"}
NEXTJS_STACKS = {"nextjs-supabase", "nextjs-mongo"}
# These two have their own long-running server on a fixed local port (not a single Studio-assigned
# one) and their own aggressive, port-freeing port-guard. The single-app stacks need none: the Studio
# starts each one on a port of its own.
WORKSPACE_STACKS = {"vite-mongo", "mern-microservices"}
AGGRESSIVE_PORT_GUARD_STACKS = WORKSPACE_STACKS
MICROSERVICES_STACKS = {"mern-microservices"}
SPA_STACKS = {"vite-supabase"}  # no server, no secret store - the Supabase-only SPA pattern


def template(stack):
    """The template folder a stack installs."""
    return scaffold.template_dir(stack).name


class ScaffoldTests(unittest.TestCase):
    def test_uploaded_media_is_preserved_when_the_app_is_scaffolded(self):
        for stack in scaffold.STACK_GUIDES:
            with self.subTest(stack=stack), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                media = workspace / "media" / "customer-photo.png"
                media.parent.mkdir()
                media.write_bytes(b"uploaded-image")
                result = scaffold.install(workspace, stack)
                self.assertTrue(result["scaffolded"])
                self.assertEqual(media.read_bytes(), b"uploaded-image")
                self.assertTrue((workspace / "package.json").is_file())

    def test_each_stack_installs_real_runner_and_keeps_skeleton_inert(self):
        for stack in scaffold.STACK_GUIDES:
            with self.subTest(stack=stack), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                result = scaffold.install(workspace, stack)
                self.assertTrue(result["scaffolded"])
                self.assertTrue((workspace / "package.json").is_file())
                self.assertTrue((workspace / "playwright.config.js").is_file())
                self.assertTrue((workspace / "e2e/a11y.spec.js").is_file())
                self.assertTrue((workspace / ".agentforge/build/scaffold.json").is_file())
                if template(stack) in AGGRESSIVE_PORT_GUARD_STACKS:
                    self.assertTrue((workspace / "scripts/port-guard.mjs").is_file())
                manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
                for script in ("build", "test", "test:e2e", "test:visual", "test:a11y", "test:perf"):
                    self.assertIn(script, manifest["scripts"])
                self.assertIn("@axe-core/playwright", manifest["devDependencies"])
                self.assertIn("@lhci/cli", manifest["devDependencies"])
                if template(stack) in NEXTJS_STACKS:
                    self.assertNotIn("3001", manifest["scripts"]["dev"])
                    self.assertNotIn("3001", manifest["scripts"]["start"])
                # Preview ownership belongs to Studio, which assigns a single-app stack an isolated
                # port of its own. The fixed-local-port workspace stacks (vite-mongo,
                # mern-microservices) are a different, deliberate convention and are exempt.
                if template(stack) not in WORKSPACE_STACKS:
                    for script in ("dev", "start"):
                        self.assertNotIn("3001", manifest["scripts"][script])
                        self.assertNotIn("5173", manifest["scripts"][script])
                self.assertNotIn(".slice(0, 8)", (workspace / "lighthouserc.cjs").read_text())
                # One command per layer that needs a running app, and the runners behind them.
                for script in ("qa:e2e", "qa:visual", "qa:a11y", "qa:perf", "qa:security"):
                    self.assertIn(script, manifest["scripts"])
                for runner in ("with-server.mjs", "run-perf.mjs", "zap-scan.mjs"):
                    self.assertTrue((workspace / "scripts" / runner).is_file(), runner)
                # A fresh machine gets a real ZAP scan by default, not just when
                # someone remembers the separate --install-zap flag - and a machine
                # that already failed once is not retried on every single run.
                zap_scan = (workspace / "scripts/zap-scan.mjs").read_text(encoding="utf-8")
                self.assertIn("autoInstallFailedAt", zap_scan)
                self.assertIn("await installZap()", zap_scan)
                slug = scaffold.project_slug(workspace.name)
                texts = {t: (workspace / t).read_text(encoding="utf-8", errors="ignore") for t in result["files"]}
                self.assertEqual([t for t, body in texts.items() if scaffold.DB_PLACEHOLDER in body], [])
                self.assertEqual(list(scaffold.guide_files(stack))[0], "pitfalls.md")

                if template(stack) in SUPABASE_STACKS:
                    # Every generated app has a Supabase project of its own; nothing here still
                    # names the shared placeholder once install() has substituted the real slug.
                    self.assertIn(f'project_id = "{slug}"', texts["supabase/config.toml"])
                    helper = texts["test/helpers/db.js"]
                    self.assertIn("must be local", helper)
                    self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", helper)  # talks to local Postgres directly, no key at all
                else:
                    self.assertFalse((workspace / "supabase").exists())
                    # Every generated Mongo app gets its own `_test`-suffixed database name; tests
                    # can never touch anything else.
                    helper_path = "packages/testing/index.js" if template(stack) == "mern-microservices" else "test/helpers/db.js"
                    helper = texts[helper_path]
                    self.assertIn(f"{slug}_test", helper)
                    self.assertIn("must end in", helper)

                if template(stack) in MICROSERVICES_STACKS:
                    self.assertTrue((workspace / "scaffold/service/package.json.tpl").is_file())
                    self.assertFalse((workspace / "scaffold/service/package.json").exists())
                    # The one Dockerfile every package (gateway or a service) is built from, in the
                    # cloud - built with a different --build-arg SERVICE per package, never per-stack.
                    self.assertIn("ARG SERVICE=packages/gateway", texts["Dockerfile"])

                if template(stack) in SPA_STACKS:
                    # This app has no server and no secret store: the service-role key must never
                    # be *read* anywhere a browser bundle could include it (mentioning it in a
                    # comment, to explain why not, is fine).
                    for path in result["files"]:
                        if path.startswith("src/"):
                            self.assertNotIn("env.SUPABASE_SERVICE_ROLE_KEY", texts[path], path)
                self.assertIn(scaffold.STACK_GUIDES[stack], scaffold.guide_files(stack))

    def test_workspace_stacks_port_guard_frees_only_its_own_fixed_port(self):
        # Unlike the single-app stacks, these run a fixed local port every project
        # shares, so a stale listener on it is freed rather than left to block the next run.
        for stack in AGGRESSIVE_PORT_GUARD_STACKS:
            guard = (scaffold.ROOT / stack / "scripts" / "port-guard.mjs").read_text(encoding="utf-8")
            self.assertIn("pathToFileURL(process.argv[1]).href", guard)
            self.assertIn("Free only the process which is listening on this exact application port", guard)

    def test_nextjs_mongo_tests_get_their_own_database_and_connection_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            scaffold.install(workspace, "nextjs-mongo")
            slug = scaffold.project_slug(workspace.name)
            env = (workspace / "vitest.env.js").read_text(encoding="utf-8")
            self.assertIn(f"{slug}_test", env)
            self.assertIn("process.env.MONGODB_URI = process.env.TEST_MONGODB_URI", env)
            self.assertIn("vitest.env.js", (workspace / "vitest.config.js").read_text(encoding="utf-8"))
            self.assertIn("readyState === 1", (workspace / "lib/db.js").read_text(encoding="utf-8"))

    def test_qa_server_wrapper_never_touches_the_projects_real_database(self):
        runner = (scaffold.ROOT / "_testing/scripts/with-server.mjs").read_text(encoding="utf-8")
        self.assertIn("never read or write the project's real data", runner)
        self.assertNotIn("truncate table", runner)
        # A Mongo stack's own isolated, uniquely-named QA database is reset and (if the app defines
        # one) seeded for the run, then dropped - never the project's real database, which this
        # wrapper never names or connects to directly.
        self.assertIn("resetQaDatabase", runner)
        self.assertIn("npm', 'run', 'seed", runner)
        self.assertIn("_e2e", runner)

    def test_smoke_a11y_and_visual_only_cover_public_pages(self):
        routes = (scaffold.ROOT / "_testing" / "e2e" / "routes.js").read_text(encoding="utf-8")
        self.assertIn("publicRoutes", routes)
        for spec in ("a11y", "visual"):
            body = (scaffold.ROOT / "_testing" / "e2e" / f"{spec}.spec.js").read_text(encoding="utf-8")
            self.assertIn("publicRoutes()", body)
        self.assertIn("refuses a signed-out visitor",
                      (scaffold.ROOT / "_testing" / "e2e" / "smoke.spec.js").read_text(encoding="utf-8"))

    def test_every_stack_can_list_and_measure_what_its_unit_tests_cover(self):
        for stack in scaffold.STACK_GUIDES:
            with self.subTest(stack=stack), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                scaffold.install(workspace, stack)
                manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["scripts"]["qa:inventory"], "node scripts/test-inventory.mjs")
                self.assertIn("vitest run --coverage", manifest["scripts"]["test:coverage"])
                self.assertIn("@vitest/coverage-v8", manifest["devDependencies"])
                self.assertTrue((workspace / "scripts/test-inventory.mjs").is_file())
                config = "vitest.config.js"
                self.assertIn(".agentforge/qa/coverage", (workspace / config).read_text(encoding="utf-8"))
        # Test helpers that keep every page/route test to its assertions.
        self.assertIn("renderPage", (scaffold.ROOT / "nextjs-supabase/test/helpers/next.js").read_text(encoding="utf-8"))
        self.assertIn("renderRoute", (scaffold.ROOT / "remix-supabase/test/helpers/remix.js").read_text(encoding="utf-8"))

    def test_builder_is_told_to_unit_test_every_page_route_and_component(self):
        self.assertIn("unit-tests.md", scaffold.COMMON_GUIDES)
        for stack in scaffold.STACK_GUIDES:
            names = list(scaffold.guide_files(stack))        # what the QA run is given to read
            self.assertIn("unit-tests.md", names)
            self.assertLess(names.index("pitfalls.md"), names.index("unit-tests.md"))
        self.assertIn("### unit-tests.md", scaffold.common_context())
        self.assertIn("every approved page", (ROOT / "prompts/builder/generate.md").read_text(encoding="utf-8"))

    def test_shared_guidance_and_templates_name_no_particular_app(self):
        # The skill, the templates and the prompts are for every product, not the one they were learned on.
        roots = [scaffold.ROOT / "_guides", scaffold.ROOT / "_testing", ROOT / "prompts" / "builder", ROOT / "prompts" / "testing"]
        for folder in roots:
            for file in folder.rglob("*"):
                if file.suffix not in {".md", ".js", ".mjs", ".cjs", ".tpl"} or "node_modules" in file.parts:
                    continue
                text = file.read_text(encoding="utf-8", errors="ignore")
                for word in ("TaskBoard", "All Tasks", "Dana", "My Tasks"):
                    self.assertNotIn(word, text, f"{word} in {file}")

    @unittest.skipUnless(shutil.which("node"), "node is needed to run the inventory script")
    def test_inventory_names_each_untested_page_route_and_component(self):
        script = scaffold.ROOT / "_testing" / "scripts" / "test-inventory.mjs"
        files = {
            "package.json": '{"dependencies":{"next":"15"}}',
            "app/page.jsx": "export default function Home() { return null }",
            "app/about/page.jsx": "export default function About() { return null }",
            "app/api/things/route.js": "export async function GET() {}\nexport async function POST() {}\n",
            "app/api/things/[id]/route.js": "export async function DELETE() {}\n",
            "app/components/Card.jsx": "export function Card() { return null }\nexport default Card\n",
            "app/components/Mocked.jsx": "export function Mocked() { return null }\n",
            "lib/util.js": "export const LIMIT = 5\nexport function clamp(n) { return n }\n",
            "lib/inner.js": "export function inner() { return 1 }\n",
            "lib/outer.js": "import { inner } from './inner.js'\nexport function outer() { return inner() }\n",
            "test/outer.test.js": "import { outer } from '@/lib/outer.js'\nexpect(outer()).toBe(1)\n",
            "test/home.test.jsx": ("import Home from '@/app/page.jsx'\nimport { Card } from '@/app/components/Card.jsx'\n"
                                   "import { Mocked } from '@/app/components/Mocked.jsx'\nvi.mock('@/app/components/Mocked.jsx', () => ({}))\n"
                                   "render(<Home />)\nrender(<Card />)\n"),
            "test/api.node.test.js": ("const { GET: list, POST: create } = await import('@/app/api/things/route.js')\n"
                                      "await list(new Request('http://x'))\nawait create(new Request('http://x'))\n"),
        }
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            for name, body in files.items():
                (workspace / name).parent.mkdir(parents=True, exist_ok=True)
                (workspace / name).write_text(body, encoding="utf-8")
            done = subprocess.run(["node", str(script), "--report-only"], cwd=workspace, capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)
            data = json.loads((workspace / ".agentforge/qa/coverage-inventory.json").read_text(encoding="utf-8"))
            status = {u["file"]: u["status"] for u in data["units"]}
            self.assertEqual(status["app/page.jsx"], "covered")                    # rendered by a test
            self.assertEqual(status["app/about/page.jsx"], "uncovered")            # no test at all
            self.assertEqual(status["app/api/things/route.js"], "covered")         # both methods called through aliases
            self.assertEqual(status["app/api/things/[id]/route.js"], "uncovered")  # DELETE never called
            self.assertEqual(status["app/components/Card.jsx"], "covered")         # named export used, default is its alias
            self.assertEqual(status["app/components/Mocked.jsx"], "uncovered")     # only a vi.mock
            self.assertEqual(status["lib/util.js"], "uncovered")                   # nothing runs it
            self.assertEqual(status["lib/outer.js"], "covered")
            inner = next(u for u in data["units"] if u["file"] == "lib/inner.js")
            self.assertEqual((inner["status"], inner.get("indirect")), ("covered", True))  # runs through a tested module
            self.assertEqual(data["untested_required"], 4)
            gate = subprocess.run(["node", str(script)], cwd=workspace, capture_output=True, text=True, timeout=60)
            self.assertEqual(gate.returncode, 1)                                   # the gate fails while a unit is untested

    @unittest.skipUnless(shutil.which("node"), "node is needed to run the inventory script")
    def test_inventory_matches_express_routes_by_method_and_path(self):
        # Not one of our own scaffolds's single-app stacks - this is the inventory script's
        # general-purpose Express support, exercised against a synthetic fixture so it keeps
        # working for a hand-written Express service (which is exactly what vite-mongo's server
        # and every mern-microservices package are).
        script = scaffold.ROOT / "_testing" / "scripts" / "test-inventory.mjs"
        files = {
            "package.json": '{"name":"m"}',
            "packages/orders/package.json": "{}",
            "packages/orders/src/routes/orders.routes.js": (
                "import { Router } from 'express'\nexport const ordersRouter = Router()\n"
                "ordersRouter.get('/', (q, r) => r.json([]))\nordersRouter.post('/', (q, r) => r.json({}))\n"
                "ordersRouter.delete('/:id', (q, r) => r.json({}))\n"),
            "packages/orders/test/orders.test.js": (
                "await request(app).get('/orders').expect(200)\nawait request(app).post('/orders').send({})\n"),
        }
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            for name, body in files.items():
                (workspace / name).parent.mkdir(parents=True, exist_ok=True)
                (workspace / name).write_text(body, encoding="utf-8")
            (workspace / "packages/orders/src").mkdir(parents=True, exist_ok=True)
            subprocess.run(["node", str(script), "--report-only"], cwd=workspace, capture_output=True, text=True, timeout=60, check=True)
            data = json.loads((workspace / ".agentforge/qa/coverage-inventory.json").read_text(encoding="utf-8"))
            route = next(u for u in data["units"] if u["kind"] == "route")
            self.assertEqual(route["status"], "partial")
            self.assertEqual(route["missing"], ["DELETE /:id"])

    def test_the_live_view_only_watches_a_run_and_never_decides_its_outcome(self):
        fixtures = (scaffold.ROOT / "_testing/e2e/fixtures.js").read_text(encoding="utf-8")
        live_view = (scaffold.ROOT / "_testing/e2e/live-view.js").read_text(encoding="utf-8")
        reporter = (scaffold.ROOT / "_testing/e2e/live-reporter.js").read_text(encoding="utf-8")
        # Streaming is best-effort: its start and stop are guarded, and a test's own failure still surfaces.
        self.assertIn("startLiveView(page, testInfo).catch(", fixtures)
        self.assertIn("finally", fixtures)
        self.assertIn("stopLive().catch(", fixtures)
        self.assertIn("expect(problems, 'the page reported problems').toEqual([])", fixtures)
        # It does nothing unless the Studio started the run, and only when somebody is watching.
        self.assertIn("process.env.AGENTFORGE_LIVE_URL", live_view)
        self.assertIn("somebodyIsWatching", live_view)
        self.assertIn("parallelIndex !== 0", live_view)
        # Off the Studio the reporter's output is what it always was.
        self.assertIn("if (!isLive) return emit(row)", reporter)
        for stack in scaffold.STACK_GUIDES:
            with tempfile.TemporaryDirectory() as temp:
                scaffold.install(Path(temp), stack)
                for name in ("live-view.js", "live-reporter.js", "fixtures.js"):
                    self.assertTrue((Path(temp) / "e2e" / name).is_file(), f"{stack}: e2e/{name}")

    def test_existing_project_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / "package.json").write_text('{"name":"mine"}', encoding="utf-8")
            result = scaffold.install(workspace, "nextjs-supabase")
            self.assertFalse(result["scaffolded"])
            self.assertEqual((workspace / "package.json").read_text(), '{"name":"mine"}')
            self.assertFalse((workspace / "playwright.config.js").exists())

    def test_unknown_stack_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                scaffold.install(Path(temp), "something-else")

    def test_visual_regression_has_a_guide_and_a_shared_baseline_helper(self):
        # Found live: a generated app's visual.spec.js and playwright.config.js had
        # been rewritten away from the scaffold's own self-recording baseline
        # contract - every re-run then reported "no snapshot exists" forever,
        # because nothing was ever told this file exists and must be extended,
        # never replaced. visual.md plus a shared, exported helper (instead of
        # logic the model has to hand-copy correctly) close that gap.
        self.assertIn("visual.md", scaffold.TEST_GUIDES)
        for stack in scaffold.STACK_GUIDES:
            self.assertIn("visual.md", scaffold.guide_files(stack))
            with tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                scaffold.install(workspace, stack)
                fixtures = (workspace / "e2e/fixtures.js").read_text(encoding="utf-8")
                self.assertIn("export async function expectMatchesBaseline(", fixtures)
                visual = (workspace / "e2e/visual.spec.js").read_text(encoding="utf-8")
                self.assertIn("expectMatchesBaseline(page, testInfo, slug(route))", visual)
                # The self-recording branch lives in fixtures.js now, not duplicated here.
                self.assertNotIn("testInfo.snapshotPath(", visual)
        guide = (scaffold.ROOT / "_guides" / "visual.md").read_text(encoding="utf-8")
        self.assertIn("expectMatchesBaseline", guide)
        self.assertIn("snapshotPathTemplate", guide)
        prompt = (ROOT / "prompts/testing/run.md").read_text(encoding="utf-8")
        self.assertIn("qa:visual", prompt)
        self.assertIn("visual.md", prompt)
        self.assertIn("expectMatchesBaseline", prompt)

    def test_supabase_stacks_get_a_local_only_test_database_and_the_right_clients(self):
        for stack in ("nextjs-supabase", "remix-supabase"):
            with self.subTest(stack=stack), tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                scaffold.install(workspace, stack)
                # A test never sees the real project's URL/keys, even though every other command does.
                env = (workspace / "vitest.env.js").read_text(encoding="utf-8")
                self.assertIn("127.0.0.1:54321", env)
                client = (workspace / "lib/supabase.js").read_text(encoding="utf-8")
                self.assertIn("createServerClient", client)
                self.assertIn("createClient", client)  # the admin (service-role) client


class EvidenceTests(unittest.TestCase):
    def test_reads_runner_results_and_real_screenshots(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / ".agentforge/qa").mkdir(parents=True)
            (workspace / ".agentforge/qa/vitest.json").write_text(
                json.dumps({"numTotalTests": 2, "numPassedTests": 1, "success": False}))
            (workspace / "test-results").mkdir()
            (workspace / "test-results/results.json").write_text(json.dumps({"stats": {"unexpected": 1}}))
            (workspace / "test-results/page.png").write_bytes(b"not-a-real-image")
            result = collect(workspace, {"project": "x", "screenshots": []})
            self.assertFalse(result["vitest"]["success"])
            self.assertEqual(result["playwright"]["stats"]["unexpected"], 1)
            self.assertEqual(result["screenshots"][0]["path"], "test-results/page.png")

    def test_security_scan_summary_becomes_the_security_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            zap = workspace / ".agentforge/qa/zap"
            zap.mkdir(parents=True)
            (zap / "summary.json").write_text(json.dumps({
                "engine": "agentforge-baseline", "status": "partial", "note": "ZAP did not run",
                "failing": [], "warnings": [{"id": "10020", "name": "Missing Anti-clickjacking Header",
                                            "risk": "Medium", "action": "WARN", "description": "x", "count": 1}]}))
            result = collect(workspace, {"project": "x"})
            self.assertEqual(result["security"]["zap"]["status"], "partial")
            self.assertIn("agentforge-baseline", result["security"]["zap"]["reason"])
            self.assertEqual(result["security"]["zap"]["findings"][0]["severity"], "Medium")

    def test_layers_run_separately_are_merged_not_picked_between(self):
        # A build runs journeys, accessibility and visual as separate runs, in separate logs.
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            qa = workspace / ".agentforge/qa"
            qa.mkdir(parents=True)
            (qa / "e2e-run.log").write_text(
                "Running 2 tests using 2 workers\n"
                "[1/2] [desktop] › e2e\\smoke.spec.js:7:3 › Login opens\n"
                "[2/2] [desktop] › e2e\\taskboard.spec.js:9:3 › member adds a task\n  2 passed (5.1s)\n", encoding="utf-8")
            (qa / "a11y-run.log").write_text(
                "Running 1 test using 1 worker\n"
                "[1/1] [desktop] › e2e\\a11y.spec.js:13:5 › @a11y › Login is accessible\n  1 passed (3.7s)\n", encoding="utf-8")
            (workspace / "test-results").mkdir()
            (workspace / "test-results/results.json").write_text(json.dumps({"suites": [
                {"file": "a11y.spec.js", "title": "a11y.spec.js", "suites": [{"title": "@a11y", "specs": [
                    {"title": "Login is accessible", "file": "a11y.spec.js", "tests": [
                        {"projectName": "desktop", "results": [{"status": "passed"}]}]}]}]}]}))
            result = collect(workspace, {"project": "x"})
            runs = result["browserRuns"]
            self.assertEqual((runs["total"], runs["passed"], runs["failed"]), (3, 3, 0))  # the JSON's copy is not a 4th test
            self.assertEqual(result["accessibility"]["audited"], 1)
            self.assertEqual(result["report"]["e2e"]["stage_total"], 2)

    def test_inventory_and_measured_coverage_reach_the_testing_view(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / ".agentforge/qa/coverage").mkdir(parents=True)
            (workspace / ".agentforge/qa/coverage-inventory.json").write_text(json.dumps({
                "units": [{"kind": "page", "file": "app/page.jsx", "status": "uncovered", "missing": ["default"], "tests": []}],
                "required": 1, "untested_required": 1}))
            root = str(workspace.resolve()).replace("\\", "/")
            (workspace / ".agentforge/qa/coverage/coverage-summary.json").write_text(json.dumps({
                "total": {"lines": {"total": 10, "covered": 5, "pct": 50}, "statements": {"pct": 50},
                          "functions": {"pct": 25}, "branches": {"pct": 0}},
                f"{root}/app/page.jsx": {"lines": {"total": 4, "covered": 0, "pct": 0}, "statements": {"pct": 0},
                                        "functions": {"pct": 0}, "branches": {"pct": 100}}}))
            result = collect(workspace, {"project": "x"})
            self.assertEqual(result["unitInventory"]["untested_required"], 1)
            self.assertEqual(result["codeCoverage"]["lines"], 50.0)
            self.assertEqual(result["codeCoverage"]["files"][0]["file"], "app/page.jsx")

    def test_build_artifacts_fill_api_runtime_repair_and_accessibility_panels(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            handler = workspace / "app/api/things/route.js"
            handler.parent.mkdir(parents=True)
            handler.write_text("export async function GET() {}\nexport async function POST() {}\n", encoding="utf-8")
            test = workspace / "test/api.node.test.js"
            test.parent.mkdir()
            test.write_text("await import('@/app/api/things/route.js')\n", encoding="utf-8")
            qa = workspace / ".agentforge/qa"
            qa.mkdir(parents=True)
            (qa / "vitest.json").write_text(json.dumps({"testResults": [{"name": str(test), "status": "passed"}]}))
            (workspace / ".agentforge/preview-runtime.json").write_text(json.dumps({"status": "running", "url": "http://127.0.0.1:3001"}))
            build = workspace / ".agentforge/build"
            build.mkdir()
            (build / "report.json").write_text(json.dumps({
                "phase_3": {
                    "layers": [
                        {"layer": "accessibility (axe-core)", "exit_code": 0, "result": "5 passed — zero violations"},
                        {"layer": "UI and screenshot check", "exit_code": 0, "result": "5 passed — no horizontal overflow"},
                    ],
                    "defects_found_and_fixed": [{"where": "Search", "defect": "missing label", "fix": "added a label"}],
                },
            }))
            result = collect(workspace, {"project": "x"})
            self.assertEqual(result["contracts"][0]["route"], "/api/things")
            self.assertEqual(result["contracts"][0]["methods"], ["GET", "POST"])
            self.assertEqual(result["contracts"][0]["tests"][0]["status"], "passed")
            self.assertEqual(result["runtimeStatus"]["status"], "running")
            self.assertEqual(result["accessibility"]["declaredAudited"], 5)
            self.assertEqual(result["uiQualitySummary"]["count"], 5)
            self.assertEqual(result["buildRepairs"]["items"][0]["fix"], "added a label")

    def test_coder_gets_unit_e2e_and_test_setup_source(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / "test").mkdir()
            (workspace / "e2e").mkdir()
            (workspace / "test" / "money.test.js").write_text("test('money', () => {})", encoding="utf-8")
            (workspace / "e2e" / "booking.spec.js").write_text("test('booking', async () => {})", encoding="utf-8")
            (workspace / "playwright.config.js").write_text("export default {}", encoding="utf-8")
            result = collect(workspace, {"project": "x"})
            sources = {(row["path"], row["kind"]): row["code"] for row in result["testSources"]}
            self.assertEqual(sources[("test/money.test.js", "unit")], "test('money', () => {})")
            self.assertEqual(sources[("e2e/booking.spec.js", "e2e")], "test('booking', async () => {})")
            self.assertEqual(sources[("playwright.config.js", "support")], "export default {}")

    def test_previous_results_are_preserved_and_visible_after_live_files_change(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            qa = workspace / ".agentforge/qa"
            qa.mkdir(parents=True)
            (qa / "vitest.json").write_text(json.dumps({"numTotalTests": 8, "numPassedTests": 8, "numFailedTests": 0}))
            (workspace / "test-results").mkdir()
            (workspace / "test-results/results.json").write_text(json.dumps({"stats": {"expected": 4, "unexpected": 0}}))
            saved = archive_results(workspace, "Before a repair", "before-repair")
            self.assertIsNotNone(saved)
            (qa / "vitest.json").write_text(json.dumps({"numTotalTests": 3, "numPassedTests": 2, "numFailedTests": 1}))
            result = collect(workspace, {"project": "x"})
            historic = result["resultHistory"][0]
            self.assertEqual(historic["label"], "Before a repair")
            self.assertEqual(historic["counts"]["unit"], {"total": 8, "passed": 8, "failed": 0})
            self.assertEqual(historic["counts"]["browser"], {"total": 4, "passed": 4, "failed": 0})


class ReportShapeEvidenceTests(unittest.TestCase):
    """Found live: every check passed, yet the Testing views showed empty route names, empty
    gaps, "not run" and no accessibility - the report used keys of its own, and Playwright's
    results file held only the last of several runs."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)
        (self.workspace / ".agentforge/build").mkdir(parents=True)
        (self.workspace / ".agentforge/qa").mkdir(parents=True)

    def write(self, rel, data):
        path = self.workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_a_report_written_before_the_template_still_fills_the_views(self):
        self.write(".agentforge/build/report.json", {
            "app": "x", "routes": ["/", "/shop"], "api": ["POST /api/cart"],
            "gaps": [{"area": "Online payments", "detail": "no live credentials", "severity": "gap"}],
            "repairs": [{"phase": "a11y", "finding": "link contrast", "fix": "underlined links"}]})
        result = collect(self.workspace, {"project": "x"})
        routes = result["build"]["routes"]
        self.assertEqual([r["route"] for r in routes], ["/", "/shop", "/api/cart"])
        self.assertEqual(routes[-1]["method"], "POST")
        gap = result["build"]["gaps"][0]
        self.assertEqual((gap["item"], gap["status"], gap["reason"]), ("Online payments", "gap", "no live credentials"))
        self.assertEqual(result["buildRepairs"]["items"][0],
                         {"where": "a11y", "problem": "link contrast", "fix": "underlined links"})

    def test_a_report_in_the_template_shape_passes_through_unchanged(self):
        gaps = [{"item": "Payments", "status": "gap", "reason": "no keys"}]
        self.write(".agentforge/build/report.json", {"app": "x", "gaps": gaps,
                                                     "routes": [{"route": "/", "verified": True, "how": "smoke"}]})
        result = collect(self.workspace, {"project": "x"})
        self.assertEqual(result["build"]["gaps"], gaps)
        self.assertEqual(result["build"]["routes"], [{"route": "/", "verified": True, "how": "smoke"}])

    def test_each_kept_run_counts_after_a_later_run_overwrote_results_json(self):
        def run(spec, title):
            return {"suites": [{"file": spec, "title": spec, "specs": [
                {"title": title, "file": spec, "tests": [{"projectName": "desktop", "results": [{"status": "passed"}]}]}]}]}
        self.write("test-results/results.json", run("journeys.spec.js", "[UJ-001] a journey"))
        self.write(".agentforge/qa/runs/test-a11y.json", run("a11y.spec.js", "@a11y Home is accessible"))
        result = collect(self.workspace, {"project": "x"})
        self.assertEqual(result["accessibility"]["audited"], 1)
        self.assertEqual(result["browserRuns"]["total"], 2)

    def test_the_unit_entry_comes_from_vitest_and_a_saved_one_still_wins(self):
        self.write(".agentforge/qa/vitest.json", {"numTotalTests": 63, "numPassedTests": 63,
                                                   "numFailedTests": 0, "success": True, "testResults": []})
        unit = collect(self.workspace, {"project": "x"})["unit"]
        self.assertEqual((unit["status"], unit["total"], unit["passed"]), ("passed", 63, 63))
        saved = {"status": "failed", "total": 2, "passed": 1, "failed": 1}
        self.assertEqual(collect(self.workspace, {"project": "x", "unit": saved})["unit"]["status"], "failed")

    def test_a_layer_recorded_only_in_the_qa_report_still_shows(self):
        self.write(".agentforge/build/report.json", {"app": "x"})
        qa = {"project": "x", "layers": [{"layer": "a11y", "exit_code": 0, "status": "passed",
                                          "result": "10 passed (axe)"}]}
        self.assertEqual(collect(self.workspace, qa)["accessibility"]["declaredAudited"], 10)

    def test_a_prose_summary_becomes_counts_and_keeps_its_words(self):
        qa = {"project": "x", "summary": "Every layer passed.",
              "layers": [{"layer": "unit", "status": "passed"}, {"layer": "e2e", "status": "failed"}]}
        result = collect(self.workspace, qa)
        self.assertEqual(result["summary"], {"pass": 1, "fail": 1, "warn": 0})
        self.assertEqual(result["summaryText"], "Every layer passed.")

    def test_api_calls_an_e2e_test_made_link_it_to_the_handler_that_answered(self):
        for rel, body in (("app/api/cart/route.js", "export async function POST() {}"),
                          ("app/api/orders/new/route.js", "export async function GET() {}"),
                          ("app/api/orders/[id]/route.js", "export async function GET() {}"),
                          ("app/api/untouched/route.js", "export async function GET() {}")):
            (self.workspace / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.workspace / rel).write_text(body, encoding="utf-8")
        calls = ["POST /api/cart 200", "GET /api/orders/new 200", "GET /api/orders/42 403", "POST /api/cart 200"]
        attachment = {"name": "api-calls", "contentType": "application/json",
                      "body": base64.b64encode(json.dumps(calls).encode()).decode()}
        self.write("test-results/results.json", {"suites": [{"file": "journeys.spec.js", "title": "journeys.spec.js", "specs": [
            {"title": "[UJ-001] a shopper orders", "file": "journeys.spec.js", "tests": [
                {"projectName": "desktop", "results": [{"status": "passed", "attachments": [attachment]}]}]}]}]})
        rows = {row["route"]: row["tests"] for row in collect(self.workspace, {"project": "x"})["contracts"]}
        link = rows["/api/cart"][0]
        self.assertEqual((link["kind"], link["file"], link["status"], link["calls"]),
                         ("e2e", "journeys.spec.js", "passed", ["POST 200"]))
        self.assertEqual(rows["/api/orders/new"][0]["calls"], ["GET 200"])   # the static route wins
        self.assertEqual(rows["/api/orders/[id]"][0]["calls"], ["GET 403"])
        self.assertEqual(rows["/api/untouched"], [])

    def test_the_e2e_fixture_attaches_the_api_calls_each_test_made(self):
        fixtures = (scaffold.ROOT / "_testing/e2e/fixtures.js").read_text(encoding="utf-8")
        self.assertIn("testInfo.attach('api-calls'", fixtures)

    def test_the_server_wrapper_keeps_each_runs_results(self):
        runner = (scaffold.ROOT / "_testing/scripts/with-server.mjs").read_text(encoding="utf-8")
        self.assertIn("keepRunResults(command, startedAt)", runner)
        self.assertIn("path.join('.agentforge', 'qa', 'runs')", runner)


if __name__ == "__main__":
    unittest.main()
