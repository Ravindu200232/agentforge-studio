import { vi } from 'vitest';

/**
 * Replace `fetch` for a component or page test, so it runs without a server.
 *
 * Routes are `'METHOD /path'` (the query string is ignored, `:id` matches one path segment) mapped to
 * the answer: a value (sent as JSON, status 200), `{ status, body }`, or a function of the request that returns
 * either. A request nobody stubbed answers 404 and is listed in `api.unhandled`, so a test cannot pass by
 * accident on a call it never planned for; assert `expect(api.unhandled).toEqual([])`.
 *
 *   const api = stubFetch({
 *     'GET /api/items': { items: [] },
 *     'POST /api/items': ({ body }) => ({ status: 201, body: { item: { id: '1', ...body } } }),
 *     'DELETE /api/items/:id': { status: 403, body: { error: 'Not allowed' } },
 *   });
 *   render(<ItemsPanel />);
 *   await userEvent.click(screen.getByRole('button', { name: 'Add' }));
 *   expect(api.calls('POST', '/api/items')[0].body).toEqual({ name: 'x' });
 *
 * `vitest.config.js` sets `unstubGlobals`, so the real `fetch` is back after each test.
 */
export function stubFetch(routes = {}) {
  const log = [];
  const unhandled = [];
  const table = Object.entries(routes).map(([key, handler]) => {
    const [method, pattern] = key.split(' ');
    const regex = new RegExp(`^${pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/:[A-Za-z0-9_]+/g, '[^/]+')}$`);
    return { method: method.toUpperCase(), regex, handler };
  });
  const fetchMock = vi.fn(async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, 'http://localhost');
    const method = String(init.method ?? (typeof input === 'object' ? input.method : undefined) ?? 'GET').toUpperCase();
    let body;
    if (typeof init.body === 'string') {
      try { body = JSON.parse(init.body); } catch { body = init.body; }
    }
    const entry = { method, path: url.pathname, query: Object.fromEntries(url.searchParams), body };
    log.push(entry);
    const route = table.find((r) => r.method === method && r.regex.test(url.pathname));
    if (!route) {
      unhandled.push(entry);
      return answer(404, { error: 'This request was not stubbed' });
    }
    const out = typeof route.handler === 'function' ? await route.handler(entry) : route.handler;
    return out && typeof out === 'object' && 'status' in out && 'body' in out ? answer(out.status, out.body) : answer(200, out);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetch: fetchMock, log, unhandled, calls: (method, path) => log.filter((e) => e.method === method.toUpperCase() && e.path === path) };
}

function answer(status, body) {
  return new Response(body === undefined || status === 204 ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}
