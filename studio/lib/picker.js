

const PICK_CSS =
  '.__lc_hi{outline:2px solid #5b7cf7!important;' +
  'outline-offset:-2px;background:rgba(91,124,247,.10)!important;' +
  'cursor:crosshair!important}'

export function frameDoc(frame) {
  try { return frame?.contentDocument || null } catch { return null }
}


// The screen the framed app is on: its address hash (`#/orders`) when it keeps its screens there, else its path.
function appRoute(w) {
  const hash = w.location.hash || ''
  return hash.startsWith('#/') ? hash.slice(1).split('?')[0] : w.location.pathname + w.location.search
}


export function elementInfo(frame, el, vpMode = 'desktop') {
  const w = frame.contentWindow
  const attrs = {}
  for (const k of ['href', 'type', 'placeholder', 'name', 'alt',
                   'aria-label', 'data-testid', 'role']) {
    const v = el.getAttribute && el.getAttribute(k)
    if (v) attrs[k] = v
  }
  const chain = []
  let par = el.parentElement
  for (let i = 0; i < 6 && par; i++, par = par.parentElement) {
    chain.push({
      tag: par.tagName.toLowerCase(), id: par.id || '',
      className: par.getAttribute('class') || '',
      text: (par.innerText || '').trim().split('\n')[0].slice(0, 80),
    })
  }
  const r = el.getBoundingClientRect()
  let bg = ''
  try {
    const m = /url\(["']?([^"')]+)/.exec(w.getComputedStyle(el).backgroundImage || '')
    if (m) bg = m[1]
  } catch {  }
  const src = (el.getAttribute && el.getAttribute('src')) || ''
  return {
    tag: el.tagName.toLowerCase(), id: el.id || '',
    src, bg,
    isImage: el.tagName.toLowerCase() === 'img' || !!bg,
    classes: Array.from(el.classList || []),
    className: el.getAttribute('class') || '',
    text: (el.innerText || '').trim().slice(0, 160),
    attrs, chain,
    rect: { x: r.x, y: r.y, w: r.width, h: r.height },
    route: appRoute(w),
    scroll: { x: w.scrollX, y: w.scrollY },

    viewport: {
      w: frame.clientWidth || w.innerWidth || 1280,
      h: frame.clientHeight || w.innerHeight || 800,
      mode: vpMode,
    },
    outerHTML: (el.outerHTML || '').slice(0, 1200),
  }
}


export function pickedFrom(frame, el, vpMode) {
  const info = elementInfo(frame, el, vpMode)
  const kids = [...el.children].filter(k => k.getBoundingClientRect().height > 0)
  if (kids.length > 1) {
    info.section = {
      start: elementInfo(frame, kids[0], vpMode),
      end: elementInfo(frame, kids[kids.length - 1], vpMode),
    }
  }
  return info
}


// A picture has no text to name it by, so it is named by its alt text or its
// file. Everything else reads better as the tag and the words in it.
export function pickLabel(info) {
  if (!info) return ''
  if (info.isImage) {
    const name = info.attrs?.alt
      || (info.src || info.bg || 'image').split('/').pop()
    return `<img> ${name.slice(0, 60)}   ${info.route}`
  }
  return `<${info.tag}>${info.text ? ' ' + info.text.slice(0, 60) : ''}   ${info.route}`
}


export function attachPicker(frame, onPick) {
  const d = frameDoc(frame)
  if (!d) return null
  if (!d.getElementById('__lc_pick_style')) {
    const st = d.createElement('style')
    st.id = '__lc_pick_style'
    st.textContent = PICK_CSS
    d.head.appendChild(st)
  }
  const hover = (e) => e.target.classList && e.target.classList.add('__lc_hi')
  const leave = (e) => e.target.classList && e.target.classList.remove('__lc_hi')
  const click = (e) => {
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation()
    onPick(e.target)
  }
  d.addEventListener('mouseover', hover, true)
  d.addEventListener('mouseout', leave, true)
  d.addEventListener('click', click, true)

  return () => {
    const doc = frameDoc(frame)
    if (!doc) return
    doc.removeEventListener('mouseover', hover, true)
    doc.removeEventListener('mouseout', leave, true)
    doc.removeEventListener('click', click, true)
    doc.querySelectorAll('.__lc_hi').forEach(e => e.classList.remove('__lc_hi'))
    doc.getElementById('__lc_pick_style')?.remove()
  }
}


/** The words an element carries itself: a leaf's whole text, or the first piece of text in a mixed element. */
export function ownText(element) {
  if (!element) return ''
  if (!element.children || element.children.length === 0) return String(element.textContent || '').replace(/\s+/g, ' ').trim()
  for (const node of element.childNodes || []) {
    if (node.nodeType === 3 && String(node.textContent || '').trim()) return String(node.textContent).replace(/\s+/g, ' ').trim()
  }
  return ''
}


/**
 * What a drawing is about: the things on the page it was drawn around or over. A stroke is a list of points in page coordinates.
 * The things that mean something (words, a control, a picture) inside the box the stroke makes, or under its line, are found; the
 * ones the drawing covers most come first. They are described like a picked element, so that a model that only reads words can be
 * told what was marked.
 */
export function elementsUnderStrokes(frame, strokes, vpMode = 'desktop', most = 4) {
  const doc = frameDoc(frame)
  const win = frame?.contentWindow
  if (!doc || !win) return []
  const meaningful = (el) => {
    for (let node = el; node && node !== doc.body && node !== doc.documentElement; node = node.parentElement) {
      const tag = node.tagName.toLowerCase()
      if (['a', 'button', 'input', 'select', 'textarea', 'img', 'svg', 'h1', 'h2', 'h3', 'h4', 'label', 'li', 'td', 'th', 'p'].includes(tag)
          || node.getAttribute('role') || (node.children.length === 0 && (node.textContent || '').trim())) return node
    }
    return null
  }
  const scored = new Map()
  for (const stroke of strokes || []) {
    if (!stroke.length) continue
    const xs = stroke.map(point => point.x - win.scrollX)
    const ys = stroke.map(point => point.y - win.scrollY)
    const box = { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) }
    const area = Math.max(1, (box.right - box.left) * (box.bottom - box.top))
    const points = stroke.filter((_, i) => i % Math.max(1, Math.floor(stroke.length / 12)) === 0).map(point => [point.x - win.scrollX, point.y - win.scrollY])
    for (let row = 0; row <= 5; row++) {
      for (let col = 0; col <= 5; col++) points.push([box.left + (box.right - box.left) * col / 5, box.top + (box.bottom - box.top) * row / 5])
    }
    for (const [x, y] of points) {
      const el = doc.elementFromPoint(x, y)
      const hit = el && meaningful(el)
      if (!hit || scored.has(hit)) continue
      const rect = hit.getBoundingClientRect()
      const across = Math.max(0, Math.min(rect.right, box.right) - Math.max(rect.left, box.left))
        * Math.max(0, Math.min(rect.bottom, box.bottom) - Math.max(rect.top, box.top))
      // How much of the element the drawing covers, and how much of the drawing is the element: a thing that fills the drawing, or
      // that the drawing fills, is what it is about; a page-sized box that only has the drawing somewhere in it is not.
      const size = Math.max(1, rect.width * rect.height)
      if (across / size < 0.3 && across / area < 0.3) continue
      scored.set(hit, across / size + across / area)
    }
  }
  return [...scored.entries()].sort((a, b) => b[1] - a[1]).slice(0, most).map(([el]) => elementInfo(frame, el, vpMode))
}
