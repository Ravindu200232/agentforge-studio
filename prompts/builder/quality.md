# Phase 3 — final product checks

The application and focused business unit tests are complete. Read the app and the phase 1–2 report before planning.

Make a short plan for these final checks:
- E2E tests for the main user journeys;
- UI and visual checks for key screens;
- accessibility checks;
- performance checks;
- security and dependency checks.

Use the project's existing test commands and local isolated server. Keep the suite focused on important flows and representative screens; do not create exhaustive per-file or 100% coverage work.

For an incremental update, run E2E only when the change adds a feature or changes user-visible behavior. A UI-only visual or styling change does not trigger E2E, visual, accessibility, performance or security checks unless the approved plan identifies a concrete effect on that layer.

Fix product failures and rerun only the affected check. Keep the scaffold reporters and their UI artifact paths unchanged:
- Playwright: `test-results/results.json` and screenshots under `test-results` or `e2e/__screenshots__`;
- accessibility: the existing Playwright/axe result;
- performance: `.lighthouseci/summary.json`;
- security: `.agentforge/qa/zap/summary.json`;
- routes, when run: `.agentforge/qa/routes.json`.

Merge honest commands, exit codes and outcomes into the existing `.agentforge/build/report.json`; preserve its prior fields and phase 1–2 evidence. Mark unavailable tools as unavailable with the exact reason. Finish after every planned layer has one recorded outcome.
