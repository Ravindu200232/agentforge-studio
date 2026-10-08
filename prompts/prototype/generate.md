{{request}}

`{{app}}` is the approved wireframe, copied for you to work on: a React app built with the web-artifacts-builder skill (`{{skill}}/SKILL.md`, read it first). Make it the finished product by editing it in place with the edit tools: `replace_text` for a change inside a file, `write_file` for a new one. The wireframe it came from, `{{wireframe}}`, stays as it is: never change it. Do not create another app and do not install packages.

Read what the product is and how it should look:

{{inputs}}

{{design_direction}}

Keep every one of these pages and the journeys between them, and make them work like the real frontend:

{{routes}}

{{journeys}}

No database, seed data, accounts or sign-in logic: each page holds its own sample data.

Uploaded images (import one with `import x from 'data-url:./relative/path'`):

{{uploads}}

When it is done, bundle it: `node {{skill}}/scripts/bundle-artifact.mjs {{app}}`.

{{resume}}
