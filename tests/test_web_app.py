"""The React apps the wireframe and the prototype are made of: the skill, the app that is created, and the bundling."""
from __future__ import annotations

import io
import json
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
        patch = mock.patch.object(web_app, "kit_dir", lambda: self.kit)
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


class CopyingTheAppTests(Scratch):
    def test_the_prototype_starts_as_a_copy_that_leaves_the_wireframe_alone(self):
        wire, proto = self.app("wire"), self.app("proto")
        web_app.create_app(wire, "App", PAGES)
        (wire / "src" / "pages").mkdir()
        (wire / "src" / "pages" / "home.tsx").write_text("export default () => 'wire'", encoding="utf-8")
        (wire / "bundle.html").write_text("<html>wire</html>", encoding="utf-8")
        (wire / "dist").mkdir()
        web_app.copy_app(wire, proto)
        self.assertEqual((proto / "src" / "pages" / "home.tsx").read_text(encoding="utf-8"), "export default () => 'wire'")
        self.assertFalse((proto / "bundle.html").exists())
        self.assertFalse((proto / "dist").exists())
        (proto / "src" / "pages" / "home.tsx").write_text("export default () => 'proto'", encoding="utf-8")
        self.assertEqual((wire / "src" / "pages" / "home.tsx").read_text(encoding="utf-8"), "export default () => 'wire'")


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
