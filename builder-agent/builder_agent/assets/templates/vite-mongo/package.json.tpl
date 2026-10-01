{
  "name": "sketch-vite-mongo",
  "private": true,
  "type": "module",
  "workspaces": [
    "server",
    "client"
  ],
  "scripts": {
    "dev": "node scripts/dev-all.mjs",
    "build": "npm run build --workspace client",
    "start": "node scripts/port-guard.mjs 4100 && node server/src/server.js",
    "seed": "node scripts/seed.mjs",
    "test": "vitest run --reporter=default --reporter=json --outputFile=test-report.json",
    "test:coverage": "vitest run --coverage",
    "test:e2e": "playwright test --project=desktop --grep-invert \"@visual|@a11y\"",
    "test:visual": "playwright test --project=desktop --grep @visual --update-snapshots=missing",
    "test:a11y": "playwright test --project=desktop --grep @a11y",
    "test:perf": "lhci collect && lhci assert",
    "qa:e2e": "node scripts/with-server.mjs -- npm run test:e2e",
    "qa:visual": "node scripts/with-server.mjs -- npm run test:visual",
    "qa:a11y": "node scripts/with-server.mjs -- npm run test:a11y",
    "qa:perf": "node scripts/with-server.mjs -- node scripts/run-perf.mjs",
    "qa:security": "node scripts/with-server.mjs -- node scripts/zap-scan.mjs",
    "qa:inventory": "node scripts/test-inventory.mjs",
    "audit": "npm audit --audit-level=high"
  },
  "engines": {
    "node": ">=20"
  },
  "devDependencies": {
    "@axe-core/playwright": "^4.10.0",
    "@lhci/cli": "^0.15.1",
    "lighthouse": "^12.6.1",
    "@playwright/test": "^1.62.0",
    "@vitest/coverage-v8": "^2.1.8",
    "vitest": "^2.1.8"
  }
}
