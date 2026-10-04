// The engine Worker is also the sign-in broker for Supabase: it holds the one OAuth app's client secret so that nobody who
// installs AgentForge registers an app of their own. These tests run the Worker's real code with a stubbed `fetch`.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = await readFile(new URL('../engine-proxy/src/index.js', import.meta.url), 'utf8')
const worker = (await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)).default

const ENGINE = 'https://engine.example.test'
const RETURN_TO = 'http://localhost:7824/__agentforge/api/supabase-oauth/callback'
const CHALLENGE = 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'  // 43 characters, as a SHA-256 PKCE challenge is
const ENV = { APP_TOKEN: 'app-token', SUPABASE_CLIENT_ID: 'client-id', SUPABASE_CLIENT_SECRET: 'client-secret', OLLAMA_API_KEY: 'ollama-key' }
const AUTH = { authorization: 'Bearer app-token', 'content-type': 'application/json' }

function call(method, path, { env = ENV, headers = {}, body } = {}) {
  const request = new Request(ENGINE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  return worker.fetch(request, env)
}

async function startFlow(overrides = {}) {
  const answer = await call('POST', '/oauth/supabase/start', {
    headers: AUTH, body: { flow_id: 'sbo_flow_0123456789', challenge: CHALLENGE, return_to: RETURN_TO, ...overrides },
  })
  return answer
}

async function stateFromStart() {
  const answer = await startFlow()
  assert.equal(answer.status, 200)
  const authorize = new URL((await answer.json()).authorize_url)
  return { authorize, state: authorize.searchParams.get('state') }
}

// --- start ---------------------------------------------------------------------------------------------------------

{
  const { authorize } = await stateFromStart()
  assert.equal(`${authorize.origin}${authorize.pathname}`, 'https://api.supabase.com/v1/oauth/authorize')
  const p = authorize.searchParams
  assert.equal(p.get('response_type'), 'code')
  assert.equal(p.get('client_id'), 'client-id')
  assert.equal(p.get('redirect_uri'), `${ENGINE}/oauth/supabase/callback`)  // the ONE callback the publisher registered
  assert.equal(p.get('code_challenge'), CHALLENGE)
  assert.equal(p.get('code_challenge_method'), 'S256')
  assert.ok(!authorize.toString().includes('client-secret'))
}

// Only an app with the app token may start a sign-in.
assert.equal((await call('POST', '/oauth/supabase/start', { body: {} })).status, 401)
assert.equal((await call('POST', '/oauth/supabase/start', { headers: { authorization: 'Bearer nope' }, body: {} })).status, 401)

// The address the browser is sent back to must be this computer's own sign-in callback and nothing else.
for (const returnTo of [
  'https://evil.example/supabase-oauth/callback',
  'http://127.0.0.1:7824/__agentforge/api/supabase-oauth/callback',
  'http://localhost.evil.example:7824/__agentforge/api/supabase-oauth/callback',
  'http://localhost:7824/__agentforge/api/other',
  'http://localhost:7824/a/../supabase-oauth/callback',
  'http://localhost/__agentforge/api/supabase-oauth/callback',
]) {
  assert.equal((await startFlow({ return_to: returnTo })).status, 400, returnTo)
}
assert.equal((await startFlow({ flow_id: 'x' })).status, 400)
assert.equal((await startFlow({ challenge: 'short' })).status, 400)

// Not configured: the publisher has not set the client id and secret yet.
{
  const bare = { APP_TOKEN: 'app-token' }
  const started = await call('POST', '/oauth/supabase/start', { env: bare, headers: AUTH, body: {} })
  assert.equal(started.status, 503)
  assert.match((await started.json()).error, /not set up/)
  assert.equal((await call('GET', '/oauth/supabase/callback?code=c&state=s', { env: bare })).status, 503)
}

// --- callback ------------------------------------------------------------------------------------------------------

// The browser carries no app token. A valid state sends it on to the app with the code and the app's own flow id.
{
  const { state } = await stateFromStart()
  const answer = await call('GET', `/oauth/supabase/callback?code=the-code&state=${encodeURIComponent(state)}`)
  assert.equal(answer.status, 302)
  const back = new URL(answer.headers.get('location'))
  assert.equal(`${back.origin}${back.pathname}`, RETURN_TO)
  assert.equal(back.searchParams.get('code'), 'the-code')
  assert.equal(back.searchParams.get('state'), 'sbo_flow_0123456789')
  assert.equal(answer.headers.get('referrer-policy'), 'no-referrer')
}

// A refusal on supabase.com is passed on as the reason, not as a code.
{
  const { state } = await stateFromStart()
  const answer = await call('GET', `/oauth/supabase/callback?error=access_denied&error_description=User%20denied&state=${encodeURIComponent(state)}`)
  const back = new URL(answer.headers.get('location'))
  assert.equal(back.searchParams.get('error'), 'User denied')
  assert.equal(back.searchParams.get('code'), null)
}

// A state not signed here, tampered with, malformed, or from another secret is refused with a page, never a redirect.
{
  const { state } = await stateFromStart()
  const [payload, signature] = state.split('.')
  const forged = Buffer.from(JSON.stringify({ f: 'sbo_flow_0123456789', r: 'http://localhost:9999/supabase-oauth/callback', t: Date.now() })).toString('base64url')
  for (const bad of ['', 'garbage', `${payload}.`, `${payload}.${signature}x`, `${forged}.${signature}`, `${payload}.${signature}.extra`]) {
    const answer = await call('GET', `/oauth/supabase/callback?code=c&state=${encodeURIComponent(bad)}`)
    assert.equal(answer.status, 400, bad)
    assert.equal(answer.headers.get('location'), null)
  }
  const other = await call('GET', `/oauth/supabase/callback?code=c&state=${encodeURIComponent(state)}`, { env: { ...ENV, SUPABASE_CLIENT_SECRET: 'another-secret' } })
  assert.equal(other.status, 400)
}

// A sign-in left for more than ten minutes lapses.
{
  const real = Date.now
  const { state } = await stateFromStart()
  Date.now = () => real() + 11 * 60 * 1000
  try {
    assert.equal((await call('GET', `/oauth/supabase/callback?code=c&state=${encodeURIComponent(state)}`)).status, 400)
  } finally {
    Date.now = real
  }
}

// --- token ---------------------------------------------------------------------------------------------------------

function stubSupabase(status, reply) {
  const seen = []
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), init })
    return new Response(JSON.stringify(reply), { status, headers: { 'content-type': 'application/json' } })
  }
  return seen
}

