#!/usr/bin/env node
// Node port of bundle-artifact.sh: bundle the React app in the current directory into one
// self-contained bundle.html (Parcel build, then html-inline). Same steps and output as the
// official script; the bundling tools come from the shared dependency store instead of a
// per-project pnpm install.
//
//   cd <project> && node bundle-artifact.mjs
//   node bundle-artifact.mjs <project-folder>          (the same, from anywhere)
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import { fail, runtimeDir, ensureRuntime, linkNodeModules } from './lib.mjs'

console.log('Bundling React app to single HTML artifact...')

if (process.argv[2]) {
  try {
    process.chdir(process.argv[2])
  } catch {
    fail('Project folder not found: ' + process.argv[2])
  }
}

if (!fs.existsSync('package.json')) fail('No package.json found. Run this script from your project root.')
if (!fs.existsSync('index.html')) fail('No index.html found in project root. This script requires an index.html entry point.')

const root = process.cwd()
const store = runtimeDir()
ensureRuntime(store)
linkNodeModules(root, store)

// See init-artifact.mjs: the lockfile keeps Parcel's project root at this folder.
if (!fs.existsSync('package-lock.json')) {
  fs.writeFileSync('package-lock.json', JSON.stringify({ lockfileVersion: 3, requires: true, packages: {} }, null, 2) + '\n')
}

if (!fs.existsSync('.parcelrc')) {
  console.log('Creating Parcel configuration with path alias support...')
  fs.writeFileSync(
    '.parcelrc',
    JSON.stringify({ extends: '@parcel/config-default', resolvers: ['parcel-resolver-tspaths', '...'] }, null, 2) + '\n'
  )
}

console.log('Cleaning previous build...')
fs.rmSync('dist', { recursive: true, force: true })
fs.rmSync('bundle.html', { force: true })

console.log('Building with Parcel...')
const parcel = path.join(store, 'node_modules', 'parcel', 'lib', 'bin.js')
const build = spawnSync(
  process.execPath,
  [parcel, 'build', 'index.html', '--dist-dir', 'dist', '--no-source-maps', '--no-autoinstall', '--public-url', './'],
  { cwd: root, stdio: 'inherit' }
)
if (build.status !== 0 || !fs.existsSync(path.join('dist', 'index.html'))) fail('The Parcel build failed (see the messages above).')

console.log('Inlining all assets into single HTML file...')
const inline = createRequire(path.join(store, 'node_modules', 'x.js'))('html-inline')
await new Promise((resolve, reject) => {
  const out = fs.createWriteStream('bundle.html')
  out.on('finish', resolve).on('error', reject)
  fs
    .createReadStream(path.join('dist', 'index.html'))
    .pipe(inline({ basedir: path.resolve('dist') }))
    .on('error', reject)
    .pipe(out)
}).catch((error) => fail('Inlining failed: ' + error.message))

const kb = Math.round(fs.statSync('bundle.html').size / 1024)
console.log('')
console.log('Bundle complete!')
console.log('Output: bundle.html (' + kb + ' KB)')
