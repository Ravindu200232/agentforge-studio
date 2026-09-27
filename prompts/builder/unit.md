# Phase 2 — focused unit tests

The complete application from phase 1 is already present. Read the implemented business modules, server routes and critical workflows before planning.

Make a short plan for business-logic unit tests only. Test calculations, validation, permissions, state transitions, persistence rules and complete critical business paths. Cover both allowed and refused outcomes where they matter.

Do not create a test merely because a page or component exists. Do not require every file to have its own test. Do not target or claim 100% coverage.

For an incremental build update, inspect the approved change and test only edited or newly added business-logic files and the direct critical paths they affect. Do not rerun the full unit suite for an unchanged file.

After inspecting the completed app and identifying independent business-test files, write up to four independent test files in one batch. Keep production changes, shared test setup, the same test file, commands and result JSON writes sequential. Each test must use the completed app's actual routes, auth rules and data shape.

Run the focused unit suite once, fix business-logic failures, then rerun only affected tests. Save the real Vitest JSON at `.agentforge/qa/vitest.json`. Add the real command, exit code and focused unit results to the existing `.agentforge/build/report.json` without renaming fields or removing phase 1 evidence. These files feed the Testing screen.
