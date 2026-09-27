/**
 * Every component a page renders has to exist by the time it renders.
 *
 * `next build` compiles JSX without resolving the identifiers inside it, so
 * `<Search />` with `Search` missing from the import list builds cleanly and
 * throws "Search is not defined" the first time that branch is rendered. A
 * dialog nobody opens during a build — a plan approval, a question — can be
 * broken for days that way, and the thing that finds it is a user.
 *
 * This resolves every capitalised element in every component against what the
 * file imports, defines or declares. It is a linter's job; there is no linter
 * here, and the one rule that matters costs forty lines.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

// Lower-case names are HTML elements; a dotted name resolves through its root,
// which is checked on its own.
const USED = /<([A-Z][A-Za-z0-9_]*)/g

// Named bindings, default imports, declarations and destructured locals: every
// way a name can come to exist in a module.
const PATTERNS = [
  /import\s+\{([^}]+)\}\s+from/g,
  /import\s+([A-Za-z0-9_$]+)\s*(?:,|from)/g,
  /import\s+\{[^}]*\}\s*,\s*([A-Za-z0-9_$]+)\s+from/g,
  /(?:const|let|var|function|class)\s+([A-Za-z0-9_$]+)/g,
  /(?:const|let|var)\s+\{([^}]+)\}\s*=/g,
  // A destructured parameter: ({ icon: Icon }) => …, and .map(({ Icon }) => …
  /\(\s*\{([^}]+)\}\s*(?:,|\)|=>)/g,
  // An array pattern: .map(([Icon, text]) => …
  /\(\s*\[([^\]]+)\]\s*(?:,|\)|=>)/g,
]

function walk(directory) {
  const out = []
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) out.push(...walk(path))
    else if (/\.jsx?$/.test(entry)) out.push(path)
  }
  return out
}

function declared(source) {
  const names = new Set(['Fragment', 'Suspense'])
  for (const pattern of PATTERNS) {
    for (const [, group] of source.matchAll(pattern)) {
      for (const part of String(group).split(',')) {
        // `Image as NextImage` binds the second name; `a: b` binds b.
        const name = part.trim().split(/\s+as\s+|:/).pop().trim().replace(/[^A-Za-z0-9_$].*$/, '')
        if (name) names.add(name)
      }
    }
  }
  return names
}

const missing = []
let checked = 0
for (const file of [...walk(join(ROOT, 'components')), ...walk(join(ROOT, 'app'))]) {
  const source = readFileSync(file, 'utf8')
  const known = declared(source)
  checked++
  for (const [, name] of source.matchAll(USED)) {
    const root = name.split('.')[0]
    if (!known.has(root)) missing.push(`${relative(ROOT, file)}: <${name}> is never defined here`)
  }
}

const unique = [...new Set(missing)]
if (unique.length) {
  console.error('Unresolved components:\n' + unique.map(line => '  ' + line).join('\n'))
  process.exit(1)
}
console.log(`Component resolution: ${checked} files, every rendered component is defined`)
