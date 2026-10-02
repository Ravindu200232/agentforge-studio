
import { useStore } from './store'
import { api, API, HTTP_FALLBACK, getAuthToken } from './api'
import { refreshQaReport } from './qa-results'

// What each outgoing message is, in the terms the overlay presents.
const WORK_KIND = {
  agent_build: 'build',
  agent_update: 'edit', agent_resume: 'build',
  feature: 'feature',
  element_edit: 'select',
}

let sock = null
let retry = null
let heartbeat = null
let lastEdit = null

// Send periodic heartbeat pings to keep WebSocket connections alive through proxies and tunnels.
const HEARTBEAT_MS = 25000

/** Resend the last edit with an answer or instruction. */
export function answerQuestion(prompt) {
  const store = useStore.getState()
  const base = lastEdit?.project === store.project && lastEdit?.agent === store.agentRole ? lastEdit : null
  useStore.setState({ question: null })
  if (!base) return false
  useStore.getState().addLog('INFO', `Edit: ${prompt}`)
  useStore.getState().setBusy(true)
  send({ ...base, prompt: `${base.prompt}\n\nScope clarification: ${prompt}` })
  return true
}

/** Sends the user's typed response to answer a pending agent question. */
export function answerAsk(reply) {
  const ask = useStore.getState().ask
  if (!ask) return false
  useStore.getState().setAsk(null)
  api.decide({ id: ask.id, project: ask.project, decision: 'answer', reply })
     .catch(e => useStore.getState().addLog('WARN', `Could not send that answer — ${e.message}`))
  return true
}

/**
 * The answer to a question that asks for a value (a password, a connection string): sent from the question's own
 * private box, never echoed into the chat. Resolves with what the server said, so the card can show why a value was
 * not accepted; the question stays open until one is.
 */
export async function answerValue(value) {
  const ask = useStore.getState().ask
  if (!ask) return { ok: false, detail: 'That question is no longer waiting.' }
  const result = await api.decide({ id: ask.id, project: ask.project, decision: 'answer', reply: value })
  if (result?.ok === false) return result
  useStore.getState().setAsk(null)
  useStore.getState().pushChat({ role: 'user', text: `Saved ${ask.variable}.`, at: Date.now() })
  return { ok: true }
}

/** One of the question's own options, taken as the answer instead of a value. */
export async function answerOption(label) {
  const ask = useStore.getState().ask
  if (!ask) return false
  useStore.getState().setAsk(null)
  useStore.getState().pushChat({ role: 'user', text: label, at: Date.now() })
  api.decide({ id: ask.id, project: ask.project, decision: 'answer', reply: label, via: 'option' })
     .catch(e => useStore.getState().addLog('WARN', `Could not send that answer — ${e.message}`))
  return true
}

/** Hand the decision back to the agent, which then says what it assumed. */
export function declineAsk() {
  const ask = useStore.getState().ask
  if (!ask) return false
  useStore.getState().setAsk(null)
  api.decide({ id: ask.id, project: ask.project, decision: 'default' })
     .catch(e => useStore.getState().addLog('WARN', `Could not send that — ${e.message}`))
  return true
}

/** Sends feedback to request a revision for the current wireframe drawing. */
export function reviseDrawing(feedback) {
  const drawing = useStore.getState().drawing
  if (!drawing) return false
  useStore.getState().setDrawing(null)
  api.decide({ id: drawing.id, decision: 'revise', feedback })
     .catch(e => useStore.getState().addLog('WARN', `Could not send that back — ${e.message}`))
  return true
}

