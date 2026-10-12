import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  isRouteErrorResponse,
  useRouteError,
} from '@remix-run/react';

import './tailwind.css';

/**
 * Response headers for every document. A ZAP baseline reports each as missing. A route that
 * exports its own `headers` replaces these for that route, so it should spread `parentHeaders`.
 * The Content-Security-Policy allows the inline scripts Remix's own document needs; the browser only
 * ever talks to this app's own server (the database is never reached from a browser), so
 * `connect-src` stays `'self'`. Add a third-party origin to `script-src` / `frame-src` / `connect-src`
 * when another integration loads one.
 *
 * Nobody may frame the app unless `FRAME_ANCESTORS` names who. Keep it strict: the AgentForge
 * Studio's preview process lifts the rule for its own iframe, so the app never has to weaken it.
 * `X-Frame-Options` cannot name another origin, so it is sent only when nobody may frame the app.
 */
export const headers = () => {
  const frameAncestors = process.env.FRAME_ANCESTORS?.trim() || "'none'";
  return {
    ...(frameAncestors === "'none'" ? { 'X-Frame-Options': 'DENY' } : {}),
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline' https:",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data: https:",
      "connect-src 'self'",
      `frame-ancestors ${frameAncestors}`,
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join('; '),
  };
};

export const meta = () => [
  { title: 'Application' },
  { name: 'description', content: 'Replace this metadata with the application’s own.' },
];

/**
 * The document, and the only place the stylesheet is imported.
 *
 * `Meta` and `Links` are what put a route's own title and stylesheets into
 * `<head>`; `Scripts` is what makes the page interactive. A document missing
 * `Scripts` renders and then does nothing, which reads as a broken component
 * rather than a missing tag.
 */
export function Layout({ children }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App() {
  return <Outlet />;
}

/**
 * One error boundary for the whole application.
 *
 * Remix renders this inside `Layout`, so a thrown error still produces a
 * complete document. Without it the framework's default page appears, which
 * says nothing the user can act on.
 */
export function ErrorBoundary() {
  const error = useRouteError();
  const thrown = isRouteErrorResponse(error);
  return (
    <main>
      <h1>{thrown ? `${error.status} ${error.statusText}` : 'Something went wrong'}</h1>
      <p>{thrown ? error.data : 'Replace this boundary with the application’s own.'}</p>
    </main>
  );
}
