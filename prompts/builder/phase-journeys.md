## What this phase is: the journey tests

Use the saved user journeys at `.agentforge/srs/user-journeys.json`, the SRS
handoff, mapped prototype routes and the implemented app to identify the actual
selectors, roles, setup and expected outcomes. Write one browser spec per
journey at `e2e/journeys/UJ-001.spec.js` (using its own ID in the filename and
test title). Write `e2e/routes.json` with the real pages and roles.

Check the requirement traceability matrix in `.agentforge/srs/srs.json` for
requirements whose pages no journey visits. Write a spec per such page under
`e2e/requirements/`, with a test title starting with its requirement ID.
The Studio runs these tests and records the results after this phase. Stop
after writing the specs and route list.
