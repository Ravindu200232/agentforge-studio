# Vitest business evidence

Use the existing Vitest setup for focused business-logic and critical-path tests. Save machine-readable output at `.agentforge/qa/vitest.json`, for example `npx vitest run <focused files> --reporter=json --outputFile=.agentforge/qa/vitest.json`, and record the real exit code. Keep test data in the scaffold's isolated `<app>_test` database. Do not require per-file tests, inventory completion or 100% coverage.
