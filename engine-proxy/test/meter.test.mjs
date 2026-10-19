import assert from 'node:assert/strict'
import test from 'node:test'
import worker from '../src/index.js'

const env = {
  APP_TOKEN: 'app', OLLAMA_API_KEY: 'upstream-private-key',
  ACCOUNTS_URL: 'https://admin.example', ENGINE_METER_SECRET: 'meter-private-key',
}

test('existing public endpoint authenticates, then forwards model traffic to Vercel unchanged', async () => {
  const original = globalThis.fetch
  const calls = []
  const answer = '{"message":{"content":"one"},"done":false}\n{"done":true,"prompt_eval_count":12,"eval_count":34}\n'
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options })
    return new Response(answer, { headers: { 'content-type': 'application/x-ndjson' } })
  }
  try {
    const input = JSON.stringify({ model: 'deepseek-v4.1-flash:cloud', messages: [{ role: 'user', content: 'Hello' }] })
      + ' '.repeat(160000)
    const request = new Request('https://engine.example/api/chat', {
      method: 'POST', headers: { authorization: 'Bearer app', 'x-agentforge-account': 'account-token' }, body: input,
    })
    const result = await worker.fetch(request, env)
    assert.equal(result.status, 200)
    assert.equal(result.headers.get('content-type'), 'application/x-ndjson')
    assert.equal(await result.text(), answer)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, 'https://admin.example/api/engine/chat')
    assert.equal(calls[0].options.redirect, 'manual', 'Cloudflare Workers do not support redirect: error')
    assert.equal(calls[0].options.headers.get('x-agentforge-account'), 'account-token')
    assert.equal(calls[0].options.headers.get('x-agentforge-upstream-key'), 'upstream-private-key')
    assert.equal(calls[0].options.headers.get('x-agentforge-meter-secret'), 'meter-private-key')
    assert.equal(await new Response(calls[0].options.body).text(), input)
  } finally { globalThis.fetch = original }
})

test('model calls without account or app token never reach Vercel', async () => {
  const original = globalThis.fetch
  let calls = 0
  globalThis.fetch = async () => { calls++; throw new Error('should not be called') }
  try {
    const request = headers => new Request('https://engine.example/api/generate', {
      method: 'POST', headers, body: '{"model":"gemma4:31b-cloud"}',
    })
    assert.equal((await worker.fetch(request({ authorization: 'Bearer wrong' }), env)).status, 401)
    assert.equal((await worker.fetch(request({ authorization: 'Bearer app' }), env)).status, 401)
    assert.equal(calls, 0)
  } finally { globalThis.fetch = original }
})

test('model provider errors pass through without exposing the upstream key', async () => {
  const original = globalThis.fetch
  globalThis.fetch = async () => Response.json({ error: 'credit used up' }, { status: 402 })
  try {
    const result = await worker.fetch(new Request('https://engine.example/api/chat', {
      method: 'POST', headers: { authorization: 'Bearer app', 'x-agentforge-account': 'account-token' },
      body: '{"model":"gemma4:31b-cloud"}',
    }), env)
    assert.equal(result.status, 402)
    const output = await result.text()
    assert.match(output, /credit used up/)
    assert.ok(!output.includes(env.OLLAMA_API_KEY))
  } finally { globalThis.fetch = original }
})
