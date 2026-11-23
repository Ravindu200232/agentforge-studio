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

const progress = new URL('../../studio/lib/progress-model.js', import.meta.url).href
const sessionSource = (await readFile(new URL('../../studio/lib/agent-session.js', import.meta.url), 'utf8'))
  .replace("'./progress-model'", JSON.stringify(progress))
const { emptySession, reduceSession } = await import(`data:text/javascript;base64,${Buffer.from(sessionSource).toString('base64')}`)
const writing = { type: 'run_state', status: 'running', run_id: 'srs' }
const section = { type: 'phase', kind: 'srs-progress', key: 'srs:part:tables', title: 'Database design', phase: 2 }
const timeline = [
  { ...writing, at: 1 },
  { ...section, status: 'active', at: 2 },
  { ...section, status: 'complete', at: 3 },
  { type: 'run_state', status: 'completed', at: 4 },
  { ...writing, at: 5 },
  { ...section, status: 'queued', at: 6 },
  { ...section, status: 'retrying', at: 7 },
  { type: 'run_state', status: 'paused', at: 8 },
].reduce(reduceSession, emptySession())
assert.deepEqual(chatTurns([], timeline.chat).map(turn => [turn.at, turn.group, turn.status]), [
  [2, 'srs-progress', 'complete'],
  [6, 'srs-progress', 'paused'],
])
assert.equal(timeline.phases[0].status, 'paused')

console.log('chat display cleaner: ok')
