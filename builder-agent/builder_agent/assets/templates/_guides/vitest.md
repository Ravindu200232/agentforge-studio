# Vitest evidence and coverage

Use the existing Vitest setup. One command writes both artifacts the Testing screen reads: `npx vitest run --coverage --reporter=json --outputFile=.agentforge/qa/vitest.json` saves the machine-readable results at `.agentforge/qa/vitest.json` and the coverage at `.agentforge/qa/coverage/coverage-summary.json`. Record the real exit code. Keep test data in the scaffold's isolated `<app>_test` database.

`unit-tests.md` says which modules get a test file, how deep each goes, and the coverage floor to reach. Do not change `coverage.include`, `coverage.exclude` or add thresholds in `vitest.config.js` to move the number.
