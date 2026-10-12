import React from 'react';

/**
 * The seams between a Remix route and a running server, written once, so a test of a loader, an action or a
 * route's page only says what it is checking.
 *
 * Loader / action (server code: start the file with `// @vitest-environment node`):
 *   import { run } from '@/test/helpers/remix.js';
 *   import { loader, action } from '~/routes/some.route.jsx';
 *   const { status, body } = await run(loader, { url: 'http://localhost/some?q=x', params: { id } });
 *   const { status, location } = await run(action, { method: 'POST', form: { name: 'x' } });
 *   const { status } = await run(action, { method: 'POST', body: { name: 'x' } });      // JSON body
 * A loader or action may return data, return a Response, or throw one (`throw redirect(...)`, `throw json(..., 404)`):
 * all three come back as { status, body, location, response }.
 *
 * A route's page (jsdom): render it inside Remix's own router so `useLoaderData`, `Link`, `Form` and
 * `useActionData` work. Give it the data instead of a database, or let the real loader run:
 *   import { renderRoute } from '@/test/helpers/remix.js';
 *   import * as route from '~/routes/some.route.jsx';
 *   renderRoute(route, { path: '/some', loader: () => ({ items: [] }) });
 *   expect(await screen.findByRole('heading', { name: '...' })).toBeInTheDocument();      // loaders are async: findBy*
 * A route with no loader or action, and no `Link`/`Form`, can be rendered directly: `render(<Route />)`.
 */

/** Call a loader or action with a real `Request` and read the answer. */
export async function run(handler, { url = 'http://localhost/', method, body, form, params = {}, headers = {}, context = {} } = {}) {
  const verb = method ?? (body === undefined && form === undefined ? 'GET' : 'POST');
  const init = { method: verb, headers: { ...headers } };
  if (form !== undefined) {
    init.body = new URLSearchParams(form);
    init.headers['content-type'] = 'application/x-www-form-urlencoded';
  } else if (body !== undefined) {
    init.body = typeof body === 'string' ? body : JSON.stringify(body);
    init.headers['content-type'] = 'application/json';
  }
  let result;
  try {
    result = await handler({ request: new Request(url, init), params, context });
  } catch (thrown) {
    if (!(thrown instanceof Response)) throw thrown;
    result = thrown;   // `throw redirect(...)` / `throw json(..., 404)`
  }
  if (!(result instanceof Response)) return { status: 200, body: result ?? null, location: null, headers: new Headers(), response: null };
  const text = await result.clone().text();
  let parsed = text;
  try { parsed = text ? JSON.parse(text) : null; } catch { /* not JSON: leave the text */ }
  return { status: result.status, body: parsed, location: result.headers.get('location'), headers: result.headers, response: result };
}

/**
 * Under jsdom the router builds `new Request(url, { signal })` with jsdom's `AbortSignal`, which Node's
 * `Request` rejects ("Expected signal to be an instance of AbortSignal"). A test never aborts a navigation,
 * so the signal is dropped.
 */
let signalsAccepted = false;
function acceptJsdomSignals() {
  if (signalsAccepted) return;
  signalsAccepted = true;
  const NativeRequest = globalThis.Request;
  globalThis.Request = class extends NativeRequest {
    constructor(input, init) {
      super(input, init?.signal ? { ...init, signal: undefined } : init);
    }
  };
}

/**
 * Render a route module's page inside Remix's test router. `route` is `import * as route from '~/routes/...'`.
 * `loader` / `action` override the module's own (use them to skip the database); `url` is where the router starts.
 * Returns Testing Library's render result.
 */
export async function renderRoute(route, { path = '/', url = path, loader, action, loaderData } = {}) {
  acceptJsdomSignals();
  const [{ render }, { createRemixStub }] = await Promise.all([import('@testing-library/react'), import('@remix-run/testing')]);
  const Stub = createRemixStub([{
    path,
    Component: route.default,
    ErrorBoundary: route.ErrorBoundary,
    loader: loader ?? (loaderData === undefined ? route.loader : () => loaderData),
    action: action ?? route.action,
  }]);
  return render(React.createElement(Stub, { initialEntries: [url] }));
}
