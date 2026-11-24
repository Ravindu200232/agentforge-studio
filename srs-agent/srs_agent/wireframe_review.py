"""Capture and check a static wireframe before the next page is drawn."""
from __future__ import annotations

import time
from pathlib import Path

from ollama_terminal import screenshot
from prototype_agent.journey_driver import Driver, DriverError
from server_modules import bus, llm, prompts, screen_review, vision
from server_modules.session import RunCancelled


class Review:
    def __init__(self, project, session, folder: Path, rows: list[dict]):
        self.project = project
        self.session = session
        self.folder = folder
        self.routes = [row["file"] for row in rows]
        self.checks: dict[str, str] = {}
        self.driver = None
        self.browser_unavailable = False
        self.model = None

    def __enter__(self):
        self.save()
        return self

    def __exit__(self, *_exc):
        if self.driver:
            self.driver.close(fast=self.session.cancelled)

    def save(self, row=None, status=""):
        if row:
            self.checks[row["route"]] = status
        self.session.write_record("wireframe", "checks.json", data=self.checks)
        bus.wireframe_changed(self.project)

    def _capture(self, row: dict, label: str) -> tuple[list[str], list[dict], list[bytes]]:
        if not self.driver or not self.driver.alive():
            driver = Driver(cancelled=lambda: self.session.cancelled)
            try:
                self.driver = driver.start()
            except DriverError:
                self.browser_unavailable = True
                raise
        root = self.session.record / "wireframe" / "review" / Path(row["file"]).stem / str(time.time_ns())
        shots = [{"viewport": name, "width": width, "height": height, "path": str(root / f"{name}.png")}
                 for name, (width, height) in screenshot.VIEWPORTS.items()]
        result = self.driver.call("wireframe", file=str(self.folder / row["file"]), shots=shots, routes=self.routes)
        files = [Path(shot["path"]) for shot in shots]
        images = [{"path": file.relative_to(self.session.workspace).as_posix(), "label": f"{label} · {file.stem}"}
                  for file in files]
        return result["defects"], images, [file.read_bytes() for file in files]

    def _findings(self, row: dict, label: str) -> list[str]:
        issues, images, pictures = self._capture(row, label)
        bus.agent_msg(self.project, "\n".join(f"- {issue}" for issue in issues) or "Desktop and mobile screenshots captured.",
                      title=f"{row['name']} · {label}", kind="visual_review", agent=bus.DESIGNER, images=images)
        if self.model is None:
            try:
                model = str(self.session.agent().model)
                self.model = model if vision.supports(model) is True else ""
            except (OSError, RuntimeError, ValueError):
                self.model = ""
        if self.model:
            try:
                finding = llm.complete_json(screen_review.SYSTEM, prompts.load("wireframe/visual-review", page=row["name"]),
                                            screen_review.clean, label="wireframe review", model=self.model,
                                            images=pictures, project=self.project, role=bus.DESIGNER)
                issues.extend(f"{d['viewport']} · {d['where'] or 'page'}: {d['problem']}"
                              for d in finding["defects"] if d["severity"] in screen_review.FIX_SEVERITIES)
            except RunCancelled:
                raise
            except Exception as exc:  # Keep the browser findings when the vision provider is unavailable.
                bus.log(self.project, "WARN", f"Wireframe vision review unavailable: {str(exc)[:180]}", agent=bus.DESIGNER)
                self.model = ""
        return issues

    def page(self, row: dict) -> None:
        if self.session.cancelled:
            raise RunCancelled(self.project)
        if self.browser_unavailable:
            self.checks[row["route"]] = "unavailable"
            return
        self.save(row, "checking")
        try:
            issues = self._findings(row, "First check")
            if issues:
                self.save(row, "fixing")
                bus.agent_msg(self.project, "\n".join(f"- {issue}" for issue in issues), title=f"{row['name']} · Fixing",
                              kind="narration", agent=bus.DESIGNER)
                relative = (self.folder / row["file"]).relative_to(self.session.workspace).as_posix()
                self.session.run_direct(prompts.load("wireframe/visual-fix", file=relative,
                                                    issues="\n".join(f"- {issue}" for issue in issues)))
                bus.wireframe_changed(self.project)
                issues = self._findings(row, "After repair")
                if issues:
                    bus.agent_msg(self.project, "\n".join(f"- {issue}" for issue in issues),
                                  title=f"{row['name']} · Issues remain", kind="narration", agent=bus.DESIGNER)
            self.save(row, "issues" if issues else "checked")
        except RunCancelled:
            raise
        except (RuntimeError, OSError, ValueError) as exc:
            self.save(row, "unavailable")
            bus.agent_msg(self.project, str(exc)[:220], title=f"{row['name']} · Browser check unavailable",
                          kind="narration", agent=bus.DESIGNER)
