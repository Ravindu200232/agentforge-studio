"""The builder copies a selected scaffold without replacing existing work."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("builder-agent", "qa-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import scaffold  # noqa: E402
from qa_agent.evidence import collect  # noqa: E402


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
                if stack in {"nextjs-mongo", "mern-microservices"}:
                    self.assertTrue((workspace / "scripts/port-guard.mjs").is_file())
                manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
                for script in ("build", "test", "test:e2e", "test:visual", "test:a11y", "test:perf"):
                    self.assertIn(script, manifest["scripts"])
                self.assertIn("@axe-core/playwright", manifest["devDependencies"])
                self.assertIn("@lhci/cli", manifest["devDependencies"])
                if stack == "nextjs-mongo":
                    self.assertIn("port-guard.mjs 3001", manifest["scripts"]["dev"])
                if stack == "mern-microservices":
                    self.assertIn("port-guard.mjs", (workspace / "scripts/dev-all.mjs").read_text())
                    self.assertIn("VITE_PORT=5173", (workspace / ".env.example").read_text())
                    self.assertIn("PORT=4000", (workspace / ".env.example").read_text())
                    self.assertNotIn("3001", (workspace / "scripts/dev-all.mjs").read_text())
                    self.assertIn("freePort(frontendPort)",
                                  (workspace / "scripts/dev-all.mjs").read_text())
                    self.assertTrue((workspace / "client/vite-dev.mjs").is_file())
                    self.assertTrue((workspace / "client/static-preview.mjs").is_file())
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
                # Every generated app has a database of its own, and tests can only touch `_test`.
                db = scaffold.database_name(workspace.name)
                texts = {t: (workspace / t).read_text(encoding="utf-8", errors="ignore") for t in result["files"]}
                self.assertEqual([t for t, body in texts.items() if scaffold.DB_PLACEHOLDER in body], [])
                self.assertIn(f"27017/{db}", texts[".env.example"])
                helper = texts["packages/testing/index.js" if stack == "mern-microservices" else "test/helpers/db.js"]
                self.assertIn(f"{db}_test", helper)
                self.assertIn("must end in", helper)
                self.assertNotIn("process.env.MONGODB_URI", helper)
                self.assertTrue(scaffold.guide_context(stack).lstrip().startswith("### pitfalls.md"))
                if stack == "mern-microservices":
                    self.assertTrue((workspace / "scaffold/service/package.json.tpl").is_file())
                    self.assertFalse((workspace / "scaffold/service/package.json").exists())
                self.assertIn(scaffold.STACK_GUIDES[stack], scaffold.guide_context(stack))

    def test_port_guard_runs_when_invoked_directly_on_windows_paths(self):
        # `file://${process.argv[1]}` never equals import.meta.url on Windows, so the guard did nothing.
        for stack in ("nextjs-mongo", "mern-microservices"):
            guard = (scaffold.ROOT / stack / "scripts" / "port-guard.mjs").read_text(encoding="utf-8")
            self.assertIn("pathToFileURL(process.argv[1]).href", guard)
            self.assertNotIn("`file://${process.argv[1]}`", guard.split("pathToFileURL(process.argv[1])")[1])

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
        self.assertIn("renderPage", (scaffold.ROOT / "nextjs-mongo/test/helpers/next.js").read_text(encoding="utf-8"))
        self.assertIn("renderRoute", (scaffold.ROOT / "remix-mongo/test/helpers/remix.js").read_text(encoding="utf-8"))

    def test_builder_is_told_to_unit_test_every_page_route_and_component(self):
        self.assertIn("unit-tests.md", scaffold.COMMON_GUIDES)
        for stack in scaffold.STACK_GUIDES:
            context = scaffold.guide_context(stack)
            self.assertIn("### unit-tests.md", context)
            self.assertLess(context.index("### pitfalls.md"), context.index("### unit-tests.md"))
        self.assertIn("### unit-tests.md", scaffold.common_context())
        for name in ("builder/generate", "builder/update", "testing/run"):
            prompt = (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("qa:inventory", prompt, name)
        self.assertIn("every page", (ROOT / "prompts/builder/generate.md").read_text(encoding="utf-8"))

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
            result = scaffold.install(workspace, "nextjs-mongo")
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
            self.assertIn("### visual.md", scaffold.guide_context(stack))
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

    def test_next_and_remix_tests_get_their_own_database_and_connection_reuse(self):
        for stack in ("nextjs-mongo", "remix-mongo"):
            with tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp)
                scaffold.install(workspace, stack)
                env = (workspace / "vitest.env.js").read_text(encoding="utf-8")
                self.assertIn(f"{scaffold.database_name(workspace.name)}_test", env)
                self.assertIn("process.env.MONGODB_URI = process.env.TEST_MONGODB_URI", env)
                self.assertIn("vitest.env.js", (workspace / "vitest.config.js").read_text(encoding="utf-8"))
                self.assertIn("readyState === 1", (workspace / "lib/db.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
