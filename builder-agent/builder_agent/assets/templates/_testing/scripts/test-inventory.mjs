/**
 * Which pages, routes and components have a unit test, and which do not?
 *
 *   npm run qa:inventory                       # list the units, exit 1 while a required one is untested
 *   node scripts/test-inventory.mjs --report-only [--out <dir>]
 *
 * It lists every unit the app is made of and the unit tests that exercise it:
 *   page        a page: Next `app/**\/page.*`, a MERN client page
 *   route       an HTTP route: Next `route.*` (each exported GET/POST/PATCH/DELETE... is one), a Remix route
 *               (its loader, action and page), an Express route (`router.get('/x')`)
 *   component   a React component (every exported component)
 *   middleware  Next `middleware.*` / `proxy.*`
 *   module      domain code (lib/, models/, services/, hooks/): needs a test that uses it, or to run as part of
 *               a tested page/route/component (`indirect`); exports no test uses directly are listed as
 *               `untested_exports`. Code that no test reaches at all is untested.
 * A unit counts when a unit test (not an E2E spec) IMPORTS it and USES it: renders `<Component />`, calls
 * `GET(request)`, `loader(...)`, `createOrder(...)`, or sends a request to the Express route. Importing a file
 * that the same test replaces with `vi.mock` does not count. Layouts and framework files (loading, error,
 * not-found) are listed as optional. Plumbing (`lib/db.js`, configs, scripts) is exempt.
 *
 * It is structural: it shows what nothing tests, not how much of each file runs. Writes
 * <out>/coverage-inventory.json (default .agentforge/qa), which the Testing view reads.
 */
import fs from 'node:fs'
import path from 'node:path'

const args = process.argv.slice(2)
const flag = (name) => args.includes(name)
const value = (name, fallback) => { const at = args.indexOf(name); return at >= 0 && args[at + 1] ? args[at + 1] : fallback }
const ROOT = process.cwd()
const OUT = path.resolve(ROOT, value('--out', path.join('.agentforge', 'qa')))
const SKIP_DIRS = new Set(['node_modules', '.next', '.git', 'build', 'dist', 'coverage', '.agentforge', 'test-results',
  'playwright-report', '.lighthouseci', '__screenshots__', '.turbo', 'scaffold', '.vercel', 'public'])
const CODE = /\.(?:jsx?|tsx?|mjs|cjs)$/
const TEST_FILE = /\.(?:test|spec)\.(?:jsx?|tsx?|mjs|cjs)$/
const HTTP = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
const posix = (file) => file.split(path.sep).join('/')
const read = (file) => { try { return fs.readFileSync(file, 'utf8').replace(/^﻿/, '') } catch { return '' } }
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function walk(dir, found = []) {
  let entries = []
  try { entries = fs.readdirSync(dir, { withFileTypes: true }) } catch { return found }
  for (const entry of entries) {
    if (entry.isDirectory()) { if (!SKIP_DIRS.has(entry.name)) walk(path.join(dir, entry.name), found) } else found.push(path.join(dir, entry.name))
  }
  return found
}

const manifest = (() => { try { return JSON.parse(read(path.join(ROOT, 'package.json'))) } catch { return {} } })()
const deps = { ...manifest.dependencies, ...manifest.devDependencies }
const stack = deps.next ? 'next' : deps['@remix-run/react'] || deps['@remix-run/node'] ? 'remix'
  : fs.existsSync(path.join(ROOT, 'packages')) ? 'mern'
  // vite-mongo: one Express server workspace plus one Vite client workspace, no packages/*.
  : fs.existsSync(path.join(ROOT, 'server')) && fs.existsSync(path.join(ROOT, 'client')) ? 'server-client'
  : 'generic'

