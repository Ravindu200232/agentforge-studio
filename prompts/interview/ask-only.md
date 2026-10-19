## In this call: only the next step

The bookkeeping of this turn — the facts, the coverage updates, any contradiction and the assumptions — is done by a separate call at the same time, so do not write it here. Read the latest answer in the transcript above, decide what to do next by the system prompt's rules, and return only:

```json
{"stage": "gathering | confirming", "next": {"question": "...", "why_needed": "...", "answer_type": "...", "topic": "...", "coverage": ["..."], "options": [{"label": "...", "value": "...", "hint": "..."}], "recommended": null, "known": [], "known_quote": "", "placeholder": "", "remaining_estimate": 4}, "confirmation_summary": null}
```

Keep `why_needed` to one short sentence and each option to a few words.
