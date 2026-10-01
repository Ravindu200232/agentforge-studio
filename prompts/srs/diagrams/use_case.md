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
- `<<include>>` and `<<extend>>` are **dashed directed dependencies**, never plain solid lines. The direction is material: base → included use case for `<<include>>`, and extending use case → base use case for `<<extend>>`: `checkout -.->|"<<include>>"| validatePayment`; `applyDiscount -.->|"<<extend>>"| checkout`.
- Actor generalization (one actor role is a specialization of another) is the sole actor-to-actor exception. Draw it from the specialized actor to the general actor, for example `superAdmin -->|"is a"| supportStaff`; Mermaid has no generalization arrowhead for this diagram type.

## How to draw it

- Start with actors outside one named system boundary and place actor goals inside it as stadium-shaped use cases.
- Connect actors only to goals supported by the approved roles and capabilities — a role the plan never grants an action to gets no edge to that use case.
- When the staged SRS explicitly identifies a mandatory internal subgoal of a larger user goal, retain that subgoal as a separate oval and draw one `<<include>>` dependency. For example, a documented stock-reservation step belongs to the supported order-placement goal. If the SRS contains no such mandatory subgoal, do not invent an include/extend link merely to decorate the view.
- Name each actor with a noun/role and each use case with a verb–noun goal. Add `<<include>>`, `<<extend>>`, or an actor generalization only when that relationship is explicit in the SRS; most use cases connect straight to their actor with nothing more. Never connect actor to actor, and do not show sequence/order of steps here.
- Keep this a stakeholder map, like the reference: normally 3–8 actors and **exactly 9–12** highest-value goals. Do not output a thirteenth goal. If the SRS has more capabilities, group them behind a supported goal rather than adding a tiny oval for every CRUD operation.
- Keep labels concise: actor names are 1–3 words and use-case names are 2–6 words. Do not paste requirement sentences, page names, or implementation details into a goal.
- Balance the layout around one visible boundary: actors on the left/right perimeter, goals in a readable grid inside, and no long crossing association lines. Use at most 3 actor generalizations and 4 include/extend dependencies.
- Preserve the reference palette with a light-blue system boundary `#75C5E8`, white/light-blue stadium goals, pale-blue actor nodes, and dark `#111827` outlines. Do not mix ERD, sequence, class, or state-machine syntax into this source; no gradients, shadows, icons, or explanatory legend arrows.
