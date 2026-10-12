import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const helperSource = await readFile(new URL('../../studio/lib/chat-display.js', import.meta.url), 'utf8')
const helper = await import(`data:text/javascript;base64,${Buffer.from(helperSource).toString('base64')}`)

assert.equal(
  helper.cleanChatProse('**A real finding:** `core` §5 requires this.'),
  'A real finding: core section 5 requires this.',
)
assert.equal(helper.cleanChatProse('ï»¿Â· **Ready**'), '· Ready')
assert.equal(helper.cleanChatProse('^[[36;1mChecking^[[0m'), 'Checking')
assert.equal(helper.cleanChatProse('**/*.test.js stays exact'), '**/*.test.js stays exact')
assert.deepEqual(
  helper.chatDisplayBlocks('**Summary**\n\n- first\n- second\n\n```sh\necho **raw**\n```'),
  [
    { kind: 'paragraph', text: 'Summary' },
    { kind: 'list', items: ['first', 'second'] },
    { kind: 'code', language: 'sh', text: 'echo **raw**' },
  ],
)

const chatSource = await readFile(new URL('../../studio/components/AgentChat.jsx', import.meta.url), 'utf8')
assert.match(chatSource, /\['command', 'command_output'\]\.includes\(turn\.kind\)[\s\S]*?<pre[\s\S]*?>\{turn\.text\}<\/pre>/)
assert.match(chatSource, /<ReadableAgentText text=\{turn\.text\} \/>/)

const turnsSource = await readFile(new URL('../../studio/lib/chat.js', import.meta.url), 'utf8')
const { chatTurns } = await import(`data:text/javascript;base64,${Buffer.from(turnsSource).toString('base64')}`)
const stages = chatTurns([], [
  { at: 1, kind: 'narration', title: 'SRS generation', text: 'Writing requirements.' },
  { at: 2, kind: 'command', title: 'Rendering diagram', text: 'Mermaid CLI' },
  { at: 3, kind: 'command_output', title: 'Mermaid output', text: 'SVG rendered successfully.' },
  { at: 4, kind: 'narration', title: 'Wireframe page', text: 'Drawing a page.' },
  { at: 5, kind: 'narration', title: 'Prototype screen', text: 'Drawing a screen.' },
])
assert.deepEqual(stages.map(turn => turn.title), [
  'SRS generation', 'Rendering diagram', 'Mermaid output', 'Wireframe page', 'Prototype screen',
])

console.log('chat display cleaner: ok')
