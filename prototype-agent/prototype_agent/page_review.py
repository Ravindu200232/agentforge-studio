"""Check one HTML screen in a browser while the prototype is being written."""
from __future__ import annotations

import time
from pathlib import Path

from ollama_terminal import screenshot
from server_modules import bus, config, llm, prompts, screen_review, vision
from server_modules.session import RunCancelled

from . import screens
from .journey_driver import Driver, DriverError


class PageReview:
    def __init__(self, project, session, accounts, sign_in):
        self.project = project
        self.session = session
        self.accounts = accounts
        self.sign_in = sign_in
        self.driver = None
        self.model = None if config.setting("prototype_visual_review", True) else ""
        self.unavailable = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        if self.driver:
            self.driver.close(fast=self.session.cancelled)

    def _capture(self, row, preview, label):
        if not self.driver or not self.driver.alive():
            try:
                self.driver = Driver(cancelled=lambda: self.session.cancelled).start()
            except DriverError:
                self.unavailable = True
                raise
        stamp = str(time.time_ns())
        folder = self.session.record / "prototype" / "review" / Path(row["file"]).stem / stamp
        shots = [{"viewport": name, "width": width, "height": height, "maxHeight": screenshot.MAX_HEIGHT[name],
                  "path": str(folder / f"{name}.png")}
                 for name, (width, height) in screenshot.VIEWPORTS.items()]
        account = "" if row["route"] == self.sign_in else screens.role_for(row, self.accounts)
        query, _, route = screens.suffix_for(row["route"], account).partition("#")
        suffix = f"?review={stamp}" + ("&" + query[1:] if query else "") + "#" + route
        result = self.driver.call("wireframe", file=str(preview), shots=shots, route=row["route"], suffix=suffix)
        files = [Path(shot["path"]) for shot in shots]
        images = [{"path": file.relative_to(self.session.workspace).as_posix(), "label": f"{label} · {file.stem}"}
                  for file in files]
        bus.agent_msg(self.project, "\n".join(f"- {issue}" for issue in result["defects"]) or "Desktop and mobile screenshots captured.",
                      title=f"{row['name']} · {label}", kind="visual_review", agent=bus.DESIGNER, images=images)
        return result["defects"], files

    def _look(self, row, preview, label, brief):
        issues, files = self._capture(row, preview, label)
        if issues:
            return issues
        try:
            if self.model is None:
                model = str(self.session.agent().model)
                self.model = model if vision.supports(model) is True else ""
            if not self.model:
                return []
            request = prompts.load("prototype/page-review", page=row["name"], steps=brief)
            finding = llm.complete_json(screen_review.SYSTEM, request, screen_review.clean, label="prototype page review",
                                        model=self.model, attempts=1, images=[file.read_bytes() for file in files],
                                        project=self.project, role=bus.DESIGNER)
            return [f"{d['viewport']} · {d['where'] or 'page'}: {d['problem']}" for d in finding["defects"]
                    if d["severity"] in screen_review.FIX_SEVERITIES]
        except RunCancelled:
            raise
        except Exception as exc:  # A provider problem still leaves the browser evidence available.
            self.model = ""
            bus.log(self.project, "WARN", f"Prototype vision review unavailable: {str(exc)[:180]}", agent=bus.DESIGNER)
            return []

    def page(self, row, preview, brief, publish):
        if self.unavailable:
            return
        bus.phase(self.project, "prototype:draw", row["name"], detail="Checking desktop and mobile screenshots", agent=bus.DESIGNER)
        try:
            issues = self._look(row, preview, "First check", brief)
            if not issues:
                return
            details = "\n".join(f"- {issue}" for issue in issues)
            bus.agent_msg(self.project, details, title=f"{row['name']} · Fixing", kind="narration", agent=bus.DESIGNER)
            request = prompts.load("prototype/page-fix", file=f".agentforge/prototype/{row['file']}", issues=details, steps=brief)
            self.session.run_direct(request)
            after = self._look(row, publish(), "After repair", brief)
            if after:
                bus.agent_msg(self.project, "\n".join(f"- {issue}" for issue in after), title=f"{row['name']} · Issues remain",
                              kind="narration", agent=bus.DESIGNER)
        except RunCancelled:
            raise
        except (RuntimeError, OSError, ValueError) as exc:
            bus.agent_msg(self.project, str(exc)[:220], title=f"{row['name']} · Check could not finish",
                          kind="narration", agent=bus.DESIGNER)