const all = walk(ROOT).filter((file) => CODE.test(file)).map((file) => posix(path.relative(ROOT, file)))
const inE2e = (rel) => /(^|\/)e2e\//.test(rel)
const tests = all.filter((rel) => TEST_FILE.test(rel) && !inE2e(rel))
const sources = all.filter((rel) => !TEST_FILE.test(rel) && !inE2e(rel) && !/(^|\/)(?:tests?|__tests__)\//.test(rel))
const sourceSet = new Set(sources)

// --- what a source file exports ----------------------------------------------------------------------

function isFunctionLike(text, name) {
  const id = escape(name)
  return new RegExp(`(?:^|[\\s;])(?:async\\s+)?function\\*?\\s+${id}\\b`).test(text)
    || new RegExp(`\\bclass\\s+${id}\\b`).test(text)
    || new RegExp(`\\b(?:const|let|var)\\s+${id}\\s*=\\s*(?:async\\s*)?(?:function\\b|\\(|[A-Za-z0-9_$]+\\s*=>|(?:React\\.)?(?:memo|forwardRef)\\()`).test(text)
}

function exportsOf(text) {
  const named = new Set()
  for (const m of text.matchAll(/export\s+(?:async\s+)?(?:function\*?|class)\s+([A-Za-z0-9_$]+)/g)) named.add(m[1])
  for (const m of text.matchAll(/export\s+(?:const|let|var)\s+([A-Za-z0-9_$]+)/g)) {
    if (isFunctionLike(text, m[1]) || /^[A-Z][a-z]/.test(m[1])) named.add(m[1])   // a model or component; USER_ROLES is data
  }
  for (const m of text.matchAll(/export\s*\{([^}]+)\}(?!\s*from)/g)) {
    for (const part of m[1].split(',')) {
      const [local, exported] = part.trim().split(/\s+as\s+/)
      const name = (exported ?? local).trim()
      if (name && name !== 'default' && isFunctionLike(text, local.trim())) named.add(name)
    }
  }
  const alias = /export\s+default\s+([A-Za-z0-9_$]+)\s*;?\s*$/m.exec(text)?.[1]   // `export default Board`
  const aliased = alias && named.has(alias) ? alias : null
  return { named: [...named], aliased, hasDefault: !aliased && /export\s+default\b|export\s*\{[^}]*\bas\s+default\b/.test(text) }
}

// --- classify every source file into a unit ----------------------------------------------------------

