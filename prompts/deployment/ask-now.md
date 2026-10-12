## You stopped without asking

You stopped, but there is no question for the customer in `.agentforge/deploy/question.json`, so nobody can
answer you. Do not restart the plan and do not redo finished steps.

If the deployment needs the customer now — a value, a decision, an account, a way past a problem you could not
solve — write that one question to `.agentforge/deploy/question.json` exactly as the rules above say (two to four
options with your recommendation first, an `assumption`; a value only the customer has with `"variable"` and
`"secret": true`), set `state` to `NEEDS_INPUT` in `run.json`, and end your reply with the blocked marker.

If it does not need them, carry on with the plan from the first step that is not finished.
