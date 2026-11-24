import { elementSelector } from './picker-move'
import { elementInfo, frameDoc } from './picker'
import { pictureSvg, placeholderPicture, PICTURE_LAYER_STYLE } from './picture-editor'

export const SHAPE_TOOLS = ['rectangle', 'ellipse', 'textbox', 'picture']

const CONTAINERS = 'section, article, main, aside, nav, header, footer, [role="region"], div'

/** Draw a temporary grayscale element in a wireframe. */
export function attachShapeTool(frame, shape, canEdit, onDraft) {
  const doc = frameDoc(frame)
  if (!doc) return undefined
  const win = doc.defaultView
  const studio = frame.ownerDocument
  const drawingPicture = shape === 'picture'
  const overlay = doc.createElement('div')
  overlay.setAttribute('aria-hidden', 'true')
  overlay.className = '__af_shape_preview'
  Object.assign(overlay.style, {
    position: 'fixed', zIndex: '2147483645', pointerEvents: 'none', boxSizing: 'border-box',
    border: drawingPicture ? '0' : '1px solid #525252', background: drawingPicture ? 'transparent' : '#e5e5e5',
    color: '#171717', overflow: 'hidden',
    font: '14px/1.4 system-ui, sans-serif', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere',
    borderRadius: shape === 'ellipse' ? '50%' : '0', padding: shape === 'textbox' ? '8px' : '0',
  })
  const cursor = doc.createElement('style')
  cursor.textContent = `
    html,html *{cursor:crosshair!important}
    html .__af_shape_preview{cursor:grab!important}
    html.__af_shape_moving,html.__af_shape_moving *{cursor:grabbing!important}
  `
  doc.head.append(cursor)

  let drag = null
  let draft = null
  let text = 'Text'
  let mask = 'rectangle'
  let picture = null
  const fitMask = bounds => {
    if (!drawingPicture || !['square', 'circle'].includes(mask)) return bounds
    const side = Math.min(bounds.w, bounds.h)
    return { ...bounds, w: side, h: side }
  }
  const url = win.location.href
  const valid = () => Boolean(draft && !drag && doc === frameDoc(frame) && url === win.location.href)
  const draw = bounds => {
    Object.assign(overlay.style, { left: bounds.x - win.scrollX + 'px', top: bounds.y - win.scrollY + 'px',
      width: bounds.w + 'px', height: bounds.h + 'px' })
    if (shape === 'textbox') overlay.textContent = text
    if (drawingPicture) overlay.innerHTML = pictureSvg({ ...picture, ...bounds, shape: mask }, '', 'af-placement-')
    if (!overlay.isConnected) doc.documentElement.append(overlay)
  }
  const release = () => {
    if (!drag) return
    const { anchor, pointer } = drag
    drag = null
    if (anchor.hasPointerCapture(pointer)) anchor.releasePointerCapture(pointer)
    doc.documentElement.classList.remove('__af_shape_moving')
    overlay.style.pointerEvents = draft ? 'auto' : 'none'
  }
  const interrupt = () => {
    if (!drag) return
    release()
    if (draft) draw(draft.bounds)
    else overlay.remove()
  }
  const cancel = () => {
    release()
    overlay.remove()
    if (!draft) return
    draft = null
    text = 'Text'
    mask = 'rectangle'
    picture = null
    onDraft(null)
  }
  const publish = () => {
    overlay.style.pointerEvents = 'auto'
    draw(draft.bounds)
    if (drawingPicture) {
      const layer = doc.querySelector('[data-af-picture-layer]')
      const measuring = layer || doc.createElement('div')
      if (!layer) {
        measuring.style.cssText = PICTURE_LAYER_STYLE
        doc.body.append(measuring)
      }
      const origin = measuring.getBoundingClientRect()
      if (!layer) measuring.remove()
      const bounds = { ...draft.bounds, x: Math.max(0, draft.bounds.x - origin.x - win.scrollX),
        y: Math.max(0, draft.bounds.y - origin.y - win.scrollY) }
      onDraft({ operation: 'picture', details: { ...picture, ...bounds, shape: mask }, cancel, valid,
        setShape: value => { mask = value; draft.bounds = fitMask(draft.bounds); publish() } })
      return
    }
    onDraft({ operation: 'insert', details: { ...draft, text: shape === 'textbox' ? text : '' }, cancel, valid,
      setText: shape === 'textbox' ? value => { text = value; if (draft) publish() } : undefined })
  }
  const pointAt = event => ({
    x: Math.round(event.clientX + win.scrollX), y: Math.round(event.clientY + win.scrollY),
  })
  const boundsAt = (defaultSize = false) => {
    if (drag.kind === 'move') return drag.bounds
    const { start, end } = drag
    const w = Math.abs(end.x - start.x)
    const h = Math.abs(end.y - start.y)
    const clickSize = w < 5 && h < 5 && defaultSize
    return fitMask({ x: Math.min(start.x, end.x), y: Math.min(start.y, end.y),
      w: clickSize ? 144 : Math.max(8, w), h: clickSize ? (shape === 'textbox' ? 38 : 80) : Math.max(8, h) })
  }
  const pickTarget = bounds => {
    const x = Math.min(win.innerWidth - 1, Math.max(0, bounds.x - win.scrollX + Math.min(4, bounds.w / 2)))
    const y = Math.min(win.innerHeight - 1, Math.max(0, bounds.y - win.scrollY + Math.min(4, bounds.h / 2)))
    const hit = doc.elementsFromPoint(x, y).find(node => node !== overlay)
    const target = hit?.closest(CONTAINERS) || doc.body
    const { tag, text: label, rect, outerHTML, scroll, viewport } = elementInfo(frame, target)
    return { target: { selector: elementSelector(target), tag, text: label, rect, outerHTML }, scroll, viewport }
  }
  const down = event => {
    if (!canEdit() || !event.isPrimary || event.button !== 0) return
    event.preventDefault()
    if (drawingPicture && !picture) picture = placeholderPicture({ w: 1, h: 1 }, mask)
    const point = pointAt(event)
    const reposition = Boolean(draft && event.target === overlay)
    drag = { pointer: event.pointerId, anchor: event.target, kind: reposition ? 'move' : 'draw',
      point, start: point, end: point, moving: false }
    if (reposition) {
      drag.bounds = { ...draft.bounds }
      drag.offset = { x: point.x - draft.bounds.x, y: point.y - draft.bounds.y }
      doc.documentElement.classList.add('__af_shape_moving')
    }
    overlay.style.pointerEvents = 'none'
    drag.anchor.setPointerCapture(drag.pointer)
  }
  const advance = event => {
    const point = pointAt(event)
    if (drag.kind === 'move') {
      drag.bounds.x = Math.max(0, point.x - drag.offset.x)
      drag.bounds.y = Math.max(0, point.y - drag.offset.y)
    } else {
      const dx = point.x - drag.point.x
      const dy = point.y - drag.point.y
      drag.end = { x: drag.end.x + dx, y: drag.end.y + dy }
      if (drag.moving) drag.start = { x: drag.start.x + dx, y: drag.start.y + dy }
    }
    drag.point = point
  }
  const move = event => {
    if (event.pointerId !== drag?.pointer) return
    advance(event)
    draw(boundsAt())
  }
  const up = event => {
    if (event.pointerId !== drag?.pointer) return
    if (!canEdit() || url !== win.location.href) { interrupt(); return }
    advance(event)
    const bounds = boundsAt(true)
    draft = { shape, bounds, ...(drawingPicture ? {} : pickTarget(bounds)) }
    release()
    publish()
  }
  const click = event => { event.preventDefault(); event.stopImmediatePropagation() }
  const key = event => {
    if (event.key === 'Escape' && event.type === 'keydown') { cancel(); return }
    if (drag?.kind !== 'draw' || event.code !== 'Space') return
    event.preventDefault()
    drag.moving = event.type === 'keydown'
    doc.documentElement.classList.toggle('__af_shape_moving', drag.moving)
  }
  const scroll = () => { if (draft && !drag) draw(draft.bounds) }
  const listeners = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: interrupt,
    lostpointercapture: interrupt, click, keydown: key, keyup: key, scroll }
  for (const [name, listener] of Object.entries(listeners)) doc.addEventListener(name, listener, true)
  studio.addEventListener('keydown', key, true)
  studio.addEventListener('keyup', key, true)
  win.addEventListener('blur', interrupt)
  win.addEventListener('hashchange', cancel, true)
  return () => {
    cancel()
    cursor.remove()
    for (const [name, listener] of Object.entries(listeners)) doc.removeEventListener(name, listener, true)
    studio.removeEventListener('keydown', key, true)
    studio.removeEventListener('keyup', key, true)
    win.removeEventListener('blur', interrupt)
    win.removeEventListener('hashchange', cancel, true)
  }
}
