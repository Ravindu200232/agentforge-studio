{{request}}

Build it as a React app with the web-artifacts-builder skill. Read `{{skill}}/SKILL.md` first, then create the app and bundle it with the skill's scripts, run from the workspace root:

    node {{skill}}/scripts/init-artifact.mjs {{app}}
    node {{skill}}/scripts/bundle-artifact.mjs {{app}}

What the product is, in the customer's own words, and its site map: `.agentforge/srs/handoff/app.md`. Read it, and draw the wireframes from it.

One page for each of these screens, all in the one app:

{{routes}}

The journeys people take through them:

{{journeys}}

No database, seed data, accounts or sign-in logic: each page holds its own sample data.

{{resume}}
