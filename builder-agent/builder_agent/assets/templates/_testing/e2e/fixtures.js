// Import `test` and `expect` from here, not from '@playwright/test'.
//
// Every test fails when the page throws, logs a console error, or a request
// answers 5xx - a page that renders while broken is still broken.
//
// A negative test provokes a 401 or 403 on purpose, and the browser logs every
// 4xx sub-request as a console error. Declare it, and only it, for that test:
//
//   test.use({ allowedStatuses: [401, 403] })
import fs from 'node:fs'
import path from 'node:path'
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
    // Every call this test's page made to the app's own API, and what it answered. The Testing
    // view links each one to its handler as E2E evidence; a unit test only links what it imports.
    let origin = ''
    try { origin = new URL(testInfo.project.use?.baseURL || process.env.BASE_URL).origin } catch { /* any origin */ }
    const apiCalls = new Set()
    page.on('response', response => {
      const status = response.status()
      if (status >= 500 && !allowed.has(status)) problems.push(`HTTP ${status} ${response.url()}`)
      try {
        const url = new URL(response.url())
        if ((!origin || url.origin === origin) && /^\/api(\/|$)/.test(url.pathname)) {
          apiCalls.add(`${response.request().method()} ${url.pathname} ${status}`)
        }
      } catch { /* not a URL of the app */ }
    })
    // When the Studio started this run, what the browser shows appears in its preview.
    // Watching must never change a test's outcome: it is best-effort and swallows its own errors.
    const stopLive = await startLiveView(page, testInfo).catch(() => async () => {})
    try {
      await use(page)
    } finally {
      await stopLive().catch(() => {})
      if (apiCalls.size) {
        await testInfo.attach('api-calls', { body: JSON.stringify([...apiCalls]), contentType: 'application/json' })
          .catch(() => {})
      }
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

/**
 * Screenshot-match a page against its recorded baseline - the same self-recording
 * check visual.spec.js does for signed-out public routes. A missing baseline is
 * written and the check passes with a "first run: baseline recorded" annotation;
 * a later run compares against it.
 *
 * Use this for any *additional* screen a journey needs a visual check for (a
 * signed-in member page, an admin screen) instead of hand-writing the
 * fs.existsSync/page.screenshot logic again, and instead of editing
 * visual.spec.js itself, which only ever covers signed-out public routes -
 * signed in, every route shows the same sign-in redirect there.
 *
 *   await signIn(page, 'admin')
 *   await page.goto('/admin/bookings')
 *   await expectMatchesBaseline(page, testInfo, 'admin-bookings')
 */
export async function expectMatchesBaseline(page, testInfo, name) {
  const file = `${name}.png`
  const baseline = testInfo.snapshotPath(file)
  if (!fs.existsSync(baseline) && !process.env.CI && testInfo.config.updateSnapshots !== 'none') {
    fs.mkdirSync(path.dirname(baseline), { recursive: true })
    await page.screenshot({ path: baseline, fullPage: true, animations: 'disabled' })
    testInfo.annotations.push({ type: 'baseline', description: 'first run: baseline recorded, nothing to compare yet' })
    return
  }
  await expect(page).toHaveScreenshot(file, { fullPage: true })
}

export { expect }
