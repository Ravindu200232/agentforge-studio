/**
 * Run a command against the built app, on a port this script owns.
 *
 *   node scripts/with-server.mjs [--log <file>] [--ready <path>] -- <command> [args...]
 *   npm run qa:e2e | qa:visual | qa:a11y | qa:perf | qa:security
 *
 * The studio owns the long-lived preview, and an agent must not start servers of
 * its own, so every QA layer that needs a running app comes through here: build
 * once (`npm run build`), then this starts the production server on a free
 * loopback-side port, exports it as BASE_URL (and PORT), runs the command, and
 * stops only the server it started. Nothing else is touched, and no port is left
 * bound. The command's exit code is this script's exit code.
 *
 * Servers, by stack: Next.js (`next start`), Remix (`remix-serve`), the MERN gateway
 * with its services (`scripts/start-all.mjs`), a single Express server that serves its
 * own built client (`server/src/server.js`, the vite-mongo layout), and a plain Vite
 * build (`vite preview`, for the Vite-only stacks that have no server of their own).
 *
 * A stack whose server talks to MongoDB gets an isolated, uniquely-named `_e2e`
 * database for this run only, seeded (if the app defines `npm run seed`) and dropped
 * when the run ends — a QA run must never read or write the project's real data.
 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'

const argv = process.argv.slice(2)
const split = argv.indexOf('--')
const options = split < 0 ? [] : argv.slice(0, split)
const command = split < 0 ? [] : argv.slice(split + 1)
if (!command.length) {
  console.error('usage: node scripts/with-server.mjs [--log <file>] [--ready <path>] -- <command> [args...]')
  process.exit(2)
}

const option = (name, fallback) => {
  const at = options.indexOf(name)
  return at >= 0 && options[at + 1] ? options[at + 1] : fallback
}
const logFile = option('--log', process.env.WITH_SERVER_LOG || path.join('.agentforge', 'qa', 'server.log'))
const readyPath = option('--ready', '/')
const windows = process.platform === 'win32'

function manifest(file = 'package.json') {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return {} }
}

function localEnv(name) {
  for (const file of ['.env.local', '.env']) {
    if (!fs.existsSync(file)) continue
    const pattern = '^\\s*(?:export\\s+)?' + name + '\\s*=\\s*[\'"]?(.*?)[\'"]?\\s*$'
    const match = fs.readFileSync(file, 'utf8').match(new RegExp(pattern, 'm'))
    if (match) return match[1]
  }
  return undefined
}

function databaseName(uri) {
  return decodeURIComponent(new URL(uri).pathname.replace(/^\/+|\/+$/g, ''))
}

/** Every manifest this project actually runs code from - wherever `mongoose`/`mongodb` might be declared. */
function allManifests() {
  const found = [manifest()]
  if (fs.existsSync(path.join('server', 'package.json'))) found.push(manifest(path.join('server', 'package.json')))
  if (fs.existsSync('packages')) {
    for (const entry of fs.readdirSync('packages', { withFileTypes: true })) {
      if (entry.isDirectory()) found.push(manifest(path.join('packages', entry.name, 'package.json')))
    }
  }
  return found
}

function usesMongo() {
  return allManifests().some((m) => (m.dependencies && (m.dependencies.mongoose || m.dependencies.mongodb)))
}

/**
 * Every browser-QA run owns a Mongo database. The server, seed script and test
 * command all receive this exact URI, so cleanup can never point at a different
 * database from the app under test. A unique name also makes an interrupted run
 * harmless to the next run.
 */
function qaMongoUri() {
  if (!usesMongo()) return null

  const explicit = process.env.E2E_MONGODB_URI
  const source = explicit || process.env.MONGODB_URI || localEnv('MONGODB_URI')
    || 'mongodb://127.0.0.1:27017/' + (manifest().name || 'app')
  const parsed = new URL(source)

  if (explicit) {
    const name = databaseName(source)
    if (!name.endsWith('_e2e')) throw new Error('E2E_MONGODB_URI database "' + name + '" must end in "_e2e"')
    return source
  }

  const base = (databaseName(source) || manifest().name || 'app').replace(/[^a-zA-Z0-9_-]/g, '_')
  parsed.pathname = '/' + base + '_' + Date.now() + '_' + process.pid + '_e2e'
  return parsed.toString()
}

