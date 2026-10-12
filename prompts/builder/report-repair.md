The application and its checks are finished. Only the two report files are left: they are not yet in the shape the Testing screen reads, which is written down in `{{template}}`.

What does not match:

{{problems}}

Open `{{template}}` and rewrite `.agentforge/build/report.json` and `.agentforge/qa/report.json` so every key in its `required` lists is there, with the same kind of value as its `example`. Keep every fact already recorded — move it into the right key instead of dropping it. Take counts from the runner files already on disk (`.agentforge/qa/vitest.json`, `test-results/`, `.agentforge/qa/runs/`, `.lighthouseci/summary.json`, `.agentforge/qa/zap/summary.json`). Do not change the application and do not run any build or test again.
