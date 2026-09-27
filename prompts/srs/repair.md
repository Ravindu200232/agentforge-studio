# Correct the SRS JSON

Return exactly one complete JSON object with the same outer shape as the
provided SRS. Return JSON only: no explanation, markdown fence, tool call,
`write_file`, or `replace_text` instruction.

Preserve every correct requirement, field, identifier, page, table, workflow,
decision and constraint. Make only the smallest changes needed to resolve the
findings. Do not introduce any capability, role, screen, record, integration,
or policy that is not present in the approved plan. Keep every functional
requirement atomic and testable, and ensure every functional requirement has
exactly one traceability row. Ensure all planned workflows, screens and records
remain covered.

## Findings to fix

{{findings}}

## Approved plan

{{plan}}

## Current SRS JSON

{{document}}
