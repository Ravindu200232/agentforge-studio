
## Continue from where you stopped

This run was interrupted before it finished (the studio stopped, or the run was cancelled). Nothing you
did is undone. Do not start over and do not repeat what is finished: read `.agentforge/deploy/events.jsonl`
and `run.json`, look at the real state of the project (`git log`, `git status`, what exists on the host),
and carry on from the first step that is not really finished. If a step was cut off in the middle
(for example an install), check what it left and redo that step cleanly.
