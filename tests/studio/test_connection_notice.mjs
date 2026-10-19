// The model service stops answering. Automatic retries are internal work and stay out of the chat; only when the run has
// asked as many times as it will and holds still for the person does the chat show a card, with "Try again".
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const lib = new URL('../../studio/lib/', import.meta.url)
const progress = new URL('progress-model.js', lib).href
const source = (await readFile(new URL('agent-session.js', lib), 'utf8')).replace(`'./progress-model'`, JSON.stringify(progress))
const { emptySession, reduceSession } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)

const feed = (events, start = emptySession()) => events.reduce(reduceSession, start)
const running = { type: 'run_state', status: 'running', run_id: 'r1' }

// A failed request that is being asked again by itself: nothing in the chat.
let s = feed([running, { type: 'connection', state: 'retrying', failed: 2, of: 10, pause: 4, detail: 'Internal Server Error (status code: 500)' }])
assert.equal(s.connection, null)
assert.equal(s.busy, true)

// Asked as many times as it will be: the run holds still for the person, and the card says so.
s = feed([{ type: 'connection', state: 'waiting', of: 10, hold: true, detail: 'Internal Server Error' }], s)
assert.equal(s.connection.state, 'waiting')
assert.equal(s.connection.of, 10)
assert.match(s.connection.detail, /Internal Server Error/)

// It answers again: the card goes, and the stream gets no recovery line.
s = feed([{ type: 'connection', state: 'ok' }], s)
assert.equal(s.connection, null)
assert.equal(s.chat.filter(row => row.role === 'connection').length, 0)

// A run that ends - done, failed, stopped, idle - takes the card with it.
for (const type of ['done', 'error', 'cancelled']) {
  const held = feed([running, { type: 'connection', state: 'waiting', of: 10, hold: true }])
  assert.ok(held.connection)
  assert.equal(feed([{ type }], held).connection, null, type)
}
const held = feed([running, { type: 'connection', state: 'waiting', of: 10, hold: true }])
assert.equal(feed([{ type: 'run_state', status: 'idle' }], held).connection, null)

// Stop clears every streaming/testing overlay and is shown as a saved pause,
// rather than a failed run.
const active = { ...emptySession(), busy: true, liveFile: 'page.jsx', liveBuf: 'partial',
  drawing: { kind: 'prototype' }, browserFrame: { frame: 'png' }, e2eLive: { step: 2 },
  tests: { running: true, rows: [] }, e2eParallel: { active: true, lanes: [{ state: 'running' }] } }
const stopped = feed([{ type: 'cancelled', text: 'Stopped.' }], active)
assert.equal(stopped.busy, false)
assert.equal(stopped.liveFile, null)
assert.equal(stopped.liveBuf, '')
assert.equal(stopped.drawing, null)
assert.equal(stopped.browserFrame, null)
assert.equal(stopped.e2eLive, null)
assert.equal(stopped.tests.running, false)
assert.equal(stopped.e2eParallel.active, false)
assert.equal(stopped.workflowStatus, 'paused')
assert.equal(stopped.chat.at(-1).tone, 'info')

// A session starts without one, and it is part of what a session keeps per project.
assert.equal(emptySession().connection, null)

// The chat shows the card while the run is busy and the button asks the server; the server answers the route.
const chat = await readFile(new URL('../../studio/components/AgentChat.jsx', import.meta.url), 'utf8')
assert.match(chat, /<ConnectionNotice connection=\{connection\} project=\{project\}/)
assert.match(chat, /api\.connectionRetry\(project\)/)
assert.match(chat, /'Try again'/)
const api = await readFile(new URL('api.js', lib), 'utf8')
assert.match(api, /connectionRetry: \(project\) => post\('\/connection\/retry', \{ project \}\)/)

console.log('connection notice: ok')
