
const API_HOST = process.env.STUDIO_API || 'http://127.0.0.1:7824'
const WS_HOST = process.env.STUDIO_WS || 'http://127.0.0.1:7825'
const EXTRA_DEV_ORIGINS = String(process.env.STUDIO_DEV_ORIGINS || '')
  .split(',').map(value => value.trim()).filter(Boolean)
// The desktop app's build: plain files in `out/`, served by the app itself (desktop/main.js), which also
// carries every API request to its backend. No server, so no proxy and no port.
const EXPORT = process.env.STUDIO_EXPORT === '1'

module.exports = {
  basePath: '/__agentforge',
  // An export is written to its distDir: `out`, never the dev server's own `.next`.
  distDir: process.env.STUDIO_DIST_DIR || (EXPORT ? 'out' : '.next'),

  turbopack: { root: __dirname },

  reactStrictMode: false,

  ...(EXPORT ? {
    output: 'export',
    images: { unoptimized: true },
  } : {
    allowedDevOrigins: ['127.0.0.1', 'localhost', ...EXTRA_DEV_ORIGINS],
    // The API rewrite below is a proxy, and its default 30 s timeout answers a fake
    // "500 Internal Server Error" while the backend is still working - a model turn
    // (the next interview question) or a PDF render routinely takes longer.
    experimental: { proxyTimeout: 600_000 },
    async rewrites() {
      return {
        beforeFiles: [
          {
            source: '/__agentforge/api/:path*',
            destination: `${API_HOST}/__agentforge/api/:path*`,
            basePath: false,
          },
          {
            // The live build feed, through the studio's own address: one port to
            // publish, and a wss:// feed when the studio is served over HTTPS.
            source: '/__agentforge/ws',
            destination: WS_HOST,
            basePath: false,
          },
        ],
      }
    },
  }),
}
