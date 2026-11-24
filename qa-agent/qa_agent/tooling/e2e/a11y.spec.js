// Accessibility: axe-core on every public page. Serious and critical violations fail.
// Signed-in pages are checked from their journeys (sign in, open the page, run axe
// with `new AxeBuilder({ page })`): a signed-out browser only sees the sign-in page
// at those routes, so scanning them here would scan the wrong page.
import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './fixtures.js'
import { publicRoutes } from './routes.js'

const BLOCKING = ['serious', 'critical']

test.describe('@a11y', () => {
  for (const { route, name } of publicRoutes()) {
    test(`${name || route} is accessible`, async ({ page }, testInfo) => {
      await test.step(`open ${route}`, async () => {
        await page.goto(route)
        await page.waitForLoadState('networkidle')
      })
      await test.step('axe finds no serious violation', async () => {
        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze()
        await testInfo.attach('axe.json', { body: JSON.stringify(results.violations), contentType: 'application/json' })
        const blocking = results.violations
          .filter(v => BLOCKING.includes(v.impact))
          .map(v => `${v.id} (${v.impact}): ${v.help} - ${v.nodes.length} element(s)`)
        expect(blocking).toEqual([])
      })
    })
  }
})
