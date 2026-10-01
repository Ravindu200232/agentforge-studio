# Update the application

{{request}}

Read the files that carry this behavior and change only what the request affects. Preserve the approved design, existing architecture and unrelated behavior.

When the change touches signing in, sessions, roles, a role's dashboard or the navigation, follow `.agentforge/auth/AUTHENTICATION.md` (when it exists): cookie sessions, access checked on the server and in the data, each role's own dashboard and navigation, and the signed-out navigation only for signed-out people. Whatever you change keeps the build's quality bar — access checked on the server, inputs validated, lists paginated, writes atomic, and loading, empty and error states with a way forward.

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

Ask the customer whenever this change genuinely needs them — you are stuck after two honest fixes, a credential must be created or supplied, sign-in accounts are about to be created, an error you could not fix changes the approach, or a business decision has no safe default. Check first whether `web_search`/`web_fetch` could settle it — a current API signature, a config option, an error message, a provider's own setup step is a search, not a question. Then write `.agentforge/build/question.json` (`{"question", "why", "options", "assumption"}`, two to four options with your recommendation first) and end your reply with the blocked marker; never invent, hardcode or skip the value. A password, key, token, secret or connection string is never asked for as plain text: add `"variable": "NAME"` and `"secret": true`, one value per question — the studio collects it in a private box that hides what is typed and you receive it in the environment under that name, never in the conversation. You are asked in the chat and this change continues from exactly where it stopped once answered. There is no cap on how many times you may ask, but each question must be a real, current need. When this change adds or changes images or other uploaded files and the project does not yet keep them somewhere, ask once whether to keep them in Supabase Storage ("Yes — Supabase Storage" recommended, unless `.agentforge/PLUGIN.md` already names an image-uploads provider); on yes, use a Storage bucket with policies on `storage.objects` and the `@supabase/supabase-js` Storage API, the service-role key only on the server. Never ask for a Supabase URL, key or password: this project's Supabase project is already connected and its values are in the environment. Ask at the moment the need comes up, in the middle of the change, never saved up for the end. When you find something this change cannot do or cannot prove, deal with it right there: close it yourself when the work is yours, otherwise ask the customer then and carry on from the answer; a gap recorded in `.agentforge/build/report.json` carries `"asked"` (the question exactly as asked) and `"answer"`, and never says the customer was asked when they were not.

If `.agentforge/PLUGIN.md` exists and this update affects that integration, use its environment-variable names without exposing values and update only the affected integration work.
