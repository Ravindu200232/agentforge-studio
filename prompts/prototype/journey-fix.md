# Fix what the journeys showed

The prototype's journeys were clicked through in a browser, step by step, and a screenshot was taken and looked at at every step. These are the places where a journey could not be done, or a screen looked wrong. Fix them in the prototype's files under `.agentforge/prototype/`.

{{defects}}

How to fix:

- A journey is the list of steps in `.agentforge/srs/user-journeys.json`; a person does each step by clicking. A step that could not be done needs a way to do it: a link to the page the step happens on (the files are listed in `.agentforge/prototype/routes.json`), the button the step names, or a form that goes on to the next screen. Put it where a real person would look for it (the page's own content or the shared header, footer and menus), not in a corner that only a test would find.
- This is a clickable prototype with fixed demo data. Do not add storage, a data model, a counter that follows what was done, or anything that makes one screen change because of another: nobody asked for it, and it makes the prototype heavier to change. Fix what cannot be clicked or looks wrong, and nothing more.
- A button that is meant to do something in the demo must show that it did: a message or a change on the page (see how `assets/app.js` already does this: `data-toast`, `data-reveal`, the dialogs), or the next screen.
- Change only what each problem needs: read the page, find the part named, and correct it with `replace_text` or a rewrite of that part. Do not redraw a page that has a small problem.
- Keep the approved design (the tokens and the shared `assets/app.css`), the routes and the wireframe structure. `assets/flow.js` owns sign-in, sign-up, `data-demo-login`, `data-user`, `data-roles` and `data-sign-out`: do not rewrite it. Add no access guard.
- A problem that shows on several pages usually lives in a shared file (`assets/app.css`, `assets/app.js`): fix it there once.
- If your model can look at pictures you have a `screenshot` tool: use it on a page you changed to check the problem is gone and nothing else moved.

Do not plan, do not create or run tests, and do not touch any page the problems do not name. Apply the fixes and finish with one sentence saying what you changed.
