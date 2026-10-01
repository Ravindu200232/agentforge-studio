import { fileURLToPath } from 'node:url';

const production = process.env.NODE_ENV === 'production';

/**
 * Response headers every page and API answer carries. A ZAP baseline reports each of these
 * as missing, and each one is a one-line default rather than a per-page decision.
 *
 * The Content-Security-Policy is production-only (the dev server evaluates code for hot
 * reload). `'unsafe-inline'` scripts are what Next's own bootstrap needs without a
 * per-request nonce. When an integration loads a third-party script, frame or API
 * (a payment widget, analytics, a map), add its origin to `script-src`, `frame-src` or
 * `connect-src` here, or the browser will block it and the console will say why.
 *
 * Nobody may frame the app unless `FRAME_ANCESTORS` names who when you BUILD (Next bakes these
 * headers into the build). Keep it strict: the AgentForge Studio's preview process lifts the rule
 * for its own iframe, so the app never has to weaken it. `X-Frame-Options` cannot name another
 * origin, so it is sent only when nobody may frame the app.
 */
const frameAncestors = process.env.FRAME_ANCESTORS?.trim() || "'none'";
const securityHeaders = [
  ...(frameAncestors === "'none'" ? [{ key: 'X-Frame-Options', value: 'DENY' }] : []),
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
  ...(production ? [{
    key: 'Content-Security-Policy',
    value: [
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
  }] : []),
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  // The application owns its tracing root.  AgentForge keeps each generated
  // project under a shared workspaces directory, which also has lockfiles.
  // Without this, Next infers the parent as the root and logs a warning on
  // every preview start.
  outputFileTracingRoot: fileURLToPath(new URL('.', import.meta.url)),
  // `X-Powered-By: Next.js` tells a scanner which framework to attack.
  poweredByHeader: false,
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

export default nextConfig;
