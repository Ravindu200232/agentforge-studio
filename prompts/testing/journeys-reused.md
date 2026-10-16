## The end-to-end journeys

The journeys already ran on the application exactly as it is now; their results are in `test-results/results.json` and `.agentforge/qa/runs/`. Use them as the journeys layer: do not run the journey tests again, and do not change them. A repair you make for another layer (accessibility, security, performance) is checked with the runtime test, not the journeys: prove it compiles with `npm run build`, and the Studio checks that every page opens when you finish.
