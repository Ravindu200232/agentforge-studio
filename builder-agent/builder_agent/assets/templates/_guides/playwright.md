# Playwright E2E and UI evidence

Use the scaffold commands for the main user journeys and representative public, protected, desktop and mobile screens. Keep its configured JSON reporter at `test-results/results.json`; never replace the reporter on the command line. Import `test` and `expect` from `e2e/fixtures.js`, use real sign-in for protected flows, assert business outcomes, and keep screenshots/traces. Run each needed layer once and rerun only a failed affected spec.

## Writing a spec

- **Select by role, not structure.** Prefer `getByRole`, `getByLabel` and `getByText` over CSS classes, ids or XPath — the accessible name a real user reads is what a well-built page exposes, and it survives a markup refactor that would break a class selector. Reach for `data-testid` only when nothing accessible identifies the element.
- **Assert with the web-first matchers, and await them.** `await expect(locator).toBeVisible()`/`toHaveText()`/`toBeEnabled()` retry until they pass or time out; a bare `if (await locator.isVisible())` reads the DOM once and is exactly the kind of race that makes a suite flaky. Never paper over a real wait with `page.waitForTimeout()` — wait for the actual condition (a locator, a response, a URL) instead.
- **Keep each test independent.** Sign in and set up state inside the test (or its own `beforeEach`), not by relying on a previous test in the file having run first or left data behind; `fullyParallel` is already on in this scaffold's config, so an order-dependent test is also a silently-broken one.
- **Never depend on a real third party.** A journey that would otherwise call a live payment gateway, email provider or other external service must stub that boundary with Playwright's route/network mocking so the test is deterministic and does not touch the real internet.
- **Debug from the trace, not from re-running with prints.** `trace: 'retain-on-failure'` is already configured — open the recorded trace (`npx playwright show-trace <path>`) for a failing test's exact DOM, network and console timeline instead of adding temporary logging or screenshots to chase it.
