import path from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import express from 'express';
import { proxyTo } from './proxy.js';

const here = path.dirname(fileURLToPath(import.meta.url));
// packages/gateway/src -> packages/gateway -> packages -> repo root -> client
const clientDist = path.resolve(here, '../../../client/dist');

export function createApp(config) {
  const app = express();
  // `X-Powered-By: Express` tells a scanner which framework to attack.
  app.disable('x-powered-by');
  // The gateway is the only public door, so it is where response headers are set. A ZAP
  // baseline reports each as missing. The policy allows the built client's inline bootstrap;
  // add a third-party origin to script-src / connect-src when an integration needs one.
  // Nobody may frame the app unless FRAME_ANCESTORS names who. Keep it strict: the AgentForge
  // Studio's preview process lifts the rule for its own iframe, so the app never has to weaken it.
  // X-Frame-Options cannot name another origin, so it is sent only when nobody may frame the app.
  const frameAncestors = process.env.FRAME_ANCESTORS?.trim() || "'none'";
  app.use((req, res, next) => {
    res.set({
      ...(frameAncestors === "'none'" ? { 'X-Frame-Options': 'DENY' } : {}),
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
      'Content-Security-Policy': [
        "default-src 'self'", "script-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline' https:",
        "img-src 'self' data: blob: https:", "font-src 'self' data: https:", "connect-src 'self'",
        `frame-ancestors ${frameAncestors}`, "base-uri 'self'", "form-action 'self'", "object-src 'none'",
      ].join('; '),
    });
    next();
  });
  app.use(express.json());

  // Readiness is about this process. It must not report the whole system
  // healthy, because a 200 here says nothing about the services behind it.
  // `/health` is the same check under the name every package in this stack
  // uses (each service has its own `/health`), so one container healthcheck
  // command works for the gateway and for every service alike.
  const ready = (req, res) => res.json({ ok: true, clientBuilt: existsSync(clientDist) });
  app.get('/ready', ready);
  app.get('/health', ready);

  app.use('/api/products', proxyTo(config.services.catalog));

  if (existsSync(clientDist)) {
    app.use(express.static(clientDist));
    // The SPA fallback comes last and must not swallow /api: a missing API
    // route has to stay a 404, not silently return index.html with status 200.
    app.get(/^(?!\/api\/).*/, (req, res) => res.sendFile(path.join(clientDist, 'index.html')));
  } else {
    app.get('/', (req, res) => res.status(503).type('text/plain')
      .send('Client bundle is not built. Run: npm run build'));
  }
  app.use((req, res) => res.status(404).json({ error: 'Not found' }));
  return app;
}
