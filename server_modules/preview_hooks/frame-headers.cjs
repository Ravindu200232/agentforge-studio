// Loaded into the Studio's PREVIEW process only (NODE_OPTIONS --require, set by preview_runtime.py).
//
// The Studio shows the running app in an iframe, and a well-secured app forbids exactly that
// (X-Frame-Options, CSP frame-ancestors). This lets this machine's pages frame the preview and
// nothing else: the app's own code, its tests and its deployment keep their strict headers.
'use strict'
const http = require('node:http')

const ANCESTORS = "'self' http://localhost:* http://127.0.0.1:*"
const CSP = /^content-security-policy(-report-only)?$/i

/** The value to send for `name`, or `undefined` when the header must not be sent at all. */
function adjust(name, value) {
  const key = String(name)
  if (/^x-frame-options$/i.test(key)) return undefined
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
