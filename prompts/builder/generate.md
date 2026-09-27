# One sequential plan — build, focused unit tests, then final checks

Read the selected scaffold, its README and folder structure, the SRS handoff, the approved prototype and design, and any `media/IMAGES.md` or `.agentforge/PLUGIN.md` that exists.

## Mandatory prototype-to-app parity workflow

The approved HTML prototype is the frontend source of truth. The real application must reproduce it at 100% visual, content, image, interaction and navigation parity while connecting the real data and business logic.

Before writing the implementation plan:

1. Open `.agentforge/prototype/routes.json`.
2. Enumerate every `.agentforge/prototype/*.html` file and read every one in full. Do not infer one page from another and do not rely on memory or a summary.
3. Read `.agentforge/prototype/assets/app.css`, `app.js` and `flow.js`, plus every local or remote image reference used by the HTML pages.
4. Put a **Prototype parity map** in the generated plan. For every approved route, list the exact source HTML file, the destination application page/component files, and the prototype image or asset sources that must be reused.

While implementing, work route by route. Immediately before creating or editing a real application page, reopen its mapped prototype HTML and the shared prototype assets it references. Reproduce the same page structure, visible copy, typography, colors, spacing, sizing, images, image crops, ordering, shells, responsive states, controls, hover/focus states, buttons, links, destinations and navigation flow. Reuse the exact same prototype images and URLs; do not replace them with placeholders, stock substitutes, generated images or different crops. Copy a local prototype asset into the application's public assets when the framework needs a served file, and keep its appearance unchanged.

The SRS defines data, permissions and business behaviour. The mapped prototype HTML defines the frontend presentation and interaction. Connect real data without redesigning, simplifying, restyling or inventing a different screen. If a detail is forgotten, reopen the mapped HTML instead of guessing. Never expose credentials from `demo-accounts.json` in the visible interface.

## Requirement recovery rule

If any requirement appears missing, contradictory or unclear while building or checking the app, do not guess and do not create another plan. Keep the current single plan, reopen the approved plan plus the relevant SRS handoff section, mapped prototype HTML/shared asset and current output application file, then correct only the affected work and continue from the current phase. Repeat this targeted read whenever memory is uncertain. Do not restart completed phases or reread unrelated files.

Create exactly one short execution plan, including the complete Prototype parity map. That one plan must contain the three sequential phases below. Do not create a separate plan for unit tests or final checks, do not run phases in parallel, and do not restart the plan from the beginning after a failure.

Implement every approved page, route, role, business rule, data record and main workflow. Match the prototype at 100% parity, use real validation, persistence, authorization, responsive states and useful errors. Keep the existing scaffold and existing application work.

## Phase 1 — complete the real application

Finish the entire application before creating or running any tests. Run only the minimum build command needed to compile it. Update `.agentforge/build/report.json` in place with delivered routes, real commands, exit codes and honest gaps. Preserve its existing fields and arrays because the Testing screen reads this JSON.

## Phase 2 — read the completed app and test business logic

Only after Phase 1 is complete, reread the implemented business modules, server routes, data models and completed critical workflows. Add focused unit tests for calculations, validation, permissions, state transitions, persistence rules and complete business paths. Cover meaningful allowed and refused outcomes. Do not create one test per file, do not test presentation-only components, do not run an inventory or full coverage campaign, and do not target or claim 100% coverage.

Write only the focused business tests the completed app needs. Run that focused unit suite once. If a business test fails because of a real defect, fix only the affected production code and rerun only the affected test file; do not restart the build or the whole test suite. Save the real Vitest JSON at `.agentforge/qa/vitest.json`, and merge the real command, exit code and focused results into `.agentforge/build/report.json` without removing Phase 1 evidence.

## Phase 3 — reread the sources and run final product checks

Only after Phase 2 is complete, reread all of these before writing any E2E journey:

- the SRS handoff under `.agentforge/srs/handoff/`;
- `.agentforge/prototype/routes.json`, the relevant mapped prototype HTML pages and their shared assets;
- the completed output application's actual routes, components, forms, API handlers, selectors, roles and authentication flow;
- the Phase 1–2 results already recorded on disk.

Derive E2E journeys, selectors, roles, setup and expected outcomes from those sources and the current working app. Do not invent routes, labels, selectors or navigation. Run focused E2E tests for the main business journeys, then representative UI/visual, accessibility, performance, security and dependency checks using the scaffold's existing runners. Keep all existing Testing-screen artifact paths unchanged: `test-results/results.json`, screenshots under `test-results` or `e2e/__screenshots__`, `.lighthouseci/summary.json`, `.agentforge/qa/zap/summary.json`, and `.agentforge/qa/routes.json` when produced.

Run each planned layer once. If a check finds a real product defect, repair only the affected code and rerun only that affected check. Never loop through the whole plan again. Record unavailable tools honestly instead of repeatedly trying to install or rerun them.

Merge the real commands, exit codes and outcomes into `.agentforge/build/report.json`, preserving all earlier evidence. Write `.agentforge/qa/report.json` in the existing UI-compatible shape and mark it complete only after every planned layer has one honest recorded outcome. Finish the single plan after Phase 3.
