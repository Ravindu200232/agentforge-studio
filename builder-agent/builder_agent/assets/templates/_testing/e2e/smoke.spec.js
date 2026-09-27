// Every public page opens, has a heading, and reports no errors (fixtures.js).
// Every protected page refuses a signed-out visitor instead of rendering.
import { test, expect } from './fixtures.js'
import { publicRoutes, protectedRoutes } from './routes.js'

for (const { route, name } of publicRoutes()) {
  test(`${name || route} opens`, async ({ page }) => {
    await test.step(`open ${route}`, async () => {
      const response = await page.goto(route)
      expect(response?.status() ?? 200, `${route} answered`).toBeLessThan(400)
    })
    await test.step('it shows its content', async () => {
      await expect(page.locator('h1, h2').first()).toBeVisible()
    })
  })
}

test.describe('signed out', () => {
  test.use({ allowedStatuses: [401, 403] })
  for (const { route, name } of protectedRoutes()) {
    test(`${name || route} refuses a signed-out visitor`, async ({ page }) => {
      const response = await page.goto(route)
      const landed = new URL(page.url()).pathname
      const refused = landed !== route || [401, 403].includes(response?.status() ?? 0)
      expect(refused, `${route} must not open signed out (it answered ${response?.status()} at ${landed})`).toBe(true)
    })
  }
})
