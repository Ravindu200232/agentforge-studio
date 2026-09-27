// Browser-only capture, shared by Studio and the standalone preview bridge.
function consoleValue(value) {
  if (typeof value === 'string') return value
  if (value && typeof value.stack === 'string') return value.stack
  if (value && typeof value.message === 'string') return value.message
  try { return JSON.stringify(value) } catch { return String(value) }
}

export function captureFrameConsole(frame, report) {
  let w
  try { w = frame?.contentWindow; if (!w || w.__agentforgeWatched) return; w.__agentforgeWatched = true }
  catch { return }
  try {
    for (const level of ['error', 'warn']) {
      const original = w.console[level].bind(w.console)
      w.console[level] = (...args) => {
        try { report(level, args.map(consoleValue).join(' ')) } catch {}
        original(...args)
      }
    }
    w.addEventListener('error', e => report('uncaught', e.error?.stack || e.message))
    w.addEventListener('unhandledrejection', e => report('uncaught', 'in a promise: ' + consoleValue(e.reason)))
    const fetch0 = w.fetch
    if (typeof fetch0 === 'function') w.fetch = async function (...args) {
      const res = await fetch0.apply(this, args)
      try {
        if (!res.ok) {
          const url = args[0]?.url || String(args[0] || '')
          const method = (args[1]?.method || args[0]?.method || 'GET').toUpperCase()
          let body = ''
          try { body = (await res.clone().text()).slice(0, 300) } catch {}
          report('request', `${method} ${url} → ${res.status}${body ? ' — ' + body : ''}`)
        }
      } catch {}
      return res
    }
  } catch { /* The frame may navigate during installation. */ }
}
