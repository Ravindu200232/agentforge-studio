
const API_HOST = process.env.STUDIO_API || 'http://127.0.0.1:7824'
const WS_HOST = process.env.STUDIO_WS || 'http://127.0.0.1:7825'
const EXTRA_DEV_ORIGINS = String(process.env.STUDIO_DEV_ORIGINS || '')
  .split(',').map(value => value.trim()).filter(Boolean)

module.exports = {
  basePath: '/__agentforge',
  distDir: process.env.STUDIO_DIST_DIR || '.next',

  turbopack: { root: __dirname },

  reactStrictMode: false,

  allowedDevOrigins: ['127.0.0.1', 'localhost', ...EXTRA_DEV_ORIGINS],
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
}
