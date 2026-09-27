# Playwright E2E and UI evidence

Use the scaffold commands for the main user journeys and representative public, protected, desktop and mobile screens. Keep its configured JSON reporter at `test-results/results.json`; never replace the reporter on the command line. Import `test` and `expect` from `e2e/fixtures.js`, use real sign-in for protected flows, assert business outcomes, and keep screenshots/traces. Run each needed layer once and rerun only a failed affected spec.
