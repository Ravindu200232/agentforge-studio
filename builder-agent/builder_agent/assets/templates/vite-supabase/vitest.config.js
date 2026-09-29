import path from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/**
 * `import.meta.env.VITE_*` is replaced by Vite when it resolves config, not read live from
 * `process.env` at call time - a `setupFiles` script (which runs after that) is too late to
 * redirect it the way `vitest.env.js` redirects `process.env.SUPABASE_URL` in the other stacks.
 * So the override happens right here, before `defineConfig` runs: a test never talks to this
 * project's real Supabase project (AgentForge injects its real URL into every command's
 * environment, including this one) - only to the local stack (`supabase start`).
 */
process.env.VITE_SUPABASE_URL = 'http://127.0.0.1:54321';
process.env.VITE_SUPABASE_ANON_KEY = process.env.TEST_SUPABASE_ANON_KEY ?? '';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(process.cwd(), 'src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // `test/helpers.js` stubs `fetch` for a test; the real one comes back after each test.
    unstubGlobals: true,
    setupFiles: ['test/setup.js'],
    include: ['test/**/*.test.{js,jsx}'],
    // `npm run test:coverage`. Every source file is listed, tested or not, so a component nothing
    // tests shows as 0% instead of being missing. `npm run qa:inventory` says which unit is untested.
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'json-summary'],
      reportsDirectory: '.agentforge/qa/coverage',
      include: ['src/**/*.{js,jsx}'],
      exclude: ['**/*.test.*', 'test/**', 'e2e/**', 'src/lib/supabase.js', 'src/main.jsx'],
    },
    testTimeout: 15000,
    hookTimeout: 15000,
  },
});
