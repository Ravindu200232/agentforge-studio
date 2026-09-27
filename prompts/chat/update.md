# Customer message

{{message}}

Stage: {{stage}}
Existing artifacts: {{artifacts}}

Decide whether this is a question or a small update.

- For a question, answer briefly from the project.
- For a change, find the affected files and update them directly.
- Keep all affected stages consistent, but do not widen the request.
- SRS text, Mermaid diagrams, wireframes and prototype changes are direct artifact updates: do not create, install, or run tests for them.
- If the request changes only a diagram, update or generate only the affected diagram artifact. Do not touch build files, prototype files, or test results.
- Mermaid and diagram support are already part of the default project setup. Reuse the existing renderer and dependencies; never install them again for an update.
- For build changes, run focused unit tests only for changed or newly added business logic files; never run the full unit suite.
- Run E2E and other quality layers only when a new feature or user-visible behavior changes. UI-only visual or styling changes do not trigger E2E, a11y, performance, or security runs.
- If something essential is unclear, state the assumption you used.

Answer in {{language}} with a concise result.

When the requested answer or update is complete, end immediately. Do not create another plan, reopen completed files, run an extra audit, or continue with optional work.
