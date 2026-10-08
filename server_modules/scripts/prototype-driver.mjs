// A browser the Studio drives from Python, one command at a time, to click through a prototype the way a person would.
//
//   node prototype-driver.mjs
//
// Commands arrive as one JSON object per line on stdin ({"id": 1, "cmd": "goto", ...}); each is answered by one line on
// stdout ({"id": 1, "ok": true, ...} or {"id": 1, "ok": false, "error": "..."}). A line with a "live" key is not an
// answer: it is what the browser is showing (a picture, the pointer), for the Studio to show in its preview while the
// journey is walked. Nothing else is ever written to stdout.
//
// The prototype is one bundled page (`bundle.html`) that shows the screen its address hash names (`#/orders`), so a click that
// moves to another screen only changes the hash. `puppeteer-core` is the Studio's own (studio/node_modules), found from
// STUDIO_ROOT. The browser is the one the Studio found and tried (`launch`'s `exe`; "shell" is Playwright's headless-only build).
import fs from 'node:fs'
import path from 'node:path'
import readline from 'node:readline'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const require = createRequire(path.join(process.env.STUDIO_ROOT || process.cwd(), 'package.json'))
const loaded = require('puppeteer-core')
const puppeteer = loaded.default || loaded

const out = line => process.stdout.write(JSON.stringify(line) + '\n')
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

let browser = null
let context = null
let page = null
let cdp = null
let settings = { live: false, pace: 0, width: 1280, height: 800, sample: '' }
let errors = []
let lastFrame = 0

/** What a page can be clicked, filled or chosen on, numbered, as the planner reads them. */
const COLLECT = () => {
  // Numbers from an earlier look are taken off first: a new number must never find an old, hidden element that still has it.
  document.querySelectorAll('[data-af-i]').forEach(el => el.removeAttribute('data-af-i'))
  const seen = []
  const taken = new Set()
  const base = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="tab"], [role="menuitem"], ' +
    '[role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], [role="combobox"], [role="switch"], [role="checkbox"], [role="radio"]'
  const clickable = Array.from(document.querySelectorAll(base))
  // Something drawn to be pressed with no button in it (a card or a row with a click handler) shows it with the pointer.
  const extra = Array.from(document.querySelectorAll('main *, [role="dialog"] *, [role="menu"] *, nav *, header *, aside *')).filter(el =>
    !el.matches(base) && !el.closest(base) && getComputedStyle(el).cursor === 'pointer'
    && !(el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer'))
  const text = el => (el.getAttribute('aria-label') || el.innerText || el.textContent || el.value || el.getAttribute('title') || el.getAttribute('placeholder') || '')
    .replace(/\s+/g, ' ').trim().slice(0, 70)
  const layer = 'dialog[open], [role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper]'
  for (const el of [...clickable, ...extra]) {
    if (taken.has(el)) continue
    taken.add(el)
    const rect = el.getBoundingClientRect()
    const style = getComputedStyle(el)
    if (!rect.width || !rect.height || style.visibility === 'hidden' || style.display === 'none') continue
    if (el.closest('dialog:not([open])') || el.closest('[hidden]') || el.closest('[aria-hidden="true"]:not([role="dialog"])')) continue
    if (el.tagName === 'INPUT' && el.type === 'hidden') continue
    const i = seen.length
    el.setAttribute('data-af-i', String(i))
    let label = ''
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = l.innerText.replace(/\s+/g, ' ').trim().slice(0, 70) }
    if (!label && el.closest('label')) label = el.closest('label').innerText.replace(/\s+/g, ' ').trim().slice(0, 70)
    const href = el.tagName === 'A' ? el.getAttribute('href') || '' : ''
    let to = ''
    let external = false
    if (href.startsWith('#/')) to = '/' + href.slice(1).split('?')[0].split('/').filter(Boolean).join('/')
    else if (href && href !== '#' && !href.startsWith('#') && !/^(mailto|tel|javascript):/i.test(href)) {
      try {
        const url = new URL(href, location.href)
        external = url.protocol !== location.protocol || url.host !== location.host
        if (!external) to = '/' + url.pathname.split('/').filter(Boolean).join('/')
      } catch { /* not a link we can follow */ }
    }
    const role = el.getAttribute('role') || ''
    const area = el.closest(layer) ? 'dialog' : el.closest('nav, header, aside') ? 'nav' : el.closest('footer') ? 'footer' : 'main'
    const field = ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)
    seen.push({
      i, tag: el.tagName.toLowerCase(), type: el.type || '', role, text: text(el) || (href ? '(icon link to ' + href + ')' : ''), label, href, to, external,
      name: el.getAttribute('name') || '', placeholder: el.getAttribute('placeholder') || '', area,
      popup: el.hasAttribute('aria-haspopup') || el.getAttribute('aria-expanded') === 'false' || role === 'combobox' || el.tagName === 'SUMMARY',
      disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
      checked: Boolean(el.checked) || el.getAttribute('aria-checked') === 'true',
      value: field && el.type !== 'password' ? String(el.value || '').slice(0, 60) : '',
      options: el.tagName === 'SELECT' ? Array.from(el.options).slice(0, 12).map(o => (o.text || o.value).trim().slice(0, 40)) : undefined,
      signOut: el.hasAttribute('data-sign-out') || /\b(log ?out|sign ?out)\b/i.test(text(el)),
    })
  }
  return seen.slice(0, 120)
}

