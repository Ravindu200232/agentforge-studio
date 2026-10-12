import assert from 'node:assert/strict'
import test from 'node:test'
import worker from '../src/index.js'

test('cloud chat needs an account and settles provider token usage once', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options })
    if (String(url).endsWith('/authorize')) return Response.json({ reservation: 'request-1' })
    if (String(url).endsWith('/settle')) return Response.json({ ok: true })
    if (String(url).endsWith('/api/chat')) return new Response(
      JSON.stringify({ done: true, prompt_eval_count: 1000, eval_count: 200 }) + '\n',
      { headers: { 'content-type': 'application/x-ndjson' } })
    throw new Error(`Unexpected URL: ${url}`)
  }
  const env = { APP_TOKEN: 'app', OLLAMA_API_KEY: 'private', ACCOUNTS_URL: 'https://admin.example',
    ENGINE_METER_SECRET: 'server-secret-is-never-in-the-desktop-app' }
  try {
    const noAccount = await worker.fetch(new Request('https://engine.example/api/chat', {
      method: 'POST', headers: { authorization: 'Bearer app' },
      body: JSON.stringify({ model: 'gpt-oss:120b', messages: [] }),
    }), env, { waitUntil() {} })
    assert.equal(noAccount.status, 401)
    assert.equal(calls.length, 0)

    const pending = []
    const response = await worker.fetch(new Request('https://engine.example/api/chat', {
      method: 'POST', headers: { authorization: 'Bearer app', 'x-agentforge-account': 'signed-account' },
      body: JSON.stringify({ model: 'gpt-oss:120b', messages: [] }),
    }), env, { waitUntil(promise) { pending.push(promise) } })
    assert.equal(response.status, 200)
    await response.text()
    await Promise.all(pending)
    const settlement = calls.find(call => call.url.endsWith('/settle'))
    assert.ok(settlement)
    const data = JSON.parse(settlement.options.body)
    assert.equal(data.reservation, 'request-1')
    assert.equal(data.inputTokens, 1000)
    assert.equal(data.outputTokens, 200)
    assert.equal(data.costMicros, 270)
    assert.equal(calls.find(call => call.url.endsWith('/authorize')).options.headers.authorization, 'Bearer signed-account')
  } finally { globalThis.fetch = original }
})
