# Data Flow diagram

**What is a Data Flow Diagram?**

A data flow diagram shows how named information enters the system, is transformed by processes, is stored, and leaves for external entities.

## Standard

- Yourdon/DeMarco-style DFD (Mermaid approximation for stores)
- Mermaid form: `flowchart TB`

## Exact notation (use these tokens, not approximations)

- An external entity (a person or outside system that sends or receives data, but is not part of the system) is a plain rectangle: `e1[Customer]`.
- A process is a numbered, verb–noun circle or rounded box: `p1((1. Validate order))`. The number establishes reading order; do not skip or repeat numbers.
- A data store is represented by the standard parallel-line/open-ended-store concept; Mermaid has no native parallel-line shape, so use its closest distinct data-store approximation: `d1[(Order table)]`. Do not use that cylinder for a process or external entity.
- Every arrow is labeled with the actual named data moving along it, never a control word: `e1 -->|order details| p1` — not `e1 --> p1: sends`.
- The Yourdon/DeMarco rule that keeps this a DFD and not a flowchart: **no edge connects entity-to-entity or entity-to-store directly.** Every flow must pass through a process. An edge that violates this is wrong even if the SRS seems to invite it — route it through the process that actually does the work.
- No "black-hole" process (has inputs but produces no output) and no "miracle" process (produces output from nothing) — every process needs at least one labeled input and one labeled output.

## How to draw it

- Start with external entities, numbered verb–noun processes, and approved data stores from the database design.
- Label every arrow with the actual data being moved rather than a control-flow action.
- Never connect entity-to-entity or entity-to-store directly, and avoid black-hole or miracle processes.
- Draw one coherent Level-1 view: use a small numbered set of major transformations in reading order, place external entities at the perimeter and data stores near their consuming processes. Do not turn a DFD into a control-flow or database-schema diagram.
- Keep the Level-1 view readable on one landscape canvas like the reference: use exactly 4 major processes, 4–5 data stores, and at most 4 external entities total (people and providers together). Combine related operations into one transformation; do not model every screen, field, status, endpoint, or actor as its own node.
- Data-flow labels are concise noun phrases of 2–6 words (for example `order details`, `payment result`, `tracking update`); never copy a full requirement sentence into an edge label.
- Use a balanced top-to-bottom composition with the four processes in a compact central reading sequence, external entities on the left/right perimeter, and stores directly below their owning process. Give a process one outgoing hand-off to the next process instead of drawing long return loops across the canvas; avoid crossing edges and do not exceed a 3:1 width-to-height ratio.
- Declare the four numbered processes first and connect them only as `p1 --> p2 --> p3 --> p4`, so Mermaid preserves a compact top-to-bottom centre. Attach each external entity to one owning process only. A store normally belongs to one process; `orders` may serve payment and fulfilment. Never draw a browse process writing catalogue data back to its product or shop store.
- Use `classDef` to preserve the reference palette: external entities pale yellow `#F8EE9C`, processes light blue `#75C5E8`, stores white with dark `#111827` outlines, dark arrow labels, and no gradients, shadows, icons, or decorative legends.
