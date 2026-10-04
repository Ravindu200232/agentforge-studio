# Fix what the end-to-end screenshots show

The end-to-end tests of the running application have finished. A model looked at the screenshot each test ended on, and found these visible problems. Fix them in the application's source.

{{defects}}

How to fix:

- Each heading names a test and the spec file it lives in. Read that spec to find which page the test ends on, then the page's own source and the components it uses, and correct what the problem names.
- Change only what each problem needs, and keep the behaviour: routes, data, roles, validation and the approved design stay as they are. Never change what a test asserts, never weaken or skip a test, and never edit `test-results/`, `playwright-report/` or any file under `.agentforge/qa/`.
- A problem that shows on several screens usually lives in a shared component, layout or stylesheet: fix it once there.
- Every fix works at both widths: desktop and mobile.
- If your model can look at pictures you have a `screenshot` tool: use it on a public page you changed (a local preview URL such as the managed preview's) to see that the problem is gone.
- When the fixes are made, run the minimum build that proves the application still compiles, then run the scaffold's journey suite once the way `playwright.md` says (`npm run qa:e2e`), so every journey's evidence is current, and make sure each journey that passed before still passes. Repair what your change broke; do not repeat the whole suite more than once after that.

Do not plan, do not add tests, and do not touch anything the problems do not name. Finish with one sentence saying what you changed.
