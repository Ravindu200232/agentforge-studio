# Verify the finished product

Read the built application, SRS handoff, approved prototype and existing build/test reports. Reuse current runner evidence from this build. Run only a missing, stale, failed or explicitly requested layer; do not repeat a fresh passing run.

For an incremental update, use the approved change scope before selecting layers: run unit tests only for edited or newly added business logic and its direct critical paths; run journeys only for a new feature or changed user-visible behavior. UI-only visual or styling changes do not trigger journeys, accessibility, performance or security checks unless the change can concretely affect that layer.

The guides listed at the end of this prompt are the scaffold's own test runners and stack notes. Read the one each layer below names before running that layer — they cover the exact command, report artifact and stack-specific pitfalls this prompt does not repeat.

## Run every applicable layer

1. **Build** — production build and a local start of the built app. Every later layer depends on the app actually starting; fix a build failure before anything else. Guides: `pitfalls.md`, the stack guide.
2. **Runtime** — the started app's main routes respond without a server error. Never hand-start a dev/production server yourself. Guides: the stack guide, `pitfalls.md`.
3. **Unit** — focused tests for business logic and complete critical paths, including every meaningful API route handler's own request/response contract (status codes, validation, authorization). Not one test per file, not coverage chasing. Guides: `unit-tests.md`, `vitest.md`.
4. **Contracts** — not a separate run: `.agentforge/qa/report.json`'s `contracts` evidence is derived automatically from the unit layer's tests matched against the built API routes. A route with no test exercising it has no contract evidence at all, so make sure step 3 actually covers every route that matters before moving on — do not treat this as satisfied by the route existing.
5. **Journeys** — end-to-end tests for the main user journeys, signed in for any journey that needs it. Guide: `playwright.md`.
6. **Accessibility** — representative public, protected, desktop and mobile screens, checked from their real signed-in journeys where relevant, not just the sign-in page. Guide: `axe.md`.
7. **Load** — both halves are real runs, never placeholders: Lighthouse performance evidence (written to `performance`) and the OWASP ZAP security baseline (written to `security`). `npm run qa:security` always writes `.agentforge/qa/zap/summary.json`; when ZAP itself is not installed on this machine it still runs the built-in passive baseline and that result is real evidence — report its status honestly as `partial`, never as a ZAP pass. Guides: `lighthouse.md`, `zap.md`.

Do not require a test for every page, component or file. Do not target or claim 100% coverage. Prefer important business behavior and complete user journeys.

Use the project's existing commands and isolated local server. Fix product failures and rerun only the affected check. Never weaken or skip a meaningful assertion to improve results. Mark an unavailable tool honestly with the exact reason.

Preserve the Testing screen contract. Update `.agentforge/qa/report.json` after each layer by merging into the existing object; never rename or delete existing fields. Keep `project`, `complete`, `provenance`, `summary`, `timeline`, `commands`, `unit`, `journeys`, `e2e`, `accessibility`, `performance`, `load`, `security`, `bugs`, `repairs`, `resolvedBugs` and `screenshots` when present. Preserve the runner files `.agentforge/qa/vitest.json`, `test-results/results.json`, `.lighthouseci/summary.json`, `.agentforge/qa/routes.json`, `.agentforge/qa/zap/summary.json` and `.agentforge/qa/coverage/coverage-summary.json`; write them only through their existing runners.

Set `complete` true when every planned layer has an honest recorded or reused-current outcome. Never invent a pass from a missing artifact.
