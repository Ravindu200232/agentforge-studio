/**
 * Which address this browser can actually load a project's app from.
 *
 * On the machine AgentForge runs on, that is the app's own local host name.
 * From anywhere else - a phone, another computer - that name means nothing, so
 * the app is loaded from the address AgentForge published for it. Until there
 * is one, there is nowhere to load it from and this answers "".
 */
export function previewHref(runtime) {
  if (!runtime?.previewUrl) return ''
  if (typeof location === 'undefined') return runtime.previewUrl
  if (onThisMachine()) return sameSite(runtime.previewUrl)
  return runtime.publicUrl || ''
}

const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

export function onThisMachine() {
  if (typeof location === 'undefined') return true
  return LOOPBACK.has(location.hostname)
}

/**
 * The app on the same host name the Studio was opened on. `localhost` and `127.0.0.1` are two
 * different sites to a browser: an app framed from the other one has its sign-in cookie
 * (SameSite=Lax) refused, so every sign-in is lost on the next request and nothing it saves
 * gets through. Both names reach the same machine, so only the name changes.
 */
function sameSite(url) {
  try {
    const target = new URL(url)
    if (!LOOPBACK.has(target.hostname) || target.hostname === location.hostname) return url
    target.hostname = location.hostname
    return target.href
  } catch {
    return url
  }
}

/** Does this app still need an address of its own before it can be shown? */
export function needsAddress(runtime) {
  return Boolean(runtime?.previewUrl) && !previewHref(runtime)
}
