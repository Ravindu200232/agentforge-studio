const HANDLES = {
  nw: [0, 0], n: [50, 0], ne: [100, 0],
  w: [0, 50], e: [100, 50],
  sw: [0, 100], s: [50, 100], se: [100, 100],
}

export const RESIZE_CSS = `
  .__af_resize_box{position:fixed;z-index:2147483646;pointer-events:none;box-sizing:border-box;outline:1px solid #5b7cf7}
  .__af_resize_handle{position:absolute;box-sizing:border-box;width:11px;height:11px;transform:translate(-50%,-50%);border:2px solid #5b7cf7;border-radius:2px;background:#fff;pointer-events:auto;touch-action:none}
  .__af_resize_size{position:absolute;right:0;padding:2px 6px;border-radius:4px;background:#253d99;color:#fff;font:600 11px/16px system-ui, sans-serif;white-space:nowrap}
`

function roundBox(x, y, w, h) {
  return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) }
}

function draggedBounds(drag, event) {
  const { edge, box } = drag
  const dx = event.clientX - drag.x
  const dy = event.clientY - drag.y
  const minW = Math.min(8, box.width), minH = Math.min(8, box.height)
  const left = edge.includes('w') ? Math.min(box.left + dx, box.right - minW) : box.left
  const right = edge.includes('e') ? Math.max(box.right + dx, box.left + minW) : box.right
  const top = edge.includes('n') ? Math.min(box.top + dy, box.bottom - minH) : box.top
  const bottom = edge.includes('s') ? Math.max(box.bottom + dy, box.top + minH) : box.bottom
  return roundBox(left, top, right - left, bottom - top)
}

/** The preview outline lives outside the page body and never becomes part of the authored source. */
export function attachPickerResize(doc, { canResize, onResize }) {
  const win = doc.defaultView
  const studio = win.frameElement?.ownerDocument
  const overlay = doc.createElement('div')
  overlay.className = '__af_resize_box'
  overlay.setAttribute('aria-hidden', 'true')
  const size = doc.createElement('span')
  size.className = '__af_resize_size'
  overlay.append(size)
  for (const [edge, [x, y]] of Object.entries(HANDLES)) {
    const handle = doc.createElement('div')
    handle.className = '__af_resize_handle'
    handle.dataset.edge = edge
    Object.assign(handle.style, { left: x + '%', top: y + '%', cursor: edge + '-resize' })
    overlay.append(handle)
  }

  let selected = null
  let drag = null
  let handleClicked = false
  const draw = box => {
    Object.assign(overlay.style, { left: box.x + 'px', top: box.y + 'px', width: box.w + 'px', height: box.h + 'px' })
    size.style.top = box.y >= 24 ? '-24px' : '8px'
    size.textContent = box.w + ' × ' + box.h
    if (!overlay.isConnected) doc.documentElement.append(overlay)
  }

  const refresh = () => {
    if (drag) return
    const box = selected?.isConnected && selected.getBoundingClientRect()
    if (box && box.width >= 1 && box.height >= 1) draw(roundBox(box.x, box.y, box.width, box.height))
    else overlay.remove()
  }
  const observer = new win.ResizeObserver(refresh)

  const cancelDrag = () => {
    if (!drag) return
    const { handle, pointer } = drag
    drag = null
    if (handle.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer)
    refresh()
  }

  const select = element => {
    cancelDrag()
    observer.disconnect()
    selected = element
    if (element) observer.observe(element)
    refresh()
  }

  const down = event => {
    if (!event.isPrimary || event.button !== 0) return
    handleClicked = overlay.contains(event.target)
    if (!handleClicked) return
    event.preventDefault()
    event.stopImmediatePropagation()
    const edge = event.target.dataset.edge
    if (!edge || !selected?.isConnected || !canResize(selected)) return
    drag = { handle: event.target, edge, pointer: event.pointerId, route: win.location.href,
      box: selected.getBoundingClientRect(), x: event.clientX, y: event.clientY }
    drag.handle.setPointerCapture(drag.pointer)
  }

  const move = event => {
    if (event.pointerId !== drag?.pointer) return
    event.preventDefault()
    if (!selected.isConnected || drag.route !== win.location.href) { select(null); return }
    draw(draggedBounds(drag, event))
  }

  const up = event => {
    if (event.pointerId !== drag?.pointer) return
    const { box, edge, route } = drag
    const before = roundBox(box.x, box.y, box.width, box.height)
    const bounds = draggedBounds(drag, event)
    const changed = bounds.w !== before.w || bounds.h !== before.h
    cancelDrag()
    if (changed && selected.isConnected && route === win.location.href && canResize(selected)) {
      onResize({ handle: edge, bounds }, selected)
      refresh()
    }
  }

  const key = event => { if (event.key === 'Escape') select(null) }
  const navigation = () => select(null)
  const listeners = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: cancelDrag,
    lostpointercapture: cancelDrag, keydown: key, scroll: refresh }
  for (const [event, listener] of Object.entries(listeners)) doc.addEventListener(event, listener, true)
  studio?.addEventListener('keydown', key, true)
  win.addEventListener('hashchange', navigation)
  win.addEventListener('resize', refresh)
  win.addEventListener('blur', cancelDrag)
  return {
    select,
    suppressClick: event => handleClicked || overlay.contains(event.target),
    detach: () => {
      select(null)
      for (const [event, listener] of Object.entries(listeners)) doc.removeEventListener(event, listener, true)
      studio?.removeEventListener('keydown', key, true)
      win.removeEventListener('hashchange', navigation)
      win.removeEventListener('resize', refresh)
      win.removeEventListener('blur', cancelDrag)
    },
  }
}
