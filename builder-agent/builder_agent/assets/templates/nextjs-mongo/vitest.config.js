import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  // Apply JSX transformation to .js files used in Next.js App Router routes.
  plugins: [react({ include: /\.(js|jsx)$/ })],
  // The same `@/` alias the application uses. A test that reaches past it with
  // a relative path breaks the moment a file moves.
  resolve: {
    alias: {
      '@': path.resolve(process.cwd()),
      'server-only': path.resolve(process.cwd(), 'test/helpers/server-only-stub.js'),
    },
  },
  test: {
    // jsdom is for components and pages. Server code (route handlers, Mongo, auth, `jose`,
    // `bcrypt`) must run in Node: under jsdom, `jose` rejects its keys ("payload must be an
    // instance of Uint8Array") because jsdom has its own `Uint8Array`. Name such a suite
    // `*.node.test.js`, or start the file with `// @vitest-environment node`.
    environment: 'jsdom',
    environmentMatchGlobs: [['test/**/*.node.test.{js,jsx}', 'node']],
    // The suites share one test database. In parallel, one file's `clearCollections()` deletes
    // the rows another file is asserting on, and the failure looks like a product bug.
    fileParallelism: false,
    // Enable global assertions required by test matchers setup file.
    globals: true,
    // `test/helpers/fetch.js` stubs `fetch` for a test; the real one comes back after each test.
    unstubGlobals: true,
    setupFiles: ['vitest.env.js', 'vitest.setup.js'],
    include: ['test/**/*.test.{js,jsx}'],
    // `npm run test:coverage`. Every source file is listed, tested or not, so a page nothing tests
    // shows as 0 % instead of being missing. `npm run qa:inventory` says which unit is untested.
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      reportsDirectory: '.agentforge/qa/coverage',
      include: ['app/**/*.{js,jsx}', 'components/**/*.{js,jsx}', 'lib/**/*.js', 'models/**/*.js', 'hooks/**/*.{js,jsx}', 'services/**/*.js', 'src/**/*.{js,jsx}', 'proxy.js', 'middleware.js'],
      exclude: ['**/*.test.*', 'test/**', 'e2e/**', 'lib/db.js'],
    },
    testTimeout: 15000,
    hookTimeout: 15000,
  },
});
