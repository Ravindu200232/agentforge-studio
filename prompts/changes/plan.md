# Plan this update

Request:
{{request}}
{{history}}

Inspect only the project files needed to understand the request. Keep the plan short and limited to affected stages.

Rules:
- Update SRS, wireframes, prototype and build only when the request actually affects them.
- SRS text, Mermaid diagrams, wireframes and prototype updates are direct artifact edits with no test steps.
- When the request is diagram-only, plan only the affected diagram update or generation; do not plan build, prototype or test work.
- Mermaid and diagram support are already installed in the default scaffold. Reuse the existing renderer and dependencies; never plan a reinstall.
- For build changes, plan focused unit tests only for changed or newly added business logic files; never plan the full unit suite.
- Plan E2E and other quality layers only for a new feature or changed user-visible behavior. UI-only visual or styling changes do not trigger E2E, accessibility, performance or security checks.
- Do not add coverage work for untouched files or target 100% coverage.
- Ask one question only when the project cannot settle a choice that changes the result. {{questions_left}}

Project artifacts:
{{artifacts}}

Return one JSON object:
- Answer: {"kind":"answer","answer":"..."}
- Question: {"kind":"question","question":"...","why":"...","options":[{"label":"...","hint":"..."}],"assumption":"..."}
- Plan: {"kind":"plan","title":"...","summary":"...","impact":[{"stage":"SRS","affected":false,"why":"..."}],"steps":[{"stage":"Prototype","title":"...","detail":"...","files":["..."]}],"assumptions":[],"risks":[],"verification":[]}

For a plan, list the project's stages in order in impact, but keep steps and verification to the minimum needed. Use {{language}} for text and return JSON only.
{{previous_plan}}
