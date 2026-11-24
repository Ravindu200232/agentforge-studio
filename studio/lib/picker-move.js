/** A stable hint for repeated UI such as two cards with the same label. */
export function elementSelector(element) {
  const parts = []
  for (let node = element; node; node = node.parentElement) {
    const escape = node.ownerDocument.defaultView.CSS.escape
    if (node.id) {
      const id = '#' + escape(node.id)
      if (node.ownerDocument.querySelectorAll(id).length === 1) {
        parts.unshift(id)
        break
      }
    }
    let index = 1
    for (let peer = node.previousElementSibling; peer; peer = peer.previousElementSibling) {
      if (peer.localName === node.localName) index++
    }
    parts.unshift(escape(node.localName) + ':nth-of-type(' + index + ')')
  }
  return parts.join(' > ')
}

function pickable(element) {
  return element?.nodeType === 1 && !element.matches('html, body, #af-page, iframe')
}

export function pickerElement(element) {
  const control = element?.closest?.('button, a, label, select, textarea, svg')
  const source = control?.closest('button, a, label') || control || element
  return pickable(source) ? source : null
}

function destination(doc, source, x, y) {
  const hit = doc.elementFromPoint(x, y)
  if (!hit) return null
  if (source.contains(hit)) {
    const parent = source.parentElement
    return { target: parent, placement: 'inside', line: parent.getBoundingClientRect() }
  }
  let peer = hit
  while (peer.parentElement && peer.parentElement !== source.parentElement) peer = peer.parentElement
  const target = hit.id === 'af-page' ? hit : peer.parentElement === source.parentElement ? peer : pickerElement(hit)
  if (!target) return null
  const box = target.getBoundingClientRect()
  const win = doc.defaultView
  const style = win.getComputedStyle(target)
  // Blank space on a layout container is a drop inside it.
  if (target === hit && target.parentElement !== source.parentElement
      && !target.matches('button, a, label, select, textarea, svg, img, input')
      && (target.contains(source) || target.children.length || target.matches('main, section, article, div, ul, ol'))) {
    const nearEdge = Math.min(y - box.top, box.bottom - y) < Math.min(18, box.height / 4)
    if (!nearEdge || target.id === 'af-page') return { target, placement: 'inside', line: box }
  }
  if (target.contains(source)) return null

  const parent = win.getComputedStyle(target.parentElement)
  const horizontal = parent.display.includes('flex') && parent.flexDirection.startsWith('row')
    || parent.display.includes('grid') && parent.gridTemplateColumns.split(' ').length > 1
    || style.display.startsWith('inline')
  const reverse = horizontal
    ? (parent.direction === 'rtl') !== (parent.flexDirection === 'row-reverse')
    : parent.display.includes('flex') && parent.flexDirection === 'column-reverse'
  const firstHalf = horizontal ? x < box.left + box.width / 2 : y < box.top + box.height / 2
  const placement = firstHalf !== reverse ? 'before' : 'after'
  if ((placement === 'before' && source.nextElementSibling === target)
      || (placement === 'after' && source.previousElementSibling === target)) return null
  const line = horizontal
    ? { x: firstHalf ? box.left : box.right, y: box.top, width: 3, height: box.height }
    : { x: box.left, y: firstHalf ? box.top : box.bottom, width: box.width, height: 3 }
  return { target, placement, line }
}

/** Install pointer drag on the selection tool only. Return a click suppressor and cleanup. */
export function attachPickerMove(doc, { canMove, onMove, onStart }) {
  const win = doc.defaultView
  const studio = win.frameElement?.ownerDocument
  let drag = null
  let dragged = false
  const marker = doc.createElement('div')
  const ghost = doc.createElement('div')
  for (const item of [marker, ghost]) {
    item.setAttribute('aria-hidden', 'true')
    item.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;box-sizing:border-box;border-radius:3px'
  }
  ghost.style.border = '2px dashed #5b7cf7'
  ghost.style.background = 'rgba(91,124,247,.15)'

  const draw = (node, box) => {
    Object.assign(node.style, {
      left: box.x + 'px', top: box.y + 'px', width: box.width + 'px', height: box.height + 'px',
    })
    if (!node.isConnected) doc.documentElement.appendChild(node)
  }

  const clear = () => {
    if (!drag) return
    const { pointer, handle } = drag
    drag = null
    if (handle.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer)
    marker.remove()
    ghost.remove()
    doc.documentElement.classList.remove('__af_moving')
  }

  const down = event => {
    if (!event.isPrimary || event.button !== 0) return
    dragged = false
    const source = pickerElement(event.target)
    if (!source || !canMove(source)) return
    drag = { source, handle: event.target, pointer: event.pointerId, route: win.location.href,
      x: event.clientX, y: event.clientY, box: source.getBoundingClientRect() }
    event.preventDefault()
    drag.handle.setPointerCapture(drag.pointer)
  }

  const move = event => {
    if (event.pointerId !== drag?.pointer) return
    if (!drag.source.isConnected || drag.route !== win.location.href) { clear(); return }
    const dx = event.clientX - drag.x
    const dy = event.clientY - drag.y
    if (!dragged) {
      if (Math.hypot(dx, dy) < 6) return
      dragged = true
      onStart?.()
    }
    event.preventDefault()
    doc.documentElement.classList.add('__af_moving')
    draw(ghost, { x: drag.box.x + dx, y: drag.box.y + dy, width: drag.box.width, height: drag.box.height })
    const drop = destination(doc, drag.source, event.clientX, event.clientY)
    if (!drop) { marker.remove(); return }
    marker.style.border = drop.placement === 'inside' ? '2px solid #5b7cf7' : ''
    marker.style.background = drop.placement === 'inside' ? 'transparent' : '#5b7cf7'
    draw(marker, drop.line)
  }

  const up = event => {
    if (event.pointerId !== drag?.pointer) return
    const { source, route, box, x, y } = drag
    const drop = dragged && source.isConnected && route === win.location.href && canMove(source)
      ? destination(doc, source, event.clientX, event.clientY) : null
    clear()
    if (!drop) return
    const point = { x: Math.round(event.clientX), y: Math.round(event.clientY) }
    onMove({
      placement: drop.placement, point,
      origin: { x: Math.round(box.x + event.clientX - x), y: Math.round(box.y + event.clientY - y) },
    }, source, drop.target)
  }

  const key = event => { if (event.key === 'Escape') clear() }
  const listeners = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: clear,
    lostpointercapture: clear, keydown: key }
  for (const [event, listener] of Object.entries(listeners)) doc.addEventListener(event, listener, true)
  studio?.addEventListener('keydown', key, true)
  win.addEventListener('blur', clear)
  return {
    suppressClick: () => {
      const suppress = dragged
      dragged = false
      return suppress
    },
    detach: () => {
      clear()
      for (const [event, listener] of Object.entries(listeners)) doc.removeEventListener(event, listener, true)
      studio?.removeEventListener('keydown', key, true)
      win.removeEventListener('blur', clear)
    },
  }
}