/** A file under node_modules, looked up from here upwards (npm workspaces hoist). */
function inNodeModules(relative) {
  for (let dir = process.cwd(); ; dir = path.dirname(dir)) {
    const candidate = path.join(dir, 'node_modules', ...relative.split('/'))
    if (fs.existsSync(candidate)) return candidate
    if (path.dirname(dir) === dir) return null
  }
}

function serverCommand(port) {
  if (fs.existsSync(path.join('scripts', 'start-all.mjs'))) {
    return { file: process.execPath, args: [path.join('scripts', 'start-all.mjs')], why: 'MERN gateway and services' }
  }
  if (fs.existsSync(path.join('server', 'src', 'server.js'))) {
    if (!fs.existsSync(path.join('client', 'dist', 'index.html'))) throw new Error('there is no production client build: run npm run build first')
    return { file: process.execPath, args: [path.join('server', 'src', 'server.js')], why: 'server (serving the built client)' }
  }
  const project = manifest()
  const deps = { ...project.dependencies, ...project.devDependencies }
  if (deps.next) {
    const bin = inNodeModules('next/dist/bin/next')
    if (!bin) throw new Error('next is not installed: run npm install')
    if (!fs.existsSync(path.join('.next', 'BUILD_ID'))) throw new Error('there is no production build: run npm run build first')
    return { file: process.execPath, args: [bin, 'start', '--port', String(port)], why: 'next start' }
  }
  if (deps['@remix-run/serve']) {
    const bin = inNodeModules('@remix-run/serve/dist/cli.js')
    if (!bin) throw new Error('@remix-run/serve is not installed: run npm install')
    if (!fs.existsSync(path.join('build', 'server', 'index.js'))) throw new Error('there is no production build: run npm run build first')
    return { file: process.execPath, args: [bin, './build/server/index.js'], why: 'remix-serve' }
  }
  if (deps.vite) {
    const bin = inNodeModules('vite/bin/vite.js')
    if (!bin) throw new Error('vite is not installed: run npm install')
    if (!fs.existsSync('dist')) throw new Error('there is no production build: run npm run build first')
    return { file: process.execPath, args: [bin, 'preview', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], why: 'vite preview' }
  }
  throw new Error('cannot tell how to start this app for a test run (no Next.js, Remix, MERN, server/ or Vite build found)')
}

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer()
    probe.once('error', reject)
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address()
      probe.close(() => resolve(port))
    })
  })
}

function answers(port) {
  return new Promise((resolve) => {
    const request = http.request({ host: '127.0.0.1', port, path: readyPath, method: 'GET' }, (response) => {
      response.resume()
      resolve(response.statusCode < 500)
    })
    request.on('error', () => resolve(false))
    request.setTimeout(2000, () => { request.destroy(); resolve(false) })
    request.end()
  })
}

/** `npm` and `npx` are .cmd files on Windows: spawning them directly fails (EINVAL), so run their JS. */
function resolveCommand([file, ...rest]) {
  if (file === 'node') return { file: process.execPath, args: rest }
  if (file === 'npm' || file === 'npx') {
    const bin = path.dirname(process.execPath)
    for (const cli of [path.join(bin, 'node_modules', 'npm', 'bin', `${file}-cli.js`),
      path.join(bin, '..', 'lib', 'node_modules', 'npm', 'bin', `${file}-cli.js`)]) {
      if (fs.existsSync(cli)) return { file: process.execPath, args: [cli, ...rest] }
    }
  }
  return { file, args: rest }
}

function stop(child) {
  if (!child || child.exitCode !== null) return
  if (windows) spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  else try { process.kill(-child.pid, 'SIGTERM') } catch { child.kill('SIGTERM') }
}

function run(commandParts, env) {
  const command = resolveCommand(commandParts)
  return new Promise((resolve, reject) => {
    const child = spawn(command.file, command.args, { stdio: 'inherit', env })
    child.on('error', reject)
    child.on('exit', (code) => resolve(code ?? 1))
  })
}

