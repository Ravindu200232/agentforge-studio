import { describe, it, expect } from 'vitest';
import request from 'supertest';
import { createApp } from '../src/app.js';

/**
 * Replace these with the application's own route tests, following the same shape: build the app
 * with `createApp()` and drive it with supertest, never binding a real port. `test/helpers/db.js`
 * (shared at the repo root) is what a route test that touches MongoDB connects through.
 */
describe('server', () => {
  it('reports its own readiness without claiming the database is reachable', async () => {
    const response = await request(createApp()).get('/ready').expect(200);
    expect(response.body.ok).toBe(true);
    expect(Object.keys(response.body)).not.toContain('database');
  });

  it('answers 404 for an unknown API route rather than the client fallback', async () => {
    const response = await request(createApp()).get('/api/does-not-exist').expect(404);
    expect(response.body).toEqual({ error: 'Not found' });
  });
});

describe('response headers', () => {
  it('sends the security headers and does not name its framework', async () => {
    const response = await request(createApp()).get('/ready').expect(200);
    expect(response.headers['x-content-type-options']).toBe('nosniff');
    expect(response.headers['x-frame-options']).toBe('DENY');
    expect(response.headers['content-security-policy']).toMatch(/frame-ancestors 'none'/);
    expect(response.headers['x-powered-by']).toBeUndefined();
  });
});
