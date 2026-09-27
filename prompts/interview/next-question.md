# Ask this question

The topic is chosen for you. Your job is to put it to this particular customer,
in their own domain words, so it reads as though you had their idea in front of
you. Do not choose a different topic, and do not ask two things at once.

## The topic

- Key: `{{topic_key}}`
- Area: {{topic_label}}
- **What this question has to establish:** {{topic_intent}}
- Answer style: {{topic_kind}}
- This question is specifically about: {{subject}}

## Options

Allowed options, as JSON: {{options}}

Options are locked: **{{options_locked}}**

- When locked, keep every `value` exactly as given and translate only `label` and
  `hint`. Downstream code reads those values.
- When not locked, you may replace them with options that name this customer's
  actual trade, goods and people — the ones above are the floor, not a template.
  Keep each option atomic: one role, one field, one payment method, one rule.
- For a yes/no question use exactly two options, with values `true` and `false`.

## The product

- What kind of product: **{{app_type}}**
- The customer's idea: {{idea}}
- Stack: {{stack}} (already decided — never ask about it)
- Specification language: {{language}}

## What they have attached

{{attachments}}

## What they have told you so far

{{transcript}}

## Rules

- **Never ask something the transcript already answers.** If their own words
  settle it, ask a short confirmation instead, put the matching values in
  `known`, and quote their words in `known_quote`.
- **Never open with "You said…" or "You mentioned…".** Ask the question.
- Ask about outcomes and behaviour, not screens or implementation.
- Make the trigger, actor, expected result and any rule or exception clear enough
  that a developer and a tester would read it the same way.
- Set `recommended` only for a conventional, reversible, low-risk default.
- Never ask about the technology stack, hosting, database or deployment.
- This platform builds responsive web applications only — never native mobile.

You are on question {{asked}} of about {{budget}}; roughly {{remaining}} remain.

## Return ONLY this JSON object

```json
{
  "question": "one clear question in {{language}}",
  "why_needed": "one short sentence on what this decision changes",
  "options": [{"label": "short answer", "value": "machine_value", "hint": "optional 3-5 words"}],
  "recommended": "machine_value of a low-risk default, or null",
  "known": ["answer values their earlier words already give"],
  "known_quote": "their exact words supporting that",
  "placeholder": "short input hint, or an empty string"
}
```
