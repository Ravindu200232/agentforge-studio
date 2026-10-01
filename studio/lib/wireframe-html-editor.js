/** Direct in-frame DOM WYSIWYG editing for wireframes and prototype pages. */

const STYLE_ID = '__wf_editor_style'
const MARK = 'data-wf-selected'

const CSS = `
  [${MARK}] {
    outline: 2px solid #0D99FF !important;
    outline-offset: 1px !important;
    cursor: grab !important;
  }
  [${MARK}].__wf_dragging {
    cursor: grabbing !important;
    box-shadow: 0 8px 24px rgba(13, 153, 255, 0.25) !important;
    z-index: 2147483640 !important;
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

  /* Smart drop indicator line */
  #__wf_drop_line {
    position: absolute;
    background: #0D99FF;
    box-shadow: 0 0 10px rgba(13, 153, 255, 0.85);
    pointer-events: none;
    z-index: 2147483647;
    border-radius: 2px;
  }
  #__wf_drop_line::before, #__wf_drop_line::after {
    content: '';
    position: absolute;
    width: 8px;
    height: 8px;
    background: #0D99FF;
    border: 1.5px solid #ffffff;
    border-radius: 50%;
    top: 50%;
    transform: translateY(-50%);
    box-shadow: 0 0 4px rgba(0, 0, 0, 0.4);
  }
  #__wf_drop_line::before { left: -4px; }
  #__wf_drop_line::after { right: -4px; }

  /* Floating live HUD coordinates badge */
  #__wf_hud {
    position: fixed;
    background: rgba(15, 23, 42, 0.94);
    color: #ffffff;
    border: 1px solid #0D99FF;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    font: 600 11px/1.4 ui-monospace, Menlo, monospace;
    padding: 3px 8px;
    border-radius: 6px;
    pointer-events: none;
    z-index: 2147483647;
    white-space: nowrap;
    display: none;
    align-items: center;
    gap: 6px;
  }

  /* Selection overlay & interactive resize handles */
  #__wf_overlay {
    position: absolute;
    pointer-events: none;
    z-index: 2147483645;
    box-sizing: border-box;
    display: none;
  }
  .__wf_handle {
    position: absolute;
    width: 8px;
    height: 8px;
    background: #ffffff;
    border: 1.5px solid #0D99FF;
    border-radius: 2px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
    pointer-events: auto;
    box-sizing: border-box;
  }
  .__wf_handle_nw { top: -4px; left: -4px; cursor: nwse-resize; }
  .__wf_handle_ne { top: -4px; right: -4px; cursor: nesw-resize; }
  .__wf_handle_se { bottom: -4px; right: -4px; cursor: nwse-resize; }
  .__wf_handle_sw { bottom: -4px; left: -4px; cursor: nesw-resize; }
  .__wf_handle_e  { top: 50%; right: -4px; transform: translateY(-50%); cursor: ew-resize; height: 12px; }
  .__wf_handle_s  { bottom: -4px; left: 50%; transform: translateX(-50%); cursor: ns-resize; width: 12px; }

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

/* Predefined wireframe HTML markup components for insertions. */
const CELL = 'border border-black px-3 py-2 text-left'
const BOX = 'border-2 border-black'
const IMG = `${BOX} flex items-center justify-center bg-[#F3F4F6] text-[11px]`

export const PARTS = [
  ['Navigation & layout', [
    ['nav', 'Nav', `<nav class="${BOX} flex items-center justify-between px-6 py-4 mb-4">
      <span class="font-bold">Product</span>
      <span class="flex gap-6 text-sm"><span>Overview</span><span>Records</span><span>Settings</span></span>
    </nav>`],
    ['footer', 'Footer', `<footer class="${BOX} grid grid-cols-3 gap-6 px-6 py-6 mt-4 text-sm">
      <div><div class="font-bold mb-2">Product</div><div>About</div><div>Contact</div></div>
      <div><div class="font-bold mb-2">Help</div><div>Guides</div><div>Support</div></div>
      <div><div class="font-bold mb-2">Legal</div><div>Terms</div><div>Privacy</div></div>
    </footer>`],
    ['panel', 'Panel', `<section class="${BOX} p-5 mb-4">
      <h3 class="font-bold mb-3">Panel title</h3>
      <p class="text-sm">What this grouping is for.</p>
    </section>`],
    ['tabs', 'Tabs', `<div class="flex gap-2 mb-4">
      <span class="${BOX} px-4 py-2 text-sm font-bold bg-black text-white">All</span>
      <span class="${BOX} px-4 py-2 text-sm">Open</span>
      <span class="${BOX} px-4 py-2 text-sm">Closed</span>
    </div>`],
    ['divider', 'Divider', '<hr class="border-t-2 border-black my-6" />'],
  ]],
  ['Typography & media', [
    ['heading', 'Heading', '<h1 class="text-3xl font-bold mb-2">Page heading</h1>'],
    ['title', 'Title', '<h2 class="text-xl font-bold mb-2">Section title</h2>'],
    ['text', 'Text', `<p class="text-sm mb-4 max-w-2xl">Two or three sentences of the copy this
      part of the page carries, written out so the length and the tone are visible.</p>`],
    ['image', 'Image', `<div class="${IMG} mb-4" style="height:220px">[ Image / Banner Placeholder ]</div>`],
    ['icon', 'Icon', `<span class="${BOX} inline-flex items-center justify-center rounded-full"
      style="width:44px;height:44px">ICON</span>`],
  ]],
  ['Wireframe notes & flow', [
    ['note', 'Annotation', `<aside class="border-2 border-dashed border-black bg-[#F3F4F6] px-3 py-2 text-xs mb-4" data-wf-note>
      <strong>NOTE</strong> — explain the interaction, data or behaviour here.
    </aside>`],
    ['flow', 'Flow arrow', `<div class="flex items-center gap-2 text-xs font-bold mb-4" data-wf-flow>
      <span class="border border-black px-2 py-1">Next action</span><span aria-hidden="true">→</span><span class="border border-dashed border-black px-2 py-1">Next screen</span>
    </div>`],
    ['placeholder', 'Placeholder', `<div class="border-2 border-dashed border-black px-4 py-8 text-center text-xs text-black mb-4" data-wf-placeholder>
      [ Content placeholder ]
    </div>`],
    ['modal', 'Modal sketch', `<section class="border-2 border-black bg-white p-5 mb-4" data-wf-modal>
      <div class="mb-3 flex items-center justify-between border-b-2 border-black pb-2 font-bold">Modal title <span>×</span></div>
      <p class="mb-4 text-sm">Explain the short decision or confirmation here.</p>
      <div class="flex gap-2"><button class="border-2 border-black px-3 py-1.5 text-sm font-bold">Confirm</button><button class="border-2 border-black px-3 py-1.5 text-sm">Cancel</button></div>
    </section>`],
  ]],
  ['Inputs & actions', [
    ['field', 'Field', `<label class="block mb-4 max-w-md">
      <span class="block text-xs font-bold uppercase tracking-wide mb-1">Field label</span>
      <input class="${BOX} w-full px-3 py-2 text-sm" value="Typed value" />
    </label>`],
    ['button', 'Button', `<button type="button" class="${BOX} px-5 py-2 text-sm font-bold mr-2 mb-4">Action</button>`],
    ['search', 'Search', `<div class="flex gap-2 mb-4 max-w-xl">
      <input class="${BOX} flex-1 px-3 py-2 text-sm" placeholder="Search…" />
      <button type="button" class="${BOX} px-5 py-2 text-sm font-bold">Search</button>
    </div>`],
  ]],
  ['Data & analytics', [
    ['table', 'Table', `<table class="${BOX} w-full border-collapse text-sm mb-4">
      <thead><tr class="bg-[#F3F4F6]">
        <th class="${CELL}">Name</th><th class="${CELL}">Owner</th><th class="${CELL}">Status</th>
      </tr></thead>
      <tbody>
        <tr><td class="${CELL}">First record</td><td class="${CELL}">A. Rivera</td><td class="${CELL}">Open</td></tr>
        <tr><td class="${CELL}">Second record</td><td class="${CELL}">M. Chen</td><td class="${CELL}">Closed</td></tr>
      </tbody>
    </table>`],
    ['row', 'Table row', `<tr><td class="${CELL}">New record</td><td class="${CELL}">Someone</td><td class="${CELL}">Open</td></tr>`],
    ['cards', 'Cards', `<div class="grid grid-cols-3 gap-4 mb-4">
      ${[1, 2, 3].map(n => `<div class="${BOX} p-4">
        <div class="${IMG} mb-3" style="height:120px">[ Image ]</div>
        <div class="font-bold text-sm">Item ${n}</div>
        <div class="text-xs">A line about it.</div>
      </div>`).join('')}
    </div>`],
    ['list', 'List', `<ul class="${BOX} divide-y divide-black text-sm mb-4">
      <li class="px-4 py-3">First item</li><li class="px-4 py-3">Second item</li>
      <li class="px-4 py-3">Third item</li>
    </ul>`],
    ['stat', 'Stat', `<div class="${BOX} p-4 mb-4 inline-block mr-3">
      <div class="text-xs uppercase tracking-wide">Total</div>
      <div class="text-3xl font-bold">128</div>
    </div>`],
    ['chart', 'Chart', `<div class="${BOX} flex items-end gap-2 p-4 mb-4" style="height:180px">
      ${[45, 70, 35, 85, 60, 75].map(h =>
        `<span class="flex-1 bg-[#E5E7EB] border border-black" style="height:${h}%"></span>`).join('')}
    </div>`],
    ['rating', 'Rating', '<div class="text-xl mb-4">★ ★ ★ ★ ☆</div>'],
  ]],
]

const SNIPPETS = Object.fromEntries(
  PARTS.flatMap(([, items]) => items.map(([kind, , html]) => [kind, html])))

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
  const cls = String(node.getAttribute('class') || '').split(/\s+/).filter(Boolean)[0]
  return cls ? `${tag}.${cls}` : tag
}

