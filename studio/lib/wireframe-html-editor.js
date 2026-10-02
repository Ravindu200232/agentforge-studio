/** Direct in-frame DOM WYSIWYG editing for wireframes and prototype pages. */

const STYLE_ID = '__wf_editor_style'
const MARK = 'data-wf-selected'

const CSS = `
  [${MARK}] {
    outline: 2px solid #0D99FF !important;
    outline-offset: 1px !important;
    cursor: grab !important;
  }
  [${MARK}][data-wf-secondary] {
    outline-style: dashed !important;
    outline-color: #7C3AED !important;
  }
  .__wf_hover {
    outline: 1.5px dashed #0D99FF !important;
    outline-offset: 1px !important;
  }
  [contenteditable="true"] {
    outline: 2px solid #16a34a !important;
    cursor: text !important;
  }

  /* Selection overlay */
  #__wf_overlay {
    position: absolute;
    pointer-events: none;
    z-index: 2147483645;
    box-sizing: border-box;
    display: none;
  }

  /* Top tag & move badge bar */
  #__wf_tag_badge {
    position: absolute;
    top: -22px;
    left: 0;
    height: 20px;
    display: flex;
    align-items: center;
    gap: 5px;
    background: #0D99FF;
    color: #ffffff;
    font: 600 10.5px/1 ui-monospace, Menlo, monospace;
    padding: 0 6px;
    border-radius: 4px 4px 0 0;
    pointer-events: auto;
    cursor: grab;
    user-select: none;
    box-shadow: 0 -2px 6px rgba(13, 153, 255, 0.25);
    white-space: nowrap;
  }
  #__wf_tag_badge:active {
    cursor: grabbing;
  }
`

/** Never select the page itself, or the wrappers that hold everything. */
function selectable(node, doc) {
  if (!node || node === doc.documentElement || node === doc.body) return null
  if (node.hasAttribute?.('data-wf-editor-ui')) return null
  if (node.hasAttribute?.('data-wf-flow-slot')) return null
  return node
}

function label(node) {
  if (!node) return ''
  const tag = node.tagName.toLowerCase()
  const cls = String(node.getAttribute('class') || '').split(/\s+/).filter(name => name && !name.startsWith('__wf_'))[0]
  return cls ? `${tag}.${cls}` : tag
}

/**
 * Attach the Figma-style interactive wireframe editor to a loaded frame.
 *
 * `textOnly` keeps just the typing: text is edited where it is clicked and undone with Ctrl+Z, and nothing else
 * (selecting a box, moving, deleting or duplicating it from the keyboard) happens.
 */
