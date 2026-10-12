"""The React apps the wireframe and the prototype are made of: the skill, the app that is created, and the bundling."""
from __future__ import annotations

import io
import json
import re
import sys
import tarfile
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
        for patch in (mock.patch.object(web_app, "kit_dir", lambda: self.kit),
                      mock.patch.object(web_app, "check_pages", return_value=None)):
            patch.start()
            self.addCleanup(patch.stop)

    def app(self, name: str = "app") -> Path:
        return self.root / name


class SkillTests(unittest.TestCase):
    def test_the_skill_is_anthropics_own_unchanged(self):
        text = (web_app.SKILL_SOURCE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: web-artifacts-builder", text)
        self.assertIn("**Stack**: React 18 + TypeScript + Vite + Parcel (bundling) + Tailwind CSS + shadcn/ui", text)
        self.assertIn("Apache License", (web_app.SKILL_SOURCE / "LICENSE.txt").read_text(encoding="utf-8"))
        for name in ("init-artifact.sh", "bundle-artifact.sh", "shadcn-components.tar.gz"):
            self.assertTrue((web_app.SKILL_SOURCE / "scripts" / name).is_file(), name)

    def test_the_agent_is_given_the_skill_inside_its_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            relative = web_app.stage_skill(Path(tmp))
            self.assertEqual(relative, ".agentforge/skills/web-artifacts-builder")
            self.assertEqual((Path(tmp) / relative / "SKILL.md").read_bytes(), (web_app.SKILL_SOURCE / "SKILL.md").read_bytes())
            self.assertTrue((Path(tmp) / relative / "LICENSE.txt").is_file())
            self.assertFalse((Path(tmp) / relative / "scripts").exists())


class ShadcnTests(Scratch):
    def test_the_shadcn_skill_is_shadcn_uis_own_unchanged_with_its_licence_and_where_it_came_from(self):
        text = (web_app.SHADCN_SOURCE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: shadcn", text)
        self.assertIn("rules/forms.md", text)
        self.assertIn("MIT License", (web_app.SHADCN_SOURCE / "LICENSE.txt").read_text(encoding="utf-8"))
        self.assertIn("https://github.com/shadcn-ui/ui", (web_app.SHADCN_SOURCE / "SOURCE.md").read_text(encoding="utf-8"))
        for name in ("forms", "composition", "styling", "icons", "base-vs-radix"):
            self.assertTrue((web_app.SHADCN_SOURCE / "rules" / f"{name}.md").is_file(), name)

    def test_the_agent_is_given_the_shadcn_skill_with_its_rules_inside_its_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            relative = web_app.stage_shadcn(Path(tmp))
            self.assertEqual(relative, ".agentforge/skills/shadcn")
            self.assertEqual((Path(tmp) / relative / "SKILL.md").read_bytes(), (web_app.SHADCN_SOURCE / "SKILL.md").read_bytes())
            self.assertTrue((Path(tmp) / relative / "rules" / "forms.md").is_file())

    def test_the_components_the_archive_lacks_are_added_to_a_new_app_and_never_over_one_the_agent_has_written(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES)
        ui = app / "src" / "components" / "ui"
        for name in ("field", "input-group", "empty", "spinner", "item", "kbd", "button-group", "native-select", "pagination",
                     "alert-dialog", "input-otp"):
            self.assertTrue((ui / f"{name}.tsx").is_file(), name)
        self.assertTrue((ui / "button.tsx").is_file())                   # the archive's own are still there
        (ui / "empty.tsx").write_text("// the agent's own", encoding="utf-8")
        web_app.create_app(app, "App", PAGES)
        self.assertEqual((ui / "empty.tsx").read_text(encoding="utf-8"), "// the agent's own")

    def test_every_component_is_written_for_this_app_and_every_package_it_imports_is_installed_by_the_kit(self):
        package = json.loads((web_app.KIT_SOURCE / "package.json").read_text(encoding="utf-8"))
        installed = {*package["dependencies"], *package["devDependencies"]}
        for path in sorted((web_app.KIT_SOURCE / "components").glob("*.tsx")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('from "cn"', text, path.name)
            self.assertNotIn('from "radix-ui"', text, path.name)
            self.assertNotIn("@/registry", text, path.name)
            self.assertNotIn("shadow-xs", text, path.name)
            for name in re.findall(r'from "([^"./@][^"]*|@[^"/]+/[^"/]+)', text):
                package_name = name if name.startswith("@") else name.split("/")[0]
                if package_name in {"react"}:
                    continue
                self.assertIn(package_name, installed, f"{path.name} imports {package_name}")
            for local in re.findall(r'from "@/components/ui/([^"]+)"', text):
                archive = (web_app.KIT_SOURCE / "components" / f"{local}.tsx").is_file() or local in {
                    "button", "input", "textarea", "label", "separator"}
                self.assertTrue(archive, f"{path.name} imports ui/{local}")

    def test_a_copy_with_the_mistake_an_earlier_kit_had_is_made_right_and_the_agents_own_is_not_touched(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES)
        ui = app / "src" / "components" / "ui"
        (ui / "item.tsx").write_text('const Comp = asChild ? Slot.Root : "div"', encoding="utf-8")
        (ui / "kbd.tsx").write_text("// the agent's own kbd", encoding="utf-8")
        web_app.create_app(app, "App", PAGES)
        self.assertNotIn("Slot.Root", (ui / "item.tsx").read_text(encoding="utf-8"))
        self.assertEqual((ui / "item.tsx").read_bytes(), (web_app.KIT_SOURCE / "components" / "item.tsx").read_bytes())
        self.assertEqual((ui / "kbd.tsx").read_text(encoding="utf-8"), "// the agent's own kbd")

    def test_no_component_uses_the_names_of_the_single_radix_package_the_kit_does_not_install(self):
        for path in sorted((web_app.KIT_SOURCE / "components").glob("*.tsx")):
            self.assertNotIn("Slot.Root", path.read_text(encoding="utf-8"), path.name)

    def test_the_kit_has_the_version_of_the_day_picker_the_skills_calendar_is_written_for(self):
        package = json.loads((web_app.KIT_SOURCE / "package.json").read_text(encoding="utf-8"))
        self.assertTrue(package["dependencies"]["react-day-picker"].startswith("^9"))
        lock = json.loads((web_app.KIT_SOURCE / "package-lock.json").read_text(encoding="utf-8"))
        self.assertTrue(lock["packages"]["node_modules/react-day-picker"]["version"].startswith("9."))

    def test_the_kit_installs_the_plugin_the_field_components_need_for_container_queries(self):
        package = json.loads((web_app.KIT_SOURCE / "package.json").read_text(encoding="utf-8"))
        self.assertIn("@tailwindcss/container-queries", package["devDependencies"])
        config = (web_app.KIT_SOURCE / "app" / "tailwind.config.cjs").read_text(encoding="utf-8")
        self.assertIn('require("@tailwindcss/container-queries")', config)
        lock = json.loads((web_app.KIT_SOURCE / "package-lock.json").read_text(encoding="utf-8"))
        for name in ("@tailwindcss/container-queries", "@radix-ui/react-alert-dialog", "input-otp"):
            self.assertIn(f"node_modules/{name}", lock["packages"], name)


class PageFileTests(unittest.TestCase):
    def test_a_route_becomes_a_readable_file_name(self):
        files = web_app.page_files(["/", "/orders", "/orders/[id]", "/staff/room-types/:roomTypeId/edit"])
        self.assertEqual(files, {"/": "home", "/orders": "orders", "/orders/[id]": "orders-id",
                                 "/staff/room-types/:roomTypeId/edit": "staff-room-types-roomtypeid-edit"})

    def test_two_routes_never_share_a_file(self):
        files = web_app.page_files(["/a-b", "/a/b", "/a_b"])
        self.assertEqual(len(set(files.values())), 3)


class CreatingTheAppTests(Scratch):
    def test_it_is_a_react_app_with_the_shadcn_components_and_the_route_table(self):
        app = self.app()
        rows = web_app.create_app(app, "Sweet Crumbs", PAGES)
        self.assertEqual([r["file"] for r in rows], ["home", "orders-id", "account"])
        for name in ("index.html", "vite.config.ts", "tailwind.config.cjs", "postcss.config.cjs", "tsconfig.json", "components.json",
                     "src/main.tsx", "src/App.tsx", "src/index.css", "src/lib/router.tsx", "src/lib/session.tsx",
                     "src/lib/utils.ts", "src/components/ui/button.tsx", "src/components/ui/card.tsx", "src/hooks/use-toast.ts"):
            self.assertTrue((app / name).is_file(), name)
        self.assertIn("<title>Sweet Crumbs</title>", (app / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((app / "package.json").read_text(encoding="utf-8"))["name"], "sweet-crumbs")
        routes = (app / "src" / "routes.ts").read_text(encoding="utf-8")
        self.assertIn('"route": "/orders/[id]"', routes)
        self.assertIn('"signedIn": true', routes)

    def test_it_has_no_accounts_unless_the_product_has_sign_in(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES)
        demo = (app / "src" / "demo.ts").read_text(encoding="utf-8")
        self.assertIn("export const accounts: Account[] = []", demo)
        self.assertIn('export const signInRoute: string = ""', demo)

    def test_the_demo_accounts_are_written_for_the_session_to_use(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES, accounts=ACCOUNTS, sign_in="/", sign_up={"route": "/account", "role_key": "baker"})
        demo = (app / "src" / "demo.ts").read_text(encoding="utf-8")
        self.assertIn('"email": "baker@example.com"', demo)
        self.assertIn('"landsOn": "/orders/[id]"', demo)
        self.assertIn('"canOpen": [\n      "/orders/[id]",\n      "/account"\n    ]', demo)
        self.assertIn('export const signInRoute: string = "/"', demo)
        self.assertIn('"roleKey": "baker"', demo.split("export const signUp")[1])

    def test_what_the_agent_wrote_is_kept_when_the_app_is_made_again_but_the_route_table_is_refreshed(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES[:1])
        (app / "src" / "pages").mkdir()
        (app / "src" / "pages" / "home.tsx").write_text("export default () => null", encoding="utf-8")
        (app / "src" / "App.tsx").write_text("// edited", encoding="utf-8")
        web_app.create_app(app, "App", PAGES)
        self.assertEqual((app / "src" / "App.tsx").read_text(encoding="utf-8"), "// edited")
        self.assertTrue((app / "src" / "pages" / "home.tsx").is_file())
        self.assertIn("/account", (app / "src" / "routes.ts").read_text(encoding="utf-8"))

    def test_the_packages_are_linked_in_not_copied(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES)
        (self.kit / "node_modules" / "vite").mkdir(parents=True, exist_ok=True)
        (self.kit / "node_modules" / "vite" / "marker").write_text("x", encoding="utf-8")
        self.assertTrue((app / "node_modules" / "vite" / "marker").is_file())
        web_app.remove_app(app)
        self.assertFalse(app.exists())
        self.assertTrue((self.kit / "node_modules" / "vite" / "marker").is_file(), "removing an app must leave the packages")

    def test_an_archive_cannot_write_outside_the_app(self):
        archive = self.root / "components.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name, body in (("components/ui/ok.tsx", b"ok"), ("../escaped.txt", b"no")):
                info = tarfile.TarInfo(name)
                info.size = len(body)
                tar.addfile(info, io.BytesIO(body))
        app = self.app()
        (app / "src").mkdir(parents=True)
        with mock.patch.object(web_app, "COMPONENTS_ARCHIVE", archive):
            web_app._extract_components(app)
        self.assertTrue((app / "src" / "components" / "ui" / "ok.tsx").is_file())
        self.assertFalse((app / "escaped.txt").exists())
        self.assertFalse((self.root / "escaped.txt").exists())


class BundlingTests(Scratch):
    def made(self) -> Path:
        app = self.app()
        web_app.create_app(app, "App", PAGES)
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
        web_app.create_app(app, "App", PAGES)
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
        web_app.create_app(app, "App", PAGES)
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

    def test_an_app_that_cannot_be_checked_is_taken_as_it_is(self):
        told = []
        with mock.patch.object(web_app, "bundle", return_value=(True, "")), mock.patch.object(web_app, "check_pages", return_value=None):
            web_app.ensure_built(self.made(), told.append)
        self.assertEqual(told, [])


class GreyWireframeTests(Scratch):
    """A wireframe is black, white and grey: the Studio writes a palette with no colour in it into the app, whatever the pages say."""

    def wireframe(self):
        return web_app.app_dir(self.root, "wireframe")

    def test_a_wireframe_app_gets_a_tailwind_config_in_which_every_colour_name_is_grey(self):
        app = self.wireframe()
        web_app.create_app(app, "App", PAGES)
        text = (app / "tailwind.config.cjs").read_text(encoding="utf-8")
        for name in ("red", "green", "amber", "blue", "emerald", "rose"):
            self.assertIn(f'"{name}"', text)
        self.assertIn("config.theme.colors = {", text)
        self.assertIn("config.theme.extend.colors.destructive", text)
        self.assertIn("module.exports = config;", text)
        self.assertNotIn("module.exports = {", text)
        self.assertIn('border: "hsl(var(--border))"', text)               # the shadcn tokens are still the kit's

    def test_the_generated_config_is_valid_and_no_colour_name_is_anything_but_the_grey_scale(self):
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        app = self.wireframe()
        web_app.create_app(app, "App", PAGES)
        config = app / "tailwind.config.cjs"
        body = config.read_text(encoding="utf-8").replace(
            'plugins: [require("tailwindcss-animate"), require("@tailwindcss/container-queries")],', "plugins: [],")
        config.write_text(body, encoding="utf-8")
        probe = ("const c = require(process.argv[1]); const out = {red: c.theme.colors.red, rose: c.theme.colors.rose, "
                 "destructive: c.theme.extend.colors.destructive, border: c.theme.extend.colors.border}; "
                 "console.log(JSON.stringify(out))")
        done = subprocess.run([node, "-e", probe, str(config)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        seen = json.loads(done.stdout)
        self.assertEqual(seen["red"], web_app.GREY_SCALE)
        self.assertEqual(seen["rose"], web_app.GREY_SCALE)
        self.assertEqual(seen["destructive"]["DEFAULT"], "#3f3f46")
        self.assertEqual(seen["border"], "hsl(var(--border))")

    def test_the_destructive_colour_in_the_stylesheet_is_grey_too(self):
        app = self.wireframe()
        web_app.create_app(app, "App", PAGES)
        css = (app / "src" / "index.css").read_text(encoding="utf-8")
        self.assertNotIn("0 84.2% 60.2%", css)
        self.assertIn("--destructive: 0 0% 25%;", css)

    def test_a_prototype_keeps_its_colours(self):
        app = web_app.app_dir(self.root, "prototype")
        web_app.create_app(app, "App", PAGES)
        self.assertEqual((app / "tailwind.config.cjs").read_bytes(), (web_app.KIT_SOURCE / "app" / "tailwind.config.cjs").read_bytes())
        self.assertIn("0 84.2% 60.2%", (app / "src" / "index.css").read_text(encoding="utf-8"))

    def test_a_wireframe_made_before_the_palette_was_grey_becomes_grey_when_it_is_bundled_again(self):
        app = self.wireframe()
        web_app.create_app(app, "App", PAGES)
        (app / "tailwind.config.cjs").write_bytes((web_app.KIT_SOURCE / "app" / "tailwind.config.cjs").read_bytes())
        css = app / "src" / "index.css"
        css.write_text(css.read_text(encoding="utf-8").replace("--destructive: 0 0% 25%;", "--destructive: 0 84.2% 60.2%;"), encoding="utf-8")
        web_app.sync_kit_files(app)
        self.assertIn("config.theme.extend.colors.destructive", (app / "tailwind.config.cjs").read_text(encoding="utf-8"))
        self.assertIn("--destructive: 0 0% 25%;", css.read_text(encoding="utf-8"))

    def test_the_wireframe_prompts_ask_for_grey_in_the_international_low_fidelity_style_and_name_red(self):
        from server_modules import prompts

        generate = prompts.load("wireframe/generate", request="x", skill="s", shadcn="sh", app="a", routes="r", resume="")
        for expected in ("international low-fidelity wireframe", "black, white and neutral greys only", "and that includes red",
                         "Showing state without colour", "A destructive action is a dark outlined button",
                         "light grey box with a thin diagonal cross", "No colour anywhere: search the pages",
                         "no red, no colour of any hue"):
            self.assertIn(expected, generate)
        edit = prompts.load("wireframe/edit", request="x", skill="s", app="a", where="")
        for expected in ("The wireframes stay low fidelity, whatever the request says", "must not turn into a high-fidelity design",
                         "no colour of any hue (not even red for an error or a delete)", "colour and visual styling are for the prototype",
                         "more polished", "src/components/layout/", "Write no colour value of your own"):
            self.assertIn(expected, edit)
        self.assertNotIn("{{", edit)


class KitOwnedFilesTests(Scratch):
    def test_the_router_and_the_session_are_written_again_when_the_studio_has_changed_them(self):
        app = self.app()
        web_app.create_app(app, "App", PAGES)
        router = app / "src" / "lib" / "router.tsx"
        router.write_text("// an older router", encoding="utf-8")
        (app / "src" / "App.tsx").write_text("// the agent's own App", encoding="utf-8")
        web_app.sync_kit_files(app)
        self.assertEqual(router.read_bytes(), (web_app.KIT_SOURCE / "app" / "src" / "lib" / "router.tsx").read_bytes())
        self.assertEqual((app / "src" / "App.tsx").read_text(encoding="utf-8"), "// the agent's own App")

    def test_a_page_that_crashes_is_caught_and_the_selftest_is_in_the_router(self):
        router = (web_app.KIT_SOURCE / "app" / "src" / "lib" / "router.tsx").read_text(encoding="utf-8")
        for needle in ("getDerivedStateFromError", "data-af-error", "window.__afErrors", 'id="af-selftest"', "selftest"):
            self.assertIn(needle, router)

    def test_a_product_with_no_page_at_the_root_opens_on_its_sign_in_page_or_its_first_screen(self):
        router = (web_app.KIT_SOURCE / "app" / "src" / "lib" / "router.tsx").read_text(encoding="utf-8")
        self.assertIn('import { signInRoute } from "@/demo";', router)
        self.assertIn('path === "/"', router)
        self.assertIn("matchRoute(signInRoute) ? signInRoute : routes[0]?.route", router)

    def test_the_session_says_who_is_signed_in_for_the_browser_that_clicks_through_the_prototype(self):
        session = (web_app.KIT_SOURCE / "app" / "src" / "lib" / "session.tsx").read_text(encoding="utf-8")
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

    def test_the_kit_names_every_package_the_skill_installs(self):
        kit = json.loads((web_app.KIT_SOURCE / "package.json").read_text(encoding="utf-8"))
        names = set(kit["dependencies"]) | set(kit["devDependencies"])
        skill = (web_app.SKILL_SOURCE / "scripts" / "init-artifact.sh").read_text(encoding="utf-8")
        for package in ("@radix-ui/react-dialog", "@radix-ui/react-tabs", "lucide-react", "class-variance-authority", "tailwind-merge",
                        "sonner", "cmdk", "vaul", "embla-carousel-react", "react-day-picker", "react-hook-form", "zod", "date-fns"):
            self.assertIn(package, skill)
            self.assertIn(package, names)
        for package in ("react", "react-dom", "vite", "recharts", "tailwindcss", "vite-plugin-singlefile"):
            self.assertIn(package, names)


if __name__ == "__main__":
    unittest.main()
