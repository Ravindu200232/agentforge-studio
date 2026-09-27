// Direct prototype edits. History retains the original nodes and listeners.
const histories = new WeakMap()
export function editorFor(doc) {
  if (histories.has(doc)) return histories.get(doc)
  const undo = [], redo = []
  let sequence = 0, changes = []
  const note = description => changes.push({sequence: ++sequence, description})
  const editor = {
    perform(forward, backward, description = 'Updated HTML structure') {
      forward()
      undo.push({forward, backward, description})
      if (undo.length > 100) undo.shift()
      redo.length = 0
      note(description)
    },
    undo() { const action = undo.pop(); if (action) { action.backward(); redo.push(action); note('Reverted: ' + action.description) } },
    redo() { const action = redo.pop(); if (action) { action.forward(); undo.push(action); note('Restored: ' + action.description) } },
    get canUndo() { return !!undo.length },
    get canRedo() { return !!redo.length },
    get sequence() { return sequence },
    markSaved(upTo = sequence) { changes = changes.filter(change => change.sequence > upTo) },
    summary() { return [...new Set(changes.map(a => a.description))].slice(-40).join('; ') },
    style(el, property, value) {
      if (value && !doc.defaultView.CSS.supports(property, value)) throw new Error(`Invalid ${property} value`)
      const before = el.style.getPropertyValue(property), priority = el.style.getPropertyPriority(property)
      if (before === value) return
      editor.perform(() => value ? el.style.setProperty(property, value) : el.style.removeProperty(property),
        () => before ? el.style.setProperty(property, before, priority) : el.style.removeProperty(property),
        `Updated <${el.tagName.toLowerCase()}> ${property}${/url|image|content/i.test(property) ? '' : ' to ' + value.slice(0,120)}`)
    },
    attribute(el, name, value) {
      if (!/^(?:id|class|title|role|tabindex|aria-[\w-]+|data-[\w-]+|href|target|rel|src|alt|width|height|name|placeholder|type|value|min|max|step|pattern|autocomplete|loading|disabled|required|checked|controls|muted|loop|poster)$/.test(name))
        throw new Error('Use a supported HTML attribute')
      if (['href', 'src', 'poster'].includes(name) && !safeUrl(value, name !== 'href')) throw new Error('Use a safe URL')
      const before = el.getAttribute(name)
      const live = name === 'value' ? el.value : ['checked','disabled','required','muted','loop','controls'].includes(name) ? el[name] : undefined
      const apply = next => {
        next == null ? el.removeAttribute(name) : el.setAttribute(name, next)
        if (name === 'value' && 'value' in el) el.value = next || ''
        else if (live !== undefined) el[name] = next != null
      }
      editor.perform(() => apply(value), () => { apply(before); if (live !== undefined) el[name] = live },
        `Updated <${el.tagName.toLowerCase()}> ${name} attribute`)
    },
    text(el, value) {
      if (el.tagName === 'INPUT') return editor.attribute(el, 'value', value)
      if (el.tagName === 'TEXTAREA') {
        const before = el.textContent
        editor.perform(() => { el.textContent = value; el.value = value }, () => { el.textContent = before; el.value = before })
        return
      }
      const nodes = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim())
      if (!nodes.length && el.children.length) throw new Error('Select the text element inside this container')
      const node = nodes[0] || doc.createTextNode('')
      const before = node.textContent, attached = !!node.parentNode
      editor.perform(() => { if (!node.parentNode) el.prepend(node); node.textContent = value },
        () => { node.textContent = before; if (!attached) node.remove() }, `Updated <${el.tagName.toLowerCase()}> text to ${value.slice(0,200)}`)
    },
    move(el, direction) {
      const parent = el.parentNode, next = el.nextSibling
      const target = direction === 'up' ? el.previousElementSibling : el.nextElementSibling
      if (!parent || !target || ['HTML', 'BODY', 'HEAD'].includes(el.tagName)) return
      editor.perform(() => direction === 'up' ? parent.insertBefore(el, target) : parent.insertBefore(el, target.nextSibling),
        () => parent.insertBefore(el, next?.parentNode === parent ? next : null))
    },
    remove(el) {
      if (['HTML', 'BODY', 'HEAD'].includes(el.tagName)) throw new Error('Select a page element')
      if (!el.parentNode) throw new Error('This element is already removed; use Undo to restore it')
      const parent = el.parentNode, next = el.nextSibling
      editor.perform(() => el.remove(), () => parent.insertBefore(el, next?.parentNode === parent ? next : null))
    },
    duplicate(el) {
      if (['HTML', 'BODY', 'HEAD'].includes(el.tagName)) throw new Error('Select a page element')
      const clone = el.cloneNode(true)
      clone.querySelectorAll('[id]').forEach(n => n.removeAttribute('id'))
      clone.removeAttribute('id')
      clone.querySelectorAll('[data-vf-key]').forEach(n => n.removeAttribute('data-vf-key'))
      clone.removeAttribute('data-vf-key')
      stripHighlights(clone)
      editor.perform(() => el.after(clone), () => clone.remove())
      return clone
    },
    insert(el, tag) {
      if (!['div', 'section', 'p', 'h2', 'span', 'a', 'button', 'img', 'input', 'ul', 'li', 'hr'].includes(tag)) throw new Error('Choose a supported element')
      const node = doc.createElement(tag)
      if (tag === 'img') { node.setAttribute('alt', ''); node.setAttribute('src', '') }
      else if (tag === 'input') node.setAttribute('placeholder', 'Enter text')
      else if (tag !== 'hr') node.textContent = tag === 'button' ? 'Button' : tag === 'a' ? 'Link' : 'New content'
      if (tag === 'a') node.setAttribute('href', '#')
      if (tag === 'button') node.setAttribute('type', 'button')
      const container = !['IMG', 'INPUT', 'HR', 'BR'].includes(el.tagName) ? el : el.parentElement
      editor.perform(() => container.append(node), () => node.remove())
      return node
    },
    responsive(el, breakpoint, property, value, state = '') {
      if (value && !doc.defaultView.CSS.supports(property, value)) throw new Error(`Invalid ${property} value`)
      let key = el.getAttribute('data-vf-key')
      if (!key || !/^[a-z0-9-]+$/i.test(key)) { key = doc.defaultView.crypto?.randomUUID?.() || `vf-${Date.now()}-${Math.random().toString(36).slice(2)}`; editor.attribute(el, 'data-vf-key', key) }
      let sheet = doc.getElementById('vf-custom-rules')
      if (!sheet) { sheet = doc.createElement('style'); sheet.id = 'vf-custom-rules'; doc.head.append(sheet) }
      const marker = `/*vf:${key}:${breakpoint}:${state}:${property}*/`
      const end = '/*vf:end*/'
      const before = sheet.textContent
      const start = before.indexOf(marker)
      const stop = start >= 0 ? before.indexOf(end, start) + end.length : -1
      const cleaned = start >= 0 ? before.slice(0, start) + before.slice(stop) : before
      const selector = `[data-vf-key="${key}"]${state ? ':' + state : ''}`
      const rule = value ? `${selector}{${property}:${value} !important;}` : ''
      const wrapped = breakpoint === 'all' ? rule : `@media(max-width:${breakpoint}px){${rule}}`
      const after = cleaned + (value ? `\n${marker}${wrapped}${end}` : '')
      editor.perform(() => { sheet.textContent = after }, () => { sheet.textContent = before },
        `Updated <${el.tagName.toLowerCase()}> ${property} for ${breakpoint === 'all' ? 'all sizes' : 'max-width ' + breakpoint + 'px'} ${state}`)
    },
  }
  histories.set(doc, editor)
  return editor
}