/**
 * Playwright overwrites test-results/results.json on every run, so after journeys, visual and
 * accessibility run one after another only the last is left. Keep this run's own copy in
 * .agentforge/qa/runs/, named after its script (test-a11y.json), where the Testing views read
 * every run from. Not this script's result to judge: a failed copy only says so.
 */
function keepRunResults(commandParts, since) {
  const source = path.join('test-results', 'results.json')
  try {
    if (!fs.existsSync(source) || fs.statSync(source).mtimeMs < since) return
    const label = String(commandParts[commandParts.length - 1] || '')
      .replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'run'
    const folder = path.join('.agentforge', 'qa', 'runs')
    fs.mkdirSync(folder, { recursive: true })
    fs.copyFileSync(source, path.join(folder, `${label}.json`))
  } catch (error) {
    console.error(`with-server: could not keep this run's results: ${error.message}`)
  }
}

async function resetQaDatabase(uri) {
  if (!uri) return
  const { default: mongoose } = await import('mongoose')
  const connection = await mongoose.createConnection(uri, { serverSelectionTimeoutMS: 10_000 }).asPromise()
  try { await connection.dropDatabase() } finally { await connection.close() }
}

async function main() {
  const port = await freePort()
  const base = `http://127.0.0.1:${port}`
  const server = serverCommand(port)
  const mongoUri = qaMongoUri()
  const qaEnv = {
    ...process.env,
    PORT: String(port),
    BASE_URL: base,
    ...(mongoUri ? { MONGODB_URI: mongoUri, E2E_MONGODB_URI: mongoUri } : {}),
  }

  if (mongoUri) {
    await resetQaDatabase(mongoUri)
    if (manifest().scripts?.seed) {
      const seeded = await run(['npm', 'run', 'seed'], qaEnv)
      if (seeded !== 0) throw new Error('could not seed isolated QA database (exit ' + seeded + ')')
    }
  }

  fs.mkdirSync(path.dirname(logFile), { recursive: true })
  const log = fs.openSync(logFile, 'w')
  const child = spawn(server.file, server.args, {
    stdio: ['ignore', log, log],
    detached: !windows,
    env: { ...qaEnv, NODE_ENV: 'production',
      // QA owns a temporary app port. Keep its service ports away from the
      // long-lived MERN preview's 4001–4020 range so tests cannot stop it.
      ...(server.why === 'MERN gateway and services'
        ? { INTERNAL_PORT_BASE: process.env.INTERNAL_PORT_BASE ?? '4102' } : {}) },
  })
  fs.closeSync(log)
  let exited = false
  child.on('exit', () => { exited = true })
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { stop(child); process.exit(130) })

  const deadline = Date.now() + 90_000
  let ready = false
  while (!ready && !exited && Date.now() < deadline) {
    ready = await answers(port)
    if (!ready) await new Promise((resolve) => setTimeout(resolve, 300))
  }
  if (!ready) {
    const tail = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8').split(/\r?\n/).slice(-15).join('\n') : ''
    console.error(`The app did not answer on ${base}${readyPath} (${server.why}${exited ? ', it exited' : ''}). Server log ${logFile}:\n${tail}`)
    stop(child)
    process.exit(1)
  }
  console.log(`Serving ${server.why} at ${base} for this run (log: ${logFile})`)

  const resolved = resolveCommand(command)
  const startedAt = Date.now()
  const code = await new Promise((resolve) => {
    const test = spawn(resolved.file, resolved.args, { stdio: 'inherit', env: qaEnv })
    test.on('error', (error) => { console.error(`could not run ${command[0]}: ${error.message}`); resolve(1) })
    test.on('exit', (exitCode) => resolve(exitCode ?? 1))
  })
  keepRunResults(command, startedAt)
  stop(child)
  await resetQaDatabase(mongoUri)
  process.exit(code)
}

main().catch((error) => {
  console.error(`with-server: ${error.message}`)
  process.exit(1)
})
