// Lighthouse CI: the performance layer of QA.
//
//   BASE_URL=http://localhost:3000 npx lhci collect && npx lhci assert
//
// Pages come from e2e/routes.json. CHROME_PATH, when set, is the browser to use.
// Only public pages are audited: a signed-out visitor is redirected away from a page
// with `roles` (or `"auth": true`), so scoring it would score the sign-in page again.
//
// On Windows, `lhci` can fail removing Chrome's temporary profile and discard the
// report; `npm run qa:perf` runs scripts/run-perf.mjs, which keeps it.
const fs = require('node:fs')
const path = require('node:path')

const base = (process.env.BASE_URL || 'http://localhost:3000').replace(/\/$/, '')
let pages = [{ route: '/' }]
const routesFile = path.join(__dirname, 'e2e', 'routes.json')
if (fs.existsSync(routesFile)) {
  // A file that exists but cannot be parsed is an error, not "just the home page".
  const text = fs.readFileSync(routesFile, 'utf8')
  pages = JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text)
}
const isProtected = row => row.auth === true || (Array.isArray(row.roles) && row.roles.length > 0)
const urls = pages
  .filter(row => row && row.route && !/\[|\/:/.test(row.route) && !isProtected(row))
  .map(row => base + row.route)

module.exports = {
  ci: {
    collect: {
      url: urls.length ? urls : [base + '/'],
      numberOfRuns: 1,
      chromePath: process.env.CHROME_PATH || undefined,
      settings: { preset: 'desktop', chromeFlags: '--headless=new --no-sandbox' },
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.7 }],
        'categories:accessibility': ['error', { minScore: 0.9 }],
        'categories:best-practices': ['warn', { minScore: 0.8 }],
        'categories:seo': ['warn', { minScore: 0.8 }],
      },
    },
    upload: { target: 'filesystem', outputDir: '.lighthouseci/reports' },
  },
}

