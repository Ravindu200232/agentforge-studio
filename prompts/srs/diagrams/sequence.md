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
  `alt condition … else … end`, `opt condition … end`, `loop while condition … end`, `par … and … end`. Fragments may nest (an `alt` inside a `loop`) exactly like the reference, only when the SRS states both the repetition and the condition.
- A message that brings a new participant into existence mid-scenario is a **create message**: declare it inline with `create participant Reservation` (or `create actor` for a human) immediately before the message that instantiates it, then message it normally — never declare a created participant up front with the rest of the lifelines.
- A lifeline that ends before the diagram does is destroyed explicitly with `destroy Participant`, drawn as the reference's `×` terminator — never let a finished lifeline simply run off the bottom when the SRS states the object/session ends.
- `Note over Participant: text` for a state or timing fact the workflow states explicitly — not for narration.

## How to draw it

- Start with the initiating actor, the application participants the scenario actually touches, and their lifelines.
- Draw requests in execution order and show the corresponding return message for every call that has one.
- Use alt, opt, loop, or parallel fragments only when the SRS states those conditions — an unconditional flow gets none of them.
- Model one named happy-path use case plus its explicitly supported alternatives, never the whole product. Keep the left-to-right lifeline order in first-use order and normally use 3–8 lifelines so message labels and activation bars remain legible.
- Keep the scenario compact: use 3–6 lifelines, 8–16 messages, and at most one `alt`, `opt`, or `loop` fragment. Choose one checkout/order flow, not every feature in the SRS.
- Message labels are short calls or returns (1–5 words plus a small argument only when necessary); never copy requirement paragraphs, screen names, or database field lists into a message. Keep participant names short and stable.
- Use `rect`/fragment boundaries only for explicit alternatives or loops, keep activation bars aligned, and avoid messages that jump backward across many lifelines. Use the reference palette with light-blue participant headers `#75C5E8`, white canvas, dark `#111827` lifelines, and no gradients or decorative annotations.
