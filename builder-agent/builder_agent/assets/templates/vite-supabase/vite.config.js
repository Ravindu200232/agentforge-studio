import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '127.0.0.1',
    port: Number(process.env.PORT ?? 0),
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: Number(process.env.PORT ?? 0),
    strictPort: true,
  },
});
