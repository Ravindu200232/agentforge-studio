{
  "name": "sketch-next",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "seed": "node scripts/seed.mjs",
    "test": "vitest run",
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
  "dependencies": {
    "next": "^15.1.4",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "mongoose": "^8.9.5",
    "bcryptjs": "^2.4.3",
    "jose": "^5.9.6"
  },
  "devDependencies": {
    "@axe-core/playwright": "^4.10.0",
    "@lhci/cli": "^0.15.1",
    "lighthouse": "^12.6.1",
    "@playwright/test": "^1.62.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.19",
    "@vitest/coverage-v8": "^2.1.8",
    "vitest": "^2.1.8"
  }
}
