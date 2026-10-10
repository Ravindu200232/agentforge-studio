## The end-to-end journeys

The Studio runs the whole journey suite itself, once, when you finish, on its own server and a fresh test database, and records the result. Do not run the whole suite (`npm run qa:e2e`, `npx playwright test` with no file): it is refused. Write or repair a journey test only where one is missing or wrong — one spec file per journey, named by its id (`e2e/journeys/UJ-001.spec.js`) — and check it by running that one file: `node scripts/with-server.mjs -- npx playwright test e2e/journeys/UJ-001.spec.js --project=desktop`.
