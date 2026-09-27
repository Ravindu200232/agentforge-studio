# Verify the finished product

Read the built application, SRS handoff, approved prototype and existing build/test reports. Reuse current runner evidence from this build. Run only a missing, stale, failed or explicitly requested layer; do not repeat a fresh passing build/unit/browser/quality run.

For an incremental update, use the approved change scope before selecting layers: run unit tests only for edited or newly added business logic and its direct critical paths; run E2E only for a new feature or changed user-visible behavior. UI-only visual or styling changes do not trigger E2E, visual, accessibility, performance or security checks unless the change can concretely affect that layer.

Make a short plan and run these focused layers:
1. production build and local startup;
2. unit tests for business logic and critical complete paths;
3. E2E tests for the main user journeys;
4. representative UI/visual and accessibility checks;
5. performance and security/dependency checks.

Do not require a test for every page, component or file. Do not target or claim 100% coverage. Prefer important business behavior and complete user journeys.

Use the project's existing commands and isolated local server. Fix product failures and rerun only the affected check. Never weaken or skip a meaningful assertion to improve results. Mark unavailable tools honestly with the exact reason.

Preserve the Testing screen contract. Update `.agentforge/qa/report.json` after each layer by merging into the existing object; never rename or delete existing fields. Keep `project`, `complete`, `provenance`, `summary`, `timeline`, `commands`, `unit`, `journeys`, `e2e`, `accessibility`, `performance`, `load`, `security`, `bugs`, `repairs`, `resolvedBugs` and `screenshots` when present. Preserve the runner files `.agentforge/qa/vitest.json`, `test-results/results.json`, `.lighthouseci/summary.json`, `.agentforge/qa/routes.json`, `.agentforge/qa/zap/summary.json` and `.agentforge/qa/coverage/coverage-summary.json`; write them only through their existing runners.

Set `complete` true when every planned layer has an honest recorded or reused-current outcome. Never invent a pass from a missing artifact.
