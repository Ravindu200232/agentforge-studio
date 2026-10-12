import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import http from 'node:http';
import request from 'supertest';
import { createApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';

/** A stand-in for the real service, so the gateway is tested, not the catalog. */
let upstream;
let config;

beforeAll(async () => {
  upstream = http.createServer((req, res) => {
    if (req.url === '/products') {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ products: [{ id: '1', slug: 'lamp', name: 'Desk lamp', priceCents: 4500, stock: 3 }] }));
      return;
    }
    res.writeHead(404, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'Product not found' }));
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  config = loadConfig({ PORT: '0', CATALOG_URL: 'http://127.0.0.1:' + upstream.address().port });
});
afterAll(async () => { await new Promise((resolve) => upstream.close(resolve)); });

describe('gateway routing', () => {
  it('forwards /api/products to the catalog service and preserves the body', async () => {
    const response = await request(createApp(config)).get('/api/products').expect(200);
    expect(response.body.products[0].priceCents).toBe(4500);
  });

  it('preserves an upstream 404 instead of turning it into a page', async () => {
    const response = await request(createApp(config)).get('/api/products/missing').expect(404);
    expect(response.body).toEqual({ error: 'Product not found' });
  });

  it('answers 503 when the service is not running, never 200 with an empty body', async () => {
    const dead = { ...config, services: { catalog: 'http://127.0.0.1:1' } };
    const response = await request(createApp(dead)).get('/api/products').expect(503);
    expect(response.body.error).toMatch(/unavailable/i);
  });

  it('reports its own readiness without claiming the services are healthy', async () => {
    const response = await request(createApp(config)).get('/ready').expect(200);
    expect(response.body.ok).toBe(true);
    expect(Object.keys(response.body)).not.toContain('services');
  });

  it('answers the same readiness at /health, the path every package in this stack uses', async () => {
    const response = await request(createApp(config)).get('/health').expect(200);
    expect(response.body.ok).toBe(true);
  });
});

describe('gateway response headers', () => {
  it('sends the security headers and does not name its framework', async () => {
    const response = await request(createApp(config)).get('/ready').expect(200);
    expect(response.headers['x-content-type-options']).toBe('nosniff');
    expect(response.headers['x-frame-options']).toBe('DENY');
    expect(response.headers['content-security-policy']).toMatch(/frame-ancestors 'none'/);
    expect(response.headers['x-powered-by']).toBeUndefined();
  });

  it('lets only the origins FRAME_ANCESTORS names frame it', async () => {
    process.env.FRAME_ANCESTORS = "'self' https://partner.example";
    try {
      const response = await request(createApp(config)).get('/ready').expect(200);
      expect(response.headers['content-security-policy']).toMatch(/frame-ancestors 'self' https:\/\/partner\.example/);
      expect(response.headers['x-frame-options']).toBeUndefined();   // it cannot name another origin
    } finally {
      delete process.env.FRAME_ANCESTORS;
    }
  });
});
