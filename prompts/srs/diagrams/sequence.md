# Sequence diagram

**What is a Sequence Diagram?**

A UML sequence diagram shows how an actor and system participants exchange messages for one scenario, with time progressing from top to bottom.

## Standard

- OMG UML 2.5.1
- Mermaid form: `sequenceDiagram`

## How to draw it

- Start with the initiating actor, application participants, and their lifelines.
- Draw requests in execution order and show the corresponding return messages.
- Use alt, opt, loop, or parallel fragments only when the SRS states those conditions.
