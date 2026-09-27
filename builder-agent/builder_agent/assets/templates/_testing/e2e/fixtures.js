// Import `test` and `expect` from here, not from '@playwright/test'.
//
// Every test fails when the page throws, logs a console error, or a request
// answers 5xx - a page that renders while broken is still broken.
//
// A negative test provokes a 401 or 403 on purpose, and the browser logs every
// 4xx sub-request as a console error. Declare it, and only it, for that test:
//
//   test.use({ allowedStatuses: [401, 403] })
import { test as base, expect } from '@playwright/test'
import { startLiveView } from './live-view.js'

export const test = base.extend({
  allowedStatuses: [[], { option: true }],
  page: async ({ page, allowedStatuses }, use, testInfo) => {
    const problems = []
    const allowed = new Set(allowedStatuses)
    page.on('pageerror', error => problems.push(`page error: ${error.message}`))
    page.on('console', message => {
      if (message.type() !== 'error') return
      const text = message.text()
      const status = /status of (\d{3})/.exec(text)?.[1]
      if (status && allowed.has(Number(status))) return
      problems.push(`console error: ${text}`)
    })
    page.on('response', response => {
      const status = response.status()
      if (status >= 500 && !allowed.has(status)) problems.push(`HTTP ${status} ${response.url()}`)
    })
    // When the Studio started this run, what the browser shows appears in its preview.
    // Watching must never change a test's outcome: it is best-effort and swallows its own errors.
    const stopLive = await startLiveView(page, testInfo).catch(() => async () => {})
    try {
      await use(page)
    } finally {
      await stopLive().catch(() => {})
    }
    expect(problems, 'the page reported problems').toEqual([])
  },
})

/**
 * Call the app's own API exactly as the signed-in browser does - same cookies, same
 * origin. `page.request` and a fresh `request` context do not reliably carry the
 * page's session, so an authorization test built on them sees a 401 where the app
 * really answers 403.
 *
 *   await signIn(page)                       // the app's own sign-in journey
 *   const api = apiFrom(page)
 *   expect((await api.get('/api/users')).status).toBe(403)
 *
 * The page must already be on the app (any page of it), not about:blank.
 */
export function apiFrom(page) {
  const call = async (method, url, body) => {
    if (page.url() === 'about:blank') throw new Error('apiFrom(page): open a page of the app first (page.goto)')
    return page.evaluate(async ({ method, url, body }) => {
      const response = await fetch(url, {
        method,
        credentials: 'include',
        headers: body === undefined ? {} : { 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      let json = null
      try { json = await response.json() } catch { /* not JSON */ }
      return { status: response.status, body: json }
    }, { method, url, body })
  }
  return {
    get: url => call('GET', url),
    post: (url, body) => call('POST', url, body ?? {}),
    put: (url, body) => call('PUT', url, body ?? {}),
    patch: (url, body) => call('PATCH', url, body ?? {}),
    delete: url => call('DELETE', url),
  }
}

export { expect }
