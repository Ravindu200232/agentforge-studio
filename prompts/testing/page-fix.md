# Fix what the pages show

Every page of the running application was photographed at desktop and mobile width, and a model looked at the pictures. These are the visible problems it found. Fix them in the application's source.

{{defects}}

How to fix:

- Each heading names a page and its route, and who it was opened as. Find that route's page in the source and the components it uses, and correct what each problem names.
- Change only what each problem needs, and keep the behaviour: routes, data, roles, validation and the approved design stay as they are. Never edit tests, `test-results/`, `playwright-report/` or anything under `.agentforge/qa/`.
- A problem that shows on several pages usually lives in a shared component, layout or stylesheet: fix it once there.
- Every fix works at both widths: desktop and mobile.
- When the fixes are made, run the minimum build that proves the application still compiles. Do not run any test: the Studio photographs the pages that had problems again itself and looks at them.

Do not plan, do not add tests, and do not touch anything the problems do not name. Finish with one sentence saying what you changed.
