// AgentForge's AI engine: a Cloudflare Worker between the app and ollama.com.
//
// The ollama.com API key lives here, as the Worker secret OLLAMA_API_KEY, and nowhere in the app: an installed
// AgentForge sends its requests to this Worker with the app token (the secret APP_TOKEN), and the Worker sends them
// on to ollama.com with the key. The app token is not a secret in the same way (it ships in every copy of the app),
// so the Worker also limits how fast any one address may call it, and only the API the app uses is passed through.
// A leaked or abused setup is fixed here, by changing a secret, with no new release of the app.
//
// The same Worker is also the sign-in broker for Supabase (see "Sign in with Supabase" below): the one OAuth app the
// publisher registered keeps its client secret here, so nobody who installs AgentForge ever creates an OAuth app.

const UPSTREAM = 'https://ollama.com'

// What the app calls: chat (and its model details and list), and the web search and fetch tools.
const ALLOWED = new Set([
  'POST /api/chat',
  'POST /api/generate',
  'POST /api/show',
  'GET /api/tags',
  'GET /api/version',
  'POST /api/web_search',
  'POST /api/web_fetch',
])

// Request and response headers passed through; everything else (cookies, the app token itself) stays here.
const FORWARD = ['content-type', 'accept', 'user-agent']

function answer(status, error) {
  return new Response(JSON.stringify({ error }), { status, headers: { 'content-type': 'application/json' } })
}

function sameToken(given, expected) {
  // Compared in full every time, so how long a wrong token takes to refuse says nothing about the right one.
  if (!expected || given.length !== expected.length) return false
  let diff = 0
  for (let i = 0; i < given.length; i++) diff |= given.charCodeAt(i) ^ expected.charCodeAt(i)
  return diff === 0
}

async function tooMany(request, env) {
  if (!env.LIMITER) return null
  const caller = request.headers.get('cf-connecting-ip') || 'unknown'
  const { success } = await env.LIMITER.limit({ key: caller })
  return success ? null : answer(429, 'too many requests from this address: wait a minute and try again')
}

// --- Sign in with Supabase -------------------------------------------------------------------------------------------
//
// Supabase's token endpoint wants the OAuth app's client secret, and a secret cannot ship inside an app everyone
// installs. So the publisher registers ONE Supabase OAuth app, whose only callback URL is this Worker's
// /oauth/supabase/callback, and the secret stays here (SUPABASE_CLIENT_SECRET; the client id, which is public, is the
// variable SUPABASE_CLIENT_ID). The flow, with nothing stored in the Worker:
//
//   start     the app asks for an authorize URL, sending its flow id, a PKCE challenge and the local address the
//             browser should come back to. The state in that URL is signed, so it can only have come from here.
//   callback  Supabase sends the browser here with the code; the signed state is checked and the browser is sent on
//             to the app's local address. The app keeps the PKCE verifier, so a code seen on the way is no use.
//   token     the app trades the code (or later a refresh token) for tokens; the Worker adds the client secret.

const SUPABASE_AUTHORIZE = 'https://api.supabase.com/v1/oauth/authorize'
const SUPABASE_TOKEN = 'https://api.supabase.com/v1/oauth/token'
const STATE_LIFETIME_MS = 10 * 60 * 1000

// Only the app on this same computer may be sent back to: `localhost` (Supabase's authorize endpoint refuses a
// loopback IP), any port, and the sign-in callback path the app serves.
const LOCAL_RETURN = /^http:\/\/localhost:\d{2,5}(\/[A-Za-z0-9_-]+)*\/supabase-oauth\/callback$/
const FLOW_ID = /^[A-Za-z0-9_-]{8,100}$/
const CHALLENGE = /^[A-Za-z0-9_-]{43,128}$/
const GRANTS = new Set(['authorization_code', 'refresh_token'])

const encoder = new TextEncoder()

function base64url(bytes) {
  let text = ''
  for (const byte of new Uint8Array(bytes)) text += String.fromCharCode(byte)
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function unbase64url(text) {
  const padded = text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (text.length % 4)) % 4)
  return atob(padded)
}

async function signature(env, payload) {
  const key = await crypto.subtle.importKey(
    'raw', encoder.encode(`agentforge-oauth-state:${env.SUPABASE_CLIENT_SECRET}`),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  )
  return base64url(await crypto.subtle.sign('HMAC', key, encoder.encode(payload)))
}

async function signState(env, flow, returnTo) {
  const payload = base64url(encoder.encode(JSON.stringify({ f: flow, r: returnTo, t: Date.now() })))
  return `${payload}.${await signature(env, payload)}`
}

// The flow id and return address a state carries, or null when it was not signed here or has lapsed.
async function readState(env, state) {
  const [payload, given, extra] = String(state || '').split('.')
  if (!payload || !given || extra !== undefined) return null
  if (!sameToken(given, await signature(env, payload))) return null
  try {
    const { f, r, t } = JSON.parse(unbase64url(payload))
    if (typeof t !== 'number' || Date.now() - t > STATE_LIFETIME_MS || t > Date.now() + 60000) return null
    if (!FLOW_ID.test(f) || !LOCAL_RETURN.test(r)) return null
    return { flow: f, returnTo: r }
  } catch {
    return null
  }
}

function callbackUrl(env, url) {
  return `${(env.PUBLIC_URL || url.origin).replace(/\/$/, '')}/oauth/supabase/callback`
}

