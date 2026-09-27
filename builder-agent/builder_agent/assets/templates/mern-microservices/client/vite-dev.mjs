import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

// Start Vite without bundling vite.config.js. On restricted Windows desktops,
// esbuild's config loader can traverse an unreadable parent directory even
// though the client and its dependencies are readable. The build still uses
// vite.config.js; local preview only needs these same settings directly.
const port = Number(process.env.VITE_PORT ?? 5173);
const gateway = Number(process.env.PORT ?? 4000);
const server = await createServer({
  configFile: false,
  root: process.cwd(),
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port,
    strictPort: true,
    proxy: { '/api': { target: `http://127.0.0.1:${gateway}`, changeOrigin: true } },
    fs: { allow: [process.cwd()] },
  },
});
await server.listen();
server.printUrls();
