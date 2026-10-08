// Shared helpers for init-artifact.mjs and bundle-artifact.mjs (AgentForge additions to the
// official web-artifacts-builder skill; the official bash scripts sit next to them unchanged).
//
// Every app links its node_modules to ONE shared dependency store, so an app is a few
// hundred KB of source and never runs its own install.
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'

export const scriptsDir = path.dirname(fileURLToPath(import.meta.url))

export function fail(message) {
  console.error('ERROR: ' + message)
  process.exit(1)
}

export function runtimePackage() {
  return JSON.parse(fs.readFileSync(path.join(scriptsDir, 'runtime', 'package.json'), 'utf8'))
}

// Where the shared store lives: AGENTFORGE_WEB_RUNTIME, then runtime.json next to these
// scripts (written when the skill is staged into a project), then the repo's tools folder.
export function runtimeDir() {
  if (process.env.AGENTFORGE_WEB_RUNTIME) return path.resolve(process.env.AGENTFORGE_WEB_RUNTIME)
  try {
    const pinned = JSON.parse(fs.readFileSync(path.join(scriptsDir, 'runtime.json'), 'utf8'))
    if (pinned.runtime) return path.resolve(pinned.runtime)
  } catch {
    // not staged: fall through to the repository default
  }
  return path.resolve(scriptsDir, '..', '..', '..', '..', '..', 'tools', 'web-artifacts-runtime')
}

// The store is ready when package.json, package-lock.json and .npmrc are the ones it was
// installed from (a marker file records their signature) and every package is on disk. A store
// left over from an older toolkit therefore reinstalls itself instead of failing in the bundler.
const STORE_FILES = ['package.json', 'package-lock.json', '.npmrc']
const MARKER = '.agentforge-runtime'

function storeSignature() {
  const hash = createHash('sha1')
  for (const name of STORE_FILES) hash.update(fs.readFileSync(path.join(scriptsDir, 'runtime', name)))
  return hash.digest('hex')
}

function missingPackages(dir) {
  const pkg = runtimePackage()
  const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies })
  const absent = names.filter((n) => !fs.existsSync(path.join(dir, 'node_modules', n, 'package.json')))
  let marker = null
  try {
    marker = fs.readFileSync(path.join(dir, 'node_modules', MARKER), 'utf8').trim()
  } catch {
    // never installed from this toolkit
  }
  return marker === storeSignature() ? absent : [...absent, 'the toolkit signature']
}

function npmCommand() {
  const bin = path.dirname(process.execPath)
  const candidates = [
    path.join(bin, 'node_modules', 'npm', 'bin', 'npm-cli.js'),
    path.join(bin, '..', 'lib', 'node_modules', 'npm', 'bin', 'npm-cli.js'),
  ]
  if (process.env.npm_execpath && process.env.npm_execpath.endsWith('.js')) {
    candidates.unshift(process.env.npm_execpath)
  }
  for (const cli of candidates) {
    if (fs.existsSync(cli)) return { command: process.execPath, args: [cli] }
  }
  return { command: process.platform === 'win32' ? 'npm.cmd' : 'npm', args: [], shell: process.platform === 'win32' }
}

// Installs the store the first time (or when the toolkit changed). One install, shared by every
// project; later calls return at once. Install scripts are skipped: everything needed ships as a
// prebuilt package, and nothing from the registry should run code on the user's machine.
export function ensureRuntime(dir) {
  if (missingPackages(dir).length === 0) return
  console.log('Preparing the shared UI toolkit in ' + dir + ' (first time only, this can take a few minutes)...')
  fs.mkdirSync(dir, { recursive: true })
  for (const name of STORE_FILES) fs.copyFileSync(path.join(scriptsDir, 'runtime', name), path.join(dir, name))
  const npm = npmCommand()
  const run = spawnSync(
    npm.command,
    [...npm.args, 'install', '--no-audit', '--no-fund', '--prefer-offline', '--ignore-scripts', '--loglevel=error'],
    { cwd: dir, stdio: 'inherit', shell: npm.shell === true }
  )
  const missing = missingPackages(dir).filter((n) => n !== 'the toolkit signature')
  if (run.status !== 0 || missing.length) {
    fail(
      'The shared UI toolkit could not be installed' +
        (missing.length ? ' (missing: ' + missing.slice(0, 6).join(', ') + ')' : '') +
        '. Check the network and try again.'
    )
  }
  fs.writeFileSync(path.join(dir, 'node_modules', MARKER), storeSignature())
}

// node_modules -> shared store. A junction on Windows (no admin needed), a symlink elsewhere.
export function linkNodeModules(projectDir, dir) {
  const link = path.join(projectDir, 'node_modules')
  const target = path.join(dir, 'node_modules')
  try {
    if (fs.lstatSync(link)) {
      if (fs.realpathSync(link) === fs.realpathSync(target)) return
      try {
        fs.unlinkSync(link)
      } catch {
        fs.rmdirSync(link)
      }
    }
  } catch {
    // no link yet
  }
  fs.symlinkSync(target, link, process.platform === 'win32' ? 'junction' : 'dir')
}

// A small tar reader so the tarball unpacks the same on every machine without a `tar` binary
// (Git for Windows' tar mistakes "C:\..." for a remote host).
export function extractTarGz(file, dest) {
  const buf = zlib.gunzipSync(fs.readFileSync(file))
  const root = path.resolve(dest)
  let off = 0
  let longName = null
  let paxPath = null
  let count = 0
  while (off + 512 <= buf.length) {
    const head = buf.subarray(off, off + 512)
    if (head.every((b) => b === 0)) break
    const field = (from, to) => {
      let end = from
      while (end < to && head[end] !== 0) end++
      return head.toString('utf8', from, end)
    }
    let name = field(0, 100)
    const size = parseInt(field(124, 136).trim() || '0', 8)
    const kind = head[156] ? String.fromCharCode(head[156]) : '0'
    if (field(257, 263).startsWith('ustar') && field(345, 500)) name = field(345, 500) + '/' + name
    off += 512
    const data = buf.subarray(off, off + size)
    off += Math.ceil(size / 512) * 512
    if (kind === 'L') { longName = data.toString('utf8').replace(/\0+$/, ''); continue }
    if (kind === 'x') {
      const found = /\d+ path=([^\n]*)\n/.exec(data.toString('utf8'))
      if (found) paxPath = found[1]
      continue
    }
    if (kind === 'g') continue
    if (longName) { name = longName; longName = null }
    if (paxPath) { name = paxPath; paxPath = null }
    const rel = name.replace(/^(\.\/)+/, '').replace(/\/+$/, '')
    const parts = rel.split('/')
    if (!rel || path.isAbsolute(rel) || parts.some((p) => p === '..' || p.startsWith('._'))) continue
    const out = path.resolve(root, ...parts)
    if (out !== root && !out.startsWith(root + path.sep)) continue
    if (kind === '5') { fs.mkdirSync(out, { recursive: true }); continue }
    if (kind !== '0') continue
    fs.mkdirSync(path.dirname(out), { recursive: true })
    fs.writeFileSync(out, data)
    count++
  }
  return count
}
