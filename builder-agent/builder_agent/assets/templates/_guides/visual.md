# Visual regression with Playwright

`npm run qa:visual` runs `e2e/visual.spec.js` against every signed-out public route
(`routes.js`'s `publicRoutes()`) at desktop and mobile size. It is a *self-recording*
check, not an ordinary assertion: a route with no baseline yet has its screenshot
written under `e2e/__screenshots__/` and the test passes with a "first run: baseline
recorded" annotation; only a later run, once a baseline exists, actually compares.
That is deliberate — `playwright.config.js` sets `updateSnapshots: 'missing'` and a
custom `snapshotPathTemplate` so baselines land in `e2e/__screenshots__/`, which is
exactly where the Testing screen's evidence collector looks for them. Two things
follow from this, and both have broken real generated apps before:

**Never rewrite `visual.spec.js`, and never touch `playwright.config.js`'s
`snapshotPathTemplate`, `updateSnapshots` or `projects` list.** A naive replacement
— looping over routes and calling `expect(page).toHaveScreenshot(...)` directly, the
way you would in an ordinary Playwright spec — throws away the self-recording branch.
Every run then reports "no snapshot exists, writing actual" and fails, forever,
because nothing ever gets the chance to write a baseline and pass. Changing the
project name or dropping the custom `snapshotPathTemplate` breaks it the same way,
and also stops the Testing screen from finding the images at all, since it only scans
`e2e/__screenshots__/`.

**A signed-in role needs its own visual coverage — add it to a journey, not to
`visual.spec.js`.** Signed out, every protected route just shows the sign-in page, so
adding it to the public loop would screenshot the wrong thing under the right name.
`fixtures.js` exports `expectMatchesBaseline(page, testInfo, name)` — the identical
baseline-record-then-compare check `visual.spec.js` uses, factored out so you call it
rather than re-implement it:

```js
import { test, expect, expectMatchesBaseline } from './fixtures.js'

test('admin sees the bookings list', async ({ page }, testInfo) => {
  // sign in through the app's own flow, same as any other journey test
  await page.goto('/login')
  await page.fill('[name=email]', 'admin@example.com')
  await page.fill('[name=password]', process.env.SEED_ADMIN_PASSWORD)
  await page.click('button[type=submit]')
  await page.goto('/admin/bookings')
  await expectMatchesBaseline(page, testInfo, 'admin-bookings')
})
```

Pick a `name` that cannot collide with a public route's own slug (`admin-bookings`,
not `bookings`) — they share the same `e2e/__screenshots__/` folder.

Run `npm run qa:visual` once per changed UI layer, not on every unrelated change: a
UI-only styling tweak is exactly when this check earns its keep, a backend-only
change is not.
