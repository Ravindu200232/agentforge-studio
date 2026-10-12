// UI and screenshot check: every public page, at the desktop and the mobile size.
//
// The first run has nothing to compare against: it records the baseline in
// e2e/__screenshots__/ and passes with a "baseline" annotation (Playwright itself would
// write the file but still fail the test). Later runs compare against it. After an
// intended change, update it with --update-snapshots. In CI (CI=true) a missing baseline
// fails, because a baseline that was never committed compares nothing.
//
// Signed-in pages are screenshotted from their journeys, not from this file: signed
// out, these routes only show the sign-in page, which would be saved under the wrong
// page's name. Use fixtures.js's expectMatchesBaseline(page, testInfo, name) there -
// it is the exact same baseline-recording check this file uses below, exported so a
// journey spec never has to re-implement or (worse) edit it here. See _guides/visual.md.
import { test, expect, expectMatchesBaseline } from './fixtures.js'
import { publicRoutes, slug } from './routes.js'

test.describe('@visual', () => {
  for (const { route, name } of publicRoutes()) {
    test(`${name || route} looks as approved`, async ({ page }, testInfo) => {
      await test.step(`open ${route}`, async () => {
        await page.goto(route)
        await page.waitForLoadState('networkidle')
      })
      await test.step('nothing overflows the viewport', async () => {
        const overflow = await page.evaluate(() =>
          document.documentElement.scrollWidth - document.documentElement.clientWidth)
        expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(1)
      })
      await test.step('it matches its screenshot', async () => {
        await expectMatchesBaseline(page, testInfo, slug(route))
      })
    })
  }
})
