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
- Two truly independent lifecycles running at once inside one composite state (an order's fulfillment status and its payment status changing independently, exactly like the reference's `Auction` state) are **orthogonal regions**: one composite block, its regions separated by a bare `--` divider, each with its own initial pseudostate and its own path out:
  ```
  state Auction {
    [*] --> GettingBid
    GettingBid --> Evaluating : bidOffered
    --
    [*] --> Checking
    Checking --> Authorized : authorized
  }
  ```
  Use this, not fork/join, when the SRS describes two independent aspects of one object changing concurrently. Reserve fork/join pseudostates (`state split <<fork>>` … `state join_state <<join>>`) for a single flow that explicitly splits into parallel steps and later reconverges.

## How to draw it

- Start from the initial pseudo-state and one explicitly modelled lifecycle field (a `status`, `state` or similar enum the database design actually defines).
- Draw only legal from-state to to-state transitions stated or clearly implied by the requirements and workflows — never invent a transition to make the diagram look complete.
- If no lifecycle field with modelled transitions is specified, return `NOT_APPLICABLE: <what field or transition evidence is missing>` instead of fabricating one.
- Focus on exactly one business object's lifecycle (for example an order, application, or payment), as in a proper state-machine figure. Keep transitions event-led and concise; cross-object workflow work belongs in sequence or activity diagrams.
- Keep one compact lifecycle with 6–10 states and 8–14 transitions. State names and trigger labels must be short (1–4 words); do not copy full workflow sentences or mix several objects' lifecycles.
- Use one clear left-to-right or top-to-bottom route, place alternative terminal states near the relevant choice, and avoid crossing transitions. The visual treatment should use light-blue rounded states `#75C5E8`, dark `#111827` arrows/text, white canvas, and no gradients, shadows, emojis, or decorative annotations.
