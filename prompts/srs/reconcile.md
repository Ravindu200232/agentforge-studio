# Which open decisions did the customer just settle?

A customer asked for a change to their software requirements specification, and it has been made. The specification keeps a list of **open decisions**: points where the writer found something unclear, assumed an answer, and asked the customer to confirm it. Say which of those the customer's request settles.

## The customer's request

{{request}}

## What was changed (the agent's own summary of it)

{{summary}}

## The open decisions

{{decisions}}

## Rules

- A decision is **settled** only when the request (or the change as summarised) states the answer, or clearly implies it: it confirms the assumption, picks between the options, gives the missing value, or says to go with the assumptions. A request that merely touches the same area without deciding the point does **not** settle it.
- A request that accepts the writer's assumptions as a whole ("go with your assumptions", "keep what you assumed", "those are fine") settles every decision it covers, with the assumption as the decision.
- When in doubt, it is not settled. Leaving a decision open costs the customer one more look; settling one that was not decided hides it from them.
- Never settle a decision the request does not mention or imply, and never invent an id.

For each settled decision give the id, what is now decided in one sentence, and the words of the request (or the summary) that settle it.

Answer with ONE JSON object and nothing else:

```json
{"settled": [{"id": "AMB-001", "decision": "one sentence: what is now decided", "evidence": "the words that settle it"}]}
```

When the request settles none of them, answer `{"settled": []}`.
