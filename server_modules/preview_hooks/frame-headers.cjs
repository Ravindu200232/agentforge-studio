// Loaded into the Studio's PREVIEW process only (NODE_OPTIONS --require, set by preview_runtime.py).
//
// The Studio shows the running app in an iframe, and a well-secured app forbids exactly that
// (X-Frame-Options, CSP frame-ancestors). This lets this machine's pages frame the preview and
// nothing else: the app's own code, its tests and its deployment keep their strict headers.
//
// The desktop app shows the Studio at agentforge://app/...: another site than the app it frames (http://127.0.0.1:PORT), so a browser
// does not send the app its own SameSite=Lax cookies and nothing it signs in survives the next request. The preview is started told so
// (AGENTFORGE_FRAMED_CROSS_SITE) and each cookie the app sets is then made one a framed page may keep.
'use strict'
const http = require('node:http')

const ANCESTORS = "'self' http://localhost:* http://127.0.0.1:* agentforge:"
const CSP = /^content-security-policy(-report-only)?$/i
const COOKIE = /^set-cookie$/i
const CROSS_SITE = process.env.AGENTFORGE_FRAMED_CROSS_SITE === '1'

/** A cookie a page framed from another site is allowed to keep: SameSite=None, which needs Secure (localhost counts as secure). */
function framed(cookie) {
  const text = String(cookie).replace(/;\s*SameSite=[^;]*/gi, '')
  return (/;\s*Secure\s*(;|$)/i.test(text) ? text : `${text}; Secure`) + '; SameSite=None'
}

/** The value to send for `name`, or `undefined` when the header must not be sent at all. */
function adjust(name, value) {
  const key = String(name)
  if (/^x-frame-options$/i.test(key)) return undefined
  if (CROSS_SITE && COOKIE.test(key)) return Array.isArray(value) ? value.map(framed) : framed(value)
  if (CSP.test(key)) {
    const text = Array.isArray(value) ? value.join(', ') : String(value)
    return text.replace(/frame-ancestors[^;,]*/i, `frame-ancestors ${ANCESTORS}`)
  }
  return value
}

const response = http.ServerResponse.prototype

const setHeader = response.setHeader
response.setHeader = function (name, value) {
  const next = adjust(name, value)
  return next === undefined ? this : setHeader.call(this, name, next)
}

const appendHeader = response.appendHeader
if (appendHeader) {
  response.appendHeader = function (name, value) {
    const next = adjust(name, value)
    return next === undefined ? this : appendHeader.call(this, name, next)
  }
}

/** `writeHead(status, [message], headers)`: headers as an object, or as a flat [name, value, ...] list. */
function cleanHeaders(headers) {
  if (!headers || typeof headers !== 'object') return headers
  if (Array.isArray(headers)) {
    const out = []
    for (let i = 0; i + 1 < headers.length; i += 2) {
      const next = adjust(headers[i], headers[i + 1])
      if (next !== undefined) out.push(headers[i], next)
    }
    return out
  }
  const out = {}
  for (const [name, value] of Object.entries(headers)) {
    const next = adjust(name, value)
    if (next !== undefined) out[name] = next
  }
  return out
}

const writeHead = response.writeHead
response.writeHead = function (status, ...rest) {
  const at = typeof rest[0] === 'string' ? 1 : 0
  if (rest[at]) rest[at] = cleanHeaders(rest[at])
  return writeHead.call(this, status, ...rest)
}
