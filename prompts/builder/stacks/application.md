# Application foundation

Use the selected stack prompt to author the infrastructure for this product. Keep app configuration at the root and separate the HTTP layer, authentication, domain logic, persistence and UI. Group product code around features and keep framework entrypoints small. Write a README covering installation, required environment variables, how to run and build, data setup, and how to add a feature and its tests. Use a regular dependency install and save the lockfile. Keep business behavior in source that can be tested independently of its pages.

The Studio owns QA tooling such as `scripts/with-server.mjs` and `playwright.config.js`. The application owns its test dependencies and scripts. Add `@playwright/test`, `@axe-core/playwright`, Lighthouse, and Vitest with versions compatible with the application. Include `dev`, `build`, `start`, and `test` at the root. Bind the assigned `PORT` and keep authentication and database credentials on the server.

Expose these package scripts for the Studio's QA flow:

| Script | Command |
| --- | --- |
| `test:e2e` | `playwright test --project=desktop --grep-invert "@visual\|@a11y\|@pages"` |
| `test:visual` | `playwright test --project=desktop --grep @visual --update-snapshots=missing` |
| `test:a11y` | `playwright test --project=desktop --grep @a11y` |
| `qa:e2e` | `node scripts/with-server.mjs -- npm run test:e2e` |
| `qa:visual` | `node scripts/with-server.mjs -- npm run test:visual` |
| `qa:a11y` | `node scripts/with-server.mjs -- npm run test:a11y` |
| `qa:perf` | `node scripts/with-server.mjs -- node scripts/run-perf.mjs` |
| `qa:security` | `node scripts/with-server.mjs -- node scripts/zap-scan.mjs` |
| `qa:inventory` | `node scripts/test-inventory.mjs` |

Write the seed, unit cases, and journey specs in their requested phases. Keep seeds idempotent and tests isolated from real data. Use the existing QA fixtures and report paths. Verify the application builds with its root package command before claiming readiness.
