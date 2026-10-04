# Fix what the screenshots show

The prototype's screens were photographed in a browser and looked at. These are the visible problems that were found. Fix them in the prototype's files under `.agentforge/prototype/`.

{{defects}}

How to fix:

- Change only these files, and only what each problem needs: read the page, find the part named, and correct it with `replace_text` or a rewrite of that part. Do not redraw a page that has a small problem.
- Keep the approved design (the tokens and the shared `assets/app.css`), the routes, the wireframe structure and the flow. `assets/flow.js` owns sign-in, sign-up, `data-demo-login`, `data-user`, `data-roles` and `data-sign-out`: do not rewrite it. Add no access guard.
- A problem that appears on several pages usually lives in `assets/app.css`: fix it there once.
- Every fix works at both widths: desktop (1440px) and mobile (390px).
- If your model can look at pictures you have a `screenshot` tool: use it on a page you changed (`dashboard.html`, desktop and mobile) to check the problem is gone and nothing else moved.

Do not plan, do not create or run tests, and do not touch any other page. Apply the fixes and finish with one sentence saying what you changed.
