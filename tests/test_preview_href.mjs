// The Studio frames the running app. It must load it on the same host name the Studio was opened on:
// `localhost` and `127.0.0.1` are different sites, and a framed app on the other one loses its sign-in cookie.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = await readFile(new URL('../studio/lib/preview.js', import.meta.url), 'utf8')
const { previewHref, needsAddress } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

const runtime = { previewUrl: 'http://127.0.0.1:4173/', publicUrl: 'https://app.example.test/' }

globalThis.location = { hostname: 'localhost' }
assert.equal(previewHref(runtime), 'http://localhost:4173/')

globalThis.location = { hostname: '127.0.0.1' }
assert.equal(previewHref(runtime), 'http://127.0.0.1:4173/')

globalThis.location = { hostname: 'localhost' }
assert.equal(previewHref({ previewUrl: 'http://localhost:5000/admin?x=1' }), 'http://localhost:5000/admin?x=1')
assert.equal(previewHref({ previewUrl: 'http://192.168.1.4:5000/' }), 'http://192.168.1.4:5000/')

globalThis.location = { hostname: 'studio.example.test' }
assert.equal(previewHref(runtime), 'https://app.example.test/')
assert.equal(needsAddress({ previewUrl: runtime.previewUrl }), true)

delete globalThis.location
assert.equal(previewHref(runtime), 'http://127.0.0.1:4173/')
console.log('preview href: ok')
