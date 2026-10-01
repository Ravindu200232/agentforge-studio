import { defineConfig } from 'vitest/config';

/**
 * Root settings for `npm run test:coverage`. Which suites run, and how, is decided by
 * `vitest.workspace.js` (the server and the client bring their own config).
 *
 * Every source file is listed, tested or not, so a route or component nothing tests shows as 0 %
 * instead of being missing. `npm run qa:inventory` says which unit is untested.
 */
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      reportsDirectory: '.agentforge/qa/coverage',
      include: ['server/src/**/*.js', 'client/src/**/*.{js,jsx}'],
      exclude: ['**/*.test.*', '**/server.js', '**/main.jsx', '**/config.js', '**/db.js'],
    },
  },
});
