# Verify the finished product

Read the built application, SRS handoff, approved prototype and existing build/test reports. Reuse current runner evidence from this build. Run only a missing, stale, failed or explicitly requested layer; do not repeat a fresh passing run.

For an incremental update, use the approved change scope before selecting layers: run unit tests only for edited or newly added business logic and its direct critical paths; run journeys only for a new feature or changed user-visible behavior. UI-only visual or styling changes do not trigger journeys, accessibility, performance or security checks unless the change can concretely affect that layer.

The guides listed at the end of this prompt are the scaffold's own test runners and stack notes. Read the one each layer below names before running that layer — they cover the exact command, report artifact and stack-specific pitfalls this prompt does not repeat. When a guide is silent on something real — a runner flag that changed, an assertion API neither you nor the guide explains — use `web_search`/`web_fetch` against the tool's own official site rather than guessing; never edit the guide with what you find.

## Run every applicable layer

1. **Build** — production build and a local start of the built app. Every later layer depends on the app actually starting; fix a build failure before anything else. Guides: `pitfalls.md`, the stack guide.
2. **Runtime** — the started app's main routes respond without a server error. Never hand-start a dev/production server yourself. Guides: the stack guide, `pitfalls.md`.
3. **Unit** — focused tests for business logic and complete critical paths, including every meaningful API route handler's own request/response contract (status codes, validation, authorization). Not one test per file, not coverage chasing. Guides: `unit-tests.md`, `vitest.md`.
4. **Contracts** — not a separate run: `.agentforge/qa/report.json`'s `contracts` evidence is derived automatically from the unit layer's tests matched against the built API routes. A route with no test exercising it has no contract evidence at all, so make sure step 3 actually covers every route that matters before moving on — do not treat this as satisfied by the route existing.
5. **Journeys** — read `.agentforge/srs/user-journeys.json`: it is the product-only source of required journey coverage, not an HTML/prototype/build instruction. Every `journeys[].id` must occur in at least one passing real Playwright journey test title (for example `[UJ-001] …`), signed in for any journey that needs it. Generic smoke, visual and accessibility checks do not substitute for a saved journey. Guide: `playwright.md`.
6. **Visual** — `npm run qa:visual` checks every signed-out public route against its recorded screenshot; a missing baseline is written and the check passes, so re-running it is always safe. Never rewrite `e2e/visual.spec.js` or touch `playwright.config.js`'s `snapshotPathTemplate`/`projects` — that silently breaks the baseline contract and the Testing screen's own screenshot evidence. A signed-in role's own screens get their visual coverage inside a journey test, using `fixtures.js`'s `expectMatchesBaseline(page, testInfo, name)` — never by editing `visual.spec.js`. Guide: `visual.md`.

   **Live browser review** — use `browser_inspect` against every concrete route in the local managed preview at both `desktop` and `mobile` when the page has user-visible layout. It opens a fresh headless browser without clicking, typing, signing in or navigating away from that preview (images, fonts and stylesheets load so the capture matches the real design). Read its rendered text and layout facts; inspect its saved screenshot in the Testing screen for visual parity, spacing, cropping and element placement. Repair real overflow, clipped controls, broken images or layout defects, then inspect the affected page again. A pending image is not automatically broken: use the saved capture and a repeat check before changing it. Dynamic/signed-in pages are reviewed through their existing journey screenshots unless a safe local fixture route is available.
7. **Accessibility** — representative public, protected, desktop and mobile screens, checked from their real signed-in journeys where relevant, not just the sign-in page. Guide: `axe.md`.
8. **Load** — both halves are real runs, never placeholders: Lighthouse performance evidence (written to `performance`) and the OWASP ZAP security baseline (written to `security`). `npm run qa:security` always writes `.agentforge/qa/zap/summary.json`; it now installs ZAP itself on a machine that does not have it yet, so plain `npm run qa:security` is a real ZAP scan by default — never widen this to `--install-zap` yourself first "to be safe", the script already does that. Only when that automatic install genuinely could not complete does it fall back to the built-in passive baseline; that result is real evidence too — report its status honestly as `partial`, never as a ZAP pass. Guides: `lighthouse.md`, `zap.md`.

Do not require a test for every page, component or file. Do not target or claim 100% coverage. Prefer important business behavior and complete user journeys.

Use the project's existing commands and isolated local server. Fix product failures and rerun only the affected check. Never weaken or skip a meaningful assertion to improve results. Mark an unavailable tool honestly with the exact reason.

## Persistent data safety and empty-data diagnosis

The connected Supabase project is persistent project data, not a disposable test database. The QA
server wrapper may start and stop a temporary local server, but it must never truncate, delete,
reset or run a destructive seed against the connected project. If a journey needs records, use
records already in the project or create uniquely named test records and remove only those records
in that journey's own cleanup. Never accept a newly empty list as an ordinary empty state when the
same project previously showed records: compare the route's query, the preview logs and the latest
QA run, then record the persistence/runtime failure and repair the actual cause. If a rerun made
data disappear, call that out explicitly in the QA report so the build conversation sees the bug
instead of silently passing an empty screen.

Preserve the Testing screen contract. Update `.agentforge/qa/report.json` after each layer by merging into the existing object; never rename or delete existing fields. Its keys and their shape are written down in the `qa` section of `{{report_template}}` — every key in that section's `required` list must be present when the run ends, with counts taken from the runners' own output. Keep `project`, `complete`, `provenance`, `summary`, `timeline`, `commands`, `unit`, `journeys`, `e2e`, `accessibility`, `performance`, `load`, `security`, `bugs`, `repairs`, `resolvedBugs` and `screenshots` when present. Preserve the runner files `.agentforge/qa/vitest.json`, `test-results/results.json`, `.lighthouseci/summary.json`, `.agentforge/qa/routes.json`, `.agentforge/qa/zap/summary.json` and `.agentforge/qa/coverage/coverage-summary.json`; write them only through their existing runners.

Set `complete` true when every planned layer has an honest recorded or reused-current outcome. Never invent a pass from a missing artifact.
