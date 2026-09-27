// Playwright runs three QA layers against the running app: end-to-end journeys,
// the visual (screenshot) check and the accessibility check.
//
//   npm run qa:e2e        # starts the built app on a free port, runs it, stops it
//   BASE_URL=http://localhost:3000 npx playwright test --project=desktop
//
// QA sets BASE_URL to the live preview. PW_CHROMIUM_EXECUTABLE, when set, is a
// Chromium already on this machine, so no second browser is downloaded.
//
// Do not pass `--reporter=...` on the command line: it replaces the reporters
// below, and test-results/results.json (which the Testing view reads) is not written.
import { defineConfig, devices } from '@playwright/test'

const executablePath = process.env.PW_CHROMIUM_EXECUTABLE || undefined

export default defineConfig({
  testDir: './e2e',
  outputDir: 'test-results/artifacts',
  timeout: 45_000,
  // Missing screenshot baselines are written, never overwritten. (Playwright still fails the
  // test that wrote one; visual.spec.js records its first baseline itself so that run passes.)
  updateSnapshots: 'missing',
  expect: {
    timeout: 7_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: 'disabled' },
  },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 3,
  retries: 0,
  reporter: [
    ['./e2e/live-reporter.js'],
    ['json', { outputFile: 'test-results/results.json' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    screenshot: 'on',
    trace: 'retain-on-failure',
    // AGENTFORGE_LIVE_SLOWMO=250 slows every browser action by that many ms, to watch a run in the
    // Studio's preview at a human pace (the default is full speed).
    launchOptions: {
      ...(executablePath ? { executablePath } : {}),
      ...(Number(process.env.AGENTFORGE_LIVE_SLOWMO) > 0 ? { slowMo: Number(process.env.AGENTFORGE_LIVE_SLOWMO) } : {}),
    },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
})
