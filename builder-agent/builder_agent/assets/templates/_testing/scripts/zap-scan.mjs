/**
 * Security baseline scan of the running app. Always leaves evidence.
 *
 *   npm run qa:security                       # starts the app on a free port (with-server.mjs)
 *   npm run qa:security -- --install-zap      # once: fetch ZAP (and a JRE if there is no Java)
 *   BASE_URL=http://localhost:<app-port> node scripts/zap-scan.mjs [--engine auto|zap|baseline] [--out <dir>]
 *
 * Which engine ran is always in the result and is never blurred:
 *
 *   zap                  OWASP ZAP's own passive baseline (spider + passive scan, its Automation
 *                        Framework). Found in ZAP_PATH, on PATH, in its default install folder or
 *                        in ~/.agentforge/zap (what --install-zap fetches: no admin rights, about
 *                        200 MB, shared by every project on this machine).
 *   agentforge-baseline  Used only when ZAP cannot run here: passive GET-only checks of response
 *                        headers, cookies, information leaks and exposed files, over the same rule
 *                        ids and .zap/rules.tsv. It is real evidence and it is NOT a ZAP scan, so
 *                        its status is `partial`, never `passed`.
 *
 * Only ever point this at the isolated local server. It sends GET requests and reads responses;
 * it never posts, fuzzes or attacks. Writes <out>/summary.json (default .agentforge/qa/zap) plus
 * the engine's report. Exit code: 0 no rule at FAIL level, 1 a FAIL-level finding, 3 could not run.
 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import net from 'node:net'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const args = process.argv.slice(2)
const has = (name) => args.includes(name)
const value = (name, fallback) => {
  const at = args.indexOf(name)
  return at >= 0 && args[at + 1] ? args[at + 1] : fallback
}
const windows = process.platform === 'win32'
const OUT = path.resolve(value('--out', path.join('.agentforge', 'qa', 'zap')))
const HOME = path.join(os.homedir(), '.agentforge', 'zap')
const engineChoice = value('--engine', 'auto')

const readJson = (file) => {
  try {
    const text = fs.readFileSync(file, 'utf8')
    return JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text)
  } catch { return null }
}
const RISK = ['Informational', 'Low', 'Medium', 'High']

// --- the rules: .zap/rules.tsv -------------------------------------------------------------

function readRules() {
  const rules = new Map()
  try {
    for (const line of fs.readFileSync(path.join('.zap', 'rules.tsv'), 'utf8').split(/\r?\n/)) {
      if (!line.trim() || line.startsWith('#')) continue
      const [id, action] = line.split('\t')
      if (id && ['IGNORE', 'WARN', 'FAIL'].includes(action?.trim())) rules.set(id.trim(), action.trim())
    }
  } catch { /* no rules file: risk decides */ }
  return rules
}

/** A rule's action, else its risk: High fails, everything else warns. */
function judge(alerts, rules) {
  const failing = []
  const warnings = []
  const ignored = []
  for (const alert of alerts) {
    const action = rules.get(alert.id) ?? (alert.risk === 'High' ? 'FAIL' : 'WARN')
    ;({ FAIL: failing, IGNORE: ignored }[action] ?? warnings).push({ ...alert, action })
  }
  return { failing, warnings, ignored }
}

// --- OWASP ZAP ------------------------------------------------------------------------------

function which(name) {
  const found = spawnSync(windows ? 'where' : 'which', [name], { encoding: 'utf8' })
  return found.status === 0 ? found.stdout.split(/\r?\n/)[0].trim() : null
}

function findZap() {
  const candidates = []
  const listed = process.env.ZAP_PATH
  if (listed) {
    const dir = fs.existsSync(listed) && fs.statSync(listed).isDirectory()
    candidates.push(dir ? path.join(listed, windows ? 'zap.bat' : 'zap.sh') : listed)
  }
  for (const name of windows ? ['zap.bat'] : ['zap.sh', 'zaproxy']) candidates.push(which(name))
  candidates.push(...(windows
    ? ['C:\\Program Files\\ZAP\\Zed Attack Proxy\\zap.bat', 'C:\\Program Files (x86)\\ZAP\\Zed Attack Proxy\\zap.bat']
    : ['/Applications/ZAP.app/Contents/Java/zap.sh', '/usr/share/zaproxy/zap.sh', '/opt/zaproxy/zap.sh']))
  const installed = readJson(path.join(HOME, 'install.json'))
  if (installed?.zap) candidates.push(installed.zap)
  const zap = candidates.find((file) => file && fs.existsSync(file))
  return zap ? { zap, javaHome: installed?.javaHome } : null
}

