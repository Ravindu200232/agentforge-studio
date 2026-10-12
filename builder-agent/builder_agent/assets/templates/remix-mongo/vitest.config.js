import react from '@vitejs/plugin-react';
import path from 'node:path';
import { defineConfig } from 'vitest/config';

/**
 * The Remix plugin is deliberately absent here.
 *
 * It rewrites route modules for the framework's own loader/action split and
 * expects a Remix request to be in flight. Under the test runner there is
 * none, so including it turns every component test into an error about a
 * missing route context. Tests import the component; the plugin belongs to
 * `vite.config.js` and to the build.
 */
export default defineConfig({
  plugins: [react({ include: /\.(js|jsx)$/ })],
  // The same two aliases the application uses: `~/` for app code, which is the
  // Remix convention, and `@/` for the project root.
  resolve: {
    alias: {
      '~': path.resolve(process.cwd(), 'app'),
      '@': path.resolve(process.cwd()),
    },
  },
  test: {
    // jsdom is for components. Server code (loaders, actions, Mongo, auth, `jose`, `bcrypt`) must run
    // in Node: under jsdom, `jose` rejects its keys ("payload must be an instance of Uint8Array")
    // because jsdom has its own `Uint8Array`. Start such a file with `// @vitest-environment node`.
    environment: 'jsdom',
    // The suites share one test database. In parallel, one file's `clearCollections()` deletes the
    // rows another file is asserting on, and the failure looks like a product bug.
    fileParallelism: false,
    globals: true,
    // `test/helpers/fetch.js` stubs `fetch` for a test; the real one comes back after each test.
    unstubGlobals: true,
    setupFiles: ['vitest.env.js', 'vitest.setup.js'],
    include: ['test/**/*.test.{js,jsx}'],
    // `npm run test:coverage`. Every source file is listed, tested or not, so a route nothing tests
    // shows as 0 % instead of being missing. `npm run qa:inventory` says which unit is untested.
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      reportsDirectory: '.agentforge/qa/coverage',
      include: ['app/**/*.{js,jsx}', 'lib/**/*.js', 'models/**/*.js', 'hooks/**/*.{js,jsx}', 'services/**/*.js'],
      exclude: ['**/*.test.*', 'test/**', 'e2e/**', 'lib/db.js', 'app/entry.*'],
    },
    testTimeout: 15000,
    hookTimeout: 15000,
  },
});
