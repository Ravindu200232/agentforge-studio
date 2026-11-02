## In this call: only the bookkeeping

The next question is chosen by a separate call. Fold the latest answer in the transcript above into the picture and return only:

```json
{"facts_extracted": [...], "coverage_updates": {...}, "contradiction": {...}, "assumptions": [...]}
```

each as the system prompt specifies — no `stage`, `next` or `confirmation_summary`. Report only what changed with this answer.
