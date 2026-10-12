// The agent asks before an edit or a command: each request is a card in the chat stream, answered on its own, and a question the
// agent asked in words is not touched by an answer to a card.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const lib = new URL('../../studio/lib/', import.meta.url)
const progress = new URL('progress-model.js', lib).href
const source = (await readFile(new URL('agent-session.js', lib), 'utf8')).replace(`'./progress-model'`, JSON.stringify(progress))
const { emptySession, reduceSession } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

const feed = (events, start = emptySession()) => events.reduce(reduceSession, start)
const card = (id, detail, extra = {}) => ({ type: 'approval', kind: 'permission', id, project: 'p', agent: 'developer', question: 'Run this command?',
  action: 'command', detail, options: ['allow', 'always', 'deny'], ...extra })

// Two cards at once (the agent writes some files in parallel): both are on screen.
let s = feed([{ type: 'run_state', status: 'running', run_id: 'r1' }, card('a1', 'npm test'), card('a2', 'npm run build')])
assert.deepEqual(s.permissions.map(c => c.id), ['a1', 'a2'])
assert.equal(s.approval, null)
assert.equal(s.ask, null)

// The same card arriving again (a reload recovering it) is not a second card.
s = feed([card('a1', 'npm test')], s)
assert.equal(s.permissions.length, 2)

// Answering one removes that one only.
s = feed([{ type: 'approval_resolved', id: 'a1', project: 'p', agent: 'developer' }], s)
assert.deepEqual(s.permissions.map(c => c.id), ['a2'])

// A question the agent asked in words stays while a card is answered, and a card does not clear it.
s = feed([{ type: 'approval', kind: 'question', id: 'q1', project: 'p', question: 'Which database?', options: [] },
  { type: 'approval_resolved', id: 'a2', project: 'p', agent: 'developer' }], s)
assert.equal(s.permissions.length, 0)
assert.equal(s.ask.id, 'q1')

// Resolving the question leaves any card alone.
s = feed([card('a3', 'terraform apply', { danger: true }), { type: 'approval_resolved', id: 'q1', project: 'p' }], s)
assert.equal(s.ask, null)
assert.deepEqual(s.permissions.map(c => c.id), ['a3'])
assert.equal(s.permissions[0].danger, true)

// A run that ends takes its waiting cards with it.
for (const type of ['done', 'error', 'cancelled']) {
  const ended = feed([{ type }], s)
  assert.deepEqual(ended.permissions, [], type)
}

// A session that never had one starts with none.
assert.deepEqual(emptySession().permissions, [])
console.log('Permission cards: ok')
