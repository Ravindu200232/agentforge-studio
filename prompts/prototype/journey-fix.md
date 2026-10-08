# Fix what the journeys showed

The prototype's journeys were clicked through in a browser, step by step, and a screenshot was taken and looked at at every step. These are the places where a journey could not be done, or a screen looked wrong. Fix them in the prototype's React app, the files under `.agentforge/prototype/app/src`.

{{defects}}

How to fix:

- A journey is the list of steps in `.agentforge/srs/user-journeys.json`; a person does each step by clicking. A step that could not be done needs a way to do it: a `<Link to="/path">` to the page the step happens on (the pages are listed in `.agentforge/prototype/routes.json`), the button the step names, or a form that goes on to the next screen. Put it where a real person would look for it (the page's own content or the shared navigation), not in a corner that only a test would find.
- A button or form that is meant to do something must really do it: change what is shown (the sample data the pages share), say that it did, or open the next screen.
- Change only what each problem needs: read the page, find the part named, and correct it with `replace_text` or a rewrite of that part. Do not redraw a page that has a small problem.
- Keep the approved design, the routes and the way the pages link. `src/lib/router.tsx` and `src/lib/session.tsx` belong to the Studio: do not edit them.
- A problem that shows on several pages usually lives in a shared component: fix it there once.

Do not plan, do not create or run tests, install packages or run the skill's scripts (the Studio bundles the app again and walks the journeys once more), and do not touch a page the problems do not name. Apply the fixes and finish with one sentence saying what you changed.
