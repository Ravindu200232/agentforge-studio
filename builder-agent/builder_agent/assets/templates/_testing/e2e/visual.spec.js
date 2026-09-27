// UI and screenshot check: every public page, at the desktop and the mobile size.
//
// The first run has nothing to compare against: it records the baseline in
// e2e/__screenshots__/ and passes with a "baseline" annotation (Playwright itself would
// write the file but still fail the test). Later runs compare against it. After an
// intended change, update it with --update-snapshots. In CI (CI=true) a missing baseline
// fails, because a baseline that was never committed compares nothing.
// Signed-in pages are screenshotted from their journeys: signed out, these routes
// only show the sign-in page, which would be saved under the wrong page's name.
import fs from 'node:fs'
import path from 'node:path'
import { test, expect } from './fixtures.js'
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
        const file = `${slug(route)}.png`
        const baseline = testInfo.snapshotPath(file)
        if (!fs.existsSync(baseline) && !process.env.CI && testInfo.config.updateSnapshots !== 'none') {
          fs.mkdirSync(path.dirname(baseline), { recursive: true })
          await page.screenshot({ path: baseline, fullPage: true, animations: 'disabled' })
          testInfo.annotations.push({ type: 'baseline', description: 'first run: baseline recorded, nothing to compare yet' })
          return
        }
        await expect(page).toHaveScreenshot(file, { fullPage: true })
      })
    })
  }
})
