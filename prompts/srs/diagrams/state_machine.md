# State Machine diagram

**What is a State Machine Diagram?**

A UML state machine shows the legal states in one object's lifecycle and the events or conditions that permit each transition.

## Standard

- OMG UML 2.5.1
- Mermaid form: `stateDiagram-v2`

## Exact notation (use these tokens, not approximations)

- The lifecycle starts from the initial pseudostate: `[*] --> Open`.
- Every terminal state points to the final pseudostate: `Closed --> [*]`.
- A transition names its trigger and, only when the SRS states one, its guard and action:
  `Open --> InProgress : assigned`
  `InProgress --> Done : completed [all subtasks closed]`
- A composite state — a state that has its own sub-lifecycle — is a nested block, not a flat state:
  ```
  state Reviewing {
    [*] --> AwaitingReviewer
    AwaitingReviewer --> Approved
  }
  ```
- A branching condition with no state of its own is a choice pseudostate: `state decide <<choice>>` then `decide --> A : [x]` / `decide --> B : [not x]`.
- Concurrent regions use fork/join pseudostates: `state split <<fork>>` … `state join_state <<join>>`.

## How to draw it

- Start from the initial pseudo-state and one explicitly modelled lifecycle field (a `status`, `state` or similar enum the database design actually defines).
- Draw only legal from-state to to-state transitions stated or clearly implied by the requirements and workflows — never invent a transition to make the diagram look complete.
- If no lifecycle field with modelled transitions is specified, return `NOT_APPLICABLE: <what field or transition evidence is missing>` instead of fabricating one.
