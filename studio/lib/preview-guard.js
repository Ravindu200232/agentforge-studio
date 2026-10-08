/**
 * The wireframe and the prototype are React apps that run inside a frame in the studio. A button in one
 * must go to another page of the same app and never anywhere else. That is the preview's own rule and it is
 * set here, on the frame: nothing the agent writes decides it, and nothing it forgets to write can break it.
 *
 * Three layers, each catching what the one before cannot:
 *   1. the frame's `sandbox` (no top navigation, no popups) and the policy the server puts in the page,
 *   2. `attachGuard`: links to anywhere else, forms and `window.open` are stopped where they start,
 *   3. `confinedTo`: if the frame is somehow carried away (a script assigning `location.href`), put it back.
 */

// Scripts and same-origin so the picker and the text tool can read the page; no top navigation, no popups.
export const FRAME_SANDBOX = 'allow-scripts allow-same-origin allow-forms allow-modals'

const NEW_WINDOW = new Set(['_blank', '_top', '_parent'])

/** `#/orders?x=1`, `/orders` or `orders` → `/orders?x=1` */
export function routeOf(hash) {
  const text = String(hash || '').replace(/^#/, '').trim()
  if (!text) return '/'
  return text.startsWith('/') ? text : `/${text}`
}

/** The hash a route is opened at; a parameter (`/orders/[id]`, `/orders/:id`) becomes a sample value. */
export function hashFor(route) {
  const filled = String(route || '/').replace(/\[[^\]]+\]|:[A-Za-z_]\w*/g, '1')
  return `#${filled.startsWith('/') ? filled : `/${filled}`}`
}

/** Does the page route `pattern` (which may hold parameters) describe the route `actual` the frame is on? */
export function routeMatches(pattern, actual) {
  const want = String(pattern || '/').split('?')[0].split('/').filter(Boolean)
  const have = String(actual || '/').split('?')[0].split('/').filter(Boolean)
  if (want.length !== have.length) return false
  return want.every((part, i) => part === have[i] || /^\[[^\]]+\]$|^:[A-Za-z_]\w*$/.test(part))
}

/** True when following `href` from the page at `base` stays inside the app: the same document, only the hash differs. */
export function staysInApp(href, base) {
  if (href === null || href === undefined) return true
  const raw = String(href).trim()
  if (raw === '' || raw.startsWith('#')) return true
  try {
    const there = new URL(raw, base)
    const here = new URL(base)
    return there.origin === here.origin && there.pathname === here.pathname && there.search === here.search
  } catch {
    return false
  }
}

/** Is the frame still showing the app it was given (and not a page it was carried to)? */
export function confinedTo(frame, expected) {
  try {
    const here = new URL(frame.contentWindow.location.href)
    const wanted = new URL(expected, typeof window !== 'undefined' ? window.location.href : undefined)
    return here.origin === wanted.origin && here.pathname === wanted.pathname
  } catch {
    return false          // a page on another origin cannot be read at all
  }
}

/** Open one page of the app: its hash is set, the app's router does the rest. */
export function goTo(frame, route) {
  try {
    const win = frame?.contentWindow
    if (!win) return false
    const next = hashFor(route)
    if (win.location.hash !== next) win.location.hash = next
    return true
  } catch {
    return false
  }
}

/**
 * Guard the app inside `frame`. `onBlocked({ what, href })` says what was stopped; `onRoute(route)` says which
 * page the app is on, whenever it changes (a router navigates with pushState, which fires no `hashchange`).
 * Returns a `detach()` that puts everything back, or null when the frame cannot be read yet.
 */
export function attachGuard(frame, { onBlocked, onRoute } = {}) {
  let doc, win
  try {
    doc = frame.contentDocument
    win = frame.contentWindow
  } catch {
    return null
  }
  if (!doc || !win) return null
  const here = () => doc.location.href
  const blocked = (what, href = '') => onBlocked?.({ what, href })

  const follow = (event) => {
    const anchor = event.target?.closest?.('a[href], area[href]')
    if (!anchor) return
    const href = anchor.getAttribute('href')
    const target = String(anchor.getAttribute('target') || '').toLowerCase()
    const inside = staysInApp(href, here())
    if (inside && !NEW_WINDOW.has(target)) return            // a link of the app: its router handles it
    event.preventDefault()
    if (inside) {                                             // an in-app link asking for a new window: open it here
      try { win.location.hash = new URL(href, here()).hash } catch { /* nowhere to go */ }
      return
    }
    blocked('link', href)
  }
  const submit = (event) => { event.preventDefault() }       // a form never leaves; the app's own handler still runs
  const drag = (event) => { if (event.target?.closest?.('a[href]')) event.preventDefault() }

  const tell = () => { try { onRoute?.(routeOf(win.location.hash)) } catch { /* the frame went away */ } }
  const wrapped = []
  for (const method of ['pushState', 'replaceState']) {
    const original = win.history?.[method]
    if (typeof original !== 'function') continue
    win.history[method] = function wrappedState(...args) {
      const result = original.apply(this, args)
      tell()
      return result
    }
    wrapped.push([method, original])
  }
  const originalOpen = win.open
  win.open = () => { blocked('popup'); return null }

  doc.addEventListener('click', follow, true)
  doc.addEventListener('auxclick', follow, true)
  doc.addEventListener('submit', submit, true)
  doc.addEventListener('dragstart', drag, true)
  win.addEventListener('hashchange', tell)
  win.addEventListener('popstate', tell)
  tell()

  return () => {
    try {
      doc.removeEventListener('click', follow, true)
      doc.removeEventListener('auxclick', follow, true)
      doc.removeEventListener('submit', submit, true)
      doc.removeEventListener('dragstart', drag, true)
      win.removeEventListener('hashchange', tell)
      win.removeEventListener('popstate', tell)
      for (const [method, original] of wrapped) win.history[method] = original
      win.open = originalOpen
    } catch { /* the frame is gone */ }
  }
}
