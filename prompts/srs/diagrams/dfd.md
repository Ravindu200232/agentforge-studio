# Data Flow diagram

**What is a Data Flow Diagram?**

A data flow diagram shows how named information enters the system, is transformed by processes, is stored, and leaves for external entities.

## Standard

- Yourdon/DeMarco-style DFD
- Mermaid form: `flowchart LR`

## How to draw it

- Start with external entities, numbered verb–noun processes, and approved data stores.
- Label every arrow with the actual data being moved rather than a control-flow action.
- Never connect entity-to-entity or entity-to-store directly, and avoid black-hole or miracle processes.
