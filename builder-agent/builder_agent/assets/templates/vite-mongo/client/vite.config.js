import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: Number(process.env.VITE_PORT ?? 5174),
    strictPort: true,
    // Proxy /api calls to the server during development.
    proxy: { '/api': { target: `http://127.0.0.1:${process.env.PORT ?? 4100}`, changeOrigin: true } },
  },
});
