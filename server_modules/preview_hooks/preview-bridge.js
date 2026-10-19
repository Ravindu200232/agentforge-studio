// The Studio's bridge inside a framed preview of a built app. frame-headers.cjs serves this file and adds it to the app's pages,
// in the Studio's preview process only (never in the app's tests, its build or its deployment).
//
// The preview is another site than the Studio (http://127.0.0.1:PORT inside localhost:3000 or agentforge://app), so the Studio
// cannot reach into the page. It sends commands instead ({type: "agentforge:command", kind: "init" | "pick" | "navigate"}),
// and this answers ({type: "agentforge:preview", kind: "ready" | "route" | "console" | "picked"}): where the page is, what it
// logged, and the element the person clicked while picking. Only the window that frames the page is listened to, and only from
// this computer or the desktop app.
(() => {
  if (window.__agentforgeBridge || window.parent === window) return
  window.__agentforgeBridge = true

  const ALLOWED = /^(?:https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?|agentforge:\/\/.*|null)$/i
  let parent = null                              // {origin, project, runtimeId}, from the first command
  let mode = 'desktop'
  let detach = null

  const send = (kind, data = {}) => {
    if (!parent) return
    try {
      window.parent.postMessage({ type: 'agentforge:preview', kind, project: parent.project, runtimeId: parent.runtimeId, ...data },
        parent.origin === 'null' ? '*' : parent.origin)
    } catch { /* a message the Studio cannot take is dropped */ }
  }

  const route = () => (location.hash.startsWith('#/') ? location.hash.slice(1).split('?')[0] : location.pathname + location.search)
  const where = () => send('route', { route: route(), scroll: { x: scrollX, y: scrollY } })
  for (const method of ['pushState', 'replaceState']) {
    const original = history[method]
    history[method] = function (...args) {
      const result = original.apply(this, args)
      setTimeout(where, 0)
      return result
    }
  }
  addEventListener('popstate', where)
  addEventListener('hashchange', where)
  let scrolled = null
  addEventListener('scroll', () => {
    clearTimeout(scrolled)
    scrolled = setTimeout(where, 150)
  }, { passive: true })

  // What the page logs as a warning or an error, for the Studio's console.
  for (const level of ['error', 'warn']) {
    const original = console[level]
    console[level] = function (...args) {
      try {
        send('console', { level, text: args.map(a => (a instanceof Error ? a.stack || a.message : typeof a === 'string' ? a : (() => {
          try { return JSON.stringify(a) } catch { return String(a) }
        })())).join(' ').slice(0, 2000) })
      } catch { /* never in the page's way */ }
      return original.apply(this, args)
    }
  }
  addEventListener('error', event => send('console', { level: 'error', text: String(event.message || 'error').slice(0, 2000) }))
  addEventListener('unhandledrejection', event => send('console', {
    level: 'error', text: `Unhandled rejection: ${String(event.reason && (event.reason.stack || event.reason.message) || event.reason).slice(0, 2000)}` }))

  // The element picker: the same description of an element the Studio makes for a page it can reach (studio/lib/picker.js).
  const STYLE = '.__lc_hi{outline:2px solid #5b7cf7!important;outline-offset:-2px;background:rgba(91,124,247,.10)!important;'
    + 'cursor:crosshair!important}'

  function info(el) {
    const attrs = {}
    for (const k of ['href', 'type', 'placeholder', 'name', 'alt', 'aria-label', 'data-testid', 'role']) {
      const v = el.getAttribute && el.getAttribute(k)
      if (v) attrs[k] = v
    }
    const chain = []
    let up = el.parentElement
    for (let i = 0; i < 6 && up; i++, up = up.parentElement) {
      chain.push({ tag: up.tagName.toLowerCase(), id: up.id || '', className: up.getAttribute('class') || '',
                   text: (up.innerText || '').trim().split('\n')[0].slice(0, 80) })
    }
    const r = el.getBoundingClientRect()
    let bg = ''
    try {
      const m = /url\(["']?([^"')]+)/.exec(getComputedStyle(el).backgroundImage || '')
      if (m) bg = m[1]
    } catch { /* no style */ }
    const src = (el.getAttribute && el.getAttribute('src')) || ''
    return {
      tag: el.tagName.toLowerCase(), id: el.id || '', src, bg,
      isImage: el.tagName.toLowerCase() === 'img' || !!bg,
      classes: Array.from(el.classList || []), className: el.getAttribute('class') || '',
      text: (el.innerText || '').trim().slice(0, 160), attrs, chain,
      rect: { x: r.x, y: r.y, w: r.width, h: r.height },
      route: route(), scroll: { x: scrollX, y: scrollY },
      viewport: { w: innerWidth, h: innerHeight, mode },
      outerHTML: (el.outerHTML || '').slice(0, 1200),
    }
  }

  function picked(el) {
    const found = info(el)
    const kids = [...el.children].filter(k => k.getBoundingClientRect().height > 0)
    if (kids.length > 1) found.section = { start: info(kids[0]), end: info(kids[kids.length - 1]) }
    return found
  }

  function pickOn() {
    if (detach) return
    let style = document.getElementById('__lc_pick_style')
    if (!style) {
      style = document.createElement('style')
      style.id = '__lc_pick_style'
      style.textContent = STYLE
      document.head.appendChild(style)
    }
    const hover = e => e.target.classList && e.target.classList.add('__lc_hi')
    const leave = e => e.target.classList && e.target.classList.remove('__lc_hi')
    const click = e => {
      e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation()
      e.target.classList && e.target.classList.remove('__lc_hi')
      send('picked', { info: picked(e.target) })
    }
    document.addEventListener('mouseover', hover, true)
    document.addEventListener('mouseout', leave, true)
    document.addEventListener('click', click, true)
    detach = () => {
      document.removeEventListener('mouseover', hover, true)
      document.removeEventListener('mouseout', leave, true)
      document.removeEventListener('click', click, true)
      document.querySelectorAll('.__lc_hi').forEach(e => e.classList.remove('__lc_hi'))
      document.getElementById('__lc_pick_style')?.remove()
      detach = null
    }
  }

  addEventListener('message', event => {
    const message = event.data
    if (event.source !== window.parent || !message || message.type !== 'agentforge:command' || !ALLOWED.test(event.origin)) return
    parent = { origin: event.origin, project: message.project, runtimeId: message.runtimeId }
    if (message.kind === 'init') {
      where()
      send('ready')
    } else if (message.kind === 'pick') {
      mode = message.mode || 'desktop'
      if (message.enabled) pickOn()
      else if (detach) detach()
    } else if (message.kind === 'navigate' && typeof message.route === 'string') {
      const url = new URL(message.route, location.origin)
      if (url.origin === location.origin) location.href = url.href
    }
  })
})()
