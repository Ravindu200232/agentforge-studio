# Put the wrong journey steps on their pages

Each workflow below is a user journey: the role that takes it and its ordered
steps, each with the page it happens on. The steps marked **WRONG** need a
route; every other step is already right and stays as it is.

For each wrong step only, give the route of the page it happens on:

- Use only routes from the page list, written exactly as they appear there.
- Use only pages the workflow's role can open. A page without sign-in is open
  to everyone; a signed-in page is open only to the roles it lists (to every
  signed-in role when it lists none); someone who never signs in opens no
  signed-in page.
- A step that names a page is on that page.
- A step that continues where the person already is — filling a form, choosing
  an option, the system answering — is on the same page as the step before it.
- Never pick a page only because it shares a word with the step.

Return JSON only, nothing before or after it — one edit per wrong step:

```json
{"edits": [{"workflow_name": "…", "step": 3, "route": "/…"}]}
```

## Pages

{{pages}}

## Workflows

{{workflows}}
