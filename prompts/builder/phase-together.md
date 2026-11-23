## Built at the same time as other phases

Other agents are building other phases of this application at this very moment. So:

- Keep changes to the files owned by your current phase. Page phases own their routes, handlers, page-specific components and progress record.
- Reuse the foundation's shared layout, navigation, models and configuration. Keep a new page-specific helper in its own file.
- The browser test author writes its specs and route list. The unit test phase owns the unit result in the build report.
