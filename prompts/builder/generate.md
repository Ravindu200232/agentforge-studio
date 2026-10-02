# One sequential plan — build, focused unit tests, then final checks

Read the selected scaffold, its README and folder structure; `.agentforge/srs/handoff.json` (the routes, collections, roles, workflows and acceptance criteria this build must match); the approved prototype and design (`.agentforge/design/design-spec.json`, and `.agentforge/design/theme.md` when a theme was selected); the stack's build guides staged at `.agentforge/build/guides/`; and any `media/IMAGES.md` or `.agentforge/PLUGIN.md` that exists.

The staged guides are hand-written for this exact scaffold and are the standard for it; they do not cover everything a framework, library or provider might do. When the guides are silent on a real question — a current API signature, a config option, an error message neither you nor the guides explain — use `web_search` and `web_fetch` against the framework's or provider's own official site before guessing or falling back on possibly-stale memory. Never edit a guide file with what you find; it is a reference for the scaffold, not a place for this run's notes.

## Mandatory prototype-to-app parity workflow

The approved HTML prototype is the frontend source of truth. The real application must reproduce it at 100% visual, content, image, interaction and navigation parity while connecting the real data and business logic.

Before writing the implementation plan:

1. Open `.agentforge/prototype/routes.json`.
2. Enumerate every `.agentforge/prototype/*.html` file and read every one in full. Do not infer one page from another and do not rely on memory or a summary.
3. Read `.agentforge/prototype/assets/app.css`, `app.js` and `flow.js`, plus every local or remote image reference used by the HTML pages.
4. Put a **Prototype parity map** in the generated plan. For every approved route, list the exact source HTML file, the destination application page/component files, and the prototype image or asset sources that must be reused.

While implementing, work route by route. Immediately before creating or editing a real application page, reopen its mapped prototype HTML and the shared prototype assets it references. Reproduce the same page structure, visible copy, typography, colors, spacing, sizing, images, image crops, ordering, shells, responsive states, controls, hover/focus states, buttons, links, destinations and navigation flow. Reuse the exact same prototype images and URLs; do not replace them with placeholders, stock substitutes, generated images or different crops. Copy a local prototype asset into the application's public assets when the framework needs a served file, and keep its appearance unchanged.