const quote = (text) => `"${text}"`

/** ZAP's proxy defaults to 8080, which is often taken; it gets a free loopback port of its own. */
function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer()
    probe.once('error', reject)
    probe.listen(0, '127.0.0.1', () => { const { port } = probe.address(); probe.close(() => resolve(port)) })
  })
}

async function runZap({ zap, javaHome }, target) {
  fs.mkdirSync(OUT, { recursive: true })
  const plan = path.join(OUT, 'automation.yaml')
  const url = target.replace(/\/$/, '')
  const forward = (file) => file.replace(/\\/g, '/')
  fs.writeFileSync(plan, `env:
  contexts:
    - name: app
      urls: ["${url}"]
      includePaths: ['${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}.*']
  parameters:
    failOnError: true
    progressToStdout: true
jobs:
  - type: passiveScan-config
    parameters:
      scanOnlyInScope: true
  - type: spider
    parameters:
      context: app
      maxDuration: 2
      maxDepth: 5
  - type: passiveScan-wait
    parameters:
      maxDuration: 5
  - type: report
    parameters:
      template: traditional-json
      reportDir: "${forward(OUT)}"
      reportFile: zap-report
      reportTitle: Baseline scan
`)
  fs.rmSync(path.join(OUT, 'zap-report.json'), { force: true })
  const port = await freePort()
  // ZAP's own working folder is ~250 MB of add-ons and a database: it lives in the temp folder, never in the project.
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'agentforge-zap-'))
  const dispose = () => { try { fs.rmSync(home, { recursive: true, force: true, maxRetries: 5, retryDelay: 400 }) } catch { /* temp: the OS clears it */ } }
  const zapArgs = ['-cmd', '-autorun', plan, '-dir', home, '-host', '127.0.0.1', '-port', String(port)]
  const env = { ...process.env }
  if (javaHome) {
    env.JAVA_HOME = javaHome
    env.PATH = `${path.join(javaHome, 'bin')}${path.delimiter}${env.PATH}`
  }
  const viaShell = windows && /\.(bat|cmd)$/i.test(zap)
  // ZAP's launcher runs `java -jar zap-x.y.z.jar` by relative path, so it must start in its own folder.
  const cwd = path.dirname(zap)
  return new Promise((resolve, reject) => {
    let output = ''
    const child = viaShell
      ? spawn([quote(zap), ...zapArgs.map(quote)].join(' '), { shell: true, env, cwd })
      : spawn(zap, zapArgs, { env, cwd })
    const timer = setTimeout(() => { child.kill(); dispose(); reject(new Error('ZAP did not finish within 12 minutes')) }, 12 * 60_000)
    for (const stream of [child.stdout, child.stderr]) stream.on('data', (chunk) => { output = (output + chunk).slice(-4000) })
    child.on('error', (error) => { clearTimeout(timer); dispose(); reject(error) })
    child.on('exit', (code) => {
      clearTimeout(timer)
      dispose()
      const report = readJson(path.join(OUT, 'zap-report.json'))
      if (!report) reject(new Error(`ZAP produced no report (exit ${code}). Its output ended: ${output.trim().split(/\r?\n/).slice(-6).join(' | ')}`))
      else resolve({ report, code, command: `${path.basename(zap)} ${zapArgs.join(' ')}` })
    })
  })
}

function alertsFromZap(report) {
  const alerts = []
  for (const site of report.site ?? []) {
    for (const alert of site.alerts ?? []) {
      alerts.push({
        id: String(alert.pluginid ?? alert.alertRef ?? ''),
        name: alert.alert ?? alert.name ?? 'alert',
        risk: RISK[Number(alert.riskcode)] ?? String(alert.riskdesc ?? '').split(' ')[0],
        count: Number(alert.count ?? alert.instances?.length ?? 1),
        description: String(alert.desc ?? '').replace(/<[^>]+>/g, '').trim().slice(0, 300),
        urls: (alert.instances ?? []).slice(0, 5).map((row) => row.uri),
      })
    }
  }
  return alerts
}

// --- installing ZAP (once per machine, only when asked) -------------------------------------

