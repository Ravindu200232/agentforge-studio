"""The JSX app the wireframe and the prototype are made of: the vendored skill, the shared dependency
store, the copy that turns the wireframe into the prototype, and what the preview serves."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules import config, prompts, store, web_app  # noqa: E402

SKILL = ROOT / "prompts" / "design" / "skills" / "web-artifacts-builder"


class VendoredSkillTests(unittest.TestCase):
    def test_the_official_skill_is_there_unchanged_and_the_loader_finds_it(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: web-artifacts-builder\n"))
        self.assertIn("Stack**: React 18 + TypeScript + Vite + Parcel", text)
        self.assertIn("Apache License", (SKILL / "LICENSE.txt").read_text(encoding="utf-8"))
        self.assertIn("web-artifacts-builder", prompts.skill("design", "web-artifacts-builder"))
        self.assertIn("web-artifacts-builder", {row["slug"] for row in prompts.catalogue("design", kind="skills")})

    def test_the_official_scripts_keep_unix_line_endings_and_the_tarball_is_whole(self):
        for name in ("init-artifact.sh", "bundle-artifact.sh"):
            self.assertNotIn(b"\r", (SKILL / "scripts" / name).read_bytes(), name)
        with tarfile.open(SKILL / "scripts" / "shadcn-components.tar.gz") as archive:
            names = [m.name for m in archive.getmembers() if m.isfile()]
        self.assertIn("components/ui/button.tsx", [n.lstrip("./") for n in names])
        self.assertGreaterEqual(len([n for n in names if "/ui/" in n]), 40)

    def test_the_toolkit_is_locked_and_dated(self):
        runtime = SKILL / "scripts" / "runtime"
        package = json.loads((runtime / "package.json").read_text(encoding="utf-8"))
        for needed in ("react", "react-router-dom", "framer-motion", "recharts", "lucide-react", "parcel", "html-inline"):
            self.assertIn(needed, {**package["dependencies"], **package["devDependencies"]})
        self.assertTrue((runtime / "package-lock.json").is_file())
        self.assertRegex((runtime / ".npmrc").read_text(encoding="utf-8"), r"(?m)^before=\d{4}-\d{2}-\d{2}$")


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store_dir = root / "store"
        (self.store_dir / "node_modules" / "react").mkdir(parents=True)
        (self.store_dir / "node_modules" / "react" / "index.js").write_text("// react", encoding="utf-8")
        patches = [
            mock.patch.object(config, "WORKSPACES", root / "workspaces"),
            mock.patch.object(config, "PROJECTS_FILE", root / ".agentforge-server" / "projects.json"),
            mock.patch.dict(os.environ, {"AGENTFORGE_WEB_RUNTIME": str(self.store_dir)}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.project = store.create(idea="A shop")["id"]

    def make_wireframe(self) -> Path:
        app = web_app.app_dir(self.project, "wireframe")
        (app / "src" / "pages").mkdir(parents=True)
        (app / "index.html").write_text("<div id=root></div>", encoding="utf-8")
        (app / "package.json").write_text("{}", encoding="utf-8")
        (app / "src" / "App.tsx").write_text("export default () => <h1>Orders</h1>", encoding="utf-8")
        (app / "src" / "pages" / "Home.tsx").write_text("export default () => <h1>Home</h1>", encoding="utf-8")
        (app / "dist").mkdir()
        (app / "dist" / "index.js").write_text("// built", encoding="utf-8")
        (app / "bundle.html").write_text("<html>built</html>", encoding="utf-8")
        (app / ".parcel-cache").mkdir()
        (app / ".parcel-cache" / "data").write_text("x", encoding="utf-8")
        web_app.link_node_modules(app)
        return app

    def test_the_two_apps_live_side_by_side_under_the_record(self):
        record = config.record_dir(self.project)
        self.assertEqual(web_app.app_dir(self.project, "wireframe"), record / "wireframe" / "app")
        self.assertEqual(web_app.app_dir(self.project, "prototype"), record / "prototype" / "app")
        with self.assertRaises(ValueError):
            web_app.app_dir(self.project, "build")

    def test_the_prototype_is_a_copy_the_wireframe_is_never_touched(self):
        wireframe = self.make_wireframe()
        before = {p.relative_to(wireframe).as_posix(): p.read_bytes() for p in wireframe.rglob("*")
                  if p.is_file() and "node_modules" not in p.parts}
        prototype = web_app.app_dir(self.project, "prototype")

        web_app.copy_app(wireframe, prototype)
        (prototype / "src" / "App.tsx").write_text("export default () => <h1>Orders, designed</h1>", encoding="utf-8")
        (prototype / "src" / "New.tsx").write_text("export const n = 1", encoding="utf-8")

        after = {p.relative_to(wireframe).as_posix(): p.read_bytes() for p in wireframe.rglob("*")
                 if p.is_file() and "node_modules" not in p.parts}
        self.assertEqual(before, after)
        self.assertEqual((prototype / "src" / "pages" / "Home.tsx").read_text(encoding="utf-8"),
                         "export default () => <h1>Home</h1>")
        for built in ("dist", "bundle.html", ".parcel-cache"):
            self.assertFalse((prototype / built).exists(), f"{built} must be rebuilt, not copied")
        self.assertTrue((prototype / "node_modules" / "react" / "index.js").is_file())

    def test_copying_again_replaces_the_prototype_and_never_empties_the_shared_store(self):
        wireframe = self.make_wireframe()
        prototype = web_app.app_dir(self.project, "prototype")
        web_app.copy_app(wireframe, prototype)
        (prototype / "src" / "Stale.tsx").write_text("stale", encoding="utf-8")

        web_app.copy_app(wireframe, prototype)

        self.assertFalse((prototype / "src" / "Stale.tsx").exists())
        self.assertTrue((self.store_dir / "node_modules" / "react" / "index.js").is_file())
        web_app.remove_app(prototype)
        self.assertFalse(prototype.exists())
        self.assertTrue((self.store_dir / "node_modules" / "react" / "index.js").is_file(),
                        "deleting an app must not follow node_modules into the shared store")

    def test_copying_needs_an_app_to_copy(self):
        with self.assertRaises(FileNotFoundError):
            web_app.copy_app(web_app.app_dir(self.project, "wireframe"), web_app.app_dir(self.project, "prototype"))

    def test_built_and_stale_follow_the_bundle_and_the_source(self):
        self.assertFalse(web_app.built(self.project, "wireframe"))
        self.assertFalse(web_app.stale(self.project, "wireframe"))   # nothing drawn yet: nothing to rebuild
        app = self.make_wireframe()
        self.assertTrue(web_app.built(self.project, "wireframe"))
        old = (app / "bundle.html").stat().st_mtime - 100
        os.utime(app / "src" / "App.tsx", (old - 100, old - 100))
        os.utime(app / "src" / "pages" / "Home.tsx", (old - 100, old - 100))
        os.utime(app / "index.html", (old - 100, old - 100))
        os.utime(app / "package.json", (old - 100, old - 100))
        self.assertFalse(web_app.stale(self.project, "wireframe"))
        (app / "src" / "App.tsx").write_text("export default () => <h1>changed</h1>", encoding="utf-8")
        self.assertTrue(web_app.stale(self.project, "wireframe"))
        (app / "bundle.html").unlink()
        self.assertFalse(web_app.built(self.project, "wireframe"))

    def test_the_fingerprint_changes_with_the_source_only(self):
        app = self.make_wireframe()
        first = web_app.fingerprint(app)
        (app / "bundle.html").write_text("<html>rebuilt</html>", encoding="utf-8")
        self.assertEqual(first, web_app.fingerprint(app))
        (app / "src" / "pages" / "Home.tsx").write_text("export default () => <h1>Home, longer</h1>", encoding="utf-8")
        self.assertNotEqual(first, web_app.fingerprint(app))

    def test_the_preview_serves_the_bundle_and_built_files_and_nothing_else(self):
        self.make_wireframe()
        served = web_app.served_file(self.project, "wireframe", "bundle.html")
        self.assertEqual(served.name, "bundle.html")
        self.assertEqual(web_app.served_file(self.project, "wireframe", "").name, "bundle.html")
        self.assertEqual(web_app.served_file(self.project, "wireframe", "index.js").name, "index.js")
        for refused in ("src/App.tsx", "package.json", "../../srs/srs.json", "..\\..\\x", "node_modules/react/index.js"):
            self.assertIsNone(web_app.served_file(self.project, "wireframe", refused), refused)

    def test_the_preview_headers_stop_a_page_calling_out_or_submitting_anywhere(self):
        csp = web_app.PREVIEW_HEADERS["Content-Security-Policy"]
        for directive in ("connect-src 'none'", "form-action 'none'", "frame-src 'none'", "base-uri 'none'"):
            self.assertIn(directive, csp)

    def test_a_label_is_retyped_in_the_source_only_when_it_is_found_exactly_once(self):
        app = self.make_wireframe()
        done = web_app.replace_text(self.project, "wireframe", "Orders", "Your orders")
        self.assertEqual(done, {"ok": True, "file": "src/App.tsx"})
        self.assertIn("Your orders", (app / "src" / "App.tsx").read_text(encoding="utf-8"))

        (app / "src" / "pages" / "Home.tsx").write_text("<h1>Your orders</h1>", encoding="utf-8")
        several = web_app.replace_text(self.project, "wireframe", "Your orders", "Orders")
        self.assertFalse(several["ok"])
        self.assertEqual(sorted(several["where"]), ["src/App.tsx", "src/pages/Home.tsx"])
        self.assertFalse(web_app.replace_text(self.project, "wireframe", "no such text", "x")["ok"])
        self.assertFalse(web_app.replace_text(self.project, "wireframe", "", "x")["ok"])

    def test_staging_the_skill_copies_the_tree_as_bytes_and_points_it_at_the_store(self):
        relative = web_app.stage_skill(self.project)
        staged = config.workspace_for(self.project) / relative
        self.assertEqual(relative, ".agentforge/skills/web-artifacts-builder")
        for name in ("SKILL.md", "scripts/init-artifact.mjs", "scripts/bundle-artifact.mjs",
                     "scripts/shadcn-components.tar.gz", "scripts/init-artifact.sh"):
            self.assertEqual((staged / name).read_bytes(), (SKILL / name).read_bytes(), name)
        pinned = json.loads((staged / "scripts" / "runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(pinned["runtime"]), self.store_dir.resolve())

    def test_the_store_is_ready_only_when_it_was_installed_from_this_toolkit(self):
        self.assertFalse(web_app.runtime_ready())
        package = json.loads((SKILL / "scripts" / "runtime" / "package.json").read_text(encoding="utf-8"))
        for name in {**package["dependencies"], **package["devDependencies"]}:
            folder = self.store_dir / "node_modules" / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "package.json").write_text("{}", encoding="utf-8")
        self.assertFalse(web_app.runtime_ready(), "packages alone are not enough: no signature yet")
        (self.store_dir / "node_modules" / ".agentforge-runtime").write_text("stale", encoding="utf-8")
        self.assertFalse(web_app.runtime_ready())
        (self.store_dir / "node_modules" / ".agentforge-runtime").write_text(web_app._store_signature(), encoding="utf-8")  # noqa: SLF001
        self.assertTrue(web_app.runtime_ready())
        shutil.rmtree(self.store_dir / "node_modules" / "parcel")
        self.assertFalse(web_app.runtime_ready())


@unittest.skipUnless(shutil.which("node") and (ROOT / "tools" / "web-artifacts-runtime" / "node_modules" / ".agentforge-runtime").is_file(),
                     "needs Node and the installed toolkit (tools/web-artifacts-runtime)")
class RealToolchainTests(unittest.TestCase):
    """The Node ports against the real toolkit: create an app, give it two hash-routed pages, bundle it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        patches = [
            mock.patch.object(config, "WORKSPACES", root / "workspaces"),
            mock.patch.object(config, "PROJECTS_FILE", root / ".agentforge-server" / "projects.json"),
            mock.patch.dict(os.environ, {"AGENTFORGE_WEB_RUNTIME": str(ROOT / "tools" / "web-artifacts-runtime")}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.project = store.create(idea="A shop")["id"]

    def test_init_then_bundle_makes_one_self_contained_page_and_the_prototype_copy_builds_too(self):
        staged = web_app.stage_skill(self.project)
        workspace = config.workspace_for(self.project)
        app = web_app.app_dir(self.project, "wireframe")
        ok, log = web_app._run([str(workspace / staged / "scripts" / "init-artifact.mjs"), str(app)], workspace, 120)  # noqa: SLF001
        self.assertTrue(ok, log)
        self.assertTrue((app / "src" / "components" / "ui" / "button.tsx").is_file())
        (app / "src" / "App.tsx").write_text(
            "import { HashRouter, Routes, Route, Link } from 'react-router-dom'\n"
            "import { Button } from '@/components/ui/button'\n"
            "export default function App() { return <HashRouter><Routes>"
            "<Route path='/' element={<Link to='/two'><Button>One</Button></Link>} />"
            "<Route path='/two' element={<h1>Page two</h1>} /></Routes></HashRouter> }\n", encoding="utf-8")

        ok, log = web_app.bundle(self.project, "wireframe")
        self.assertTrue(ok, log)
        html = (app / "bundle.html").read_text(encoding="utf-8")
        self.assertNotIn('src="./', html)          # everything inlined
        self.assertIn("Page two", html)

        prototype = web_app.app_dir(self.project, "prototype")
        web_app.copy_app(app, prototype)
        ok, log = web_app.bundle(self.project, "prototype")
        self.assertTrue(ok, log)
        self.assertTrue(web_app.built(self.project, "prototype"))


if __name__ == "__main__":
    unittest.main()