export function attachEditor(iframe, { onSelect, onSelection, onDirty, textOnly = false } = {}) {
  let doc
  try {
    doc = iframe.contentDocument
    if (!doc || !doc.body) return null
  } catch {
    return null
  }

  let selected = null
  let selectedNodes = new Set()
  let dirty = false
  const undoStack = []
  let typedFrom = null
  const redoStack = []
  const editLog = []

  function ensureEditorStyle() {
    if (doc.getElementById(STYLE_ID)) return
    const style = doc.createElement('style')
    style.id = STYLE_ID
    style.textContent = CSS
    doc.head.appendChild(style)
  }
  ensureEditorStyle()

  function touched() {
    if (!dirty) { dirty = true; onDirty?.(true) }
  }

  function historyMarkup() {
    const clone = doc.documentElement.cloneNode(true)
    clone.querySelectorAll(`[${MARK}]`).forEach(node => {
      node.removeAttribute(MARK)
      node.removeAttribute('data-wf-tag')
      node.removeAttribute('data-wf-secondary')
      node.classList.remove('__wf_dragging')
    })
    clone.querySelectorAll('.__wf_hover, .__wf_dragging').forEach(node => node.classList.remove('__wf_hover', '__wf_dragging'))
    clone.querySelectorAll('[data-wf-editor-ui]').forEach(node => node.remove())
    clone.querySelector(`#${STYLE_ID}`)?.remove()
    clone.querySelector('body')?.removeAttribute('data-wf-editing')
    return clone.outerHTML
  }

  function snapshot(change = selected ? `Edited <${label(selected)}>` : 'Edited wireframe') {
    undoStack.push(historyMarkup())
    if (undoStack.length > 50) undoStack.shift()
    redoStack.length = 0
    editLog.push(change)
    if (editLog.length > 50) editLog.shift()
  }

  function restore(markup) {
    doc.open(); doc.write(markup); doc.close()
    selected = null
    selectedNodes = new Set()
    ensureEditorStyle()
    onSelect?.('')
  }

  function updateOverlay() {
    let overlay = doc.getElementById('__wf_overlay')
    if (!selected) {
      if (overlay) overlay.style.display = 'none'
      return
    }
    if (!overlay) {
      overlay = doc.createElement('div')
      overlay.id = '__wf_overlay'
      overlay.setAttribute('data-wf-editor-ui', 'true')
      overlay.innerHTML = `
        <div id="__wf_tag_badge" data-wf-editor-ui="true">
          <span id="__wf_tag_name"></span>
          <span id="__wf_tag_dims" style="opacity:0.75;font-size:9.5px;margin-left:4px;"></span>
        </div>
      `
      doc.body.appendChild(overlay)
    }

    overlay.style.display = 'block'
    const r = selected.getBoundingClientRect()
    const scrollX = doc.defaultView?.scrollX || doc.documentElement.scrollLeft || 0
    const scrollY = doc.defaultView?.scrollY || doc.documentElement.scrollTop || 0

    overlay.style.left = `${r.left + scrollX}px`
    overlay.style.top = `${r.top + scrollY}px`
    overlay.style.width = `${r.width}px`
    overlay.style.height = `${r.height}px`

    const tagName = overlay.querySelector('#__wf_tag_name')
    if (tagName) tagName.textContent = label(selected)
    const tagDims = overlay.querySelector('#__wf_tag_dims')
    if (tagDims) {
      const curX = Math.round(parseFloat(selected.style.left) || 0)
      const curY = Math.round(parseFloat(selected.style.top) || 0)
      tagDims.textContent = `${Math.round(r.width)}×${Math.round(r.height)}${curX || curY ? ` (X:${curX} Y:${curY})` : ''}`
    }
  }

  function clearSelection() {
    selectedNodes.forEach(item => {
      item.removeAttribute(MARK)
      item.removeAttribute('data-wf-tag')
      item.removeAttribute('data-wf-secondary')
      item.classList.remove('__wf_dragging')
    })
    selectedNodes.clear()
    selected = null
  }

  function select(node, { additive = false } = {}) {
    const next = selectable(node, doc)
    if (!additive) clearSelection()
    if (next) {
      if (additive && selectedNodes.has(next)) {
        next.removeAttribute(MARK)
        next.removeAttribute('data-wf-tag')
        next.removeAttribute('data-wf-secondary')
        selectedNodes.delete(next)
        if (selected === next) selected = Array.from(selectedNodes).at(-1) || null
      } else {
        if (selected && selectedNodes.has(selected)) {
          selected.removeAttribute('data-wf-tag')
          selected.setAttribute('data-wf-secondary', '')
        }
        selected = next
        selectedNodes.add(next)
        next.setAttribute(MARK, '')
        next.removeAttribute('data-wf-secondary')
        next.setAttribute('data-wf-tag', label(next))
      }
    }
    updateOverlay()
    const details = selected ? {
      label: label(selected),
      tag: selected.tagName.toLowerCase(),
      text: String(selected.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 180),
    } : null
    // Keep the original string callback for existing prototype consumers, while
    // exposing safe selection context for the wireframe AI prompt tool.
    onSelect?.(details?.label || '')
    onSelection?.(details, Array.from(selectedNodes).map(item => ({
      label: label(item),
      tag: item.tagName.toLowerCase(),
      text: String(item.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 180),
    })))
  }

  /**
   * Figma's "ignore auto layout" keeps the surrounding frame stable while the
   * chosen layer moves freely. In HTML an absolute child would normally make all
   * following flex/grid siblings reflow. Keep an invisible, size-locked slot in
   * the old flow position, then make the visible layer absolute over the canvas.
   * This prevents the common wireframe-editor failure where a heading collapses
   * into a skinny column and every card/button below it jumps upward.
   */
  function liftFree(el) {
    const computed = doc.defaultView.getComputedStyle(el)
    const parent = el.parentElement
    if (!parent || el.hasAttribute('data-wf-free')) return
    const elRect = el.getBoundingClientRect()
    if (parent && doc.defaultView.getComputedStyle(parent).position === 'static') {
      parent.style.position = 'relative'
    }
    const anchor = (el.offsetParent || parent || doc.body).getBoundingClientRect()
    const left = Math.round(elRect.left - anchor.left)
    const top = Math.round(elRect.top - anchor.top)

    const slot = doc.createElement('div')
    slot.setAttribute('data-wf-flow-slot', '')
    slot.setAttribute('aria-hidden', 'true')
    slot.style.width = `${Math.round(elRect.width)}px`
    slot.style.height = `${Math.round(elRect.height)}px`
    slot.style.minWidth = `${Math.round(elRect.width)}px`
    slot.style.minHeight = `${Math.round(elRect.height)}px`
    slot.style.maxWidth = `${Math.round(elRect.width)}px`
    slot.style.boxSizing = 'border-box'
    slot.style.flex = `0 0 ${Math.round(elRect.width)}px`
    slot.style.marginTop = computed.marginTop
    slot.style.marginRight = computed.marginRight
    slot.style.marginBottom = computed.marginBottom
    slot.style.marginLeft = computed.marginLeft
    el.before(slot)

    el.setAttribute('data-wf-free', '')
    el.style.position = 'absolute'
    el.style.left = `${left}px`
    el.style.top = `${top}px`
    el.style.width = `${Math.round(elRect.width)}px`
    el.style.height = `${Math.round(elRect.height)}px`
    el.style.boxSizing = 'border-box'
    el.style.flex = '0 0 auto'
    el.style.margin = '0'
    el.style.zIndex = '1'
  }

  let hovered = null
  const onOver = event => {
    if (hovered) hovered.classList.remove('__wf_hover')
    hovered = selectable(event.target, doc)
    if (textOnly && hovered && !ownText(hovered)) hovered = null
    if (hovered && hovered !== selected) {
      hovered.classList.add('__wf_hover')
    }
  }
  const onOut = () => {
    hovered?.classList.remove('__wf_hover')
    hovered = null
  }

  // An element that holds text of its own (a heading, a paragraph, a label, a button's words) is typed into
  // where it is clicked; anything else is selected. Nothing is dragged, moved or resized from here.
  function ownText(node) {
    if (!node || /^(INPUT|TEXTAREA|SELECT|IMG|SVG|VIDEO|CANVAS|IFRAME|TABLE|TBODY|THEAD|TR|UL|OL)$/i.test(node.tagName)) return false
    return Array.from(node.childNodes || []).some(child => child.nodeType === 3 && child.textContent.trim())
  }

  const onMouseDown = event => {
    const target = event.target
    if (target.hasAttribute?.('data-wf-editor-ui')) return
    const editing = doc.body.getAttribute('data-wf-editing') === 'text'
    // Inside the text being typed: let the browser place the caret and select words as usual.
    if (editing && selected && (target === selected || selected.contains(target))) return
    if (editing) api.editText(false)

    if (textOnly) {
      // Only words are edited: a press on text starts typing there, a press anywhere else just stops it.
      select(target)
      if (selected && ownText(selected)) {
        event.stopPropagation()
        api.editText(true)
        return
      }
      select(null)
      event.preventDefault()
      event.stopPropagation()
      return
    }

    if (event.ctrlKey || event.metaKey) {
      event.preventDefault()
      event.stopPropagation()
      select(target, { additive: true })
      return
    }

    select(target)
    if (selected && ownText(selected)) {
      // Made editable before the browser handles this press, so the caret lands where it was clicked.
      event.stopPropagation()
      api.editText(true)
      return
    }
    event.preventDefault()
    event.stopPropagation()
  }

  // A wireframe is an editable drawing while it is open in this canvas, not a
  // live application. Generated pages legitimately contain links, forms and
  // client-side click handlers; letting any of those run here navigates the
  // iframe away from the wireframe endpoint (for example to `/login`) and the
  // Studio then displays its own 404 page. Capture the activation before page
  // scripts see it. Selection and dragging are handled from `mousedown` above.
  const onActivate = event => {
    const editingText = doc.body.getAttribute('data-wf-editing') === 'text'
    const interactive = event.target?.closest?.('a, button, input, select, textarea, label')
    if (event.type === 'click' && editingText && selected?.contains(event.target) && !interactive) {
      // Keep normal caret placement while typing, but do not let generated
      // click handlers run against the editable canvas.
      event.stopImmediatePropagation()
      return
    }
    event.preventDefault()
    event.stopImmediatePropagation()
  }

  const onSubmit = event => {
    event.preventDefault()
    event.stopImmediatePropagation()
  }

  const onNativeDrag = event => {
    // Prevent the browser's built-in link/image drag from competing with the
    // editor's free-move and flow-reorder gestures.
    event.preventDefault()
  }

  const onKeyDown = event => {
    const editingText = doc.body.getAttribute('data-wf-editing') === 'text'
    const field = event.target?.closest?.('input, textarea, select, [contenteditable="true"]')
    const modifier = event.ctrlKey || event.metaKey
    const key = event.key.toLowerCase()

    if (editingText) {
      if (event.key === 'Escape') {
        event.preventDefault()
        api.editText(false)
      }
      return
    }
    if (field) return

    if (modifier && key === 'z') {
      event.preventDefault()
      if (event.shiftKey) api.redo()
      else api.undo()
      return
    }
    if (modifier && key === 'y') {
      event.preventDefault()
      api.redo()
      return
    }
    if (!selected || textOnly) return

    if (modifier && key === 'd') {
      event.preventDefault()
      api.duplicate()
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      api.editText(true)
      return
    }

    const shift = event.shiftKey
    const step = shift ? 10 : 1

    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      api.nudge(-step, 0)
    } else if (event.key === 'ArrowRight') {
      event.preventDefault()
      api.nudge(step, 0)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      api.nudge(0, -step)
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      api.nudge(0, step)
    } else if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault()
      api.remove()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      select(null)
    }
  }

  const onScroll = () => { updateOverlay() }
  // Words typed into the canvas are an edit the moment they are typed, so Save is offered straight away.
  const onInput = () => { if (doc.body.getAttribute('data-wf-editing') === 'text') touched() }

  doc.addEventListener('mousedown', onMouseDown, true)
  doc.addEventListener('click', onActivate, true)
  doc.addEventListener('auxclick', onActivate, true)
  doc.addEventListener('submit', onSubmit, true)
  doc.addEventListener('dragstart', onNativeDrag, true)
  doc.addEventListener('mouseover', onOver, true)
  doc.addEventListener('mouseout', onOut, true)
  doc.addEventListener('keydown', onKeyDown, true)
  doc.addEventListener('input', onInput, true)
  doc.defaultView?.addEventListener('scroll', onScroll, true)
  doc.defaultView?.addEventListener('resize', onScroll, true)

  const api = {
    selected: () => selected,
    nudge(dx, dy) {
      if (!selected) return
      snapshot(`Nudged <${label(selected)}>`)
      liftFree(selected)
      const curLeft = parseFloat(selected.style.left) || 0
      const curTop = parseFloat(selected.style.top) || 0
      selected.style.left = `${Math.round(curLeft + dx)}px`
      selected.style.top = `${Math.round(curTop + dy)}px`
      touched()
      updateOverlay()
    },
    duplicate() {
      if (!selected?.parentElement) return
      snapshot(`Duplicated <${label(selected)}>`)
      const copy = selected.cloneNode(true)
      copy.removeAttribute(MARK)
      copy.removeAttribute('data-wf-tag')
      // A copied layer starts in normal document flow.  Retaining free-mode
      // attributes would make it share no protected flow slot and create a
      // second, unexpectedly absolute layer.
      copy.classList.remove('__wf_dragging')
      if (selected.hasAttribute('data-wf-free')) {
        copy.removeAttribute('data-wf-free')
        copy.style.left = ''
        copy.style.top = ''
        copy.style.position = ''
        copy.style.width = ''
        copy.style.height = ''
        copy.style.minWidth = ''
        copy.style.minHeight = ''
        copy.style.maxWidth = ''
        copy.style.flex = ''
        copy.style.zIndex = ''
        copy.style.boxSizing = ''
        copy.style.margin = ''
      }
      selected.after(copy)
      select(copy)
      touched()
    },
    remove() {
      if (!selected?.parentElement) return
      snapshot(`Deleted <${label(selected)}>`)
      const slot = selected.previousElementSibling?.hasAttribute('data-wf-flow-slot')
        ? selected.previousElementSibling
        : null
      const next = selected.nextElementSibling || selected.parentElement
      selected.remove()
      slot?.remove()
      select(next)
      touched()
    },
    editText(on) {
      if (!selected) return
      if (!on && doc.body.getAttribute('data-wf-editing') !== 'text') return
      selected.contentEditable = on ? 'true' : 'false'
      doc.body.setAttribute('data-wf-editing', on ? 'text' : '')
      if (on) {
        snapshot(`Typed in <${label(selected)}>`)
        typedFrom = selected.innerHTML
        selected.focus()
      } else {
        if (typedFrom !== null && selected.innerHTML === typedFrom) {
          // Clicked into the text and left it unchanged: not an edit, so not an undo step either.
          undoStack.pop()
          editLog.pop()
        } else {
          touched()
        }
        typedFrom = null
        updateOverlay()
      }
    },
    undo() {
      const previous = undoStack.pop()
      if (!previous) return false
      editLog.pop()
      redoStack.push(historyMarkup())
      restore(previous)
      onDirty?.(undoStack.length > 0)
      return true
    },
    redo() {
      const next = redoStack.pop()
      if (!next) return false
      undoStack.push(historyMarkup())
      restore(next)
      onDirty?.(true)
      return true
    },
    // Whether an earlier state is still on the stack after that pop - the caller
    // uses this instead of guessing at a "dirty" flag: an empty stack means undo
    // has walked all the way back to what is actually saved on the server.
    hasHistory: () => undoStack.length > 0,
    changes: () => [...editLog],
    serialize() {
      const clone = doc.documentElement.cloneNode(true)
      clone.querySelectorAll(`[${MARK}]`).forEach(n => {
        n.removeAttribute(MARK)
        n.removeAttribute('data-wf-tag')
        n.removeAttribute('data-wf-secondary')
        n.classList.remove('__wf_dragging')
      })
      clone.querySelectorAll('.__wf_hover').forEach(n => n.classList.remove('__wf_hover'))
      clone.querySelectorAll('.__wf_dragging').forEach(n => n.classList.remove('__wf_dragging'))
      clone.querySelectorAll('[contenteditable]').forEach(n => n.removeAttribute('contenteditable'))
      clone.querySelectorAll('[data-wf-editor-ui]').forEach(n => n.remove())
      clone.querySelector(`#${STYLE_ID}`)?.remove()
      clone.querySelector('body')?.removeAttribute('data-wf-editing')
      return `<!DOCTYPE html>\n${clone.outerHTML}`
    },
    saved() { dirty = false; editLog.length = 0; onDirty?.(false) },
    detach() {
      doc.removeEventListener('mousedown', onMouseDown, true)
      doc.removeEventListener('click', onActivate, true)
      doc.removeEventListener('auxclick', onActivate, true)
      doc.removeEventListener('submit', onSubmit, true)
      doc.removeEventListener('dragstart', onNativeDrag, true)
      doc.removeEventListener('mouseover', onOver, true)
      doc.removeEventListener('mouseout', onOut, true)
      doc.removeEventListener('keydown', onKeyDown, true)
      doc.removeEventListener('input', onInput, true)
      doc.defaultView?.removeEventListener('scroll', onScroll, true)
      doc.defaultView?.removeEventListener('resize', onScroll, true)
      doc.getElementById('__wf_overlay')?.remove()
      doc.getElementById('__wf_hud')?.remove()
    },
  }
  return api
}