/**
 * Attach the Figma-style interactive wireframe editor to a loaded frame.
 */
export function attachEditor(iframe, { onSelect, onSelection, onDirty, onMetrics } = {}) {
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
  let dragMode = 'free' // 'free' (Figma Canvas Free Move) | 'flow' (DOM Flow Reorder)
  const undoStack = []
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
    onMetrics?.(null)
  }

  function getMetrics() {
    if (!selected) return null
    const curX = Math.round(parseFloat(selected.style.left) || 0)
    const curY = Math.round(parseFloat(selected.style.top) || 0)
    const rect = selected.getBoundingClientRect()
    return {
      tag: label(selected),
      x: curX,
      y: curY,
      w: Math.round(rect.width),
      h: Math.round(rect.height),
      hasOffset: curX !== 0 || curY !== 0,
      mode: dragMode,
      canMoveUp: Boolean(selected.previousElementSibling),
      canMoveDown: Boolean(selected.nextElementSibling),
    }
  }

  function notifyMetrics() {
    onMetrics?.(getMetrics())
  }

  function showHud(text, clientX, clientY) {
    let hud = doc.getElementById('__wf_hud')
    if (!hud) {
      hud = doc.createElement('div')
      hud.id = '__wf_hud'
      hud.setAttribute('data-wf-editor-ui', 'true')
      doc.body.appendChild(hud)
    }
    hud.textContent = text
    hud.style.display = 'flex'
    hud.style.left = `${Math.min(doc.documentElement.clientWidth - 170, clientX + 16)}px`
    hud.style.top = `${clientY + 18}px`
  }

  function hideHud() {
    const hud = doc.getElementById('__wf_hud')
    if (hud) hud.style.display = 'none'
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
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.9;flex-shrink:0;">
            <polyline points="5 9 2 12 5 15"></polyline>
            <polyline points="9 5 12 2 15 5"></polyline>
            <polyline points="15 19 12 22 9 19"></polyline>
            <polyline points="19 9 22 12 19 15"></polyline>
            <line x1="2" x2="22" y1="12" y2="12"></line>
            <line x1="12" x2="12" y1="2" y2="22"></line>
          </svg>
          <span id="__wf_tag_name"></span>
          <span id="__wf_tag_dims" style="opacity:0.75;font-size:9.5px;margin-left:4px;"></span>
        </div>
        <div class="__wf_handle __wf_handle_nw" data-handle="nw" data-wf-editor-ui="true"></div>
        <div class="__wf_handle __wf_handle_ne" data-handle="ne" data-wf-editor-ui="true"></div>
        <div class="__wf_handle __wf_handle_se" data-handle="se" data-wf-editor-ui="true"></div>
        <div class="__wf_handle __wf_handle_sw" data-handle="sw" data-wf-editor-ui="true"></div>
        <div class="__wf_handle __wf_handle_e" data-handle="e" data-wf-editor-ui="true"></div>
        <div class="__wf_handle __wf_handle_s" data-handle="s" data-wf-editor-ui="true"></div>
      `
      doc.body.appendChild(overlay)

      const badge = overlay.querySelector('#__wf_tag_badge')
      badge?.addEventListener('mousedown', e => {
        e.preventDefault()
        e.stopPropagation()
        startDrag(e, null)
      })

      overlay.querySelectorAll('.__wf_handle').forEach(h => {
        h.addEventListener('mousedown', e => {
          e.preventDefault()
          e.stopPropagation()
          const handleType = h.getAttribute('data-handle')
          startDrag(e, handleType)
        })
      })
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

  function updateDropLine(target) {
    let line = doc.getElementById('__wf_drop_line')
    if (!target) {
      if (line) line.style.display = 'none'
      return
    }
    if (!line) {
      line = doc.createElement('div')
      line.id = '__wf_drop_line'
      line.setAttribute('data-wf-editor-ui', 'true')
      doc.body.appendChild(line)
    }
    line.style.display = 'block'
    const r = target.rect
    const scrollX = doc.defaultView?.scrollX || doc.documentElement.scrollLeft || 0
    const scrollY = doc.defaultView?.scrollY || doc.documentElement.scrollTop || 0

    if (target.isVertical) {
      line.style.width = `${Math.max(40, r.width)}px`
      line.style.height = '3px'
      line.style.left = `${r.left + scrollX}px`
      line.style.top = target.position === 'before'
        ? `${r.top + scrollY - 2}px`
        : `${r.bottom + scrollY - 1}px`
    } else {
      line.style.width = '3px'
      line.style.height = `${Math.max(20, r.height)}px`
      line.style.top = `${r.top + scrollY}px`
      line.style.left = target.position === 'before'
        ? `${r.left + scrollX - 2}px`
        : `${r.right + scrollX - 1}px`
    }
  }

  function findDropTarget(clientX, clientY) {
    const overlay = doc.getElementById('__wf_overlay')
    if (overlay) overlay.style.display = 'none'
    const el = doc.elementFromPoint(clientX, clientY)
    if (overlay) overlay.style.display = 'block'

    if (!el || el === selected || selected.contains(el) || el === doc.documentElement || el === doc.body) {
      return null
    }
    if (el.hasAttribute?.('data-wf-editor-ui')) return null

    const rect = el.getBoundingClientRect()
    const isVertical = rect.height >= rect.width || rect.width > 300
    const position = isVertical
      ? (clientY < rect.top + rect.height / 2 ? 'before' : 'after')
      : (clientX < rect.left + rect.width / 2 ? 'before' : 'after')

    return { element: el, rect, position, isVertical }
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
    notifyMetrics()
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

  /**
   * A flex child sized by a non-`auto` flex-basis (Tailwind's `flex-1` and similar,
   * common throughout these wireframes) ignores an explicit `width`/`height` entirely
   * - the flex algorithm sizes it from flex-basis, not from `width`. A flex or grid
   * child that stretches to fill its row/track (the default `align-items: stretch`)
   * ignores an explicit `height` the same way. Resizing one by hand must opt it out
   * of that auto-sizing first, the way a real design tool's resize handle does, or
   * the drag changes the inline style while the rendered box never moves.
   */
  function freeSize(el) {
    const computed = doc.defaultView.getComputedStyle(el)
    const parentDisplay = el.parentElement ? doc.defaultView.getComputedStyle(el.parentElement).display : ''
    if (/flex/.test(parentDisplay) &&
        (computed.flexBasis !== 'auto' || Number(computed.flexGrow) !== 0 || Number(computed.flexShrink) !== 0)) {
      el.style.flex = '0 0 auto'
    }
    if (/flex|grid/.test(parentDisplay) && computed.alignSelf !== 'flex-start' && computed.alignSelf !== 'start') {
      el.style.alignSelf = 'flex-start'
    }
  }

  let hovered = null
  const onOver = event => {
    if (hovered) hovered.classList.remove('__wf_hover')
    hovered = selectable(event.target, doc)
    if (hovered && hovered !== selected) {
      hovered.classList.add('__wf_hover')
    }
  }
  const onOut = () => {
    hovered?.classList.remove('__wf_hover')
    hovered = null
  }

  // --- DRAGGING ENGINE ---
  let isDragging = false
  let dragStart = null
  let activeResize = null
  let dropCandidate = null

  function startDrag(e, resizeType = null) {
    if (!selected) return
    if (doc.body.getAttribute('data-wf-editing') === 'text') return

    const initialLeft = parseFloat(selected.style.left) || 0
    const initialTop = parseFloat(selected.style.top) || 0
    const rect = selected.getBoundingClientRect()

    dragStart = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      initLeft: initialLeft,
      initTop: initialTop,
      initWidth: rect.width,
      initHeight: rect.height,
    }
    activeResize = resizeType
    isDragging = false
  }

  function onMouseMove(e) {
    if (!dragStart || !selected) return

    const dx = e.clientX - dragStart.mouseX
    const dy = e.clientY - dragStart.mouseY

    if (!isDragging && (Math.abs(dx) > 2 || Math.abs(dy) > 2)) {
      isDragging = true
      selected.classList.add('__wf_dragging')
      // Exactly once per gesture, before this drag's first mutation (resize, free
      // move or reorder all still lie below this line) - not on mouseup, by which
      // point the live preview during mousemove already applied the change, so a
      // snapshot taken there just re-captures the state already on screen and one
      // undo click appears to do nothing.
      snapshot(activeResize ? `Resized <${label(selected)}>` : `Moved <${label(selected)}>`)
    }

    if (!isDragging) return

    e.preventDefault()

    // 1. Resizing
    if (activeResize) {
      if (!dragStart.freed) {
        liftFree(selected)
        freeSize(selected)
        dragStart.freed = true
      }
      let newW = dragStart.initWidth
      let newH = dragStart.initHeight

      if (activeResize.includes('e')) newW = Math.max(30, Math.round(dragStart.initWidth + dx))
      if (activeResize.includes('s')) newH = Math.max(20, Math.round(dragStart.initHeight + dy))
      if (activeResize.includes('w')) newW = Math.max(30, Math.round(dragStart.initWidth - dx))
      if (activeResize.includes('n')) newH = Math.max(20, Math.round(dragStart.initHeight - dy))

      selected.style.width = `${newW}px`
      if (activeResize.includes('s') || activeResize.includes('n')) {
        selected.style.height = `${newH}px`
      }
      showHud(`W: ${newW}px  H: ${newH}px`, e.clientX, e.clientY)
      updateOverlay()
      notifyMetrics()
      return
    }

    // 2. Moving
    const effectiveMode = (e.ctrlKey || e.metaKey)
      ? (dragMode === 'free' ? 'flow' : 'free')
      : dragMode

    if (effectiveMode === 'flow') {
      dropCandidate = findDropTarget(e.clientX, e.clientY)
      updateDropLine(dropCandidate)
      if (dropCandidate) {
        showHud(`Reorder ${dropCandidate.position} <${label(dropCandidate.element)}>`, e.clientX, e.clientY)
      } else {
        showHud('Drag over element to reorder', e.clientX, e.clientY)
      }
    } else {
      updateDropLine(null)
      dropCandidate = null

      // Lifted lazily, only once an actual free-move drag is happening: a click that
      // turns into a flow-reorder (ctrl/meta held) must never have been lifted out of
      // flow first, or the leftover absolute position would misplace it at its new
      // flow spot too.
      if (!dragStart.lifted) {
        liftFree(selected)
        dragStart.initLeft = parseFloat(selected.style.left) || 0
        dragStart.initTop = parseFloat(selected.style.top) || 0
        dragStart.lifted = true
      }

      let curDx = dx
      let curDy = dy

      if (e.shiftKey) {
        if (Math.abs(curDx) > Math.abs(curDy)) curDy = 0
        else curDx = 0
      }

      const newLeft = Math.round(dragStart.initLeft + curDx)
      const newTop = Math.round(dragStart.initTop + curDy)

      selected.style.left = `${newLeft}px`
      selected.style.top = `${newTop}px`

      const signX = curDx >= 0 ? `+${curDx}` : `${curDx}`
      const signY = curDy >= 0 ? `+${curDy}` : `${curDy}`
      showHud(`X: ${newLeft}px  Y: ${newTop}px (Δ ${signX}, ${signY})`, e.clientX, e.clientY)
      updateOverlay()
      notifyMetrics()
    }
  }

  function onMouseUp() {
    if (!dragStart) return

    if (isDragging) {
      if (selected) selected.classList.remove('__wf_dragging')
      hideHud()
      updateDropLine(null)

      if (dropCandidate && dropCandidate.element && selected) {
        // Already snapshotted pre-drag, above, when this gesture first crossed the
        // move threshold - that one entry covers this reorder too.
        const target = dropCandidate.element
        if (dropCandidate.position === 'before') {
          target.before(selected)
        } else {
          target.after(selected)
        }
        selected.scrollIntoView({ block: 'nearest' })
        touched()
      } else {
        touched()
      }
      updateOverlay()
      notifyMetrics()
    }

    dragStart = null
    activeResize = null
    dropCandidate = null
    isDragging = false
  }

  const onMouseDown = event => {
    if (doc.body.getAttribute('data-wf-editing') === 'text') return
    const target = event.target

    if (target.hasAttribute?.('data-wf-editor-ui')) return

    if (event.ctrlKey || event.metaKey) {
      event.preventDefault()
      event.stopPropagation()
      select(target, { additive: true })
      return
    }

    if (selected && (target === selected || selected.contains(target))) {
      event.preventDefault()
      startDrag(event, null)
      return
    }

    event.preventDefault()
    event.stopPropagation()
    select(target)
    startDrag(event, null)
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
    if (!selected) return

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
      if (event.altKey) api.move(-1)
      else api.nudge(0, -step)
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (event.altKey) api.move(1)
      else api.nudge(0, step)
    } else if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault()
      api.remove()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      select(null)
    }
  }

  const onScroll = () => { updateOverlay() }

  doc.addEventListener('mousedown', onMouseDown, true)
  doc.addEventListener('mousemove', onMouseMove, true)
  doc.addEventListener('mouseup', onMouseUp, true)
  doc.addEventListener('click', onActivate, true)
  doc.addEventListener('auxclick', onActivate, true)
  doc.addEventListener('submit', onSubmit, true)
  doc.addEventListener('dragstart', onNativeDrag, true)
  doc.addEventListener('mouseover', onOver, true)
  doc.addEventListener('mouseout', onOut, true)
  doc.addEventListener('keydown', onKeyDown, true)
  doc.defaultView?.addEventListener('scroll', onScroll, true)
  doc.defaultView?.addEventListener('resize', onScroll, true)

  const api = {
    selected: () => selected,
    selections: () => Array.from(selectedNodes),
    parent() {
      if (selected?.parentElement) select(selected.parentElement)
    },
    move(delta) {
      if (!selected?.parentElement) return
      let sibling = delta < 0
        ? selected.previousElementSibling
        : selected.nextElementSibling
      // A free-positioned item owns the invisible slot immediately before it.
      // Never treat that editor-only slot as a real drawing-layer sibling.
      while (sibling?.hasAttribute('data-wf-flow-slot')) {
        sibling = delta < 0 ? sibling.previousElementSibling : sibling.nextElementSibling
      }
      if (!sibling) return
      snapshot(`Reordered <${label(selected)}>`)
      if (delta < 0) sibling.before(selected)
      else sibling.after(selected)
      selected.scrollIntoView({ block: 'nearest' })
      touched()
      updateOverlay()
      notifyMetrics()
    },
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
      notifyMetrics()
    },
    setPos(x, y) {
      if (!selected) return
      snapshot(`Set position for <${label(selected)}>`)
      liftFree(selected)
      if (x === null || x === undefined || x === '') selected.style.left = ''
      else selected.style.left = `${Math.round(Number(x))}px`
      if (y === null || y === undefined || y === '') selected.style.top = ''
      else selected.style.top = `${Math.round(Number(y))}px`
      touched()
      updateOverlay()
      notifyMetrics()
    },
    resetPos() {
      if (!selected) return
      snapshot(`Reset position for <${label(selected)}>`)
      const slot = selected.previousElementSibling
      if (slot?.hasAttribute('data-wf-flow-slot')) slot.replaceWith(selected)
      selected.removeAttribute('data-wf-free')
      selected.style.left = ''
      selected.style.top = ''
      selected.style.position = ''
      selected.style.width = ''
      selected.style.height = ''
      selected.style.minWidth = ''
      selected.style.minHeight = ''
      selected.style.maxWidth = ''
      selected.style.flex = ''
      selected.style.zIndex = ''
      selected.style.boxSizing = ''
      selected.style.margin = ''
      touched()
      updateOverlay()
      notifyMetrics()
    },
    setDragMode(mode) {
      dragMode = mode === 'flow' ? 'flow' : 'free'
      notifyMetrics()
    },
    getDragMode() {
      return dragMode
    },
    getMetrics,
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
    wider(step) {
      if (!selected) return
      snapshot(`Resized <${label(selected)}>`)
      const now = parseFloat(selected.style.width) || 100
      selected.style.width = `${Math.max(10, Math.min(100, now + step))}%`
      touched()
      updateOverlay()
      notifyMetrics()
    },
    align(how) {
      if (!selected) return
      snapshot(`Aligned <${label(selected)}> ${how}`)
      selected.style.marginLeft = how === 'center' || how === 'right' ? 'auto' : ''
      selected.style.marginRight = how === 'center' || how === 'left' ? 'auto' : ''
      if (how === 'left') selected.style.marginLeft = ''
      if (how === 'right') selected.style.marginRight = ''
      selected.style.textAlign = how === 'center' ? 'center' : ''
      if (how === 'full') {
        selected.style.width = '100%'
        selected.style.marginLeft = ''
        selected.style.marginRight = ''
        selected.style.display = 'block'
      }
      touched()
      updateOverlay()
      notifyMetrics()
    },
    style(property, value) {
      if (!selected || !property) return
      snapshot(`Updated ${property} on <${label(selected)}>`)
      selected.style.setProperty(String(property).trim(), String(value ?? '').trim())
      touched()
      updateOverlay()
      notifyMetrics()
    },
    text(value) {
      if (!selected) return
      snapshot(`Changed text in <${label(selected)}>`)
      selected.textContent = String(value ?? '')
      touched()
      updateOverlay()
      notifyMetrics()
    },
    insert(kind) {
      const markup = SNIPPETS[kind]
      if (!markup) return
      snapshot(`Inserted ${kind}`)
      const host = doc.createElement(kind === 'row' ? 'tbody' : 'div')
      if (kind === 'row') {
        const table = doc.createElement('table')
        table.innerHTML = `<tbody>${markup}</tbody>`
        const row = table.querySelector('tr')
        const body = selected?.closest('tbody') || doc.querySelector('tbody')
        if (!body || !row) return
        body.appendChild(row)
        select(row)
        touched()
        return
      }
      host.innerHTML = markup.trim()
      const node = host.firstElementChild
      if (!node) return
      if (selected && selected.parentElement) {
        // Insert right after the currently selected element.
        selected.after(node)
      } else {
        // Nothing selected: insert at the visible centre of the iframe viewport
        // so the element appears where the user is looking rather than scrolling
        // them to the bottom of the page.
        const vw = doc.defaultView?.innerWidth || doc.documentElement.clientWidth || 800
        const vh = doc.defaultView?.innerHeight || doc.documentElement.clientHeight || 600
        const midX = vw / 2
        const midY = vh / 2
        // Walk up from the point to find a sensible block-level host.
        let anchor = doc.elementFromPoint(midX, midY)
        while (anchor && anchor !== doc.body && anchor !== doc.documentElement) {
          if (['DIV', 'SECTION', 'MAIN', 'ARTICLE', 'HEADER', 'FOOTER', 'ASIDE'].includes(anchor.tagName)) break
          anchor = anchor.parentElement
        }
        const container = (anchor && anchor !== doc.documentElement ? anchor : null)
          || doc.querySelector('main, body > div, body')
          || doc.body
        container.appendChild(node)
      }
      select(node)
      node.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
      touched()
      return node
    },
    editText(on) {
      if (!selected) return
      selected.contentEditable = on ? 'true' : 'false'
      doc.body.setAttribute('data-wf-editing', on ? 'text' : '')
      if (on) {
        snapshot(`Typed in <${label(selected)}>`)
        selected.focus()
      } else {
        touched()
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
    canRedo: () => redoStack.length > 0,
    deselect: () => select(null),
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
      doc.removeEventListener('mousemove', onMouseMove, true)
      doc.removeEventListener('mouseup', onMouseUp, true)
      doc.removeEventListener('click', onActivate, true)
      doc.removeEventListener('auxclick', onActivate, true)
      doc.removeEventListener('submit', onSubmit, true)
      doc.removeEventListener('dragstart', onNativeDrag, true)
      doc.removeEventListener('mouseover', onOver, true)
      doc.removeEventListener('mouseout', onOut, true)
      doc.removeEventListener('keydown', onKeyDown, true)
      doc.defaultView?.removeEventListener('scroll', onScroll, true)
      doc.defaultView?.removeEventListener('resize', onScroll, true)
      doc.getElementById('__wf_overlay')?.remove()
      doc.getElementById('__wf_hud')?.remove()
      doc.getElementById('__wf_drop_line')?.remove()
    },
  }
  return api
}
