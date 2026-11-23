## What this phase is: these pages

Build these pages of the approved application now, each one completely and working for real: its route in the application, the API or server handlers behind it, the data access, validation, authorization for the roles that may open it, and its loading, empty and error states.

{{routes}}

For each page, open the mapped prototype page and its relevant imports before
implementing it. Preserve its layout, text, typography, colors, images, responsive
states, controls and navigation. Reuse the exact prototype assets and the shared
components and styling from the foundation. Keep demo credentials out of the
visible interface. Leave the seed, full compile and tests to later phases.

When a page is finished, record it in `{{progress}}` (this phase's own record), merging into what is already there and never replacing it:

```json
{"routes": {"/the/route": ["every file written for this page, relative to the workspace"]}}
```

A page is only done when it has an entry there with its real files. Every page above gets one.
