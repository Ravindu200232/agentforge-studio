# Fix what the screenshots show

The prototype's screens were photographed in a browser and looked at. These are the visible problems that were found. Fix them in the prototype's React app, the files under `.agentforge/prototype/app/src`.

{{defects}}

How to fix:

- Change only what each problem needs: read the page, find the part named, and correct it with `replace_text` or a rewrite of that part. Do not redraw a page that has a small problem.
- Keep the approved design (its colours and type are in `src/index.css` and the Tailwind theme), the routes and the way the pages work. `src/lib/router.tsx` and `src/lib/session.tsx` belong to the Studio: do not edit them.
- A problem that appears on several pages usually lives in a shared component or in `src/index.css`: fix it there once.
- Every fix works at both widths: desktop (1440px) and mobile (390px).

Do not plan, do not create or run tests, install packages or run the skill's scripts (the Studio bundles the app again and looks at it once more), and do not touch a page the problems do not name. Apply the fixes and finish with one sentence saying what you changed.
