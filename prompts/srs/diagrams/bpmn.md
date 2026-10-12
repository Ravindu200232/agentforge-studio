# BPMN Process diagram

**What is a BPMN Process Diagram?**

A BPMN process diagram models a business process with events, tasks, gateways, and participant lanes that make responsibility and hand-offs explicit.

## Standard

- OMG BPMN 2.0.2
- Mermaid form: `flowchart LR`

## Exact notation (use these tokens, not approximations)

- The pool is the whole process, named after the workflow; each lane inside it is one responsible role, as a nested subgraph:
  ```
  subgraph Pool["Assigning a task"]
    subgraph Admin["Admin"]
      s1((Start))
      t1(Create task)
    end
    subgraph Staff["Staff"]
      t2(Complete task)
      e1(((End)))
    end
  end
  ```
- A start event is a thin-bordered circle: `s1((Start))`. An end event is a thick/double-bordered circle, approximated as `e1(((End)))`.
- A task is a rounded rectangle placed inside the lane of the participant who performs it: `t1(Create task)`.
- A gateway is a diamond, used only where the process actually branches, with every outgoing path labeled: `g1{Approved?} -->|yes| t3` / `g1 -->|no| t4`.
- Sequence flow (the solid arrow moving work forward) stays inside the pool. If a message genuinely crosses to a different pool/participant, mark it as a dashed arrow — never a plain solid one, which BPMN reserves for sequence flow only.
- A data object the process reads or produces (a document, a record) is its own small page-shaped node, connected to the task by a **dotted** association, never a sequence-flow arrow: `t1 -.-> d1["Purchase Order\n[Create]"]`. When the same document changes state as it moves through the process, repeat it at each relevant point with its new bracketed state, exactly like the reference's `[Create]` → `[To be Assigned]` → `[To be Delivered]` → `[Completed]` — never mutate one node's label after other flow already points to it.
- A short clarifying remark on the process (not a task, not a document) is a text annotation attached by a dotted line, exactly like the reference: `note1["Over 90% of requests are made by phone call, 10% by email."]` connected `t1 -.- note1`. Use one only when the SRS states a real qualifying fact worth calling out.

## How to draw it

- Start with a named pool, horizontal responsibility lanes for every role the workflow names, and one start event.
- Place each task in the lane of the participant responsible for it and follow sequence flow in the order the workflow states.
- Use gateways only for explicit branch semantics and finish every path with an end event.
- Keep a single business process in this figure. Use 2–5 lanes for roles/participants actually handing work off, keep flow left-to-right across the lanes, and show data objects only where the SRS explicitly names a business document or data hand-off.
- The output must contain a real connected BPMN-like source, not an explanation or an empty response: declare one pool, 2–4 lanes, one start event, the concise tasks/gateways needed for the named process, and an end event on every branch.
- Keep the process readable on one landscape canvas: use 6–14 tasks, at most 2 gateways, and short task labels of 1–5 words. Do not copy requirement paragraphs into task or message labels.
- Keep hand-offs explicit and avoid disconnected lane islands. Use the reference palette with light-blue pool/lane backgrounds `#75C5E8`, pale-yellow task cards `#F8EE9C`, dark `#111827` outlines, and no gradients, shadows, emojis, or decorative legends.
