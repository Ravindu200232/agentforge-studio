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
 * Servers, by stack: Next.js (`next start`), Remix (`remix-serve`), and a plain Vite build
 * (`vite preview`, for the two Vite-only stacks that have no server of their own).
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

function manifest() {
  return JSON.parse(fs.readFileSync('package.json', 'utf8'))
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

/**
 * Every browser-QA run truncates this project's own Supabase project's tables first, then seeds
 * fresh. Unlike the old per-run disposable MongoDB database, there is nothing to create or drop:
 * this Supabase project already belongs to this app alone (see supabase_connect.py), so truncating
 * in place is the equivalent safety - an interrupted run leaves stale rows, not a stale server.
 */
function qaSupabaseDbUrl() {
  const project = manifest()
  const deps = { ...project.dependencies, ...project.devDependencies }
  if (!deps['@supabase/supabase-js']) return null
  return process.env.SUPABASE_DB_URL || localEnv('SUPABASE_DB_URL') || null
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
  throw new Error('cannot tell how to start this app for a test run (no Next.js, Remix or Vite build found)')
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

async function resetQaDatabase(dbUrl) {
  if (!dbUrl) return
  const hostname = new URL(dbUrl.replace(/^postgres(ql)?:/, 'http:')).hostname
  if (['127.0.0.1', 'localhost', '::1'].includes(hostname)) {
    throw new Error(`Refusing to reset "${hostname}": SUPABASE_DB_URL must be this project's real `
      + 'Supabase project, not a local one - that project already belongs to this app alone.')
  }
  const { default: pg } = await import('pg')
  const client = new pg.Client({ connectionString: dbUrl })
  await client.connect()
  try {
    const { rows } = await client.query("select tablename from pg_tables where schemaname = 'public'")
    if (rows.length) {
      const names = rows.map((row) => `"${row.tablename}"`).join(', ')
      await client.query(`truncate table ${names} restart identity cascade`)
    }
  } finally {
    await client.end()
  }
}

async function main() {
  const port = await freePort()
  const base = `http://127.0.0.1:${port}`
  const server = serverCommand(port)
  const supabaseDbUrl = qaSupabaseDbUrl()
  const qaEnv = { ...process.env, PORT: String(port), BASE_URL: base }

  if (supabaseDbUrl) {
    await resetQaDatabase(supabaseDbUrl)
    if (manifest().scripts?.seed) {
      const seeded = await run(['npm', 'run', 'seed'], qaEnv)
      if (seeded !== 0) throw new Error('could not seed the QA run (exit ' + seeded + ')')
    }
  }

  fs.mkdirSync(path.dirname(logFile), { recursive: true })
  const log = fs.openSync(logFile, 'w')
  const child = spawn(server.file, server.args, {
    stdio: ['ignore', log, log],
    detached: !windows,
    env: { ...qaEnv, NODE_ENV: 'production' },
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
  const code = await new Promise((resolve) => {
    const test = spawn(resolved.file, resolved.args, { stdio: 'inherit', env: qaEnv })
    test.on('error', (error) => { console.error(`could not run ${command[0]}: ${error.message}`); resolve(1) })
    test.on('exit', (exitCode) => resolve(exitCode ?? 1))
  })
  stop(child)
  await resetQaDatabase(supabaseDbUrl)
  process.exit(code)
}

main().catch((error) => {
  console.error(`with-server: ${error.message}`)
  process.exit(1)
})
