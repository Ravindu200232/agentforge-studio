# Use Case diagram

**What is a Use Case Diagram?**

A UML use case diagram shows the system boundary, the external actors that use the system, and the observable goals they expect the system to fulfil.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart LR` (Mermaid has no native actor/oval primitives, so the shapes below are the closest standard approximation — use them exactly, not a plain box for everything)

## Exact notation (use these tokens, not approximations)

- The system boundary is a subgraph, named after the product: `subgraph SB["TeamTrack"]`.
- Each use case is a **stadium shape** inside the boundary — the closest Mermaid gets to a UML oval: `uc1(["Assign task"])`. Never draw a use case as a plain rectangle.
- Each actor is a node **outside** the boundary, styled distinctly so it reads as an actor rather than a use case:
  ```
  actor1[/"Admin"/]
  ```
  (a trapezoid/parallelogram shape, or apply `classDef actor` with a visibly different fill — pick one convention and hold it for every actor.)
- An actor-to-use-case line is a plain, unlabeled association: `actor1 --- uc1`.
- `<<include>>` (this use case always triggers the other) and `<<extend>>` (it triggers it only sometimes, from an extension point) are edge labels, not plain lines: `uc1 -->|"<<include>>"| uc2`.
- Actor generalization (one actor role is a specialization of another) is a labeled edge too: `admin --- staff` won't do; use `staff -->|"is a"| admin` or state it in a note — Mermaid has no generalization arrowhead for this diagram type.

## How to draw it

- Start with actors outside one named system boundary and place actor goals inside it as stadium-shaped use cases.
- Connect actors only to goals supported by the approved roles and capabilities — a role the plan never grants an action to gets no edge to that use case.
- Add `<<include>>`, `<<extend>>`, or an actor generalization only when that relationship is explicit in the SRS; most use cases connect straight to their actor with nothing more.
