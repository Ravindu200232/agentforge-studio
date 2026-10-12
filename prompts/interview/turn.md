# This turn

Fold in the latest answer, update the coverage picture, and decide what to do
next — following the system prompt's rules for choosing a gap, handling a
contradiction, and deciding whether to keep gathering or move to confirmation.

## The product

- What kind of product: **{{app_type}}**
- The customer's idea: {{idea}}
- Stack: {{stack}} (already decided — never ask about it)
- Specification language: {{language}}

## What they have attached

{{attachments}}

## What they have told you so far

{{transcript}}

## Coverage so far

Every category's current status, confidence and recorded facts:

```json
{{coverage_json}}
```

## The category taxonomy

Every category's meaning and importance — this is the complete list; never
report a `coverage_updates` or `next.coverage` key that is not one of these:

```json
{{categories_json}}
```

## Contradictions not yet resolved

```json
{{open_contradictions_json}}
```

## Where this interview stands

Stage: **{{stage}}** — question {{asked}} so far, roughly {{budget}} as a hard
ceiling if the picture is still incomplete by then.

## Rules

- **Never ask something the transcript or coverage already answers.** If it is
  already KNOWN, do not ask about it again — not even to confirm.
- **Never open with "You said…" or "You mentioned…".** Ask the question.
- Ask about outcomes and behaviour, not screens or implementation.
- Make the trigger, actor, expected result and any rule or exception clear
  enough that a developer and a tester would read it the same way.
- Set `recommended` only for a conventional, reversible, low-risk default.
- Never ask about the technology stack, hosting, database or deployment.
- This platform builds responsive web applications only — never native mobile.

Return the JSON object the system prompt specifies, and nothing else.
