## What this phase is: the unit tests

Read the implemented business logic needed for the tests. Write focused unit
tests for meaningful allowed and refused outcomes in validation, permissions,
state changes, data requests, and interactive components. Use the real project
test setup and isolate test data from production.

Run that unit suite. When a business test exposes a defect, fix the affected
logic and rerun its test file. Save the real Vitest JSON to
`.agentforge/qa/vitest.json` and merge the command, exit code and result into
`.agentforge/build/report.json` using the template in the build references.
Leave browser tests and whole-app checks to their own phases.
