"""The React apps the wireframe and the prototype are made of: the skill, the app that is created, and the bundling."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server_modules import web_app  # noqa: E402

REAL_CHECK = web_app.check_pages          # the tests of the bundling leave the browser alone

PAGES = [
    {"route": "/", "page_name": "Home"},
    {"route": "/orders/[id]", "page_name": "Order", "login_required": True, "allowed_roles": ["baker"]},
    {"route": "/account", "page_name": "Account", "login_required": True, "allowed_roles": ["customer", "baker"]},
]
ACCOUNTS = [{"role": "Baker", "role_key": "baker", "display_name": "Demo Baker", "email": "baker@example.com",
             "password": "Demo!2026", "lands_on": "/orders/[id]", "can_open": [{"route": "/orders/[id]"}, {"route": "/account"}]}]


class Scratch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.kit = self.root / "kit"
        for patch in (mock.patch.object(web_app, "kit_dir", lambda legacy=False: self.root / "legacy-kit" if legacy else self.kit),
                      mock.patch.object(web_app, "check_pages", return_value=None)):
            patch.start()
            self.addCleanup(patch.stop)

    def app(self, name: str = "app") -> Path:
        return self.root / name


class CustomUiTests(Scratch):
    def test_staged_guide_uses_product_authored_components(self):
        relative = web_app.stage_skill(self.root)
        self.assertEqual(relative, ".agentforge/skills/custom-ui")
        guide = (self.root / relative / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("semantic HTML", guide)
        self.assertIn("Do not install, generate from, or copy ready-made UI components", guide)
        self.assertFalse((self.root / ".agentforge/skills/shadcn").exists())

    def test_legacy_app_preserves_its_component_files_and_package_link(self):
        app = self.app()
        legacy_config = app / "components.json"
        component = app / "src/components/ui/button.tsx"
        component.parent.mkdir(parents=True)
        component.write_text("// existing component", encoding="utf-8")
        legacy_config.write_text("{}", encoding="utf-8")

        web_app.create_app(app, PAGES)

        self.assertTrue(web_app.legacy_kit(app))
        self.assertEqual(component.read_text(encoding="utf-8"), "// existing component")
        self.assertEqual(list(component.parent.iterdir()), [component])
        self.assertEqual((app / "node_modules").resolve(), self.root / "legacy-kit" / "node_modules")


class PageFileTests(unittest.TestCase):
    def test_a_route_becomes_a_readable_file_name(self):
        files = web_app.page_files(["/", "/orders", "/orders/[id]", "/staff/room-types/:roomTypeId/edit"])
        self.assertEqual(files, {"/": "home", "/orders": "orders", "/orders/[id]": "orders-id",
                                 "/staff/room-types/:roomTypeId/edit": "staff-room-types-roomtypeid-edit"})

    def test_two_routes_never_share_a_file(self):
        files = web_app.page_files(["/a-b", "/a/b", "/a_b"])
        self.assertEqual(len(set(files.values())), 3)


class CreatingTheAppTests(Scratch):
    def test_it_is_a_react_app_with_routes_and_no_premade_components(self):
        app = self.app()
        rows = web_app.create_app(app, PAGES)
        self.assertEqual([r["file"] for r in rows], ["home", "orders-id", "account"])
        for name in ("src/lib/router.tsx", "src/lib/session.tsx", "src/routes.ts", "src/demo.ts"):
            self.assertTrue((app / name).is_file(), name)
        for name in ("index.html", "package.json", "vite.config.ts", "tailwind.config.cjs", "src/main.tsx",
                     "src/App.tsx", "src/index.css", "src/components", "components.json"):
            self.assertFalse((app / name).exists(), name)
        routes = (app / "src" / "routes.ts").read_text(encoding="utf-8")
        self.assertIn('"route": "/orders/[id]"', routes)
        self.assertIn('"signedIn": true', routes)

    def test_it_has_no_accounts_unless_the_product_has_sign_in(self):
        app = self.app()
        web_app.create_app(app, PAGES)
        demo = (app / "src" / "demo.ts").read_text(encoding="utf-8")
        self.assertIn("export const accounts: Account[] = []", demo)
        self.assertIn('export const signInRoute: string = ""', demo)

    def test_the_demo_accounts_are_written_for_the_session_to_use(self):
        app = self.app()
        web_app.create_app(app, PAGES, accounts=ACCOUNTS, sign_in="/", sign_up={"route": "/account", "role_key": "baker"})
        demo = (app / "src" / "demo.ts").read_text(encoding="utf-8")
        self.assertIn('"email": "baker@example.com"', demo)
        self.assertIn('"landsOn": "/orders/[id]"', demo)
        self.assertIn('"canOpen": [\n      "/orders/[id]",\n      "/account"\n    ]', demo)
        self.assertIn('export const signInRoute: string = "/"', demo)
        self.assertIn('"roleKey": "baker"', demo.split("export const signUp")[1])

    def test_what_the_agent_wrote_is_kept_when_the_app_is_made_again_but_the_route_table_is_refreshed(self):
        app = self.app()
        web_app.create_app(app, PAGES[:1])
        (app / "src" / "pages").mkdir()
        (app / "src" / "pages" / "home.tsx").write_text("export default () => null", encoding="utf-8")
        (app / "src" / "App.tsx").write_text("// edited", encoding="utf-8")
        web_app.create_app(app, PAGES)
        self.assertEqual((app / "src" / "App.tsx").read_text(encoding="utf-8"), "// edited")
        self.assertTrue((app / "src" / "pages" / "home.tsx").is_file())
        self.assertIn("/account", (app / "src" / "routes.ts").read_text(encoding="utf-8"))

    def test_the_packages_are_linked_in_not_copied(self):
        app = self.app()
        web_app.create_app(app, PAGES)
        (self.kit / "node_modules" / "vite").mkdir(parents=True, exist_ok=True)
        (self.kit / "node_modules" / "vite" / "marker").write_text("x", encoding="utf-8")
        self.assertTrue((app / "node_modules" / "vite" / "marker").is_file())
        web_app.remove_app(app)
        self.assertFalse(app.exists())
        self.assertTrue((self.kit / "node_modules" / "vite" / "marker").is_file(), "removing an app must leave the packages")


class BundlingTests(Scratch):
    def made(self) -> Path:
        app = self.app()
        web_app.create_app(app, PAGES)
        return app

    def fake_vite(self, app: Path, ok: bool = True, text: str = ""):
        def run(args, cwd, timeout, env=None):
            if ok:
                (Path(cwd) / "dist").mkdir(exist_ok=True)
                (Path(cwd) / "dist" / "index.html").write_text("<html>app</html>", encoding="utf-8")
            return ok, text
        return mock.patch.object(web_app, "_run", run)

    def test_it_leaves_one_page_and_remembers_what_it_was_made_from(self):
        app = self.made()
        with mock.patch.object(web_app, "prepare_kit", return_value=(True, "")), self.fake_vite(app):
            ok, _ = web_app.bundle(app)
        self.assertTrue(ok)
        self.assertEqual(web_app.page(app), b"<html>app</html>")
        self.assertFalse((app / "dist").exists())
        self.assertFalse(web_app.stale(app))
        (app / "src" / "pages").mkdir()
        (app / "src" / "pages" / "home.tsx").write_text("export default () => null", encoding="utf-8")
        self.assertTrue(web_app.stale(app), "an edit after the bundle makes it stale")

    def test_a_missing_toolkit_is_said_plainly(self):
        app = self.made()
        with mock.patch.object(web_app, "prepare_kit", return_value=(False, "Node.js was not found")):
            self.assertEqual(web_app.bundle(app), (False, "Node.js was not found"))

    def test_a_bundle_that_fails_is_given_to_the_agent_to_fix_and_tried_again(self):
        app = self.made()
        outcomes = iter([(False, "Could not resolve ./missing"), (True, "")])

        def run(args, cwd, timeout, env=None):
            ok, text = next(outcomes)
            if ok:
                (Path(cwd) / "dist").mkdir(exist_ok=True)
                (Path(cwd) / "dist" / "index.html").write_text("<html>fixed</html>", encoding="utf-8")
            return ok, text

        told = []
        with mock.patch.object(web_app, "prepare_kit", return_value=(True, "")), mock.patch.object(web_app, "_run", run):
            web_app.ensure_built(app, told.append)
        self.assertEqual(told, ["Could not resolve ./missing"])
        self.assertEqual(web_app.page(app), b"<html>fixed</html>")

    def test_it_gives_up_after_two_repairs_and_says_what_the_bundler_said(self):
        app = self.made()
        told = []
        with mock.patch.object(web_app, "prepare_kit", return_value=(True, "")), self.fake_vite(app, ok=False, text="boom"):
            with self.assertRaisesRegex(web_app.BuildFailed, "boom"):
                web_app.ensure_built(app, told.append)
        self.assertEqual(len(told), 2)

    def test_the_agent_fix_is_a_run_of_its_own_with_the_bundler_text(self):
        session = mock.Mock(workspace=self.root, cancelled=False)
        app = web_app.app_dir(self.root, "wireframe")
        web_app.create_app(app, PAGES)
        outcomes = iter([(False, "Unexpected token"), (True, "")])

        def run(args, cwd, timeout, env=None):
            ok, text = next(outcomes)
            if ok:
                (Path(cwd) / "dist").mkdir(exist_ok=True)
                (Path(cwd) / "dist" / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            return ok, text

        with mock.patch.object(web_app, "prepare_kit", return_value=(True, "")), mock.patch.object(web_app, "_run", run), \
                mock.patch.object(web_app.bus, "log"):
            web_app.build_for(session, "prj", "wireframe")
        fix = session.run_direct.call_args.args[0]
        self.assertIn("Unexpected token", fix)
        self.assertIn(".agentforge/wireframe/app", fix)

    def test_the_preview_cannot_call_out(self):
        self.assertIn("connect-src 'none'", web_app.PREVIEW_POLICY)
        self.assertIn("default-src 'none'", web_app.PREVIEW_POLICY)
        self.assertIn("https://fonts.googleapis.com", web_app.PREVIEW_POLICY)

    def test_the_policy_is_the_first_thing_in_the_page(self):
        page = web_app.preview_page(b"<!doctype html><html><head><title>x</title></head><body></body></html>")
        head = page.index(b"<head>") + len(b"<head>")
        self.assertTrue(page[head:].startswith(b'<meta http-equiv="Content-Security-Policy"'))
        self.assertIn(b"connect-src 'none'", page)
        self.assertTrue(web_app.preview_page(b"<p>no head</p>").startswith(b"<meta"))


class CheckingThePagesTests(Scratch):
    DOM = ('<html><body><div id="root"></div><pre id="af-selftest" hidden>'
           '[{"route":"/admin/analytics","error":"ReferenceError: yen is not defined"},{"route":"/blank","error":"the page is blank"}]'
           '</pre></body></html>')

    def made(self) -> Path:
        app = self.app()
        web_app.create_app(app, PAGES)
        (app / web_app.BUNDLE).write_text("<html></html>", encoding="utf-8")
        return app

    def check(self, dom, browser=("edge", "chrome")):
        from ollama_terminal import screenshot

        with mock.patch.object(screenshot, "working_browser", return_value=browser),                 mock.patch.object(screenshot, "dump_dom", return_value=dom) as dump:
            return REAL_CHECK(self.made()), dump

    def test_the_screens_that_crash_are_named_with_what_went_wrong(self):
        found, dump = self.check(self.DOM)
        self.assertEqual(found, [("/admin/analytics", "ReferenceError: yen is not defined"), ("/blank", "the page is blank")])
        self.assertEqual(dump.call_args.args[1], "?selftest=1#/")

    def test_an_app_whose_screens_all_open_has_nothing_to_fix(self):
        self.assertEqual(self.check('<pre id="af-selftest" hidden>[]</pre>')[0], [])

    def test_an_empty_react_root_reports_an_entry_failure(self):
        found, _ = self.check('<html><body><div id="root"></div></body></html>')
        self.assertEqual(found[0][0], "/")
        self.assertIn("Router pages prop", found[0][1])

    def test_a_check_that_cannot_run_says_nothing_and_stops_nothing(self):
        self.assertIsNone(self.check(self.DOM, browser=None)[0], "no browser")
        self.assertIsNone(self.check("<html><body>the page never answered</body></html>")[0])
        self.assertIsNone(self.check('<pre id="af-selftest" hidden>not json</pre>')[0])
        from ollama_terminal import screenshot
        with mock.patch.object(screenshot, "working_browser", side_effect=OSError("no")):
            self.assertIsNone(REAL_CHECK(self.made()))

    def test_a_screen_that_crashes_is_given_to_the_agent_and_checked_again(self):
        app = self.made()
        told = []
        answers = iter([[("/admin/analytics", "ReferenceError: yen is not defined")], []])
        with mock.patch.object(web_app, "bundle", return_value=(True, "")),                 mock.patch.object(web_app, "check_pages", side_effect=lambda a: next(answers)):
            web_app.ensure_built(app, told.append)
        self.assertEqual(len(told), 1)
        self.assertIn("`/admin/analytics`: ReferenceError: yen is not defined", told[0])
        self.assertIn("bundle, but crash", told[0])

    def test_a_screen_that_still_crashes_after_the_tries_is_not_an_error(self):
        app = self.made()
        told = []
        with mock.patch.object(web_app, "bundle", return_value=(True, "")),                 mock.patch.object(web_app, "check_pages", return_value=[("/x", "TypeError: nope")]):
            web_app.ensure_built(app, told.append)          # bundled; the page shows its own error
        self.assertEqual(len(told), 2)

    def test_a_crash_fix_that_breaks_the_bundle_still_gets_its_own_repairs(self):
        # A fix of `incomeRows is not defined` took out the page's <AppShell opening tag: the bundle stopped building, and
        # with the tries the crash had used up, the journey test ended. The bundle has its own tries.
        app = self.made()
        told = []
        bundles = iter([(True, ""), (True, ""), (False, "dashboard.tsx:239:6: ERROR: Expected"), (True, "")])
        pages = iter([[("/dashboard", "ReferenceError: incomeRows is not defined")],
                      [("/dashboard", "ReferenceError: expenseRows is not defined")], []])
        with mock.patch.object(web_app, "bundle", side_effect=lambda a: next(bundles)), \
                mock.patch.object(web_app, "check_pages", side_effect=lambda a: next(pages)):
            web_app.ensure_built(app, told.append)
        self.assertEqual(len(told), 3)
        self.assertIn("Expected", told[2])

    def test_an_app_that_cannot_be_checked_is_taken_as_it_is(self):
        told = []
        with mock.patch.object(web_app, "bundle", return_value=(True, "")), mock.patch.object(web_app, "check_pages", return_value=None):
            web_app.ensure_built(self.made(), told.append)
        self.assertEqual(told, [])


class GeneratedStylesTests(Scratch):
    def test_a_resume_keeps_the_authored_wireframe_styles(self):
        app = self.app("wireframe") / "app"
        web_app.create_app(app, PAGES)
        style = app / "tailwind.config.cjs"
        style.write_text("module.exports = { theme: { extend: {} } };", encoding="utf-8")
        web_app.sync_kit_files(app)
        self.assertEqual(style.read_text(encoding="utf-8"), "module.exports = { theme: { extend: {} } };")

    def test_wireframe_setup_and_grayscale_are_prompt_requirements(self):
        from server_modules import prompts
        prompt = prompts.load("wireframe/generate", setup=prompts.load("shared/preview-app"))
        self.assertIn("grayscale", prompt)
        self.assertIn("index.html", prompt)
        self.assertIn("tailwind.config.cjs", prompt)
        self.assertIn("SessionProvider", prompt)


class KitOwnedFilesTests(Scratch):
    def test_the_router_and_the_session_are_written_again_when_the_studio_has_changed_them(self):
        app = self.app()
        web_app.create_app(app, PAGES)
        router = app / "src" / "lib" / "router.tsx"
        router.write_text("// an older router", encoding="utf-8")
        (app / "src" / "App.tsx").write_text("// the agent's own App", encoding="utf-8")
        web_app.sync_kit_files(app)
        self.assertEqual(router.read_bytes(), (web_app.RUNTIME / "router.tsx").read_bytes())
        self.assertEqual((app / "src" / "App.tsx").read_text(encoding="utf-8"), "// the agent's own App")

    def test_a_page_that_crashes_is_caught_and_the_selftest_is_in_the_router(self):
        router = (web_app.RUNTIME / "router.tsx").read_text(encoding="utf-8")
        for needle in ("getDerivedStateFromError", "data-af-error", "window.__afErrors", 'id="af-selftest"', "selftest"):
            self.assertIn(needle, router)

    def test_a_product_with_no_page_at_the_root_opens_on_its_sign_in_page_or_its_first_screen(self):
        router = (web_app.RUNTIME / "router.tsx").read_text(encoding="utf-8")
        self.assertIn('import { signInRoute } from "@/demo";', router)
        self.assertIn('path === "/"', router)
        self.assertIn("matchRoute(signInRoute) ? signInRoute : routes[0]?.route", router)

    def test_the_session_says_who_is_signed_in_for_the_browser_that_clicks_through_the_prototype(self):
        session = (web_app.RUNTIME / "session.tsx").read_text(encoding="utf-8")
        self.assertIn("__afUser", session)


class KitTests(Scratch):
    def test_the_kit_is_only_installed_once(self):
        with mock.patch.object(web_app, "_npm", return_value="npm"), mock.patch.object(web_app, "node_exe", return_value="node"):
            def install(args, cwd, timeout, env=None):
                (Path(cwd) / "node_modules" / "vite" / "bin").mkdir(parents=True, exist_ok=True)
                (Path(cwd) / "node_modules" / "vite" / "bin" / "vite.js").write_text("", encoding="utf-8")
                return True, ""
            with mock.patch.object(web_app, "_run", side_effect=install) as run:
                self.assertEqual(web_app.prepare_kit(), (True, ""))
                self.assertEqual(web_app.prepare_kit(), (True, ""))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][1], "ci", "the lock pins the packages")
        self.assertTrue(web_app.kit_ready())

    def test_a_lock_that_does_not_fit_falls_back_to_a_plain_install(self):
        calls = []
        with mock.patch.object(web_app, "_npm", return_value="npm"), mock.patch.object(web_app, "node_exe", return_value="node"):
            def install(args, cwd, timeout, env=None):
                calls.append(args[1])
                if args[1] == "ci":
                    return False, "lock mismatch"
                (Path(cwd) / "node_modules" / "vite" / "bin").mkdir(parents=True, exist_ok=True)
                (Path(cwd) / "node_modules" / "vite" / "bin" / "vite.js").write_text("", encoding="utf-8")
                return True, ""
            with mock.patch.object(web_app, "_run", side_effect=install):
                self.assertEqual(web_app.prepare_kit(), (True, ""))
        self.assertEqual(calls, ["ci", "install"])

    def test_no_node_is_said_plainly(self):
        with mock.patch.object(web_app, "node_exe", return_value=None):
            ok, text = web_app.prepare_kit()
        self.assertFalse(ok)
        self.assertIn("Node.js", text)

    def test_new_kit_has_framework_packages_and_legacy_keeps_its_old_dependencies(self):
        kit = json.loads((web_app.KIT_SOURCE / "package.json").read_text(encoding="utf-8"))
        names = set(kit["dependencies"]) | set(kit["devDependencies"])
        for package in ("react", "react-dom", "lucide-react", "vite", "tailwindcss", "vite-plugin-singlefile"):
            self.assertIn(package, names)
        lock = json.loads((web_app.KIT_SOURCE / "package-lock.json").read_text(encoding="utf-8"))
        self.assertFalse(any("@radix-ui/" in name for name in lock["packages"]))
        legacy = json.loads((web_app.KIT_SOURCE / "legacy" / "package.json").read_text(encoding="utf-8"))
        self.assertIn("@radix-ui/react-dialog", legacy["dependencies"])


if __name__ == "__main__":
    unittest.main()
