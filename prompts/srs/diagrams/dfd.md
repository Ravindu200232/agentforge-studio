# Data Flow diagram

**What is a Data Flow Diagram?**

A data flow diagram shows how named information enters the system, is transformed by processes, is stored, and leaves for external entities.

## Standard

- Yourdon/DeMarco-style DFD
- Mermaid form: `flowchart LR`

## Exact notation (use these tokens, not approximations)

- An external entity (a person or outside system that sends or receives data, but is not part of the system) is a plain rectangle: `e1[Customer]`.
- A process is a numbered, verb–noun circle or rounded box: `p1((1. Validate order))`. The number establishes reading order; do not skip or repeat numbers.
- A data store is an open-ended rectangle, approximated as `d1[(Order table)]`.
- Every arrow is labeled with the actual named data moving along it, never a control word: `e1 -->|order details| p1` — not `e1 --> p1: sends`.
- The Yourdon/DeMarco rule that keeps this a DFD and not a flowchart: **no edge connects entity-to-entity or entity-to-store directly.** Every flow must pass through a process. An edge that violates this is wrong even if the SRS seems to invite it — route it through the process that actually does the work.
- No "black-hole" process (has inputs but produces no output) and no "miracle" process (produces output from nothing) — every process needs at least one labeled input and one labeled output.

## How to draw it

- Start with external entities, numbered verb–noun processes, and approved data stores from the database design.
- Label every arrow with the actual data being moved rather than a control-flow action.
- Never connect entity-to-entity or entity-to-store directly, and avoid black-hole or miracle processes.
