# Update the application

{{request}}

Read the files that carry this behavior and change only what the request affects. Preserve the approved design, existing architecture and unrelated behavior.

Testing rules for updates:
- If no application code or behavior changes, do not add or run tests.
- If business logic changes, add or update only the unit tests for edited or newly added business-logic files and run only that focused suite; never run the full unit suite.
- Run E2E and other quality checks only when the update adds a feature or changes user-visible behavior. UI-only visual or styling changes do not trigger E2E, UI, accessibility, performance or security checks unless they concretely affect that layer.
- SRS text, Mermaid diagrams, wireframes and prototype changes are outside this application update and require no tests. Diagram support is already installed; never reinstall it.
- Do not chase total coverage, add tests for untouched pages/components, or rerun every test by default.

Run the minimum build/check needed for the changed area. Update existing result records only for checks actually rerun. If the request conflicts with the approved specification, record it in `.agentforge/build/CHANGES.md`.

If `.agentforge/PLUGIN.md` exists and this update affects that integration, use its environment-variable names without exposing values and update only the affected integration work.
