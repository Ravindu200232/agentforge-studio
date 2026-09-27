import { describe, it, expect, vi } from 'vitest';
import { request, formatPrice } from '../src/api.js';
import { stubFetch } from './helpers.js';

/**
 * The client's one door to the gateway. These also show how a component or page test stubs the network:
 * `stubFetch` answers by 'METHOD /path' and records every call, so a test states what was sent and shown.
 */
describe('request', () => {
  it('sends JSON under /api and returns the parsed body', async () => {
    const api = stubFetch({ 'POST /api/things': ({ body }) => ({ status: 201, body: { thing: body } }) });
    const result = await request('/things', { method: 'POST', body: { name: 'x' } });
    expect(result).toEqual({ thing: { name: 'x' } });
    expect(api.calls('POST', '/api/things')[0].body).toEqual({ name: 'x' });
  });

  it('turns a failed answer into an Error that carries the message and the status', async () => {
    stubFetch({ 'GET /api/missing': { status: 404, body: { error: 'Not here' } } });
    await expect(request('/missing')).rejects.toMatchObject({ message: 'Not here', status: 404 });
  });

  it('keeps the real status when the gateway answers with something that is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>Bad gateway</html>', { status: 502 })));
    await expect(request('/anything')).rejects.toMatchObject({ message: 'Request failed (502)', status: 502 });
  });
});

describe('formatPrice', () => {
  it('formats cents as the string a page shows', () => {
    expect(formatPrice(4500)).toBe('$45.00');
  });

  it('treats a missing price as zero rather than throwing', () => {
    expect(formatPrice(undefined)).toBe('$0.00');
  });
});
