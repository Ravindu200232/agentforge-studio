# Put every journey step on its page

Each workflow below is a user journey: the role that takes it and its ordered
steps. Some of their step routes are wrong (see the problems). For every listed
workflow, give the route of the page each step happens on.

- Use only routes from the page list, written exactly as they appear there.
- Use only pages the workflow's role can open. A page without sign-in is open
  to everyone; a signed-in page is open only to the roles it lists (to every
  signed-in role when it lists none); someone who never signs in opens no
  signed-in page.
- A step that names a page is on that page.
- A step that continues where the person already is — filling a form, choosing
  an option, the system answering — repeats the route of the step before it.
- Never pick a page only because it shares a word with the step.
- Exactly one route per step, in the steps' order.

Return JSON only, nothing before or after it:

```json
{"workflows": [{"workflow_name": "…", "step_routes": ["/…"]}]}
```

## Pages

{{pages}}

## Workflows to correct

{{workflows}}

## Problems found

{{problems}}