The prototype's `assets/app.css` already fixes one numeric spacing scale and one definition per common component (button, input, card, table row, empty state) — port those into the application's own styling system once (the framework's theme config, a global stylesheet or CSS custom properties) and build one shared component per kind (`Button`, `Card`, `Input`, ...) that every page imports. Do not let each page's own file re-derive its own padding, margin or control size by eyeballing the prototype HTML page by page: that is exactly how the real app drifts from the prototype's own consistency one page at a time. Two buttons of the same kind, on two different pages, use the same shared component and are pixel-identical unless the design spec defines a real size variant.

The SRS defines data, permissions and business behaviour. The mapped prototype HTML defines the frontend presentation and interaction. Connect real data without redesigning, simplifying, restyling or inventing a different screen. If a detail is forgotten, reopen the mapped HTML instead of guessing. Never expose credentials from `demo-accounts.json` in the visible interface.

## Requirement recovery rule

If any requirement appears missing, contradictory or unclear while building or checking the app, do not guess and do not create another plan. Keep the current single plan, reopen the approved plan plus the relevant SRS handoff section, mapped prototype HTML/shared asset and current output application file, then correct only the affected work and continue from the current phase. Repeat this targeted read whenever memory is uncertain. Do not restart completed phases or reread unrelated files.

## Quality bar

Build it the way a senior team ships a product people depend on, in every part of it:

- **Security.** Every page, API route and server action checks on the server who is calling and what their role
  may do, and the data layer enforces it again (Row Level Security, or every query scoped to the signed-in
  user). Every input is validated on the server with a schema; queries are parameterised; no secret reaches
  client code or a `NEXT_PUBLIC_`/`VITE_` variable; uploads are checked for type and size; every response
  carries security headers; an error never shows a stack trace, a query or whether an account exists.
- **Performance.** Render on the server where the stack can. Paginate every list — never load a whole table;
  fetch independent data in parallel, never one query per row; index the columns you filter, sort and join on.
  Images carry their dimensions and load lazily below the first screen; client bundles stay small, with no heavy
  library for what a few lines do.
- **Reliability.** A write that changes several records is atomic (a transaction or one database function). A
  repeated submit never creates a duplicate: the button is disabled while sending and the write is idempotent.
  Every call to another service has a timeout and a clear error, and a missing optional setting is reported,
  not a crash.
- **Availability.** A failure stays where it happened: an error page or boundary per area with a retry, a real
  not-found page, and a health route the deployment can check. A provider that is down gives a message, never a
  blank page.
- **Flow.** Every action gives feedback — a pending state, a success message, an error beside the field — and
  leads somewhere sensible. Every list and form has its loading, empty and error states; no page is a dead end;
  back and refresh keep working.

## Never stop to ask

Whatever the customer was asked before this plan is listed under "Decided with the customer before this plan" in your request: build on it and never ask it again. From this plan onward the build runs from its first step to its last without stopping to ask the customer anything: nobody is there to answer in the middle of it, and a build that waits on an answer never finishes. Where you would have asked, decide it yourself with the safe default below, build on that, and record what you assumed under `gaps` in `.agentforge/build/report.json` so the customer sees it. Each gap is one row in the report's own shape: `{"item": "what was assumed or could not be proven", "status": "gap|unavailable|untested|known", "reason": "why, and what the customer can do about it"}`.

Before deciding anything yourself, make sure it is not something you can find out: a current API signature, a config option, an error message or a provider's own setup step is a `web_search`/`web_fetch` job against the framework's or provider's own official site, not a guess.

- **You are stuck.** The same failure came back after two honest fixes. Do not loop and do not stop: take the simplest alternative that still meets the requirement (another library, a plainer version of the feature), build that, and record what failed and what you did instead as a `"gap"`.
- **A credential is needed.** An API key, an OAuth client, a mail or payment provider key, a provider account — something only the customer can create. Write the real integration against the documented environment variable (list it in `.env.example`, read it only on the server, and report a missing one as a clear error, never a crash). Never invent, hardcode or placeholder the value, never silently skip the feature, and never build a stand-in (a recorded or fake mode, a button that is switched off) in its place. Record it as an `"unavailable"` gap that names the variable the customer must supply. **Nothing Supabase is ever a missing credential**: this project's Supabase project was connected before the build started, and its URL, keys and database password are already in the environment of every command and of the preview.
- **Sign-in accounts are about to be created.** Seed the prototype's demo accounts (`.agentforge/prototype/demo-accounts.json`), with real hashed passwords from the seed script. The customer's own details are theirs to change after the build.
- **An error you could not fix changes the way forward.** You tried, and searched the framework's or provider's own documentation, and the remaining fixes change the approach — another library or service, a simpler version of a feature, a paid plan. Take the way that keeps the product working at no cost, and record the choice and what it left out as a `"gap"`.
- **A real business decision has no safe default.** Take the most conservative reading of the specification (the one that grants the least access and spends nothing), build that, and record it as a `"known"` gap saying what you assumed.
- **You find a gap** — anything the build cannot do or cannot prove: a provider that is not connected, a feature that would be switched off, a check that cannot run, a tool this computer lacks. Deal with it right there, in the phase where you found it, not at the end. Close it yourself when the work is yours to do (a check you have not written yet, a path no test exercises yet); otherwise record it honestly as `"unavailable"` or `"untested"` and carry on. Never write a gap as resolved when it was only worked around.

Never end the reply with a request for an answer. The build finishes with every question settled by a default and every default on the record.

## Images and uploaded files

When the specification or the prototype has anything image-related that people upload or the app stores — an upload field, a profile photo, product or listing pictures, a gallery, attachments — build it on this project's own Supabase Storage, unless `.agentforge/PLUGIN.md` already names an image-uploads provider (then use exactly that provider instead).

This project's own Supabase project is already connected, and `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are already in the environment of every command and of the preview, on every stack. Create one Storage bucket per kind of image in a migration, with policies on `storage.objects` for who may upload, replace, delete and read; upload with the `@supabase/supabase-js` Storage API (the service-role key only on the server, never in browser code); store the object path in the record; show public images by their public URL and private ones through short-lived signed URLs; check type and size before upload. Seed and test images go through the same bucket. Never write uploads to the local disk as the production answer.

## E2E journey contract

Read `.agentforge/srs/user-journeys.json` before writing the journey tests. It is the complete, product-only list of required user journeys: it contains actors, actions and routes, not instructions for HTML, prototype, build or QA phases. Every `journeys[].id` is mandatory E2E coverage. Give at least one real Playwright business-journey test the corresponding ID in its title, for example `[UJ-001] Visitor places an order`; follow the saved steps and assert the journey's real business outcome. Route smoke, visual and accessibility checks do not count as journey coverage. Before marking QA complete, confirm that every saved UJ id appears in a passing journey-test result; a missing or failed ID must remain an honest failure, never be replaced by a generic E2E count.

## Persistence regression check

The project's connected Supabase data persists across preview restarts and QA reruns. The test
wrapper may own a temporary server port, but it must never truncate, delete, reset or destructively
seed the connected project. When a route showed records earlier in the build and shows an empty
list after a rerun, treat that as a real persistence/runtime regression: inspect the route query,
the preview logs and the runner commands, identify what removed or hid the data, record it in the
QA report and repair it. Do not silently accept that empty list as a normal empty state, and do not
let an external test wrapper hide the finding from the build report.

## Confirming an already-finished plan

Resuming this plan after an interruption and finding every phase's evidence already on disk is not the same as finishing it. Before ending the run, always open `.agentforge/qa/report.json` yourself and check that its `complete` field is literally `true` — an earlier run interrupted after the real testing work but before that one field was written leaves every layer's evidence genuinely passing on disk while the file itself still reads incomplete. If it is not `true`, write it now, merging it in the same way as every other write to this file, never replacing what is already there. Describing the work as complete in your own summary is not a substitute for this: the Studio's own gate checks this exact field, not your description of it, and will keep failing the run on every resume until it is actually set.

Create exactly one short execution plan, including the complete Prototype parity map. That one plan must contain the three sequential phases below. Do not create a separate plan for unit tests or final checks, do not run phases in parallel, and do not restart the plan from the beginning after a failure.

Implement every approved page, route, role, business rule, data record and main workflow. Match the prototype at 100% parity, use real validation, persistence, authorization, responsive states and useful errors. Keep the existing scaffold and existing application work.

## Phase 1 — complete the real application

Finish the entire application before creating or running any tests. Run only the minimum build command needed to compile it. Update `.agentforge/build/report.json` in place with delivered routes, real commands, exit codes and honest gaps, in the shape written down in `{{report_template}}` — the Testing screen reads exactly those keys.

## Phase 2 — read the completed app and test business logic

Only after Phase 1 is complete, reread the implemented business modules, server routes, data models, forms, hooks, UI components and completed critical workflows. Add focused unit tests across both halves of the app: pure functions and utility/helper functions; forms and inputs (accepted and refused input, the error state a bad submission leaves); tables and lists (sorting, filtering, pagination, empty state); custom hooks / state-management logic; UI components that carry real logic (a button's loading/disabled state, a modal's open/close and focus behavior, a card's conditional content — not a component that only renders static markup); API services / data-fetching layers (a service's request shape and its handling of success and failure); and, as before, business logic — calculations, validation, permissions, state transitions, persistence rules and complete business paths. Cover meaningful allowed and refused outcomes for each. Do not create one test per file, do not test a component with no logic of its own, do not run an inventory or full coverage campaign, and do not target or claim 100% coverage.

Write only the focused business tests the completed app needs. Run that focused unit suite once. If a business test fails because of a real defect, fix only the affected production code and rerun only the affected test file; do not restart the build or the whole test suite. Save the real Vitest JSON at `.agentforge/qa/vitest.json`, and merge the real command, exit code and focused results into `.agentforge/build/report.json` without removing Phase 1 evidence.

## Phase 3 — reread the sources and run final product checks

Only after Phase 2 is complete, reread all of these before writing any E2E journey:

- the SRS handoff under `.agentforge/srs/handoff/`;
- `.agentforge/prototype/routes.json`, the relevant mapped prototype HTML pages and their shared assets;
- the completed output application's actual routes, components, forms, API handlers, selectors, roles and authentication flow;
- the Phase 1–2 results already recorded on disk.

Derive E2E selectors, roles, setup and expected outcomes from the saved user-journey contract, the sources above and the current working app. Do not invent routes, labels, selectors or navigation. Run focused E2E tests for every saved business journey, then representative UI/visual, accessibility, performance, security and dependency checks using the scaffold's existing runners. Keep all existing Testing-screen artifact paths unchanged: `test-results/results.json`, screenshots under `test-results` or `e2e/__screenshots__`, `.lighthouseci/summary.json`, `.agentforge/qa/zap/summary.json`, and `.agentforge/qa/routes.json` when produced.

Run each planned layer once. If a check finds a real product defect, repair only the affected code and rerun only that affected check. Never loop through the whole plan again. When a tool is unavailable, do not keep trying to install or rerun it: record it honestly as an `"unavailable"` gap, as above, and carry on.

Then reopen `{{report_template}}` and fill both report files from it: `.agentforge/build/report.json` from its `build` section, preserving all earlier evidence, and `.agentforge/qa/report.json` from its `qa` section. Take every count from the runners' own output on disk, not from memory. Mark the QA report complete only after every planned layer has one honest recorded outcome. Finish the single plan after Phase 3.
