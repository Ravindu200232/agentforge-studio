import { advance, emptyProgress } from './progress-model'
// One reducer owns all agent events, including events for a background project.
export const ROLES = ['designer', 'developer']

export function emptySession() {
  return { logs: [], chat: [], runStats: null, agentState: '', agentDetail: '', reasoning: false, busy: false,
    steps: {}, phases: [], files: {}, fileHistory: {}, readFiles: {}, activeFile: null, liveFile: null, liveBuf: '',
    progress: emptyProgress(), selection: [], approval: null, ask: null, drawing: null,
    browserFrame: null, browserConsole: [], question: null, undo: null, previewRoute: '/', draft: '',
    tests: { running: false, attempt: 0, rows: [], fixing: [], pass: 0, fail: 0, warn: 0 },
    e2eLive: null, qaReport: null, e2eParallel: { active: false, lanes: [] },
    prototypeStamp: 0, lastEventAt: 0, eventIds: [], runId: '', runStartedAt: 0, workKind: '', workflowStatus: 'idle' }
}

export const SESSION_FIELDS = Object.keys(emptySession())
export function captureSession(state) {
  const defaults = emptySession()
  return Object.fromEntries(SESSION_FIELDS.map(key => [key, state[key] ?? defaults[key]]))
}

export function reduceSession(session, event) {
  const s = session || emptySession()
  if (event.event_id && s.eventIds.includes(event.event_id)) return s
  const next = { ...s, eventIds: event.event_id ? [...s.eventIds.slice(-1199), event.event_id] : s.eventIds }
  const at = event.at || Date.now()
  next.lastEventAt = Math.max(s.lastEventAt || 0, at)
  // The server is the durable source of truth, but an open Studio must not
  // drop an earlier turn simply because a long run is still arriving.
  const log = (level, text) => { next.logs = [...s.logs, { level, text, at }] }
  const chat = entry => { next.chat = [...s.chat, { at, ...entry }] }
  switch (event.type) {
    case 'log': log(event.level, event.text); break
    case 'user_msg': chat({ role: 'user', text: event.text }); break
    case 'agent_msg': chat({ role: 'assistant', text: event.text, title: event.title, kind: event.kind, design: event.design }); break
    case 'run_state':
      next.runId = event.run_id || s.runId
      next.busy = ['running', 'queued'].includes(event.status)
      next.workflowStatus = event.status
      next.runStartedAt = next.busy ? at : 0
      if (next.busy) {
        // A new request must not inherit the previous request's generated
        // total while it is waiting for the first provider usage report.
        next.runStats = { ...(s.runStats || {}), at, turn_started_at: at,
          turn_tokens: 0, sent: 0, received: 0 }
      }
      break
    case 'agent_state':
      next.agentState = event.state || ''; next.agentDetail = event.detail || ''; next.reasoning = Boolean(event.thinking); break
    case 'memory': next.runStats = event; break
    case 'step': next.steps = { ...s.steps, [event.step]: event.status }; break
    case 'progress': next.progress = advance(s.progress, event.step, event.pct, at); break
    case 'phase': {
      const phaseKey = `${event.kind || 'run'}:${event.key || event.title || event.phase}`
      next.phases = [...s.phases.filter(p =>
        `${p.kind || 'run'}:${p.key || p.title || p.phase}` !== phaseKey), event]
      const previous = s.chat.findIndex(row => row.role === 'stage' && row.phaseKey === phaseKey &&
        row.runId === s.runId)
      const stage = { role: 'stage', phaseKey, runId: s.runId,
        title: event.title || event.key || 'Stage', status: event.status || 'active',
        detail: event.detail || '', number: event.phase, group: event.kind || 'run' }
      if (previous < 0) chat(stage)
      else next.chat = s.chat.map((row, index) => index === previous ? { ...row, ...stage } : row)
      break
    }
    case 'file': {
      if (event.agent === 'designer') next.prototypeStamp = at
      if (event.content !== undefined) {
        const prev = s.files[event.name] || event.old_content || ''
        next.files = { ...s.files, [event.name]: event.content }
        next.fileHistory = {
          ...(s.fileHistory || {}),
          [event.name]: {
            oldContent: event.old_content !== undefined ? event.old_content : prev,
            newContent: event.content,
            note: event.note || (prev ? 'patched' : 'written'),
            at,
          },
        }
      }
      break
    }
    case 'file_read': {
      if (event.name && event.content !== undefined) {
        next.readFiles = { ...(s.readFiles || {}), [event.name]: event.content }
      }
      break
    }
    case 'stream_start': next.liveFile = event.file; next.liveBuf = ''; break
    case 'stream': next.liveBuf = (s.liveBuf + (event.token || '')).slice(-200000); break
    case 'stream_end': next.files = { ...s.files, [event.file]: event.content || '' }; next.liveFile = null; next.liveBuf = ''; break
    // Each question goes where it is answered: a free-form question is a turn
    // in the chat, a drawing is looked at in the preview, and everything else
    // is a dialog. The same split as `route()` in lib/ws.js, which is what
    // recovers one after a reload - when the two disagreed, a question shown
    // live and a question recovered went to different places.
    case 'approval':
      if (event.kind === 'question') next.ask = event
      else if (event.kind === 'prototype') next.drawing = event
      else next.approval = event
      break
    case 'approval_resolved': next.approval = null; next.ask = null; next.drawing = null; break
    case 'browser_frame': next.browserFrame = event.frame ? event : null; break
    case 'undo_point': next.undo = event; break
    case 'ask': next.question = event; break
    case 'test_start': next.tests = { ...emptySession().tests, running: true, startedAt: at }; break
    case 'test_run': next.tests = { ...s.tests, running: true, attempt: event.attempt }; break
    case 'test_result': {
      const rows = [...s.tests.rows.slice(-999), { ...event, at }]
      next.tests = { ...s.tests, rows, pass: rows.filter(r => ['pass', 'passed'].includes(r.status)).length,
        fail: rows.filter(r => ['fail', 'failed'].includes(r.status)).length,
        warn: rows.filter(r => r.status === 'warn').length }
      chat({ role: 'test_result', title: event.msg || 'Test result',
        detail: event.detail || '', status: event.status })
      break
    }
    case 'test_fixing': next.tests = { ...s.tests, fixing: [...s.tests.fixing, event] }; break
    case 'e2e_parallel': {
      const current = s.e2eParallel
      if (event.state === 'start') next.e2eParallel = { active: true, lanes: [],
        workers: Math.max(1, Math.min(4, Number(event.workers) || 1)), waves: Number(event.waves) || 0, wave: 0 }
      else if (event.state === 'wave') next.e2eParallel = { ...current, active: true, lanes: [],
        wave: Number(event.wave) || 0, waves: Number(event.waves) || current.waves }
      else if (event.state === 'done') next.e2eParallel = { ...current, active: false }
      break
    }
    // A request typed in the chat, at the stage it has reached. The plan is one card in the stream that
    // follows the request; a newer plan for the same request replaces the older one on screen.
    case 'change': {
      if (!event.plan) break
      const card = { role: 'change', changeId: event.change_id, revision: event.revision || 0, status: event.status,
        plan: event.plan, request: event.request, summary: event.summary, error: event.error, version: event.version,
        flow: event.flow || '', target: event.target || '' }
      const rows = s.chat.map(row => row.role === 'change' && row.changeId === event.change_id
        && row.revision < card.revision && ['proposed', 'approved'].includes(row.status)
        ? { ...row, status: 'superseded' } : row)
      const at1 = rows.findIndex(row => row.role === 'change' && row.changeId === event.change_id && row.revision === card.revision)
      next.chat = at1 < 0 ? [...rows, { at, ...card }]
        : rows.map((row, index) => index === at1 ? { ...row, ...card } : row)
      break
    }
    case 'prototype': next.prototypeStamp = at; break
    case 'e2e_event': {
      const current = s.e2eParallel
      const lane = Math.max(1, Math.min(4, Number(event.lane) || 1))
      const lanes = [...current.lanes]
      lanes[lane - 1] = { ...lanes[lane - 1], ...event, lane, updatedAt: at }
      next.e2eParallel = { ...current, lanes, active: current.active || event.state !== 'journey_done',
        workers: Math.max(current.workers || 0, lane) }
      next.e2eLive = { ...event, at }
      // A journey on screen is a test running, whether or not a stage announced it.
      next.tests = { ...s.tests, running: true, startedAt: s.tests.startedAt || at }
      break
    }
    // The run whose browser was on screen is over: give the preview back.
    case 'e2e_done': case 'test_done':
      next.tests = { ...s.tests, running: false }
      next.e2eLive = null; next.browserFrame = null
      next.e2eParallel = { ...s.e2eParallel, active: false }
      break
    case 'done': case 'error': case 'cancelled':
      next.busy = false; next.agentState = ''; next.liveFile = null; next.liveBuf = ''
      next.browserFrame = null; next.approval = null; next.ask = null
      next.tests = { ...s.tests, running: false }
      next.e2eParallel = { ...s.e2eParallel, active: false }; next.reasoning = false
      next.workflowStatus = event.type === 'done' ? 'completed' : event.type === 'cancelled' ? 'paused' : 'failed'
      if (event.type !== 'done') chat({ role: 'assistant', tone: 'bad', title: event.type === 'cancelled' ? 'Paused' : 'Run failed',
        text: event.text || 'Your files and conversation are saved. Continue when ready.' })
      break
    default: break
  }
  return next
}
