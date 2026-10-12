# Which review findings does the specification no longer have?

A software requirements specification was reviewed against requirements-writing standards, and the review listed findings. The customer then asked for changes and they were made. For each finding below, say whether the requirement, **as it reads now**, no longer has the problem the finding names.

## What the customer asked for

{{request}}

## What was changed (the agent's own summary of it)

{{summary}}

## The findings, each with the requirement text as it reads now

{{findings}}

## Rules

- Judge only from the text shown under each finding ("As it reads now"). Do not assume a change was made because it was asked for: the words have to be there.
- A finding is **resolved** only when the text shown now fixes the problem it names: it states the number, the bound, the rule, the control, the measurable threshold, the order of precedence, or whatever the finding said was missing, in a way a tester could check.
- A finding that is only partly put right, or whose problem is still there in the text, is **not** resolved. When in doubt, it is not resolved.
- Do not raise new findings, and do not judge anything the finding does not name.

For each resolved finding, give its number and the words from the text shown that put it right, copied exactly.

Answer with ONE JSON object and nothing else:

```json
{"resolved": [{"finding": "F1", "evidence": "the exact words from the text above that fix it"}]}
```

When none is resolved, answer `{"resolved": []}`.
