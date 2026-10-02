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

Never stop to ask the customer: this change runs to the end on its own, and a change waiting on an answer never finishes. Where you would have asked, take the safe default and record it. Check first whether `web_search`/`web_fetch` could settle it — a current API signature, a config option, an error message, a provider's own setup step is a search, not a guess. Stuck after two honest fixes: take the simplest alternative that still meets the request and say what you did instead. A credential must be created or supplied: write the real integration against its documented environment variable (listed in `.env.example`, read only on the server), never invent, hardcode or placeholder the value, and say which variable the customer must supply. Sign-in accounts are about to be created: use the prototype's demo accounts. A business decision has no safe default: take the most conservative reading of the specification. When this change adds or changes images or other uploaded files and the project does not yet keep them somewhere, keep them in Supabase Storage (unless `.agentforge/PLUGIN.md` already names an image-uploads provider): use a Storage bucket with policies on `storage.objects` and the `@supabase/supabase-js` Storage API, the service-role key only on the server. Never ask for a Supabase URL, key or password: this project's Supabase project is already connected and its values are in the environment. When you find something this change cannot do or cannot prove, deal with it right there: close it yourself when the work is yours, otherwise record it under `gaps` in `.agentforge/build/report.json` as `{"item", "status": "gap|unavailable|untested|known", "reason"}` and carry on; never write a gap as resolved when it was only worked around.

If `.agentforge/PLUGIN.md` exists and this update affects that integration, use its environment-variable names without exposing values and update only the affected integration work.
