Fix the end-to-end journeys below, which failed their last run.

For each one, run only its own spec file (`node scripts/with-server.mjs -- npx playwright test <file> --project=desktop`), read why it fails (the error, and the trace and screenshot under `test-results/`), and fix the application so the journey really works. Change the test only when the test itself is wrong, and never by weakening what it checks. Do not run the whole suite: when you finish, the Studio runs these journeys again itself and shows the result.

{{journeys}}
