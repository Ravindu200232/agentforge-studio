import express from 'express';
import { itemsRouter } from './routes/items.routes.js';

/**
 * The app is built without listening, so a suite can drive it over supertest
 * with no port and no teardown, and server.js stays the only file that binds.
 */
export function createApp() {
  const app = express();
  app.use(express.json());
  // Readiness is about this process only. It must not claim anything about
  // the services or databases behind it.
  app.get('/health', (req, res) => res.json({ ok: true }));
  app.use('/items', itemsRouter);
  app.use((req, res) => res.status(404).json({ error: 'Not found' }));
  // Four arguments: Express only treats this as an error handler with all four.
  app.use((error, req, res, next) => {
    if (error?.code === 11000) return res.status(409).json({ error: 'Duplicate key' });
    if (error?.name === 'ValidationError') return res.status(400).json({ error: error.message });
    console.error('unhandled service error', error);
    res.status(500).json({ error: 'Internal error' });
  });
  return app;
}