async function state() {
  const info = await page.evaluate(() => ({
    url: location.href, title: document.title,
    path: '/' + location.hash.replace(/^#/, '').split('?')[0].split('/').filter(Boolean).join('/'),
    heading: (document.querySelector('h1') || document.querySelector('h2') || {}).innerText || '',
    user: window.__afUser || '',
    failed: (document.querySelector('[data-af-error]') || {}).innerText || '',
  })).catch(() => ({ url: page.url(), title: '', path: '/', heading: '', user: '', failed: '' }))
  info.heading = String(info.heading).replace(/\s+/g, ' ').trim().slice(0, 120)
  info.failed = String(info.failed).replace(/\s+/g, ' ').trim().slice(0, 200)
  return info
}

/** The picture the Studio shows live: the page as it is now. */
async function push(kind = 'frame') {
  if (!settings.live || !page) return
  try {
    // The window as it is: no resizing of the page to take the picture, which would move what is about to be clicked.
    const shot = await page.screenshot({ type: 'jpeg', quality: 55, encoding: 'base64', captureBeyondViewport: false })
    const info = await page.evaluate(() => ({ url: location.href, title: document.title, bg: getComputedStyle(document.body).backgroundColor }))
    out({ live: { kind, frame: 'data:image/jpeg;base64,' + shot, url: info.url, title: info.title, bg: info.bg,
                  viewport: { width: settings.width, height: settings.height } } })
  } catch { /* a picture that could not be taken is only a picture */ }
}

// Where the pointer is and what it is doing. No box is drawn around the element it uses: the page stays as it is.
function pointer(x, y, action) {
  if (settings.live) out({ live: { kind: 'cursor', cursor: { x, y, action } } })
}

async function pace() {
  if (settings.pace) await sleep(settings.pace)
}

async function open() {
  if (context) await context.close().catch(() => {})
  context = await browser.createBrowserContext()
  page = await context.newPage()
  page.on('pageerror', e => errors.push(String(e.message || e).slice(0, 300)))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)) })
  page.on('dialog', d => d.accept().catch(() => {}))    // an alert or a "are you sure" is answered yes, like a person would
  await page.setViewport({ width: settings.width, height: settings.height })
  if (settings.live) {
    cdp = await page.createCDPSession()
    cdp.on('Page.screencastFrame', async ({ data, sessionId }) => {
      try { await cdp.send('Page.screencastFrameAck', { sessionId }) } catch { /* the page went away */ }
      const now = Date.now()
      if (now - lastFrame < 110) return
      lastFrame = now
      out({ live: { kind: 'frame', frame: 'data:image/jpeg;base64,' + data, url: page.url(), title: '',
                    viewport: { width: settings.width, height: settings.height } } })
    })
    await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 50, everyNthFrame: 1 }).catch(() => {})
  }
}

