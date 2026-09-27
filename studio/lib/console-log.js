import { useStore } from './store'
import { captureFrameConsole } from './console-capture'

/** Capture preview browser evidence for bug reports. */

const MAX_ENTRIES = 80
const MAX_REPORT_CHARS = 6000
const MAX_TEXT = 400


// The same vocabulary as `reproduce._NOISE`, and for the same reason.
const NOISE = new RegExp([
  '_next/(?:static|hmr)', '/_next/webpack', 'hot-update',
  'WebSocket connection to .*_next', 'React DevTools', 'favicon\\.ico',
  'Fast Refresh', '\\[HMR\\]', 'webpack-internal', 'turbopack',
  'forward-logs', '__agentforge',
].join('|'), 'i')


function owner(project, role) {
  const state = useStore.getState()
  return { project: project || state.project, role: role || state.agentRole, epoch: state.accountEpoch }
}
function entriesFor(scope) {
  const state = useStore.getState()
  if (scope.epoch !== state.accountEpoch) return []
  return (state.project === scope.project && state.agentRole === scope.role
    ? state.browserConsole : state.projectSessions[scope.project]?.[scope.role]?.browserConsole) || []
}
let observer = null

export function observeConsole(callback) { observer = callback }
export function recordConsole(kind, text, project, role) { push(kind, text, owner(project, role)) }


function push(kind, text, scope = owner()) {
  if (scope.epoch !== useStore.getState().accountEpoch) return
  let entries = entriesFor(scope)
  const line = String(text || '').replace(/\s+/g, ' ').trim().slice(0, MAX_TEXT)
  if (!line || NOISE.test(line)) return
  observer?.(kind, line)

  const last = entries[entries.length - 1]
  if (last && last.kind === kind && last.text === line) {
    entries = [...entries.slice(0, -1), { ...last, count: last.count + 1 }]
  } else entries = [...entries.slice(-(MAX_ENTRIES - 1)), { kind, text: line, count: 1, at: Date.now() }]
  useStore.getState().patchAgentSession(scope.project, scope.role, { browserConsole: entries })
}


/** Start recording in this frame's document. */
export function watchFrame(frame, project, role) {
  const scope = owner(project, role)
  captureFrameConsole(frame, (kind, text) => push(kind, text, scope))
}


/** Clear evidence before the next run. */
export function forgetConsole() {
  const scope = owner()
  useStore.getState().patchAgentSession(scope.project, scope.role, { browserConsole: [] })
}


/** The evidence as prose, or "" when the browser saw nothing wrong. */
export function consoleReport() {
  const entries = entriesFor(owner())
  if (!entries.length) return ''

  const line = (e) => `  ${e.text}${e.count > 1 ? `  (×${e.count})` : ''}`
  const parts = []
  const uncaught = entries.filter(e => e.kind === 'uncaught')
  const requests = entries.filter(e => e.kind === 'request')
  const logged = entries.filter(e => e.kind === 'error' || e.kind === 'warn')

  if (uncaught.length) {
    parts.push('Uncaught in the browser:\n' + uncaught.map(line).join('\n'))
  }
  if (requests.length) {
    parts.push('Requests that failed:\n' + requests.map(line).join('\n'))
  }
  if (logged.length) {
    parts.push('The browser console:\n' + logged.map(line).join('\n'))
  }
  if (!parts.length) return ''

  // Newest last, and the tail is the part that matters.
  const body = parts.join('\n\n')
  return body.length > MAX_REPORT_CHARS
    ? '…\n' + body.slice(-MAX_REPORT_CHARS)
    : body
}