function configured(env) {
  return Boolean(env.SUPABASE_CLIENT_ID && env.SUPABASE_CLIENT_SECRET)
}

function page(status, message) {
  const body = `<!doctype html><html><head><meta charset="utf-8"><title>AgentForge</title></head>`
    + `<body style="font:16px system-ui,sans-serif;padding:2.5rem;color:#16181d"><p>${message}</p></body></html>`
  return new Response(body, {
    status,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' },
  })
}

async function jsonBody(request) {
  try {
    const body = await request.json()
    return body && typeof body === 'object' ? body : {}
  } catch {
    return {}
  }
}

async function supabaseStart(request, env, url) {
  const { flow_id: flow, challenge, return_to: returnTo } = await jsonBody(request)
  if (!FLOW_ID.test(String(flow)) || !CHALLENGE.test(String(challenge)) || !LOCAL_RETURN.test(String(returnTo))) {
    return answer(400, 'that sign-in request is not valid')
  }
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: env.SUPABASE_CLIENT_ID,
    redirect_uri: callbackUrl(env, url),
    scope: 'all',
    state: await signState(env, flow, returnTo),
    code_challenge: challenge,
    code_challenge_method: 'S256',
  })
  return new Response(JSON.stringify({ authorize_url: `${SUPABASE_AUTHORIZE}?${params}` }), {
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  })
}

async function supabaseCallback(request, env, url) {
  const state = await readState(env, url.searchParams.get('state'))
  if (!state) return page(400, 'This sign-in link is not valid or has expired. Start the sign-in again from AgentForge.')
  const back = new URL(state.returnTo)
  back.searchParams.set('state', state.flow)
  const error = url.searchParams.get('error_description') || url.searchParams.get('error')
  if (error) back.searchParams.set('error', error.slice(0, 300))
  else back.searchParams.set('code', url.searchParams.get('code') || '')
  return new Response(null, {
    status: 302,
    headers: { location: back.toString(), 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' },
  })
}

async function supabaseToken(request, env, url) {
  const body = await jsonBody(request)
  const grant = String(body.grant_type || '')
  if (!GRANTS.has(grant)) return answer(400, 'that sign-in request is not valid')
  const form = new URLSearchParams({ grant_type: grant })
  if (grant === 'authorization_code') {
    if (!body.code || !body.code_verifier) return answer(400, 'that sign-in request is not valid')
    form.set('code', String(body.code))
    form.set('code_verifier', String(body.code_verifier))
    form.set('redirect_uri', callbackUrl(env, url))
  } else {
    if (!body.refresh_token) return answer(400, 'that sign-in request is not valid')
    form.set('refresh_token', String(body.refresh_token))
  }
  const upstream = await fetch(SUPABASE_TOKEN, {
    method: 'POST',
    headers: {
      authorization: `Basic ${btoa(`${env.SUPABASE_CLIENT_ID}:${env.SUPABASE_CLIENT_SECRET}`)}`,
      'content-type': 'application/x-www-form-urlencoded',
      accept: 'application/json',
    },
    body: form,
  })
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') || 'application/json', 'cache-control': 'no-store' },
  })
}

// Route -> [handler, whether the app token is needed]. The callback is opened by a browser, which has no app token.
const SIGN_IN = {
  'POST /oauth/supabase/start': [supabaseStart, true],
  'GET /oauth/supabase/callback': [supabaseCallback, false],
  'POST /oauth/supabase/token': [supabaseToken, true],
}

async function signIn(request, env, url, [handler, needsToken]) {
  if (needsToken) {
    const auth = request.headers.get('authorization') || ''
    if (!sameToken(auth.replace(/^Bearer\s+/i, ''), env.APP_TOKEN || '')) return answer(401, 'unauthorized')
  }
  if (!configured(env)) {
    return needsToken ? answer(503, 'Supabase sign-in is not set up on this engine yet') : page(503, 'Supabase sign-in is not set up yet.')
  }
  const limited = await tooMany(request, env)
  if (limited) return limited
  return handler(request, env, url)
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    const route = `${request.method} ${url.pathname}`
    if (SIGN_IN[route]) return signIn(request, env, url, SIGN_IN[route])
    if (!ALLOWED.has(route)) return answer(404, 'not found')

    const auth = request.headers.get('authorization') || ''
    if (!sameToken(auth.replace(/^Bearer\s+/i, ''), env.APP_TOKEN || '')) return answer(401, 'unauthorized')
    if (!env.OLLAMA_API_KEY) return answer(503, 'the engine has no key yet')

    const limited = await tooMany(request, env)
    if (limited) return limited

    const headers = new Headers()
    for (const name of FORWARD) {
      const value = request.headers.get(name)
      if (value) headers.set(name, value)
    }
    headers.set('authorization', `Bearer ${env.OLLAMA_API_KEY}`)

    const upstream = await fetch(UPSTREAM + url.pathname + url.search, {
      method: request.method,
      headers,
      body: request.method === 'GET' ? undefined : await request.arrayBuffer(),
    })

    // Streamed straight back: a chat answer arrives token by token, as it would from ollama.com.
    const out = new Headers()
    for (const name of ['content-type', 'retry-after']) {
      const value = upstream.headers.get(name)
      if (value) out.set(name, value)
    }
    return new Response(upstream.body, { status: upstream.status, headers: out })
  },
}