export function safeUrl(value, image = false) {
  const normalized = String(value || '').replace(/[\u0000-\u0020]/g, '')
  if (!normalized || /^(?:https?:|mailto:|tel:|blob:)/i.test(normalized)) return true
  if (image && /^data:image\/(?:png|jpeg|gif|webp|avif);base64,[a-z0-9+/=]+$/i.test(normalized)) return true
  return !/^[a-z][a-z\d+.-]*:/i.test(normalized)
}

export function stripHighlights(root) {
  for (const node of [root, ...root.querySelectorAll('*')]) {
    node.classList?.remove('__vf_hi', '__vf_selected', '__lc_hi', '__lc_selected')
    if (node.hasAttribute?.('class') && !node.getAttribute('class')) node.removeAttribute('class')
  }
}

export function serializePrototype(doc) {
  const clone = doc.documentElement.cloneNode(true)
  stripHighlights(clone)
  clone.querySelectorAll('#__vf_style, #__lc_style, [data-agentforge-inspector]').forEach(n => n.remove())
  // Preserve edited form defaults, not runtime password/session values.
  const sources = doc.querySelectorAll('textarea, input, select')
  clone.querySelectorAll('textarea, input, select').forEach((target, index) => {
    const source = sources[index]
    if (target.tagName === 'INPUT' && ['password', 'file'].includes(target.type)) target.removeAttribute('value')
    if (target.tagName === 'TEXTAREA') target.textContent = source.defaultValue
  })
  const dt = doc.doctype
  const doctype = dt ? `<!DOCTYPE ${dt.name}${dt.publicId ? ` PUBLIC "${dt.publicId}"` : dt.systemId ? ' SYSTEM' : ''}${dt.systemId ? ` "${dt.systemId}"` : ''}>` : '<!DOCTYPE html>'
  return doctype + '\n' + clone.outerHTML
}
