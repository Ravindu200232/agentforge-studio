{{request}}

Make the wireframes as a React app, with the web-artifacts-builder skill. Read `{{skill}}/SKILL.md` first.

The app is already set up in `{{app}}` (step 1 of the skill: React, TypeScript, Vite, Tailwind CSS and the shadcn/ui components are in it) and the Studio bundles it when you are done (step 3), so you only develop it (step 2): write files under `{{app}}/src`. Do not run the skill's scripts, install packages or start a server.

What the product is, in the customer's own words, and its site map: `.agentforge/srs/handoff/app.md`. Read it, and draw the wireframes from it.

One wireframe for each page of the site map, each in its own file, a component with a default export:

{{routes}}

Link from page to page with `<Link to="/orders">` from `@/lib/router`; `useParams()` from the same file gives the values in a route such as `/orders/[id]`.

A wireframe is low fidelity: the layout of a page and what is on it. Greys and outlines, shadcn/ui components, plain boxes for pictures and charts, real words from the product for every label, button and heading, and believable sample rows. No brand colours, photographs or animation. Put the navigation and the page frame in one shared component and use it on every page, so the wireframes read as one product.

{{resume}}
