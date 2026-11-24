/** Keep a single reversible edit in the preview frame until Studio saves or cancels it. */
export function previewLayout(doc, describe, onDraft) {
  const win = doc.defaultView
  const properties = ['transform', 'display', 'box-sizing', 'width', 'min-width', 'max-width',
    'height', 'min-height', 'max-height']
  let draft = null

  const valid = () => Boolean(draft?.element.isConnected && draft.parent.isConnected && draft.url === win.location.href)

  function restore(entry) {
    const { element, parent, next, styles, hadStyle, inserted } = entry
    if (inserted && element.isConnected && parent.isConnected) {
      const anchor = next?.parentNode === parent ? next : null
      if (element.parentNode !== parent || element.nextSibling !== anchor) parent.insertBefore(element, anchor)
    }
    for (const [key, value, priority] of styles) {
      if (value) element.style.setProperty(key, value, priority)
      else element.style.removeProperty(key)
    }
    if (!hadStyle && !element.getAttribute('style')) element.removeAttribute('style')
  }

  function cancel() {
    if (!draft) return
    const entry = draft
    draft = null
    restore(entry)
    onDraft(null)
  }

  function record(element) {
    if (draft) return draft
    draft = {
      element, parent: element.parentNode, next: element.nextSibling, url: win.location.href,
      source: describe(element), hadStyle: element.hasAttribute('style'), inserted: false,
      styles: properties.map(key => [key, element.style.getPropertyValue(key), element.style.getPropertyPriority(key)]),
      widthEdge: '', heightEdge: '',
    }
    return draft
  }

  function paint(entry) {
    const { element, move, target, resize } = entry
    entry.inserted = false
    if (move && target?.isConnected) {
      if (move.placement === 'before') target.before(element)
      else if (move.placement === 'after') target.after(element)
      else if (target !== entry.parent && !element.contains(target)) target.append(element)
      entry.inserted = move.placement !== 'inside' || target !== entry.parent
    }
    const set = (key, value) => element.style.setProperty(key, value, 'important')
    let dx = 0, dy = 0
    if (resize) {
      set('box-sizing', 'border-box')
      if (win.getComputedStyle(element).display === 'inline' && !element.matches('img,svg,input,select,textarea,canvas,video')) {
        set('display', 'inline-block')
      }
      if (entry.widthEdge) {
        set('width', resize.bounds.w + 'px')
        set('min-width', resize.bounds.w + 'px')
        set('max-width', resize.bounds.w + 'px')
      }
      if (entry.heightEdge) {
        set('height', resize.bounds.h + 'px')
        set('min-height', resize.bounds.h + 'px')
        set('max-height', resize.bounds.h + 'px')
      }
      if (entry.widthEdge === 'w') dx = entry.source.rect.w - resize.bounds.w
      if (entry.heightEdge === 'n') dy = entry.source.rect.h - resize.bounds.h
    }
    if (move?.placement === 'inside') {
      const box = element.getBoundingClientRect()
      dx = move.origin.x + entry.scroll.x - win.scrollX - box.x
      dy = move.origin.y + entry.scroll.y - win.scrollY - box.y
    }
    if (dx || dy) {
      const transform = win.getComputedStyle(element).transform
      set('transform', `translate(${dx}px, ${dy}px)${transform === 'none' ? '' : ' ' + transform}`)
    }
  }

  function publish(entry) {
    if (!entry.move && !entry.resize) { cancel(); return }
    paint(entry)
    const { move, resize } = entry
    const operation = move && resize ? 'layout' : move ? 'move' : 'resize'
    onDraft({ operation, details: operation === 'layout' ? { move, resize } : move || resize, cancel, valid })
  }

  function move(details, element, target) {
    const entry = record(element)
    restore(entry)
    entry.target = target
    entry.scroll = { x: win.scrollX, y: win.scrollY }
    const box = element.getBoundingClientRect()
    const sameOrder = details.placement === 'before' && element.nextElementSibling === target
      || details.placement === 'after' && element.previousElementSibling === target
    const samePosition = details.placement === 'inside' && target === entry.parent
      && Math.abs(details.origin.x - box.x) < 2 && Math.abs(details.origin.y - box.y) < 2 && !entry.resize
    entry.move = sameOrder || samePosition ? null : { ...details, source: entry.source, target: describe(target) }
    publish(entry)
  }

  function resize(details, element) {
    const entry = record(element)
    restore(entry)
    const { w, h } = entry.source.rect
    const bounds = details.bounds
    entry.widthEdge = bounds.w === Math.round(w) ? '' : details.handle.match(/[ew]/)?.[0] || entry.widthEdge
    entry.heightEdge = bounds.h === Math.round(h) ? '' : details.handle.match(/[ns]/)?.[0] || entry.heightEdge
    entry.resize = entry.widthEdge || entry.heightEdge
      ? { ...details, source: entry.source, handle: entry.heightEdge + entry.widthEdge } : null
    if (entry.move?.placement === 'inside') {
      entry.scroll = { x: win.scrollX, y: win.scrollY }
      entry.move.origin = { x: bounds.x, y: bounds.y }
    }
    publish(entry)
  }

  return { move, resize, cancel, permits: element => !draft || draft.element === element }
}
