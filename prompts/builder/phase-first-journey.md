## First journey {{journey}}

Read `.agentforge/build/journey-contract.json` and its `first_journey` entry before writing. Use the approved SRS for business rules and the mapped prototype for visuals and interaction. Implement only this flow and its listed support screens, real server handlers, data requirements and authentication. Reuse the foundation and build these routes as production code.

{{routes}}

Use the selected stack's regular build and start scripts. Write or extend idempotent seed data for just this flow. On MongoDB, `npm run seed` receives the Studio's unique test database at runtime. When using Supabase, define `npm run qa:prepare` to apply the required migrations and seed the supplied isolated test project using its explicit connection variables. Use the provided Postgres URL for SQL and the test project's Supabase URL for Auth and Storage. Never use a linked production CLI target or reset user data. Use the same application schema, policies, role checks and server handlers that the real app uses.

Write `e2e/journeys/{{journey}}.spec.js` with `[{{journey}}]` in its title. Use a deterministic seed and scoped test records. Set up the correct demo role, use visible controls, and assert the approved outcome at each important step. For a write, verify the confirmation and read the created or changed record again after navigation or reload. Check required role changes and access through the actual sign-in flow. Keep any external calls in an approved test mode or choose a documented success path that needs no live transaction. Never replace app routes, storage, authentication or database writes with mocks. Studio runs just this spec and uses its recorded browser result to decide when to continue.

Record the implemented route files in `{{progress}}` using the existing `{"routes": {"/route": ["path/to/file"]}}` shape. Install the dependencies the flow and its spec actually need. Stop once the routes, setup and browser spec are in place. Subsequent phases extend the same pages, data and helpers.
