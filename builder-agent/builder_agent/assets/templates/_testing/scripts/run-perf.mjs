/**
 * Lighthouse over the app's public pages, with the report kept.
 *
 *   npm run qa:perf                          # starts the app on a free port (with-server.mjs)
 *   BASE_URL=http://localhost:<app-port> node scripts/run-perf.mjs
 *
 * `lhci collect` cannot be relied on on Windows: Chrome's launcher fails removing its
 * temporary profile (EPERM) and the CI wrapper throws the finished report away. The
 * `lighthouse` CLI itself writes the report to an explicit path before that cleanup,
 * so a non-zero launcher exit with a report on disk is still a measured result.
 *
 * Pages come from e2e/routes.json, public ones only: a signed-out visitor is redirected
 * away from a protected page, and a page that lands somewhere else is recorded as
 * skipped rather than scoring the sign-in page under another name.
 * Writes .lighthouseci/reports/<page>.json and .lighthouseci/summary.json.
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const require = createRequire(path.join(process.cwd(), 'package.json'))
const base = (process.env.BASE_URL || '').replace(/\/$/, '')
if (!base) {
  console.error('BASE_URL is not set. Run `npm run qa:perf`, which starts the app and sets it.')
  process.exit(3)
}

const REPORTS = path.join('.lighthouseci', 'reports')
const THRESHOLDS = {
  performance: { level: 'warn', min: 0.7 },
  accessibility: { level: 'error', min: 0.9 },
  'best-practices': { level: 'warn', min: 0.8 },
  seo: { level: 'warn', min: 0.8 },
}

function publicRoutes() {
  let rows = [{ route: '/' }]
  const file = path.join('e2e', 'routes.json')
  if (fs.existsSync(file)) {
    // A file that exists but cannot be parsed is an error, not "just the home page".
    const text = fs.readFileSync(file, 'utf8')
    rows = JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text)
  }
  const isProtected = (row) => row.auth === true || (Array.isArray(row.roles) && row.roles.length > 0)
  const routes = rows.filter((row) => row?.route && !/\[|\/:/.test(row.route) && !isProtected(row)).map((row) => row.route)
  return routes.length ? routes : ['/']
}

/** The browser to use: an explicit one, else the Chromium Playwright already downloaded. */
async function chromium() {
  for (const candidate of [process.env.CHROME_PATH, process.env.PW_CHROMIUM_EXECUTABLE]) {
    if (candidate && fs.existsSync(candidate)) return candidate
  }
  try {
    const playwright = await import(pathToFileURL(require.resolve('@playwright/test')).href)
    const found = playwright.chromium.executablePath()
    if (found && fs.existsSync(found)) return found
  } catch { /* let Lighthouse look for Chrome itself */ }
  return undefined
}

let cli
try { cli = require.resolve('lighthouse/cli/index.js') } catch {
  console.error('lighthouse is not installed: run npm install')
  process.exit(3)
}

fs.mkdirSync(REPORTS, { recursive: true })
const chrome = await chromium()
const results = []
let failures = 0

for (const route of publicRoutes()) {
  const slug = route.replace(/\W+/g, '') || 'home'
  const out = path.join(REPORTS, `${slug}.json`)
  fs.rmSync(out, { force: true })
  console.log(`Auditing ${base}${route}${chrome ? ` (chrome: ${chrome})` : ''}`)

  let errors = ''
  const code = await new Promise((resolve) => {
    const child = spawn(process.execPath, [
      cli, `${base}${route}`, '--output=json', `--output-path=${out}`,
      '--only-categories=performance,accessibility,best-practices,seo', '--preset=desktop',
      '--chrome-flags=--headless=new --no-sandbox', '--quiet',
      ...(chrome ? [`--chrome-path=${chrome}`] : []),
    ], { stdio: ['ignore', 'inherit', 'pipe'], env: process.env })
    child.stderr.on('data', (chunk) => { errors = (errors + chunk).slice(-6000) })
    child.on('exit', (exitCode) => resolve(exitCode ?? 1))
  })
  if (!fs.existsSync(out)) {
    console.log(`  no report was written (exit ${code})`)
    console.log(errors.trim().split(String.fromCharCode(10)).slice(0, 8).join(String.fromCharCode(10)))
    failures += 1
    continue
  }
  // Chrome's launcher failing to delete its temporary profile (EPERM) is noise once the report exists.
  if (code !== 0 && /EPERM/.test(errors)) console.log('  (Chrome could not remove its temp profile: a known Windows cleanup error, the report was written)')

  const report = JSON.parse(fs.readFileSync(out, 'utf8'))
  const landed = new URL(report.finalDisplayedUrl || `${base}${route}`).pathname
  if (landed !== route) {
    console.log(`  skipped: ${route} redirected to ${landed}`)
    results.push({ route, url: report.finalDisplayedUrl, skipped: `redirected to ${landed}`, report: out })
    continue
  }

  const scores = {}
  for (const [category, rule] of Object.entries(THRESHOLDS)) {
    const score = report.categories[category]?.score ?? null
    scores[category] = score === null ? null : Math.round(score * 100)
    const below = score !== null && score < rule.min
    if (below && rule.level === 'error') failures += 1
    console.log(`  ${category.padEnd(15)} ${scores[category] ?? 'n/a'}${below ? `  <- below ${Math.round(rule.min * 100)} (${rule.level})` : ''}`)
  }
  const metric = (id) => report.audits[id]?.displayValue?.replace(/\s+/g, ' ') ?? 'n/a'
  results.push({
    route, url: report.finalDisplayedUrl, report: out, scores,
    metrics: {
      first_contentful_paint: metric('first-contentful-paint'),
      largest_contentful_paint: metric('largest-contentful-paint'),
      cumulative_layout_shift: metric('cumulative-layout-shift'),
      total_blocking_time: metric('total-blocking-time'),
      speed_index: metric('speed-index'),
    },
    lighthouse_cli_exit_code: code,
  })
}

fs.writeFileSync(path.join('.lighthouseci', 'summary.json'),
  `${JSON.stringify({ audited_at: new Date().toISOString(), thresholds: THRESHOLDS, results }, null, 2)}\n`)
const scored = results.filter((row) => row.scores).length
console.log(failures === 0 && scored
  ? `\nPASS: ${scored} page(s) met the thresholds`
  : failures ? `\nFAIL: ${failures} threshold(s) not met or report(s) missing` : '\nFAIL: no page was scored')
process.exit(failures === 0 && scored ? 0 : 1)
