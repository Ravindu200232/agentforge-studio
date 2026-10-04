# Unit tests: a test file for every module that has logic

Read the finished app and write real unit tests for every module that carries logic, across both halves of it. The Testing screen shows what the unit tests actually execute, so a few test files over a large app read as an untested app. Write enough files to cover the logic, not a sample of it.

## Who decides how much

The customer is asked, before the build is planned, how much the unit tests should cover. When the request has their answer (a "Decided with the customer" entry marked `[unit-test coverage]`, or a "How much the unit tests cover" section), it wins over the defaults in this guide: test the modules and go as deep as it says, and reach the coverage figure it names. When it names no figure, use the floor below for the scope it chose. Everything below is the default for when nothing was decided.

## What gets its own test file

Every one of these that exists in this app, each in a test file of its own:

- **API route handlers, server actions and loaders** — one file per route (or per resource): its request/response contract, validation, authorization and the data it writes.
- **Models, services and data-access modules** — creating, reading, updating, deleting, uniqueness, relations, and the refusals.
- **Validation schemas, auth/session helpers, permission checks, middleware** — accepted and refused input, each role.
- **Pure functions and utility/helper modules** — calculations, formatting, parsing, mapping: exact inputs to exact outputs.
- **Custom hooks, stores and reducers** — each transition (loading, success, error, reset), tested through the hook or the component that owns the state.
- **Forms** — each validation rule (accepted and refused input), submission, and the error state a bad submission leaves on screen.
- **Tables and lists with behavior** — sorting, filtering, pagination, search, the empty state.
- **UI components with logic of their own** — a button's loading/disabled state, a modal's open/close and focus, a card's conditional content, a menu that depends on the role.
- **API services / data-fetching layers** — a service function's request shape and its handling of a success and a failure response, mocked at the fetch/client boundary.

A component that only renders its props as static markup needs no test of its own.

## How deep each file goes

Cover every outcome the module can produce, not just the happy path:

- the success path, with the real result asserted (status, body, stored data, rendered text, returned value);
- each validation rule, accepted and refused;
- each permission outcome: signed out, the wrong role, the right role, the owner and someone else's record;
- not found, a duplicate or conflicting write, an invalid id;
- a dependency that fails (the database, a fetch, a third-party call), mocked at the boundary;
- the edges: empty, zero, one, the maximum, negative, very long, a missing optional value;
- both sides of every conditional that changes behavior.

A route handler gets at least: success, bad input, signed out, forbidden, and not found. Assert what happened, not that a function was called. Use the scaffold's helpers and the isolated `<app>_test` database.

## Measure, then fill the gaps (at most twice)

1. Write the test files for all of the modules above first, then run them with coverage, once:
   `npx vitest run --coverage --reporter=json --outputFile=.agentforge/qa/vitest.json`
   That writes the Vitest JSON and `.agentforge/qa/coverage/coverage-summary.json` together. `npm run qa:inventory` may be run once to list the pages, routes and components that have no test of their own.
2. Open `coverage-summary.json`. The floor is the customer's figure when they named one, otherwise **70% of lines overall and 80% in the logic modules** (route handlers, models/services, validation, hooks, `lib`/utility code). For each logic file below it, read the lines the report says were not run and add tests for those branches — the error path, the refusal, the edge case — in that module's own test file.
3. Run the same command once more and keep that result. Stop there.
4. Record the final percentages. If a logic file is still under the floor because the code cannot be reached from a test, say why under `gaps` in `.agentforge/build/report.json`; never report the floor as met when it was not.

If a test fails because of a real defect, fix only the production code and rerun only the affected test file; the last coverage run is the one that refreshes the JSON.

## What does not count

- A test of static markup, a snapshot that nothing reads, an assertion that cannot fail, or a mock of the very module under test.
- Narrowing `coverage.include`/`exclude` in `vitest.config.js`, adding thresholds, or skipping a test to move the number. Never weaken a meaningful assertion either.
- Chasing more than the floor (100% only when the customer asked for exactly that). Once the floor is met and the obvious branches are covered, stop.