async function download(url, file, label) {
  console.log(`Downloading ${label} ...`)
  const response = await fetch(url, { redirect: 'follow', headers: { 'user-agent': 'agentforge-zap-install' } })
  if (!response.ok || !response.body) throw new Error(`${label}: HTTP ${response.status} from ${url}`)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(file))
  console.log(`  saved ${(fs.statSync(file).size / 1e6).toFixed(0)} MB to ${file}`)
}

function extract(archive, into) {
  fs.mkdirSync(into, { recursive: true })
  const done = spawnSync('tar', ['-xf', archive, '-C', into], { encoding: 'utf8' })
  if (done.status !== 0) throw new Error(`could not extract ${archive}: ${done.stderr || done.error?.message}`)
}

function findFile(dir, name, depth = 4) {
  if (depth < 0 || !fs.existsSync(dir)) return null
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isFile() && entry.name === name) return full
    if (entry.isDirectory()) { const hit = findFile(full, name, depth - 1); if (hit) return hit }
  }
  return null
}

const javaWorks = (javaHome) =>
  spawnSync(javaHome ? path.join(javaHome, 'bin', 'java') : 'java', ['-version'], { stdio: 'ignore' }).status === 0

async function installZap() {
  const statePath = path.join(HOME, 'install.json')
  const state = readJson(statePath) ?? {}
  fs.mkdirSync(HOME, { recursive: true })

  if (!javaWorks(state.javaHome)) {
    const kind = windows ? 'windows' : process.platform === 'darwin' ? 'mac' : 'linux'
    const arch = process.arch === 'arm64' ? 'aarch64' : 'x64'
    const archive = path.join(HOME, 'downloads', windows ? 'jre.zip' : 'jre.tar.gz')
    await download(`https://api.adoptium.net/v3/binary/latest/17/ga/${kind}/${arch}/jre/hotspot/normal/eclipse`, archive, 'a Java 17 runtime (Eclipse Temurin, about 50 MB)')
    extract(archive, path.join(HOME, 'jre'))
    fs.rmSync(archive, { force: true }) // the extracted copy is the install
    const java = findFile(path.join(HOME, 'jre'), windows ? 'java.exe' : 'java')
    if (!java) throw new Error('the Java runtime archive did not contain java')
    state.javaHome = path.dirname(path.dirname(java))
  }

  if (!state.zap || !fs.existsSync(state.zap)) {
    const release = await (await fetch('https://api.github.com/repos/zaproxy/zaproxy/releases/latest', { headers: { 'user-agent': 'agentforge-zap-install' } })).json()
    const asset = (release.assets ?? []).find((row) => /^ZAP_.*_Crossplatform\.zip$/.test(row.name))
    if (!asset) throw new Error('no cross-platform ZAP package in the latest ZAP release')
    const archive = path.join(HOME, 'downloads', asset.name)
    await download(asset.browser_download_url, archive, `OWASP ZAP ${release.tag_name ?? ''} (${(asset.size / 1e6).toFixed(0)} MB)`)
    extract(archive, path.join(HOME, 'zap'))
    fs.rmSync(archive, { force: true })
    const zap = findFile(path.join(HOME, 'zap'), windows ? 'zap.bat' : 'zap.sh')
    if (!zap) throw new Error('the ZAP package did not contain its launcher')
    if (!windows) fs.chmodSync(zap, 0o755)
    state.zap = zap
  }
  fs.writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`)
  console.log(`ZAP is installed for this machine: ${state.zap}`)
}

// --- the built-in passive baseline ---------------------------------------------------------

const ASSET = /\.(?:css|js|mjs|map|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|json|txt|xml)$/i
const PROBES = ['/.env', '/.env.local', '/.git/HEAD', '/package.json', '/server.log', '/app.log', '/.agentforge/qa/server.log']

async function baseline(target) {
  const origin = new URL(target).origin
  const secure = origin.startsWith('https:')
  const queue = ['/']
  try {
    for (const row of readJson(path.join('e2e', 'routes.json')) ?? []) {
      if (row?.route && !/\[|\/:/.test(row.route)) queue.push(row.route)
    }
  } catch { /* the home page and what it links to */ }
  const found = new Map()
  const seen = new Set()
  let requests = 0

  const add = (id, name, risk, description, url) => {
    const key = `${id}|${name}`
    const alert = found.get(key) ?? { id, name, risk, count: 0, description, urls: [] }
    alert.count += 1
    if (alert.urls.length < 5 && !alert.urls.includes(url)) alert.urls.push(url)
    found.set(key, alert)
  }

  const fetchPage = async (pathname) => {
    requests += 1
    try {
      const response = await fetch(origin + pathname, {
        redirect: 'manual', headers: { 'user-agent': 'agentforge-baseline', accept: 'text/html,*/*' },
        signal: AbortSignal.timeout(15_000),
      })
      const type = response.headers.get('content-type') ?? ''
      const body = response.status < 300 && /html/.test(type) ? (await response.text()).slice(0, 512_000) : ''
      return { response, type, body }
    } catch { return null }
  }

  for (let at = 0; at < queue.length && at < 60; at += 1) {
    const pathname = queue[at]
    if (seen.has(pathname)) continue
    seen.add(pathname)
    const page = await fetchPage(pathname)
    if (!page) continue
    const { response, type, body } = page
    const url = origin + pathname
    for (const [, href] of body.matchAll(/href="(\/[^"#?]*)/g)) {
      if (!href.startsWith('/_next/') && !ASSET.test(href) && !seen.has(href)) queue.push(href)
    }
    const header = (name) => response.headers.get(name)
    const html = /html/.test(type)
    if (response.status < 200 || response.status >= 300) continue

    const csp = header('content-security-policy') ?? ''
    if (html && !header('x-frame-options') && !/frame-ancestors/i.test(csp)) {
      add('10020', 'Missing Anti-clickjacking Header', 'Medium', 'Neither X-Frame-Options nor a CSP frame-ancestors directive stops other sites framing this page.', url)
    }
    if (html && !csp) add('10038', 'Content Security Policy (CSP) Header Not Set', 'Medium', 'No Content-Security-Policy header limits where scripts and other content may load from.', url)
    if (!/nosniff/i.test(header('x-content-type-options') ?? '')) {
      add('10021', 'X-Content-Type-Options Header Missing', 'Low', 'Without `X-Content-Type-Options: nosniff` older browsers may treat a response as another content type.', url)
    }
    if (secure && !header('strict-transport-security')) add('10035', 'Strict-Transport-Security Header Not Set', 'Low', 'HTTPS responses do not tell browsers to keep using HTTPS.', url)
    if (html && !header('permissions-policy')) add('10063', 'Permissions Policy Header Not Set', 'Low', 'No Permissions-Policy header restricts powerful browser features.', url)
    if (header('x-powered-by')) add('10037', 'Server Leaks Information via "X-Powered-By" HTTP Response Header', 'Low', `X-Powered-By: ${header('x-powered-by')}`, url)
    if (/\d/.test(header('server') ?? '')) add('10036', 'HTTP Server Response Header Discloses Version', 'Low', `Server: ${header('server')}`, url)
    if (header('access-control-allow-origin') === '*') add('10098', 'Cross-Domain Misconfiguration', 'Medium', 'Access-Control-Allow-Origin is `*`: any site may read this response.', url)
    for (const cookie of response.headers.getSetCookie?.() ?? []) {
      const name = cookie.split('=')[0]
      if (!/;\s*httponly/i.test(cookie)) add('10010', 'Cookie No HttpOnly Flag', 'Low', `Cookie "${name}" can be read by page scripts.`, url)
      if (secure && !/;\s*secure/i.test(cookie)) add('10011', 'Cookie Without Secure Flag', 'Low', `Cookie "${name}" is also sent over plain HTTP.`, url)
      if (!/;\s*samesite=/i.test(cookie)) add('10054', 'Cookie without SameSite Attribute', 'Low', `Cookie "${name}" has no SameSite policy.`, url)
    }
  }

  for (const probe of PROBES) {
    const page = await fetchPage(probe)
    if (page?.response.status === 200 && !/html/.test(page.type)) {
      add('agentforge-exposed-file', 'Sensitive file is served', 'High', `${probe} answered 200 and is not a page.`, origin + probe)
    }
  }
  return { alerts: [...found.values()], requests, urls: seen.size }
}

// --- main ----------------------------------------------------------------------------------

async function main() {
  const statePath = path.join(HOME, 'install.json')
  if (has('--install-zap')) {
    try { await installZap() } catch (error) {
      console.error(`Could not install ZAP: ${error.message}`)
      if (engineChoice === 'zap') process.exit(3)
    }
  } else if (engineChoice !== 'baseline' && !findZap()) {
    // Nobody asked for --install-zap, and nothing is installed: try it once,
    // automatically, so a real scan is the default on a fresh machine rather
    // than something that only happens if whoever runs this remembers the
    // separate flag. A machine that already tried and failed (no network, a
    // blocked download, ...) is not retried on every single run after that -
    // that failure is recorded, not re-discovered the slow way each time.
    // An explicit --install-zap (above) always retries regardless.
    const state = readJson(statePath) ?? {}
    if (!state.autoInstallFailedAt) {
      console.log('OWASP ZAP is not installed yet - installing it once for this machine...')
      try {
        await installZap()
      } catch (error) {
        console.error(`Could not auto-install ZAP, falling back to the built-in baseline this run: ${error.message}`)
        fs.mkdirSync(HOME, { recursive: true })
        fs.writeFileSync(statePath, `${JSON.stringify(
          { ...state, autoInstallFailedAt: new Date().toISOString(), autoInstallError: error.message }, null, 2)}\n`)
      }
    }
  }
  const target = (process.env.BASE_URL || '').replace(/\/$/, '')
  if (!target) {
    console.error('BASE_URL is not set. Run `npm run qa:security`, which starts the app and sets it.')
    process.exit(3)
  }
  fs.mkdirSync(OUT, { recursive: true })
  const rules = readRules()
  const date = new Date().toISOString()
  let engine = 'agentforge-baseline'
  let alerts
  let command = 'GET requests to the local server (headers, cookies, exposed files)'
  let exitCode = 0
  let reason = ''
  let requests = null
  let urls = null

  const zap = engineChoice === 'baseline' ? null : findZap()
  if (zap) {
    try {
      console.log(`Running OWASP ZAP (${zap.zap}) against ${target}`)
      const run = await runZap(zap, target)
      engine = 'zap'
      alerts = alertsFromZap(run.report)
      command = run.command
      exitCode = run.code
    } catch (error) {
      reason = `OWASP ZAP was found but did not complete: ${error.message}`
    }
  } else if (engineChoice !== 'baseline') {
    reason = 'OWASP ZAP is not installed on this machine (nothing at ZAP_PATH, on PATH, in its default folder or in ~/.agentforge/zap). '
      + 'Run `npm run qa:security -- --install-zap` once to fetch it (about 200 MB, no admin rights).'
  }
  if (engineChoice === 'zap' && engine !== 'zap') {
    console.error(reason)
    process.exit(3)
  }
  if (engine !== 'zap') {
    console.log(`${reason ? `${reason}\n` : ''}Running the built-in passive baseline against ${target} (this is not a ZAP scan).`)
    const run = await baseline(target)
    alerts = run.alerts
    requests = run.requests
    urls = run.urls
    fs.writeFileSync(path.join(OUT, 'baseline-report.json'), `${JSON.stringify({ target, date, alerts }, null, 2)}\n`)
  }

  const { failing, warnings, ignored } = judge(alerts, rules)
  const counts = Object.fromEntries(RISK.map((risk) => [risk.toLowerCase(), alerts.filter((a) => a.risk === risk).length]))
  const status = failing.length ? 'failed' : engine === 'zap' ? 'passed' : 'partial'
  const summary = {
    engine, zap_available: engine === 'zap', status, target, date, command, exit_code: exitCode,
    counts, failing, warnings, ignored: ignored.length, requests, urls_checked: urls,
    rules: fs.existsSync(path.join('.zap', 'rules.tsv')) ? '.zap/rules.tsv' : null,
    report: path.join(OUT, engine === 'zap' ? 'zap-report.json' : 'baseline-report.json'),
    reason: engine === 'zap' ? '' : reason,
    note: engine === 'zap'
      ? 'OWASP ZAP passive baseline (spider + passive scan). No active attack scan was run.'
      : 'ZAP itself did not run. This is a passive baseline of headers, cookies and exposed files: partial evidence, not a ZAP pass.',
  }
  fs.writeFileSync(path.join(OUT, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`)

  console.log(`\nengine: ${engine}   status: ${status}   findings: ${alerts.length} (${failing.length} fail, ${warnings.length} warn, ${ignored.length} ignored)`)
  for (const alert of [...failing, ...warnings].slice(0, 12)) {
    console.log(`  ${alert.action.padEnd(4)} ${String(alert.risk).padEnd(13)} ${alert.id.padEnd(8)} ${alert.name} (${alert.count})`)
  }
  console.log(`summary: ${path.join(OUT, 'summary.json')}`)
  process.exit(failing.length ? 1 : 0)
}

main().catch((error) => {
  console.error(`zap-scan: ${error.message}`)
  process.exit(3)
})