{
  const seen = stubSupabase(200, { access_token: 'at', refresh_token: 'rt', expires_in: 3600 })
  const answer = await call('POST', '/oauth/supabase/token', {
    headers: AUTH, body: { grant_type: 'authorization_code', code: 'the-code', code_verifier: 'the-verifier' },
  })
  assert.equal(answer.status, 200)
  assert.equal((await answer.json()).access_token, 'at')
  assert.equal(seen.length, 1)
  assert.equal(seen[0].url, 'https://api.supabase.com/v1/oauth/token')
  assert.equal(seen[0].init.headers.authorization, `Basic ${Buffer.from('client-id:client-secret').toString('base64')}`)
  const sent = new URLSearchParams(seen[0].init.body)
  assert.deepEqual(Object.fromEntries(sent), {
    grant_type: 'authorization_code', code: 'the-code', code_verifier: 'the-verifier', redirect_uri: `${ENGINE}/oauth/supabase/callback`,
  })
}

{
  const seen = stubSupabase(200, { access_token: 'at2', refresh_token: 'rt2', expires_in: 3600 })
  const answer = await call('POST', '/oauth/supabase/token', { headers: AUTH, body: { grant_type: 'refresh_token', refresh_token: 'rt' } })
  assert.equal(answer.status, 200)
  assert.deepEqual(Object.fromEntries(new URLSearchParams(seen[0].init.body)), { grant_type: 'refresh_token', refresh_token: 'rt' })
}

// Supabase's own refusal comes back with its status, so the app can show the reason.
{
  stubSupabase(400, { error_description: 'Invalid code' })
  const answer = await call('POST', '/oauth/supabase/token', {
    headers: AUTH, body: { grant_type: 'authorization_code', code: 'bad', code_verifier: 'v' },
  })
  assert.equal(answer.status, 400)
  assert.equal((await answer.json()).error_description, 'Invalid code')
}

// Nothing but the two grants the app uses goes to Supabase, and never without the app token.
{
  const seen = stubSupabase(200, {})
  for (const body of [
    { grant_type: 'client_credentials' }, { grant_type: 'password' }, {},
    { grant_type: 'authorization_code', code: 'c' }, { grant_type: 'authorization_code', code_verifier: 'v' },
    { grant_type: 'refresh_token' },
  ]) {
    assert.equal((await call('POST', '/oauth/supabase/token', { headers: AUTH, body })).status, 400, JSON.stringify(body))
  }
  assert.equal((await call('POST', '/oauth/supabase/token', { body: { grant_type: 'refresh_token', refresh_token: 'rt' } })).status, 401)
  assert.equal(seen.length, 0)
}

// The rate limit applies to every sign-in call.
{
  const limited = { ...ENV, LIMITER: { limit: async () => ({ success: false }) } }
  assert.equal((await call('POST', '/oauth/supabase/start', { env: limited, headers: AUTH, body: {} })).status, 429)
  assert.equal((await call('POST', '/oauth/supabase/token', { env: limited, headers: AUTH, body: {} })).status, 429)
  assert.equal((await call('GET', '/oauth/supabase/callback?state=x', { env: limited })).status, 429)
}

// --- the engine itself is untouched ------------------------------------------------------------------------------

assert.equal((await call('GET', '/api/tags')).status, 401)
assert.equal((await call('GET', '/nothing')).status, 404)
assert.equal((await call('GET', '/oauth/supabase/start', { headers: AUTH })).status, 404)  // wrong method
assert.equal((await call('GET', '/api/tags', { env: { APP_TOKEN: 'app-token' }, headers: AUTH })).status, 503)
{
  const seen = []
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), init })
    return new Response('{"models":[]}', { status: 200, headers: { 'content-type': 'application/json' } })
  }
  const answer = await call('GET', '/api/tags', { headers: AUTH })
  assert.equal(answer.status, 200)
  assert.equal(seen[0].url, 'https://ollama.com/api/tags')
  assert.equal(seen[0].init.headers.get('authorization'), 'Bearer ollama-key')
}

console.log('engine proxy oauth: ok')
