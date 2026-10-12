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
  // The account's remaining credits (https://docs.ollama.com/api/balance), for the AgentForge admin app's balance bar:
  // read with the key that stays here, so the admin app never holds it.
  'GET /api/balance',
])

// Request and response headers passed through; everything else (cookies, the app token itself) stays here.
const FORWARD = ['content-type', 'accept', 'user-agent']

// Standard per-million-token rates from https://ollama.com/pricing (2026-10-12).
// Unknown models fail closed until their published rate is added. Cached input is
// charged at the regular input rate, a conservative upper bound for the credit ledger.
const PRICE = {
  'deepseek-v4.1-flash': [0.30, 1.20], 'deepseek-v4-pro': [1.32, 3.96],
  gemma4: [0.14, 0.40], 'glm-5.3': [1.40, 4.40], 'glm-5.3-flash': [0.15, 0.50],
  'glm-5.2': [1.40, 4.40], 'gpt-oss:120b': [0.15, 0.60], 'gpt-oss:20b': [0.07, 0.30],
  'kimi-k3': [3.00, 15.00], 'kimi-k2.7-code': [0.95, 4.00], 'kimi-k2.6': [0.95, 4.00],
  'minimax-m3': [0.60, 2.40], 'minimax-m2.7': [0.30, 1.20],
  'mistral-large-4': [0.68, 2.09], 'mistral-large-3': [0.50, 1.50],
  'nemotron-3-nano': [0.06, 0.24], 'nemotron-3-super': [0.015, 0.60],
  'nemotron-3-ultra': [0.10, 3.00],
}

function priceFor(model) {
  const name = String(model || '').replace(/:cloud$|-cloud$/, '')
  const rate = PRICE[name] || PRICE[name.split(':')[0]]
  if (!rate) return null
  const now = new Date()
  const peak = now.getUTCDay() >= 1 && now.getUTCDay() <= 5 && now.getUTCHours() >= 12 && now.getUTCHours() < 18
  return !peak && (name === 'deepseek-v4.1-flash' || name === 'deepseek-v4-pro')
    ? rate.map(value => value / 2) : rate
}

async function meter(env, path, accountToken, payload) {
  if (!env.ACCOUNTS_URL || !env.ENGINE_METER_SECRET) throw new Error('Cloud metering is not configured')
  const response = await fetch(`${env.ACCOUNTS_URL.replace(/\/$/, '')}/api/accounts/${path}`, {
    method: 'POST', headers: { 'content-type': 'application/json',
      'x-agentforge-meter-secret': env.ENGINE_METER_SECRET,
      ...(accountToken ? { authorization: `Bearer ${accountToken}` } : {}) },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw Object.assign(new Error(data.error || 'Cloud credit service is unavailable'), { status: response.status })
  return data
}

function usageOf(reply, payloadSize, outputSize) {
  const usage = reply?.usage || reply || {}
  const prompt = Number(usage.prompt_eval_count ?? usage.prompt_tokens ?? usage.input_tokens)
  const output = Number(usage.eval_count ?? usage.completion_tokens ?? usage.output_tokens)
  const exact = Number.isFinite(prompt) && Number.isFinite(output)
  return { inputTokens: exact ? Math.max(0, prompt) : Math.ceil(payloadSize / 4),
    outputTokens: exact ? Math.max(0, output) : Math.ceil(outputSize / 4), estimated: !exact }
}

async function recordStream(stream, env, reservation, model, rate, payloadSize) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = '', final = null, bytes = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      bytes += value.byteLength
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        try { const row = JSON.parse(line); if (row.done || row.usage) final = row } catch {}
      }
    }
    if (buffer.trim()) { try { final = JSON.parse(buffer) } catch {} }
  } finally {
    const tokens = usageOf(final, payloadSize, bytes)
    const costMicros = Math.ceil(tokens.inputTokens * rate[0] + tokens.outputTokens * rate[1])
    await meter(env, 'settle', '', { reservation, model, costMicros, ...tokens }).catch(() => {})
  }
}

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
  async fetch(request, env, ctx) {
    const url = new URL(request.url)
    const route = `${request.method} ${url.pathname}`
    if (SIGN_IN[route]) return signIn(request, env, url, SIGN_IN[route])
    if (!ALLOWED.has(route)) return answer(404, 'not found')

    const auth = request.headers.get('authorization') || ''
    const needed = route === 'GET /api/balance' ? env.ENGINE_METER_SECRET : env.APP_TOKEN
    if (!sameToken(auth.replace(/^Bearer\s+/i, ''), needed || '')) return answer(401, 'unauthorized')
    if (!env.OLLAMA_API_KEY) return answer(503, 'the engine has no key yet')

    const limited = await tooMany(request, env)
    if (limited) return limited

    const modelCall = route === 'POST /api/chat' || route === 'POST /api/generate'
    let reservation = null, model = '', rate = null, requestBody = null
    if (modelCall) {
      const accountToken = request.headers.get('x-agentforge-account') || ''
      if (!accountToken) return answer(401, 'Sign in to AgentForge to use cloud models.')
      requestBody = await request.arrayBuffer()
      try { model = JSON.parse(new TextDecoder().decode(requestBody)).model || '' }
      catch { return answer(400, 'Invalid model request.') }
      rate = priceFor(model)
      if (!rate) return answer(400, 'This cloud model has no published USD rate yet.')
      try { reservation = (await meter(env, 'authorize', accountToken, {})).reservation }
      catch (error) { return answer(error.status || 503, error.message) }
    }

    const headers = new Headers()
    for (const name of FORWARD) {
      const value = request.headers.get(name)
      if (value) headers.set(name, value)
    }
    headers.set('authorization', `Bearer ${env.OLLAMA_API_KEY}`)

    let upstream
    try {
      upstream = await fetch(UPSTREAM + url.pathname + url.search, {
        method: request.method, headers,
        body: request.method === 'GET' ? undefined : requestBody || await request.arrayBuffer(),
      })
    } catch {
      if (reservation) ctx.waitUntil(meter(env, 'settle', '', { reservation, model, costMicros: 0 }).catch(() => {}))
      return answer(502, 'The cloud model could not be reached.')
    }

    if (reservation && !upstream.ok) {
      ctx.waitUntil(meter(env, 'settle', '', { reservation, model, costMicros: 0 }).catch(() => {}))
    }

    // Streamed straight back: a chat answer arrives token by token, as it would from ollama.com.
    const out = new Headers()
    for (const name of ['content-type', 'retry-after']) {
      const value = upstream.headers.get(name)
      if (value) out.set(name, value)
    }
    if (reservation && upstream.ok && upstream.body) {
      const [toClient, toMeter] = upstream.body.tee()
      ctx.waitUntil(recordStream(toMeter, env, reservation, model, rate, requestBody.byteLength))
      return new Response(toClient, { status: upstream.status, headers: out })
    }
    return new Response(upstream.body, { status: upstream.status, headers: out })
  },
}
