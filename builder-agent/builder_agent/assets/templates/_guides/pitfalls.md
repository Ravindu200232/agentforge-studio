# Build and test pitfalls — read this first

These are not about any one product. They are the mistakes that cost every build time, taken from real runs (a build can spend half its time on problems like these). The scaffold already fixes most of them; each entry says what to use.

## How to spend the build

- Build the complete application first. Testing is handled by the later focused phases. Do not re-run a layer after its current result is recorded unless affected code changed or it failed.
- Use the scaffold's runners, do not write your own: `npm run qa:e2e`, `qa:visual`, `qa:a11y`, `qa:perf`, `qa:security`. Each builds nothing and starts nothing by hand: it starts the built app on a free port, runs the layer, stops only its own server. Run `npm run build` first, and again only after **app** code changed.
- Never start dev/production servers yourself, never `taskkill /IM node` / `Stop-Process -Name node`. The Studio owns every preview and assigns each project its own loopback port; if it is stale it is restarted for that project after the build.
- Unit-test important business rules and complete critical paths in the focused unit phase. Do not use per-file inventory or 100% coverage as a completion gate.
- Delete throwaway diagnostic scripts before finishing. Keep the ones you cite in the report.
- Timestamps in `report.json` come from a command (`node -p "new Date().toISOString()"`), never from memory: a typed time was hours off (local time labelled UTC).
- `npm audit` advisories in dev tooling, or in a dependency the pinned framework bundles (`postcss` inside Next), are **gaps to record**, not work items. Do not bump the framework's major version to silence them (a major bump renames APIs, e.g. Next 15 → 16 renamed `middleware` to `proxy`, and forces a re-run of every layer for an app that was approved on the pinned stack). Record them, and check `npm audit --omit=dev` for what actually ships.
- Do not weaken a test to make it pass: no `.skip`/`.todo`, no loosened assertion, no expected value copied from the bug. If a test is wrong, say why in one line and fix its reasoning.

## Windows PowerShell 5.1 (the shell you are in)

| Symptom | Cause | Do this |
|---|---|---|
| `The token '&&' is not a valid statement separator` | not PowerShell 5.1 syntax | `;` between commands, or `if ($?) { … }` |
| `node -e "…"` fails on `$`, quotes or braces | PowerShell expands them before Node sees them | write a `.mjs` file and run it |
| `--grep @a11y` finds "No tests found" | `@name` is **splatting** in PowerShell, the argument vanishes | quote it: `--grep '@a11y'` (npm scripts are unaffected) |
| a path with `[id]` matches nothing | `[ ]` is a wildcard | `-LiteralPath` |
| log file is unreadable / doubled characters | `>` writes UTF-16 in 5.1 | `\| Out-File -Encoding utf8`, or use the tool's own `--outputFile` |
| an em dash or accent turns into `â€”` after an edit | PowerShell `-replace`/`Set-Content` re-encoded the file | edit with the edit tools, keep regexes ASCII (`.` or `—`) |
| `spawn EINVAL` running `npm`/`npx` from Node | they are `.cmd` files | spawn `process.execPath` with the JS entry (see `scripts/with-server.mjs`) |
| `npm.ps1` / `npx.ps1` is blocked | PowerShell execution policy blocks script shims | call `npm.cmd` / `npx.cmd`, or call npm's CLI JS through `node`; do not retry the `.ps1` shim |
| `npm install` has no CPU, network, files or output for 60 seconds, or registry fetches return `EACCES` | package registry access is unavailable | stop only that install child process. Compare this `package.json` dependency versions with sibling workspace projects; when an exact compatible installed `node_modules` exists, create a local directory junction to it and continue. Never repeat a ten-minute network wait. Recheck `Test-Path node_modules/next/package.json` before declaring the toolchain blocked |

## Test data

- Set test environment variables (secrets, URLs) in a setup module imported before the code under test (`vitest.env.js`), and never "restore" them by deleting them in `afterAll` — that breaks the next file.
- Data your E2E journeys create outlives the run: give it a unique prefix and delete it in `afterAll`, or the next run (and the existing counts) drift. `_testing/scripts/with-server.mjs` only owns the temporary test server; it never resets or seeds the project's connected database. Never make a QA wrapper truncate a real project's tables.

## Vitest

- jsdom is only for components. Anything that touches Postgres directly (`test/helpers/db.js`), route handlers, loaders or actions runs in Node: name it `*.node.test.js` (Next.js) or start the file with `// @vitest-environment node`.
- Ambiguous queries fail (the most repeated time-sink): `getByText('Reports')` matches the nav link *and* the page heading, one word matches a filter chip and a stat label, the same button exists in a toolbar and in an empty state. When you write a component, give an element that repeats or shares a word a `data-testid` (or a distinct accessible name) **as you build it**; in the test use `getByRole(role, { name })`, `within(region)` or the test id, never bare `getByText` on a word the page uses twice.
- `npx vitest run --reporter=json --outputFile=.agentforge/qa/vitest.json` for the record; while iterating, run one file.

## Playwright

- `page.request` and a bare `request` context do not reliably carry the signed-in browser's cookies: an authorization test sees `401` where the app answers `403`. Use `apiFrom(page)` from `e2e/fixtures.js` (in-page `fetch`) after signing in through the UI.
- A negative test that provokes a 401/403 logs a browser console error and fails the fixture: declare it, only for that test: `test.use({ allowedStatuses: [401, 403] })`.
- `getByLabel('Status')` is a strict-mode error when a table header and a select share the word: use ids/test ids or `{ exact: true }`.
- `test.use()` belongs at file or `describe` scope. A sign-in helper must cope with already being signed in (`/login` redirects) and must `page.goto` first (`about:blank` cannot `fetch`).
- Do not pass `--reporter=…`: it replaces the config's reporters and `test-results/results.json` (read by the Testing view) is not written. The scaffold's `smoke`, `a11y`, `visual` specs cover **public** pages; pages with `roles` in `e2e/routes.json` are checked to refuse a signed-out visitor, and must be screenshotted / axe-checked from their journeys once signed in.
- The first visual run records the baselines and passes with a `baseline` annotation (a bare `toHaveScreenshot` writes the file but **fails** that first run). They are recorded from the build, not from an approved design: say so in the report, and note that a first run compared nothing. In CI a missing baseline fails.

## Lighthouse, axe, ZAP

- `lhci` on Windows can fail deleting Chrome's temp profile (EPERM) and throw the report away: use `npm run qa:perf`. It audits public pages only (a protected page redirects to sign-in and would score the sign-in page again).
- axe fails on contrast: never fade text or controls with `opacity < 1` (a "60 % until hover" action row measured 2.57:1). Icon-only buttons, and buttons whose label is hidden on mobile, need an `aria-label` so the accessible name exists at every width. Keep a skip link, visible focus and labelled inputs.
- Keep the scaffold's anti-clickjacking headers strict (`X-Frame-Options: DENY`, `frame-ancestors 'none'`). The Studio's own preview process lifts them for its iframe, so never loosen them "to make the Preview work"; only `FRAME_ANCESTORS` at build time may name an origin that is allowed to embed the app.
- `npm run qa:security` always runs and always writes `.agentforge/qa/zap/summary.json`. `engine: "zap"` is a real OWASP ZAP baseline; `engine: "agentforge-baseline"` (status `partial`) means ZAP is not installed here — record it as that, **never as a ZAP pass**. To get ZAP once per machine: `npm run qa:security -- --install-zap`.
