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

If the update or rerun makes previously visible persisted records disappear, treat it as a
regression. Inspect the application's data query, preview logs and test wrapper before accepting
an empty state, and record the root cause in the test/build result so it is visible to the next
model turn. Never fix a QA failure by truncating, resetting or destructively seeding the project's
connected Supabase database.

Before asking anything, check whether `web_search`/`web_fetch` could actually settle it — a current API signature, a config option, an error message, a provider's own setup step is a search, not a question. If finishing this change genuinely needs a value or decision only the customer can give after that — a real credential, a real account detail, a choice with no safe default — do not invent, hardcode or skip it. Write `.agentforge/build/question.json` (`{"question", "why", "options", "assumption"}`, or add `"variable": "NAME"` and `"secret": true` for a value only the customer holds — the studio collects it in a private box and you receive it in the environment under that name, never in the conversation) and end your reply with the blocked marker. You are asked in the chat and this change continues from exactly where it stopped once answered. There is no cap on how many times you may ask, but ask only for a real, current blocker.

If `.agentforge/PLUGIN.md` exists and this update affects that integration, use its environment-variable names without exposing values and update only the affected integration work.
