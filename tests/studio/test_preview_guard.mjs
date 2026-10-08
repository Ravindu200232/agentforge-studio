/**
 * A button in the wireframe or the prototype must go to another page of the app, never out of it. This runs the
 * preview's guard against a stand-in frame (no browser): what it stops, what it lets through, and how it follows
 * the page the app is on.
 */
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const source = await readFile(new URL('../../studio/lib/preview-guard.js', import.meta.url), 'utf8')
const guard = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

const BASE = 'http://studio.test/__agentforge/api/app/prj_1/wireframe/bundle.html?v=7#/home'

function anchor(href, target = '') {
  const attrs = { href, ...(target ? { target } : {}) }
  const node = { getAttribute: (name) => (name in attrs ? attrs[name] : null) }
  node.closest = (selector) => (selector.includes('a[href]') && href !== null ? node : null)
  return node
}

function stand_in(url = BASE) {
  const listeners = new Map()
  const winListeners = new Map()
  const calls = { pushed: 0 }
  const win = {
    location: { hash: new URL(url).hash },
    history: {
      pushState(_s, _t, next) { calls.pushed++; if (next) win.location.hash = new URL(next, url).hash },
      replaceState() {},
    },
    open: () => 'a window',
    addEventListener: (type, fn) => winListeners.set(type, fn),
    removeEventListener: (type) => winListeners.delete(type),
  }
  const doc = {
    location: { href: url },
    addEventListener: (type, fn, capture) => listeners.set(type, { fn, capture }),
    removeEventListener: (type) => listeners.delete(type),
  }
  const event = (target, extra = {}) => ({ target, prevented: false, preventDefault() { this.prevented = true }, ...extra })
  return { frame: { contentDocument: doc, contentWindow: win }, listeners, winListeners, win, doc, event, calls }
}

test('only a hash, or the same document, stays inside the app', () => {
  assert.equal(guard.staysInApp('#/orders', BASE), true)
  assert.equal(guard.staysInApp('', BASE), true)
  assert.equal(guard.staysInApp(null, BASE), true)
  assert.equal(guard.staysInApp('bundle.html?v=7#/orders', BASE), true)
  assert.equal(guard.staysInApp('https://example.com/out', BASE), false)
  assert.equal(guard.staysInApp('/orders', BASE), false, 'a root path leaves the app for the studio itself')
  assert.equal(guard.staysInApp('other.html', BASE), false)
  assert.equal(guard.staysInApp('mailto:a@b.c', BASE), false)
  assert.equal(guard.staysInApp('tel:123', BASE), false)
  assert.equal(guard.staysInApp('javascript:alert(1)', BASE), false)
})

test('a link to anywhere else is stopped where it starts, and said', () => {
  const s = stand_in()
  const seen = []
  guard.attachGuard(s.frame, { onBlocked: (b) => seen.push(b) })
  for (const type of ['click', 'auxclick']) {
    assert.equal(s.listeners.get(type).capture, true, `${type} is caught before the app's own handlers`)
    const event = s.event(anchor('https://example.com/out'))
    s.listeners.get(type).fn(event)
    assert.equal(event.prevented, true)
  }
  assert.deepEqual(seen[0], { what: 'link', href: 'https://example.com/out' })
})

test('a link to another page of the app is left to the app', () => {
  const s = stand_in()
  const seen = []
  guard.attachGuard(s.frame, { onBlocked: (b) => seen.push(b) })
  const event = s.event(anchor('#/orders'))
  s.listeners.get('click').fn(event)
  assert.equal(event.prevented, false)
  assert.deepEqual(seen, [])
  s.listeners.get('click').fn(s.event({ closest: () => null }))   // not a link at all
})

