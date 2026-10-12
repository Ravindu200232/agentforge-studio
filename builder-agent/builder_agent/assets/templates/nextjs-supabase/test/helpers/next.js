import { vi } from 'vitest';

/**
 * The seams between Next.js code and a running server, written once, so a test of a page, a route
 * handler or a component only says what it is checking.
 *
 * Route handlers and server pages read the signed-in user through `next/headers`, and leave through
 * `redirect()` / `notFound()`; components use `useRouter()`. None of that works outside a request, so a
 * test replaces exactly those modules and keeps everything else real (database, bcrypt, jose, validation):
 *
 *   vi.mock('next/headers', async () => (await import('@/test/helpers/next.js')).headersMock);
 *   vi.mock('next/navigation', async () => (await import('@/test/helpers/next.js')).navigationMock);
 *   import { jar, call, withParams, renderPage, redirectedTo, router } from '@/test/helpers/next.js';
 *
 * Route handler:  const { status, body } = await call(POST, { body: { name: 'x' } });
 *                 const { status } = await call(PATCH, { method: 'PATCH', body: { name: 'y' }, params: { id } });
 * Server page:    const view = await renderPage(Page, { params: { id }, searchParams: { q: 'x' } });
 * Redirect:       expect(await redirectedTo(() => Page({ params: {}, searchParams: {} }))).toBe('/login');
 * Signed-in user: put the real session cookie in `jar` (sign in through the real login handler), and
 *                 `jar.clear()` in `beforeEach`.
 */

/** The cookie jar behind `next/headers`' `cookies()`. */
export const jar = new Map();
/** Request headers returned by `next/headers`' `headers()`. */
export const requestHeaders = {};

export const headersMock = {
  cookies: async () => ({
    get: (name) => (jar.has(name) ? { name, value: jar.get(name) } : undefined),
    getAll: () => [...jar].map(([name, value]) => ({ name, value })),
    has: (name) => jar.has(name),
    set: (nameOrOptions, value) => {
      if (typeof nameOrOptions === 'object') jar.set(nameOrOptions.name, nameOrOptions.value);
      else jar.set(nameOrOptions, value);
    },
    delete: (name) => jar.delete(typeof name === 'object' ? name.name : name),
  }),
  headers: async () => new Headers(requestHeaders),
};

/** What `redirect()` and `notFound()` throw in the real framework, as a value a test can read. */
export class NavigationSignal extends Error {
  constructor(kind, url = null) {
    super(`NEXT_${kind.toUpperCase()}`);
    this.kind = kind;
    this.url = url;
  }
}

/** One router shared by every `useRouter()`, so a test can assert on `router.push`. */
export const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn(), prefetch: vi.fn() };
/** Set these before rendering a client component that reads the URL. */
export const location = { pathname: '/', search: '', params: {} };

export const navigationMock = {
  redirect: (url) => { throw new NavigationSignal('redirect', url); },
  permanentRedirect: (url) => { throw new NavigationSignal('redirect', url); },
  notFound: () => { throw new NavigationSignal('not_found'); },
  useRouter: () => router,
  usePathname: () => location.pathname,
  useSearchParams: () => new URLSearchParams(location.search),
  useParams: () => location.params,
};

/**
 * Run something that may call `redirect()` / `notFound()`. Returns the redirect target, or 'not_found', or
 * null when it finished without navigating. Any other error is rethrown.
 */
export async function redirectedTo(run) {
  try {
    await run();
  } catch (error) {
    if (error instanceof NavigationSignal) return error.kind === 'redirect' ? error.url : error.kind;
    throw error;
  }
  return null;
}

/** Route context for a dynamic segment: `params` is a Promise in Next 15 and an object before; this is both. */
export const withParams = (params) => ({ params: both(params) });

function both(value) {
  return Object.assign(Promise.resolve(value), value);
}

/**
 * Call a route handler (`GET`, `POST`, ...) with a real `Request` and read its answer.
 * `body` is sent as JSON. Returns { status, body, headers, response }; `body` is parsed when the answer is JSON.
 */
export async function call(handler, { method, url = 'http://localhost/api', body, params, headers = {} } = {}) {
  const verb = method ?? (body === undefined ? 'GET' : 'POST');
  const init = { method: verb, headers: { ...(body === undefined ? {} : { 'content-type': 'application/json' }), ...headers } };
  if (body !== undefined) init.body = typeof body === 'string' ? body : JSON.stringify(body);
  let request;
  try {
    const { NextRequest } = await import('next/server');
    request = new NextRequest(url, init);
  } catch {
    request = new Request(url, init);
  }
  const response = await handler(request, params === undefined ? undefined : withParams(params));
  const text = await response.clone().text();
  let parsed = text;
  try { parsed = text ? JSON.parse(text) : null; } catch { /* not JSON: leave the text */ }
  return { status: response.status, body: parsed, headers: response.headers, response };
}

/** A `Request` with a JSON body, for handlers you call yourself. */
export const jsonRequest = (body, { method = 'POST', url = 'http://localhost/api', headers = {} } = {}) => new Request(url, {
  method,
  headers: { 'content-type': 'application/json', ...headers },
  body: JSON.stringify(body),
});

/**
 * Render a page. A server page is an async function: this awaits it and renders what it returns, giving it
 * `params` and `searchParams` the way Next does. A client page renders as usual.
 * Returns Testing Library's render result.
 */
export async function renderPage(Page, { params = {}, searchParams = {}, ...props } = {}) {
  const { render } = await import('@testing-library/react');
  const tree = await Page({ params: both(params), searchParams: both(searchParams), ...props });
  return render(tree);
}