/**
 * Bring an element into view and find the point on it that a click really reaches.
 *
 * `behavior: 'instant'` because a page that scrolls smoothly (`scroll-behavior: smooth`) keeps moving while it is measured, and
 * the click then lands where the element was. The element is measured until it has stopped. A sticky header or a bar fixed to the
 * bottom can lie over part of it, as it would for a person: another point on it is tried, and when nothing on it can be reached
 * the error says what covers it.
 */
async function aim(handle) {
  await handle.evaluate(el => el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' })).catch(() => {})
  let box = null
  for (let tries = 0; tries < 8; tries++) {
    await sleep(60)
    const next = await handle.boundingBox()
    const still = next && box && Math.abs(next.x - box.x) < 1 && Math.abs(next.y - box.y) < 1
    box = next
    if (still) break
  }
  if (!box) throw new Error('that element has nowhere to click')
  for (const [fx, fy] of [[0.5, 0.5], [0.5, 0.25], [0.5, 0.75], [0.15, 0.5], [0.85, 0.5]]) {
    const x = box.x + box.width * fx
    const y = box.y + box.height * fy
    const reached = await handle.evaluate((el, px, py) => {
      const top = document.elementFromPoint(px, py)
      return Boolean(top && (top === el || el.contains(top)))
    }, x, y)
    if (reached) return { x, y, box }
  }
  const covering = await handle.evaluate((el, px, py) => {
    const top = document.elementFromPoint(px, py)
    return top ? top.tagName.toLowerCase() + (top.className && typeof top.className === 'string' ? '.' + top.className.split(' ')[0] : '') : 'nothing'
  }, box.x + box.width / 2, box.y + box.height / 2)
  throw new Error(`something else covers it (${covering})`)
}

/** After a click: long enough to see whether another screen is opening (the address hash changes), and for it to be drawn. */
async function afterAction(before) {
  await sleep(450)
  if (page.url() === before) await sleep(450)       // a handler can take a moment before it moves to the next screen
  await sleep(250)
  await push()
  await pace()
}

const handlers = {
  async launch({ exe, how, width, height, live, pace: ms, sample }) {
    settings = { live: Boolean(live), pace: Number(ms) || 0, width: Number(width) || 1280, height: Number(height) || 800, sample: sample || '' }
    browser = await puppeteer.launch({
      executablePath: exe, headless: how === 'shell' ? 'shell' : true, defaultViewport: null,
      args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-gpu', '--hide-scrollbars'],
    })
    await open()
    return {}
  },
  async reset() { await open(); return {} },
  /** Open the prototype's page (a file on disk) with `suffix` (`?as=…#/route`) on its address. */
  async goto({ file, suffix }) {
    await page.goto(pathToFileURL(path.resolve(file)).href + (suffix || ''), { waitUntil: 'load', timeout: 30_000 })
    // The app draws itself once its script has run: wait until there is something on the screen.
    await page.waitForFunction(() => (document.getElementById('root') || document.body).innerText.trim().length > 0, { timeout: 8_000 }).catch(() => {})
    await sleep(250)
    await push()
    await pace()
    return { state: await state() }
  },
  /** Move to another screen the way a person who types an address would (only for getting a journey started). */
  async hash({ route }) {
    const before = page.url()
    await page.evaluate(to => { window.location.hash = '#' + to }, String(route || '/'))
    await afterAction(before)
    return { state: await state() }
  },
  async state() { return { state: await state() } },
  async elements() { return { elements: await page.evaluate(COLLECT), state: await state() } },
  /** The start of what the screen says, so that a model can use words that are really on it. */
  async text() {
    const body = await page.evaluate(() => (document.querySelector('main') || document.getElementById('root') || document.body).innerText || '')
    const lines = String(body).split(/\r?\n/).map(line => line.replace(/\s+/g, ' ').trim()).filter(Boolean)
    return { text: lines.join('\n').slice(0, 1400) }
  },
  async click({ i }) {
    const handle = await page.$(`[data-af-i="${Number(i)}"]`)
    if (!handle) throw new Error('that element is no longer on the page')
    const { x, y } = await aim(handle)
    await push()      // what is shown before the click (the page is not moved by taking it)
    pointer(x, y, 'click')
    const before = page.url()
    await page.mouse.click(x, y)
    await afterAction(before)
    return { state: await state(), navigated: page.url() !== before }
  },
  async fill({ i, value }) {
    const handle = await page.$(`[data-af-i="${Number(i)}"]`)
    if (!handle) throw new Error('that field is no longer on the page')
    const kind = await handle.evaluate(el => (el.tagName === 'SELECT' ? 'select' : el.type || el.tagName.toLowerCase()))
    const spot = await aim(handle)
    pointer(spot.x, spot.y, 'type')
    if (kind === 'select') {
      const chosen = await handle.evaluate((el, wanted) => {
        const w = String(wanted).trim().toLowerCase()
        const option = Array.from(el.options).find(o => (o.text || '').trim().toLowerCase() === w || (o.value || '').toLowerCase() === w)
          || Array.from(el.options).find(o => (o.text || '').toLowerCase().includes(w)) || Array.from(el.options).find(o => o.value)
        if (!option) return false
        // The native setter, so that the app's own change handler (React keeps its own record of a value) notices the change.
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, option.value)
        el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }))
        return true
      }, value)
      if (!chosen) throw new Error('that list has no such choice')
    } else if (kind === 'checkbox' || kind === 'radio') {
      if (!(await handle.evaluate(el => el.checked))) await page.mouse.click(spot.x, spot.y)
    } else if (kind === 'file') {
      if (!settings.sample) throw new Error('there is no picture to upload')
      await handle.uploadFile(settings.sample)
      await handle.evaluate(el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })) })
    } else {
      await page.mouse.click(spot.x, spot.y)
      await handle.evaluate(el => { el.focus(); if (typeof el.select === 'function') el.select() })    // what was there is replaced
      await page.keyboard.press('Backspace')
      await page.keyboard.type(String(value ?? ''), { delay: 14 })
    }
    await push()
    await pace()
    return { state: await state() }
  },
  /** A key a person presses, for what is open to be closed (Escape closes a dialog). */
  async key({ key }) {
    await page.keyboard.press(String(key))
    await sleep(250)
    await push()
    return { state: await state() }
  },
  async screenshot({ path: target }) {
    fs.mkdirSync(path.dirname(target), { recursive: true })
    await page.screenshot({ path: target, type: 'jpeg', quality: 72, captureBeyondViewport: false })
    return { path: target }
  },
  async errors() { const found = errors; errors = []; return { errors: [...new Set(found)].slice(0, 6) } },
  async close() {
    try { if (cdp) await cdp.send('Page.stopScreencast') } catch { /* closing anyway */ }
    try { if (browser) await browser.close() } catch { /* closing anyway */ }
    browser = context = page = cdp = null
    return {}
  },
}

const lines = readline.createInterface({ input: process.stdin })
let chain = Promise.resolve()      // one command at a time, in order
lines.on('line', line => {
  chain = chain.then(async () => {
    let message
    try { message = JSON.parse(line) } catch { return }
    try {
      const answer = await handlers[message.cmd](message)
      out({ id: message.id, ok: true, ...answer })
      if (message.cmd === 'close') process.exit(0)
    } catch (error) {
      out({ id: message.id, ok: false, error: String(error && error.message || error).slice(0, 400) })
    }
  })
})
lines.on('close', async () => { try { if (browser) await browser.close() } catch { /* gone */ } process.exit(0) })
