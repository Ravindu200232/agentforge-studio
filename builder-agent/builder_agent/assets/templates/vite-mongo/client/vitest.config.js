import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Enable test globals so setup files can extend expect.
    globals: true,
    setupFiles: ['test/setup.js'],
    // `test/helpers.js` stubs `fetch` for a test; the real one comes back after each test.
    unstubGlobals: true,
    include: ['test/**/*.test.{js,jsx}'],
  },
});
