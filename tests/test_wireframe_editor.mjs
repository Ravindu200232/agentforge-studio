import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = await readFile(new URL('../studio/lib/wireframe-html-editor.js', import.meta.url), 'utf8')
const editorModule = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

const listeners = new Map()
const removed = new Map()
const styleNodes = []

const document = {
  body: {
    appendChild() {},
    getAttribute() { return '' },
    removeAttribute() {},
  },
  head: { appendChild(node) { styleNodes.push(node) } },
  documentElement: {},
  defaultView: {
    addEventListener() {},
    removeEventListener() {},
  },
  createElement(tagName) {
    return { tagName, id: '', textContent: '' }
  },
  getElementById() { return null },
  addEventListener(type, handler, capture) {
    listeners.set(type, { handler, capture })
  },
  removeEventListener(type, handler, capture) {
    removed.set(type, { handler, capture })
  },
}

const editor = editorModule.attachEditor({ contentDocument: document })
assert.ok(editor, 'the editor attaches to a wireframe document')
assert.equal(styleNodes.length, 1, 'editor styles are installed')

for (const eventName of ['click', 'auxclick', 'submit']) {
  const registered = listeners.get(eventName)
  assert.ok(registered, `${eventName} is intercepted`)
  assert.equal(registered.capture, true, `${eventName} is caught before page scripts`)

  let prevented = false
  let stopped = false
  registered.handler({
    preventDefault() { prevented = true },
    stopImmediatePropagation() { stopped = true },
  })
  assert.equal(prevented, true, `${eventName} cannot navigate the iframe`)
  assert.equal(stopped, true, `${eventName} cannot run generated page handlers`)
}

editor.detach()
for (const eventName of ['click', 'auxclick', 'submit', 'dragstart']) {
  const registered = listeners.get(eventName)
  const detached = removed.get(eventName)
  assert.equal(detached?.handler, registered?.handler, `${eventName} handler is detached cleanly`)
  assert.equal(detached?.capture, true)
}

console.log('wireframe editor navigation guard: ok')