test('an in-app link that asks for a new window opens in the frame instead', () => {
  const s = stand_in()
  guard.attachGuard(s.frame, {})
  const event = s.event(anchor('#/orders', '_blank'))
  s.listeners.get('click').fn(event)
  assert.equal(event.prevented, true)
  assert.equal(s.win.location.hash, '#/orders')
  const outside = s.event(anchor('https://example.com', '_top'))
  s.listeners.get('click').fn(outside)
  assert.equal(outside.prevented, true)
})

test('a form never leaves the frame, and a popup never opens', () => {
  const s = stand_in()
  const seen = []
  guard.attachGuard(s.frame, { onBlocked: (b) => seen.push(b.what) })
  const submit = s.event({})
  s.listeners.get('submit').fn(submit)
  assert.equal(submit.prevented, true)
  assert.equal(s.win.open('https://example.com'), null)
  assert.deepEqual(seen, ['popup'])
})

test('the page the app is on is followed, including a router that uses pushState', () => {
  const s = stand_in()
  const routes = []
  guard.attachGuard(s.frame, { onRoute: (r) => routes.push(r) })
  assert.deepEqual(routes, ['/home'], 'it says where the app starts')
  s.win.history.pushState({}, '', '#/orders/12')
  assert.equal(routes.at(-1), '/orders/12')
  s.winListeners.get('hashchange')()
  assert.ok(routes.length >= 3)
})

test('detaching puts the frame back as it was', () => {
  const s = stand_in()
  const originalPush = s.win.history.pushState
  const originalOpen = s.win.open
  const detach = guard.attachGuard(s.frame, {})
  assert.notEqual(s.win.history.pushState, originalPush)
  detach()
  assert.equal(s.win.history.pushState, originalPush)
  assert.equal(s.win.open, originalOpen)
  assert.equal(s.listeners.size, 0)
  assert.equal(s.winListeners.size, 0)
})

test('a frame that cannot be read yet is not guarded', () => {
  const unreadable = { get contentDocument() { throw new Error('cross-origin') } }
  assert.equal(guard.attachGuard(unreadable, {}), null)
  assert.equal(guard.attachGuard({ contentDocument: null, contentWindow: null }, {}), null)
})

test('a frame carried to another page is noticed', () => {
  globalThis.window = { location: { href: 'http://studio.test/' } }
  try {
    const expected = '/__agentforge/api/app/prj_1/wireframe/bundle.html?v=7#/home'
    const home = { contentWindow: { location: { href: 'http://studio.test/__agentforge/api/app/prj_1/wireframe/bundle.html?v=7#/orders' } } }
    assert.equal(guard.confinedTo(home, expected), true)
    const away = { contentWindow: { location: { href: 'https://example.com/' } } }
    assert.equal(guard.confinedTo(away, expected), false)
    const unreadable = { get contentWindow() { throw new Error('cross-origin') } }
    assert.equal(guard.confinedTo(unreadable, expected), false)
  } finally {
    delete globalThis.window
  }
})

test('routes are opened by hash, parameters get a sample value, and the list follows the frame', () => {
  assert.equal(guard.hashFor('/orders'), '#/orders')
  assert.equal(guard.hashFor('orders'), '#/orders')
  assert.equal(guard.hashFor('/orders/[id]'), '#/orders/1')
  assert.equal(guard.hashFor('/orders/:id/edit'), '#/orders/1/edit')
  assert.equal(guard.hashFor(''), '#/')
  assert.equal(guard.routeOf('#/orders?x=1'), '/orders?x=1')
  assert.equal(guard.routeOf(''), '/')
  assert.equal(guard.routeMatches('/orders/[id]', '/orders/12'), true)
  assert.equal(guard.routeMatches('/orders/:id', '/orders/12?tab=a'), true)
  assert.equal(guard.routeMatches('/orders', '/orders/12'), false)
  assert.equal(guard.routeMatches('/', '/'), true)

  const s = stand_in()
  assert.equal(guard.goTo(s.frame, '/orders/[id]'), true)
  assert.equal(s.win.location.hash, '#/orders/1')
  assert.equal(guard.goTo({ contentWindow: null }, '/x'), false)
})
