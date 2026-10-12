# Fix the SRS with edits

The SRS below was reviewed and the findings list what must change. Fix every
finding with the smallest edits that resolve it. Do not return the SRS again:
return only the edits, and change nothing a finding does not ask for.

Return JSON only — no explanation, markdown fence or tool call:

```json
{"edits": [
  {"op": "set", "path": "functional_requirements[id=FR-012].requirement", "value": "The system shall ..."},
  {"op": "add", "path": "requirement_traceability_matrix", "value": {"requirement_id": "FR-031", "...": "..."}},
  {"op": "remove", "path": "non_functional_requirements[id=NFR-009]"}
]}
```

- `set` replaces the value at `path` (a field, or a whole list item).
- `add` appends `value` to the list `path` names.
- `remove` deletes the field or list item at `path`.
- A path is dot-separated keys from the top of the SRS JSON shown below. Pick a
  list item by one of its own identifying fields — `[id=FR-012]`,
  `[requirement_id=FR-012]`, `[route=/orders]`, `[table_name=orders]`,
  `[workflow_name=...]`, `[role_key=...]` — and by position (`[0]`) only when
  the item has no such field.
- A new item carries every field its neighbours carry, with a new unique id.

Keep every requirement atomic and testable, every functional requirement with
exactly one traceability row, and every planned workflow, screen and record
covered. Do not introduce any capability, role, screen, record, integration or
policy that is not in the approved plan.

## Findings to fix

{{findings}}

## Approved plan

{{plan}}

## Current SRS JSON

{{document}}
