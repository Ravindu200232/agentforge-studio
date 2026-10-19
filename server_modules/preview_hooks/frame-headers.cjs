// Loaded into the Studio's PREVIEW process only (NODE_OPTIONS --require, set by preview_runtime.py).
//
// The Studio shows the running app in an iframe, and a well-secured app forbids exactly that
// (X-Frame-Options, CSP frame-ancestors). This lets this machine's pages frame the preview and
// nothing else: the app's own code, its tests and its deployment keep their strict headers.
//
// The desktop app shows the Studio at agentforge://app/...: another site than the app it frames (http://127.0.0.1:PORT), so a browser
// does not send the app its own SameSite=Lax cookies and nothing it signs in survives the next request. The preview is started told so
// (AGENTFORGE_FRAMED_CROSS_SITE) and each cookie the app sets is then made one a framed page may keep.
//
// Being another site also means the Studio cannot reach into the framed page: picking an element, following the page's address and
// its console all go through the Studio's bridge (preview-bridge.js), which this serves at BRIDGE_PATH and adds to every page the
// preview sends, as the first thing in its <head>. A page is asked for uncompressed so it can be added to.
'use strict'
const fs = require('node:fs')
const http = require('node:http')
const path = require('node:path')

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

// --- The Studio's bridge, in every page of the preview ----------------------------------------------------------------------

const BRIDGE_PATH = '/__agentforge/preview-bridge.js'
const TAG = Buffer.from(`<script src="${BRIDGE_PATH}" defer></script>`)
const INJECT = Symbol('agentforge.bridge')     // set on a page's response until the bridge is in it, or it turns out not to be a page
let BRIDGE = ''
try {
  BRIDGE = fs.readFileSync(path.join(__dirname, 'preview-bridge.js'), 'utf8')
} catch { /* no bridge: the preview works as before, without element picking */ }

/** A page the browser is loading (not data, a script, a picture or a client-side navigation's payload). */
function isPage(req) {
  return req.method === 'GET' && /text\/html/i.test(String(req.headers.accept || '')) && !req.headers.rsc
}

if (BRIDGE) {
  const emit = http.Server.prototype.emit
  http.Server.prototype.emit = function (event, req, res) {
    if (event === 'request' && req && res && req.headers) {
      try {
        if (String(req.url || '').split('?')[0] === BRIDGE_PATH) {
          res.writeHead(200, { 'content-type': 'text/javascript; charset=utf-8', 'cache-control': 'no-store' })
          res.end(BRIDGE)
          return true
        }
        if (isPage(req)) {
          delete req.headers['accept-encoding']
          res[INJECT] = true
        }
      } catch { /* the app answers exactly as it would */ }
    }
    return emit.apply(this, arguments)
  }
}

function headerIn(headers, name) {
  if (!headers || typeof headers !== 'object') return undefined
  if (Array.isArray(headers)) {
    for (let i = 0; i + 1 < headers.length; i += 2) if (String(headers[i]).toLowerCase() === name) return headers[i + 1]
    return undefined
  }
  const key = Object.keys(headers).find(k => k.toLowerCase() === name)
  return key === undefined ? undefined : headers[key]
}

function withoutLength(headers) {
  if (!headers || typeof headers !== 'object') return headers
  if (Array.isArray(headers)) {
    const out = []
    for (let i = 0; i + 1 < headers.length; i += 2) if (String(headers[i]).toLowerCase() !== 'content-length') out.push(headers[i], headers[i + 1])
    return out
  }
  return Object.fromEntries(Object.entries(headers).filter(([k]) => k.toLowerCase() !== 'content-length'))
}

/** Whether this response is still a plain HTML page the bridge can go into (`headers`: what writeHead is given). */
function stillAPage(res, headers) {
  if (!res[INJECT]) return false
  const type = headerIn(headers, 'content-type') ?? res.getHeader('content-type')
  const encoding = headerIn(headers, 'content-encoding') ?? res.getHeader('content-encoding')
  if (!/text\/html/i.test(String(type || '')) || (encoding && !/^identity$/i.test(String(encoding)))) res[INJECT] = false
  return Boolean(res[INJECT])
}

const HEAD = Buffer.from('<head')
const BODY = Buffer.from('<body')
const AFTER_HEAD = new Set([0x3e, 0x20, 0x09, 0x0a, 0x0d])        // '>' or white space: <head>, not <header>

/** The chunk with the bridge right after the page's <head ...>, or the chunk as it is. */
function withBridge(res, chunk, encoding) {
  if (!res[INJECT] || chunk == null || typeof chunk === 'function') return chunk
  if (!res.headersSent && !stillAPage(res)) return chunk
  const buffer = Buffer.isBuffer(chunk) ? chunk
    : typeof chunk === 'string' ? Buffer.from(chunk, typeof encoding === 'string' ? encoding : 'utf8')
      : chunk instanceof Uint8Array ? Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength) : null
  if (!buffer) return chunk
  const body = buffer.indexOf(BODY)
  for (let at = buffer.indexOf(HEAD); at >= 0; at = buffer.indexOf(HEAD, at + 1)) {
    if (body >= 0 && at > body) break
    if (!AFTER_HEAD.has(buffer[at + HEAD.length])) continue
    const close = buffer.indexOf(0x3e, at)
    if (close < 0) return chunk
    res[INJECT] = false
    // Headers not sent yet (an end() with the whole page): the length the app set is no longer the page's.
    if (!res.headersSent && res.hasHeader('content-length')) res.removeHeader('content-length')
    return Buffer.concat([buffer.subarray(0, close + 1), TAG, buffer.subarray(close + 1)])
  }
  if (body >= 0) res[INJECT] = false                                 // a page with no <head> of its own: left as it is
  return chunk
}

const writeHead = response.writeHead
response.writeHead = function (status, ...rest) {
  const at = typeof rest[0] === 'string' ? 1 : 0
  if (rest[at]) rest[at] = cleanHeaders(rest[at])
  try {
    if (stillAPage(this, rest[at])) {
      // The page grows by the bridge's tag: its length is no longer what the app said.
      if (rest[at]) rest[at] = withoutLength(rest[at])
      if (this.hasHeader('content-length')) this.removeHeader('content-length')
    }
  } catch {
    this[INJECT] = false
  }
  return writeHead.call(this, status, ...rest)
}

const write = response.write
response.write = function (chunk, encoding, callback) {
  let next = chunk
  try { next = withBridge(this, chunk, encoding) } catch { this[INJECT] = false }
  if (next === chunk) return write.apply(this, arguments)
  return write.call(this, next, typeof encoding === 'function' ? encoding : callback)
}

const end = response.end
response.end = function (chunk, encoding, callback) {
  let next = chunk
  try { next = withBridge(this, chunk, encoding) } catch { this[INJECT] = false }
  if (next === chunk) return end.apply(this, arguments)
  return end.call(this, next, typeof encoding === 'function' ? encoding : callback)
}
