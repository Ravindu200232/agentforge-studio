// Streams what a test's browser is showing to the AgentForge Studio, which displays it full-size in
// its preview while the test runs: the page, the pointer, the element being clicked or typed into.
//
// It only WATCHES. It never touches what the test does or how it ends: every failure in here is
// swallowed, nothing here awaits anything for long, and without AGENTFORGE_LIVE_URL or
// AGENTFORGE_LIVE_DIR (set only by the Studio) it does nothing at all, so `npm run qa:*` is the
// same run everywhere else.
//
// The Studio's desktop app listens on no port: it names a folder instead, and each message is
// dropped there as a file it reads in order.
//
// Only the first worker streams: three browsers fighting over one picture is unwatchable, and
// the others run as fast as ever. Chromium only (the screencast is a DevTools feature).
import fs from 'node:fs'
import path from 'node:path'

const target = process.env.AGENTFORGE_LIVE_URL || ''
const folder = process.env.AGENTFORGE_LIVE_DIR || ''
const FRAME_MS = 100      // at most ten pictures a second
const CURSOR_MS = 60      // pointer updates are tiny; at most sixteen a second

export const isLive = Boolean(target || folder)

let dropped = 0
let watching = { at: 0, answer: {} }

/** One message into the Studio's folder: written aside, then renamed, so it is never read half-written. */
function drop(body) {
  try {
    const name = `${String(Date.now()).padStart(15, '0')}-${String(dropped++).padStart(7, '0')}`
    const aside = path.join(folder, `${name}.part`)
    fs.writeFileSync(aside, JSON.stringify(body))
    fs.renameSync(aside, path.join(folder, `${name}.json`))
  } catch { /* nobody is watching the folder */ }
  // The Studio says whether anyone is looking in a file of its own, read at most once a second.
  if (Date.now() - watching.at > 1000) {
    try { watching = { at: Date.now(), answer: JSON.parse(fs.readFileSync(path.join(folder, 'watching.json'), 'utf8')) } }
    catch { watching = { at: Date.now(), answer: {} } }
  }
  return Promise.resolve(watching.answer)
}

/** Send one message to the Studio. Never throws and never waits long: a test must not depend on a viewer. */
export function post(body, timeout = 2000) {
  if (folder && !target) return drop(body)
  if (!target) return Promise.resolve()
  try {
    return fetch(target, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeout),
    }).then(response => response.json()).catch(() => {})
  } catch {
    return Promise.resolve()
  }
}

// Nobody has the Studio open (or it is not reachable): stream nothing, and stop asking for a while.
let unwatchedUntil = 0
async function somebodyIsWatching() {
  if (Date.now() < unwatchedUntil) return false
  const answer = await post({ kind: 'hello' }, 600)
  if (answer && answer.watching === false) {
    unwatchedUntil = Date.now() + 30_000
    return false
  }
  return Boolean(answer)   // no answer: not reachable, so nothing to stream to
}

/** Runs in every page of the test's browser: reports where the pointer is and what it does. */
function watchPointer() {
  const report = window.__agentforgeLive
  if (typeof report !== 'function' || window.__agentforgeLiveOn) return
  window.__agentforgeLiveOn = true
  let last = 0
  const paper = () => {
    try {
      let colour = getComputedStyle(document.body).backgroundColor
      if (!colour || colour === 'rgba(0, 0, 0, 0)') colour = getComputedStyle(document.documentElement).backgroundColor
      return colour
    } catch { return '' }
  }
  const send = (action, element, x, y) => {
    const now = Date.now()
    if (action === 'move' && now - last < 40) return
    last = now
    let box = null
    try {
      const rect = action !== 'move' && element && element.getBoundingClientRect ? element.getBoundingClientRect() : null
      if (rect && rect.width && rect.height) box = { x: rect.left, y: rect.top, width: rect.width, height: rect.height }
    } catch { /* no box */ }
    report({ action, x, y, box, bg: action === 'move' ? '' : paper() })
  }
  const inside = element => {
    const rect = element.getBoundingClientRect()
    return [rect.left + Math.min(rect.width / 2, 48), rect.top + rect.height / 2]
  }
  addEventListener('mousemove', e => send('move', null, e.clientX, e.clientY), true)
  addEventListener('pointerdown', e => send('click', e.target, e.clientX, e.clientY), true)
  addEventListener('input', e => { try { const [x, y] = inside(e.target); send('type', e.target, x, y) } catch { /* ignore */ } }, true)
  addEventListener('keydown', e => {
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) return   // typed characters are reported as input
    try { const el = document.activeElement || e.target; const [x, y] = inside(el); send('key', el, x, y) } catch { /* ignore */ }
  }, true)
}

/** Begin streaming `page`. Returns the function that stops it (await it before the test ends). */
export async function startLiveView(page, testInfo) {
  const nothing = async () => {}
  if (!isLive || testInfo.parallelIndex !== 0) return nothing
  try {
    if (!(await somebodyIsWatching())) return nothing
    let session
    try {
      session = await page.context().newCDPSession(page)
    } catch {
      return nothing   // not Chromium
    }
    let lastFrame = 0
    let lastCursor = 0
    let sending = null
    let sendingCursor = null
    let stopped = false
    let paper = ''

    // The pointer, from inside the page. Registered before the test navigates anywhere.
    try {
      await page.exposeFunction('__agentforgeLive', point => {
        if (stopped || !point) return
        if (point.bg) paper = point.bg
        const now = Date.now()
        if (sendingCursor || (point.action === 'move' && now - lastCursor < CURSOR_MS)) return
        lastCursor = now
        sendingCursor = post({ kind: 'cursor', cursor: point, bg: paper }).finally(() => { sendingCursor = null })
      })
      await page.addInitScript(watchPointer)
    } catch { /* watching the pointer is optional: the picture still streams */ }

    session.on('Page.screencastFrame', ({ data, metadata, sessionId }) => {
      session.send('Page.screencastFrameAck', { sessionId }).catch(() => {})
      const now = Date.now()
      if (stopped || sending || now - lastFrame < FRAME_MS) return
      lastFrame = now
      sending = post({
        kind: 'frame',
        frame: `data:image/jpeg;base64,${data}`,
        url: page.url(),
        title: testInfo.title,
        bg: paper,
        viewport: { width: metadata.deviceWidth, height: metadata.deviceHeight },
      }).finally(() => { sending = null })
    })
    try {
      await session.send('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: 1280, everyNthFrame: 3 })
    } catch {
      return nothing
    }
    return async () => {
      stopped = true
      try {
        await session.send('Page.stopScreencast').catch(() => {})
        await sending
        await sendingCursor
        await session.detach().catch(() => {})
      } catch { /* the test is over either way */ }
    }
  } catch {
    return nothing
  }
}
