// AgentForge's AI engine: a Cloudflare Worker between the app and ollama.com.
//
// The ollama.com API key lives here, as the Worker secret OLLAMA_API_KEY, and nowhere in the app: an installed
// AgentForge sends its requests to this Worker with the app token (the secret APP_TOKEN), and the Worker sends them
// on to ollama.com with the key. The app token is not a secret in the same way (it ships in every copy of the app),
// so the Worker also limits how fast any one address may call it, and only the API the app uses is passed through.
// A leaked or abused setup is fixed here, by changing a secret, with no new release of the app.

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

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    if (!ALLOWED.has(`${request.method} ${url.pathname}`)) return answer(404, 'not found')

    const auth = request.headers.get('authorization') || ''
    if (!sameToken(auth.replace(/^Bearer\s+/i, ''), env.APP_TOKEN || '')) return answer(401, 'unauthorized')
    if (!env.OLLAMA_API_KEY) return answer(503, 'the engine has no key yet')

    if (env.LIMITER) {
      const caller = request.headers.get('cf-connecting-ip') || 'unknown'
      const { success } = await env.LIMITER.limit({ key: caller })
      if (!success) return answer(429, 'too many requests from this address: wait a minute and try again')
    }

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