const EXEMPT = [/(^|\/)(?:[a-z-]+\.)?config\.[cm]?[jt]sx?$/, /^lib\/db\.[jt]s$/, /(^|\/)server\.[jt]s$/, /(^|\/)db\.[jt]s$/,
  /^app\/entry\.[a-z]+\.[jt]sx?$/, /(^|\/)main\.jsx?$/, /^vitest\./, /^lighthouserc/, /^playwright\./, /^scripts\//, /\.d\.ts$/]
const SPECIAL = /(?:^|\/)(?:layout|loading|error|not-found|global-error|template|default)\.[jt]sx?$/

function routeOf(rel) {
  if (stack === 'next') {
    const dir = rel.replace(/^src\//, '').replace(/^app\//, '').replace(/\/?[^/]+$/, '')
    return '/' + dir.split('/').filter((part) => part && !/^\(.*\)$/.test(part)).map((part) => part.replace(/^\[\.{0,3}(.+?)\]$/, ':$1')).join('/')
  }
  if (stack === 'remix') {
    const name = rel.replace(/^app\/routes\//, '').replace(/\.[jt]sx?$/, '')
    if (name === '_index') return '/'
    return '/' + name.split(/[./]/).filter((p) => p && p !== '_index' && !/^_/.test(p)).map((p) => p.replace(/^\$/, ':')).join('/')
  }
  return ''
}

function classify(rel) {
  if (EXEMPT.some((rx) => rx.test(rel))) return null
  const isJsx = /\.[jt]sx$/.test(rel)
  if (stack === 'next') {
    if (/(^|\/)route\.[jt]s$/.test(rel)) return { kind: 'route', route: routeOf(rel) }
    if (/(^|\/)page\.[jt]sx?$/.test(rel)) return { kind: 'page', route: routeOf(rel) }
    if (SPECIAL.test(rel)) return { kind: 'special' }
    if (/^(?:src\/)?(?:middleware|proxy)\.[jt]s$/.test(rel)) return { kind: 'middleware' }
    if (isJsx) return { kind: 'component' }
    if (/^(?:src\/)?(?:app\/)?(?:lib|models|services|hooks|utils|server)\//.test(rel)) return { kind: 'module' }
    return null
  }
  if (stack === 'remix') {
    if (/^app\/routes\//.test(rel)) return { kind: 'route', route: routeOf(rel) }
    if (/^app\/root\.[jt]sx?$/.test(rel)) return { kind: 'special' }
    if (isJsx) return { kind: 'component' }
    if (/^(?:app\/)?(?:lib|models|services|hooks|utils)\//.test(rel)) return { kind: 'module' }
    return null
  }
  if (stack === 'mern') {
    if (/^client\/src\//.test(rel)) return isJsx ? { kind: /(^|\/)pages\/|Page\.[jt]sx$/.test(rel) ? 'page' : 'component' } : { kind: 'module' }
    if (/^packages\/[^/]+\/src\//.test(rel)) return /(^|\/)routes\/|\.routes\.[jt]s$/.test(rel) ? { kind: 'route' } : { kind: 'module' }
    return null
  }
  if (stack === 'server-client') {
    if (/^client\/src\//.test(rel)) return isJsx ? { kind: /(^|\/)pages\/|Page\.[jt]sx$/.test(rel) ? 'page' : 'component' } : { kind: 'module' }
    if (/^server\/src\//.test(rel)) return /(^|\/)routes\/|\.routes\.[jt]s$/.test(rel) ? { kind: 'route' } : { kind: 'module' }
    return null
  }
  if (/^(?:src|lib|app)\//.test(rel)) return isJsx ? { kind: 'component' } : { kind: 'module' }
  return null
}

// --- what each unit test imports, under which names, and whether it is only a mock -------------------

function resolveSpec(dir, spec) {
  const bases = spec.startsWith('.') ? [path.posix.normalize(path.posix.join(dir, spec))]
    : spec.startsWith('@/') ? [spec.slice(2), `src/${spec.slice(2)}`]
      : spec.startsWith('~/') ? [`app/${spec.slice(2)}`] : []
  for (const base of bases) {
    for (const tail of ['', '.js', '.jsx', '.ts', '.tsx', '.mjs', '/index.js', '/index.jsx', '/index.ts', '/index.tsx']) {
      if (sourceSet.has(base + tail)) return base + tail
    }
  }
  return null
}

const testData = tests.map((rel) => {
  const raw = read(path.join(ROOT, rel))
  const dir = path.posix.dirname(rel)
  const resolve = (spec) => resolveSpec(dir, spec)
  const mocked = new Set()
  for (const m of raw.matchAll(/vi\.(?:mock|doMock)\(\s*['"]([^'"]+)['"]/g)) { const target = resolve(m[1]); if (target) mocked.add(target) }
  const real = /importActual|importOriginal|requireActual/.test(raw)
  const refs = new Map()   // source file -> [{ exported, local }]   (exported: a name, 'default' or '*')
  const add = (spec, exported, local) => {
    const target = resolve(spec)
    if (!target || (mocked.has(target) && !real)) return
    if (!refs.has(target)) refs.set(target, [])
    refs.get(target).push({ exported, local })
  }
  let body = raw.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
  const take = (regex, handle) => { body = body.replace(regex, (...m) => { handle(m); return ' ' }) }
  const bindings = (clause, spec) => {
    const braces = /\{([^}]*)\}/.exec(clause)
    for (const part of (braces ? braces[1] : '').split(',')) {
      const [exported, local] = part.trim().split(/\s+(?:as|:)\s+/)
      if (exported) add(spec, exported.trim(), (local ?? exported).trim())
    }
    const lead = clause.replace(/\{[^}]*\}/, '').replace(/,/g, ' ').trim()
    const star = /^\*\s+as\s+([A-Za-z0-9_$]+)$/.exec(lead)
    if (star) add(spec, '*', star[1])
    else if (lead) add(spec, 'default', lead)
  }
  take(/import\s+([^'";]+?)\s+from\s*['"]([^'"]+)['"]/g, (m) => bindings(m[1], m[2]))
  take(/(?:const|let|var)\s+(\{[^}]*\}|[A-Za-z0-9_$]+)\s*=\s*await\s+import\(\s*['"]([^'"]+)['"]\s*\)/g, (m) => {
    if (m[1].startsWith('{')) bindings(m[1].replace(/\s*:\s*/g, ' as '), m[2]); else add(m[2], '*', m[1])
  })
  take(/\(\s*await\s+import\(\s*['"]([^'"]+)['"]\s*\)\s*\)\.([A-Za-z0-9_$]+)/g, (m) => add(m[1], m[2], `__inline_${m[2]}`))
  return { rel, body, refs }
})

const IDENT = '[A-Za-z0-9_$]'
/** True when `local` is called, rendered or handed on as a value in the test body (not just named in a string). */
function used(body, local) {
  if (local.startsWith('__inline_')) return true
  const id = escape(local)
  return new RegExp(`(?<![.\\w$'"\`])${id}\\s*\\(`).test(body) || new RegExp(`<${id}(?![\\w$])`).test(body)
    || new RegExp(`[(,=]\\s*${id}\\s*[,)]`).test(body) || new RegExp(`(?<![.\\w$'"\`])${id}\\s*\\.\\s*${IDENT}+\\s*\\(`).test(body)
}
function exercises(test, source, name) {
  return (test.refs.get(source) ?? []).some((ref) => {
    if (ref.exported === name) return used(test.body, ref.local)
    if (ref.exported !== '*') return false
    const id = escape(ref.local)
    // `route.loader(...)` names one export; `renderRoute(route, ...)` hands the whole module on.
    return new RegExp(`(?<![\\w$])${id}\\s*\\.\\s*${escape(name)}\\b`).test(test.body) || new RegExp(`[(,=]\\s*${id}\\s*[,)]`).test(test.body)
  })
}
const testsUsing = (source, ...names) => testData.filter((t) => names.some((name) => exercises(t, source, name))).map((t) => t.rel)
const importedBy = (source) => testData.filter((t) => t.refs.has(source)).map((t) => t.rel)

// --- what a test reaches through other files (a module used only via the app it is part of) --------

const reached = new Set()
{
  const graph = new Map(sources.map((rel) => [rel, [...read(path.join(ROOT, rel)).matchAll(/(?:from\s*|import\(\s*|require\(\s*)['"]([^'"]+)['"]/g)]
    .map((m) => resolveSpec(path.posix.dirname(rel), m[1])).filter(Boolean)]))
  const queue = testData.flatMap((t) => [...t.refs.keys()])
  while (queue.length) {
    const file = queue.pop()
    if (reached.has(file)) continue
    reached.add(file)
    queue.push(...(graph.get(file) ?? []))
  }
}

// --- Express routes: covered by a request to their path, not by an import ---------------------------

function expressRoutes(text) {
  return [...text.matchAll(/\b[A-Za-z0-9_$]+\.(get|post|put|patch|delete)\(\s*['"`](\/[^'"`]*)['"`]/g)]
    .map((m) => ({ method: m[1].toUpperCase(), path: m[2] }))
}
function requestPattern(route, method) {
  const tail = route.path === '/' ? '' : escape(route.path).replace(/:[A-Za-z0-9_]+/g, '[^/\'"`?]+')
  return new RegExp(`\\.${method.toLowerCase()}\\(\\s*[\`'"][^\`'"]*${tail}[\`'"?/]`)
}

// --- decide ------------------------------------------------------------------------------------------

const units = []
for (const rel of sources) {
  const unit = classify(rel)
  if (!unit) continue
  const text = read(path.join(ROOT, rel))
  const exp = exportsOf(text)
  const row = { kind: unit.kind, file: rel, route: unit.route || undefined, tests: [], missing: [] }
  const parts = []   // [label, covered-by[]] — everything about this file that needs a test

  if (unit.kind === 'route' && (stack === 'next' || stack === 'remix')) {
    const handlers = stack === 'next' ? exp.named.filter((n) => HTTP.includes(n)) : exp.named.filter((n) => n === 'loader' || n === 'action')
    for (const name of handlers) parts.push([name, testsUsing(rel, name)])
    if (stack === 'remix' && exp.hasDefault) parts.push(['page', testsUsing(rel, 'default')])
    if (!parts.length) parts.push(['(nothing exported)', importedBy(rel)])
  } else if (unit.kind === 'route') {
    const found = expressRoutes(text)
    for (const route of found) {
      const by = testData.filter((t) => requestPattern(route, route.method).test(t.body)).map((t) => t.rel)
      parts.push([`${route.method} ${route.path}`, by])
    }
    if (!parts.length) parts.push(['(no routes found)', importedBy(rel)])
  } else if (unit.kind === 'page' || unit.kind === 'component') {
    const wanted = exp.named.filter((n) => /^[A-Z]/.test(n))
    if (exp.hasDefault) wanted.unshift('default')
    if (!wanted.length) wanted.push('default')
    for (const name of wanted) parts.push([name, testsUsing(rel, name, ...(name === exp.aliased ? ['default'] : []))])
  } else if (unit.kind === 'middleware') {
    const wanted = exp.named.filter((n) => n === 'middleware' || n === 'proxy')
    if (exp.hasDefault || !wanted.length) wanted.push('default')
    const by = [...new Set(wanted.flatMap((name) => testsUsing(rel, name)))]
    parts.push([wanted.join(' / '), by])
  } else if (unit.kind === 'special') {
    row.optional = true
    parts.push(['default', importedBy(rel)])
  } else {   // module: one test using any export is enough; the rest is advisory
    const wanted = exp.named.length ? exp.named : exp.hasDefault ? ['default'] : []
    const per = wanted.map((name) => [name, testsUsing(rel, name, ...(name === exp.aliased ? ['default'] : []))])
    if (per.length) {
      const anyBy = [...new Set(per.flatMap(([, by]) => by))]
      // Code that only runs as part of a page, route or app that IS tested counts as exercised; `npm run
      // test:coverage` says how much of it. Code no test reaches at all is untested.
      if (!anyBy.length && reached.has(rel)) row.indirect = true
      else parts.push(['(any export)', anyBy])
      row.untested_exports = per.filter(([, by]) => !by.length).map(([name]) => name)
    }
  }

  if (unit.kind === 'component') {
    // A small component that a tested component of the same file renders (`<Foot />` inside `<AppBar />`) is exercised with it.
    const covering = [...new Set(parts.flatMap(([, by]) => by))]
    for (const part of parts) {
      if (!part[1].length && covering.length && new RegExp(`<${escape(part[0])}(?![\\w$])`).test(text)) part[1] = covering
    }
  }
  row.methods = parts.map(([name, by]) => ({ name, covered: by.length > 0, tests: by }))
  row.missing = row.methods.filter((m) => !m.covered).map((m) => m.name)
  row.tests = [...new Set(row.methods.flatMap((m) => m.tests))]
  row.status = !row.methods.length ? 'covered' : row.missing.length === 0 ? 'covered' : row.tests.length ? 'partial' : 'uncovered'
  if (!row.untested_exports?.length) delete row.untested_exports
  units.push(row)
}

const KINDS = ['page', 'route', 'component', 'middleware', 'module', 'special']
const summary = Object.fromEntries(KINDS.map((kind) => {
  const rows = units.filter((u) => u.kind === kind)
  const count = (status) => rows.filter((u) => u.status === status).length
  return [kind, { total: rows.length, covered: count('covered'), partial: count('partial'), uncovered: count('uncovered') }]
}))
const required = units.filter((u) => !u.optional)
const open = required.filter((u) => u.status !== 'covered')

fs.mkdirSync(OUT, { recursive: true })
fs.writeFileSync(path.join(OUT, 'coverage-inventory.json'), `${JSON.stringify({
  generated_at: new Date().toISOString(), stack, test_files: tests.length, summary,
  required: required.length, untested_required: open.length, units,
}, null, 2)}\n`)

console.log(`stack: ${stack}   unit test files: ${tests.length}`)
for (const kind of KINDS) {
  const s = summary[kind]
  if (s.total) console.log(`  ${kind.padEnd(11)} ${String(s.covered).padStart(3)}/${String(s.total).padEnd(3)} covered${s.partial ? `, ${s.partial} partial` : ''}${s.uncovered ? `, ${s.uncovered} untested` : ''}${kind === 'special' ? '  (optional)' : ''}`)
}
for (const u of open.slice(0, 60)) {
  console.log(`  ${u.status.toUpperCase().padEnd(9)} ${u.kind.padEnd(10)} ${u.file}${u.route ? `  (${u.route})` : ''}  needs a test for: ${u.missing.join(', ')}`)
}
if (open.length > 60) console.log(`  ... and ${open.length - 60} more (see coverage-inventory.json)`)
const advisory = units.filter((u) => u.untested_exports)
for (const u of advisory.slice(0, 20)) console.log(`  note      module     ${u.file}  ${u.indirect ? 'runs only through other tested code; ' : ''}exports no test uses directly: ${u.untested_exports.join(', ')}`)
console.log(open.length
  ? `\n${open.length} of ${required.length} required unit(s) have no unit test that uses them. Test them, or record each in report.json gaps with the reason.`
  : `\nEvery page, route, component and module (${required.length}) has a unit test that uses it.`)
console.log(`inventory: ${path.join(OUT, 'coverage-inventory.json')}`)
process.exit(open.length && !flag('--report-only') ? 1 : 0)
