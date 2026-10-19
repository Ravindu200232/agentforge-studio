# The final checks, after the journeys

The Studio has photographed every page and had what looked wrong fixed, and has run the whole journey suite on this application; its result is in `.agentforge/qa/e2e-run.json` and the runs kept under `.agentforge/qa/runs/`. Now run the remaining layers, once each, with the scaffold's existing runners, reading each layer's guide first (`visual.md`, `axe.md`, `lighthouse.md`, `zap.md` among the stack build guides):

- visual: `npm run qa:visual`;
- accessibility: `npm run qa:a11y`;
- performance: `npm run qa:perf`;
- security: `npm run qa:security`;
- dependencies: `npm audit --omit=dev --json`.

If a check finds a real product defect, repair only the affected code, prove it still compiles with `npm run build`, and rerun only the check that found it. A repair here is never checked with the journeys: do not run a journey spec or the whole suite. When you finish, the Studio checks your changes with the runtime test (the build, then every page opens), not the journeys. When a tool is unavailable, do not keep trying to install or rerun it: record it honestly as an `"unavailable"` gap and carry on.

Then reopen `{{report_template}}` and fill both report files from it: `.agentforge/build/report.json` from its `build` section, preserving all earlier evidence, and `.agentforge/qa/report.json` from its `qa` section, with the journeys taken from the Studio's run. Take every count from the runners' own output on disk, not from memory. Mark the QA report complete only after every layer has one honest recorded outcome. Finish with one paragraph saying what the checks found and what you changed.
