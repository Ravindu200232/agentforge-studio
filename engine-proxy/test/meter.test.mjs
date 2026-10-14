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
    assert.equal(pending.length, 0, 'completed model streams must settle with the response, not a short-lived waitUntil task')
    await Promise.all(pending)
    const settlement = calls.find(call => call.url.endsWith('/settle'))
    assert.ok(settlement)
    const data = JSON.parse(settlement.options.body)
    assert.equal(data.reservation, 'request-1')
    assert.equal(data.inputTokens, 1000)
    assert.equal(data.outputTokens, 200)
    assert.equal(data.costMicros, 270)
    const authorized = calls.find(call => call.url.endsWith('/authorize'))
    assert.equal(authorized.options.headers.authorization, 'Bearer signed-account')
    assert.ok(JSON.parse(authorized.options.body).reserveMicros < 250_000)
  } finally { globalThis.fetch = original }
})

test('a canceled model response releases its cloud reservation', async () => {
  const original = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options })
    if (String(url).endsWith('/authorize')) return Response.json({ reservation: 'canceled-request' })
    if (String(url).endsWith('/settle')) return Response.json({ ok: true })
    if (String(url).endsWith('/api/chat')) return new Response(new ReadableStream({
      start(controller) { controller.enqueue(new TextEncoder().encode('{"message":{"content":"partial"}}\n')) },
    }))
    throw new Error(`Unexpected URL: ${url}`)
  }
  const env = { APP_TOKEN: 'app', OLLAMA_API_KEY: 'private', ACCOUNTS_URL: 'https://admin.example',
    ENGINE_METER_SECRET: 'server-secret' }
  try {
    const response = await worker.fetch(new Request('https://engine.example/api/chat', {
      method: 'POST', headers: { authorization: 'Bearer app', 'x-agentforge-account': 'signed-account' },
      body: JSON.stringify({ model: 'gpt-oss:120b', messages: [] }),
    }), env, { waitUntil() {} })
    const reader = response.body.getReader()
    await reader.read()
    await reader.cancel()
    const settlement = calls.find(call => call.url.endsWith('/settle'))
    assert.equal(JSON.parse(settlement.options.body).reservation, 'canceled-request')
  } finally { globalThis.fetch = original }
})

test('free accounts cannot call GLM 5.3 models, while paid accounts can', async () => {
  const original = globalThis.fetch
  const calls = []
  let plan = 'free'
  let unlimited = false
  globalThis.fetch = async (url) => {
    calls.push(String(url))
    if (String(url).endsWith('/api/accounts/me')) return Response.json({ account: { plan, unlimited } })
    if (String(url).endsWith('/authorize')) return Response.json({ reservation: 'request-2' })
    if (String(url).endsWith('/settle')) return Response.json({ ok: true })
    if (String(url).endsWith('/api/chat')) return Response.json({ done: true, prompt_eval_count: 1, eval_count: 1 })
    throw new Error(`Unexpected URL: ${url}`)
  }
  const env = { APP_TOKEN: 'app', OLLAMA_API_KEY: 'private', ACCOUNTS_URL: 'https://admin.example',
    ENGINE_METER_SECRET: 'server-secret' }
  const request = model => new Request('https://engine.example/api/chat', {
    method: 'POST', headers: { authorization: 'Bearer app', 'x-agentforge-account': 'signed-account' },
    body: JSON.stringify({ model, messages: [] }),
  })
  try {
    for (const model of ['glm-5.3:cloud', 'glm-5.3-flash:cloud']) {
      const response = await worker.fetch(request(model), env, { waitUntil() {} })
      assert.equal(response.status, 403)
    }
    assert.equal(calls.filter(url => url.endsWith('/authorize')).length, 0)
    assert.equal(calls.filter(url => url.endsWith('/api/chat')).length, 0)
    plan = 'paid'
    const pending = []
    const allowed = await worker.fetch(request('glm-5.3:cloud'), env, { waitUntil(promise) { pending.push(promise) } })
    assert.equal(allowed.status, 200)
    await allowed.text()
    await Promise.all(pending)
    assert.equal(calls.filter(url => url.endsWith('/authorize')).length, 1)
    plan = 'free'
    unlimited = true
    const adminPending = []
    const admin = await worker.fetch(request('glm-5.3-flash:cloud'), env,
      { waitUntil(promise) { adminPending.push(promise) } })
    assert.equal(admin.status, 200)
    await admin.text()
    await Promise.all(adminPending)
  } finally { globalThis.fetch = original }
})
