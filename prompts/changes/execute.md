# Apply the approved update

Request:
{{request}}

Approved plan:
{{plan}}

Project:
{{artifacts}}

Follow the plan in order and change only affected files. Keep derived artifacts consistent when their source changes.

Testing:
- Do not create or run tests for SRS text, Mermaid diagram, wireframe or prototype-only updates.
- For diagram-only updates, update or generate only the affected diagram artifact and leave build, prototype and test result files unchanged.
- Mermaid and diagram support is already installed by the default scaffold. Reuse it and never install the renderer or dependencies again.
- For build updates, add or run focused unit tests only for changed or newly added business logic files; never run the full unit suite.
- Run E2E and other quality checks only for a new feature or changed user-visible behavior. UI-only visual or styling changes do not trigger E2E, accessibility, performance or security checks.
- Do not rerun the full suite or chase coverage for untouched code.
- Update saved result records only for checks actually run; preserve earlier entries.

Read before editing. Use local edits where possible. If the approved plan needs adjustment after inspecting the files, make the smallest necessary correction and explain it briefly.

Existing result records:
{{results}}

Application guides, only when build code is affected:
{{guides}}

If .agentforge/PLUGIN.md exists, handle it only when the requested update affects that integration. Never expose environment values.

Finish in {{language}} with a short summary of the change and any affected checks that ran.

After that summary, end the task immediately. Do not reopen the plan, reread completed files, start an extra audit, or continue with optional improvements.