function wsUrl() {
  if (typeof location === 'undefined') return 'ws://127.0.0.1:7825'
  // Route WebSocket connections through the studio host address.
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/__agentforge/ws`
}

/** Dispatches incoming questions and decisions to their appropriate UI handlers. */
function route(question) {
  const store = useStore.getState()
  if (question?.kind === 'prototype') store.setDrawing(question)
  else if (question?.kind === 'question') store.setAsk(question)
  else if (question?.kind === 'plan') {
    api.decide({ id: question.id, decision: 'accept' }).catch(() => {})
  }
  else store.setApproval(question)
}

async function recoverPendingDecision() {
  try {
    const { pending } = await api.decisions()
    const question = (pending || [])[0]
    const store = useStore.getState()
    if (question && question.project === store.project && (!question.agent || question.agent === store.agentRole) && !store.approval && !store.ask && !store.drawing) route(question)
  } catch {
    // An older backend has no such endpoint; the announcement is all there is.
  }
}

/** The desktop app's own channel to its backend (desktop/preload.js), when the studio runs inside it. */
const desktop = () => (typeof window !== 'undefined' ? window.agentforgeDesktop : null) || null
let desktopOff = null

/** In the desktop app there is no socket and no port: the backend's events arrive over the app itself. */
function connectDesktop(bridge) {
  desktopOff?.()
  const offEvent = bridge.onEvent(handle)
  const offStatus = bridge.onStatus?.(status => {
    if (status === 'ready') {
      useStore.getState().setStatus('live', 'ready')
      const project = useStore.getState().project
      if (project) api.workflow(project).then(snapshot => useStore.getState().restoreProject(snapshot)).catch(() => {})
      recoverPendingDecision()
    } else {
      useStore.getState().setStatus('disconnected', status === 'restarting' ? 'restarting the engine…' : String(status))
    }
  })
  desktopOff = () => { offEvent?.(); offStatus?.() }
  useStore.getState().setStatus('live', 'ready')
  const project = useStore.getState().project
  if (project) api.workflow(project).then(snapshot => useStore.getState().restoreProject(snapshot)).catch(() => {})
  recoverPendingDecision()
  window.__studioFeed = handle
  return disconnect
}

export function connect() {
  if (typeof window === 'undefined') return
  const bridge = desktop()
  if (bridge) return connectDesktop(bridge)
  const s = useStore.getState()

  // Close whatever is already open FIRST.
  if (sock) {
    try {
      sock.onclose = null
      sock.onmessage = null
      sock.onerror = null
      sock.close()
    } catch { }
    sock = null
  }
  clearTimeout(retry)
  clearInterval(heartbeat)

  try {
    sock = new WebSocket(wsUrl())
  } catch {
    s.setStatus('disconnected', 'no socket')
    return
  }
  const mine = sock
  // Every handler checks it is still the current socket before it speaks.
  sock.onopen = () => {
    if (mine !== sock) return
    useStore.getState().setStatus('live', 'ready')
    clearInterval(heartbeat)
    heartbeat = setInterval(() => {
      if (mine !== sock || sock.readyState !== 1) return
      try { sock.send(JSON.stringify({ type: 'ping' })) } catch { }
    }, HEARTBEAT_MS)
    const project = useStore.getState().project
    if (project) api.workflow(project).then(snapshot => useStore.getState().restoreProject(snapshot)).catch(() => {})
    recoverPendingDecision()
  }
  sock.onclose = (event) => {
    if (mine !== sock) return
    clearInterval(heartbeat)
    // 4401: nobody is signed in on this socket. Reconnecting cannot fix that;
    // signing in does, and that calls connect() again.
    if (event?.code === 4401) {
      sock = null
      useStore.getState().setStatus('disconnected', 'sign in to continue')
      return
    }
    useStore.getState().setStatus('disconnected', 'reconnecting…')
    clearTimeout(retry)
    retry = setTimeout(connect, 3000)
  }
  sock.onerror = () => {
    if (mine === sock) useStore.getState().setStatus('disconnected', 'error')
  }
  sock.onmessage = (e) => {
    if (mine !== sock) return
    let m
    try { m = JSON.parse(e.data) } catch { return }
    handle(m)
  }

  if (typeof window !== 'undefined') window.__studioFeed = handle
  return disconnect
}

export function disconnect() {
  desktopOff?.()
  desktopOff = null
  clearTimeout(retry)
  clearInterval(heartbeat)
  retry = heartbeat = null
  if (sock) {
    sock.onopen = sock.onclose = sock.onerror = sock.onmessage = null
    sock.close()
    sock = null
  }
}

export function send(obj) {
  const current = useStore.getState()
  const agent = obj.agent || current.agentRole || 'developer'
  obj = { ...obj, agent }
  if (obj.project) current.applyProjectEvent({ type: 'run_state', project: obj.project, agent, status: 'queued' })
  if (obj && obj.type) {
    useStore.getState().setWorkKind(WORK_KIND[obj.type] || 'build')
    // Whose run this is. The project on screen can change while it works.
    if (obj.project) useStore.getState().setBusyProject(obj.project)
  }
  if (obj && obj.prompt !== undefined) {
    lastEdit = obj
    useStore.setState({ question: null })
  }
  if (desktop()) {
    desktop().send(obj)
    return
  }
  if (sock && sock.readyState === 1) {
    sock.send(JSON.stringify(obj))
    return
  }
  const ep = HTTP_FALLBACK[obj.type]
  if (!ep) {
    useStore.getState().addLog('WARN',
      `not sent — the socket is down and ${obj.type} has no fallback route`)
    return
  }
  fetch(API + ep, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}) },
    body: JSON.stringify(obj),
  }).then(async response => { if (!response.ok) throw new Error((await response.json()).error || 'Request failed') }).catch(err => {
    useStore.getState().applyProjectEvent({ type: 'error', project: obj.project, agent, text: `Send failed: ${err.message}` })
  })
}

function handle(m) {
  const s = useStore.getState()
  // Contracts: approval?.id === m.id | browser_frame
  if (m.type === 'runtime_state') { s.setRuntime(m); return }
  if (m.type === 'project') {
    // Only the unnamed new run can adopt its server-assigned project.
    if (!s.project && s.busy) useStore.setState({ project: m.project, busyProject: m.project })
    s.bumpProjects()
    return
  }
  if (!m.project) return
  // What the app's tests are doing is watched in the Preview, so the Preview comes up for the
  // first picture of a run (once: someone who then goes elsewhere is left there), and for a
  // finished build, so the app is what they see.
  if (m.type === 'show_preview') {
    if (m.project === s.project && !s.drawing) {
      // The project list has not caught up with the build yet, and the Preview is refused until it has.
      useStore.setState(st => ({ buildAvailability: { ...st.buildAvailability, [m.project]: true } }))
    }
    return
  }
  // A live picture arrives ten times a second: it goes straight to the screen, not through the
  // session reducer (which copies the chat and the logs for every event). The pointer arrives on
  // its own and is kept across pictures.
  if (m.type === 'browser_frame' && m.frame) {
    if (m.project === s.project) {
      useStore.setState(st => ({ browserFrame: { ...m, cursor: st.browserFrame?.cursor, bg: m.bg || st.browserFrame?.bg } }))
    }
    return
  }
  if (m.type === 'browser_cursor') {
    if (m.project === s.project) {
      useStore.setState(st => st.browserFrame
        ? { browserFrame: { ...st.browserFrame, cursor: { ...m.cursor, at: Date.now() }, bg: m.bg || st.browserFrame.bg } }
        : {})
    }
    return
  }
  s.applyProjectEvent(m)
  if (['done', 'cancelled', 'error'].includes(m.type)) {
    s.bumpProjects()
    api.runtime(m.project).then(runtime => useStore.getState().setRuntime(runtime)).catch(() => {})
    if (m.agent !== 'designer' && m.type === 'done') {
      refreshQaReport(m.project).catch(() => {})
    }
  }
}
