## What this phase is: these pages

Build these pages of the approved application now, each one completely and working for real: its route in the application, the API or server handlers behind it, the data access, validation, authorization for the roles that may open it, and its loading, empty and error states.

{{routes}}

For each page, reopen its mapped prototype page (a `.tsx` file under `.agentforge/prototype/`) and the components it imports immediately before you build it, and reproduce the page at full parity (the parity map in the plan names the destination files). Reuse the shared components and styling from the foundation; add to them rather than copying.

When a page is finished, record it in `.agentforge/build/progress.json`, merging into what is already there and never replacing it:

```json
{"routes": {"/the/route": ["every file written for this page, relative to the workspace"]}}
```

A page is only done when it has an entry there with its real files. Every page above gets one.
