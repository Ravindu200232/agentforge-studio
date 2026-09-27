# Sequence diagram

**What is a Sequence Diagram?**

A UML sequence diagram shows how an actor and system participants exchange messages for one scenario, with time progressing from top to bottom.

## Standard

- OMG UML 2.5.1
- Mermaid form: `sequenceDiagram`

## Exact notation (use these tokens, not approximations)

- Declare every lifeline first: `actor Customer` for a human, `participant API` / `participant DB` for system parts.
- A synchronous call is a **solid arrow with a filled head**: `Customer->>API: submitOrder(items)`.
- Its return is a **dashed arrow**: `API-->>Customer: orderId`. Never use a solid arrow for a return.
- Mark the call's execution with activation: `activate API` right after the call arrives, `deactivate API` right before its return — or the `+`/`-` shorthand: `Customer->>+API: submitOrder(items)` … `API-->>-Customer: orderId`.
- An asynchronous, fire-and-forget message (no return expected) uses a single-line arrow: `API->>Queue: emailReceipt`.
- Conditional or repeated behaviour only when the SRS actually states it:
  `alt condition … else … end`, `opt condition … end`, `loop while condition … end`, `par … and … end`.
- `Note over Participant: text` for a state or timing fact the workflow states explicitly — not for narration.

## How to draw it

- Start with the initiating actor, the application participants the scenario actually touches, and their lifelines.
- Draw requests in execution order and show the corresponding return message for every call that has one.
- Use alt, opt, loop, or parallel fragments only when the SRS states those conditions — an unconditional flow gets none of them.
