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
  if (typeof location === 'undefined' || onThisMachine()) return runtime.previewUrl
  return runtime.publicUrl || ''
}

export function onThisMachine() {
  if (typeof location === 'undefined') return true
  const here = location.hostname
  return here === 'localhost' || here === '127.0.0.1' || here === '[::1]' || here === '::1'
}

/** Does this app still need an address of its own before it can be shown? */
export function needsAddress(runtime) {
  return Boolean(runtime?.previewUrl) && !previewHref(runtime)
}
