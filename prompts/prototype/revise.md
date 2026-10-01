# Update the prototype

{{request}}

Find only the prototype files affected by this request, read them and update them directly.

Keep the approved wireframe structure, design system, routes, images and user flow unless the request changes one of them. If a new route is requested, add it to `routes.json`.

Keep every page full of realistic sample data, and keep the role-based demo login as it is: `assets/flow.js` owns sign-in, `data-demo-login`, `data-user`, `data-roles` and `data-sign-out` — do not rewrite it. Add no access guard: every page keeps opening directly when it is clicked.

Do not plan a new prototype, change unrelated pages, create tests, run tests, or perform a separate verification pass. Apply the update and finish.
