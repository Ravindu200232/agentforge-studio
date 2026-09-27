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

## How to draw it

- Start with a named pool, horizontal responsibility lanes for every role the workflow names, and one start event.
- Place each task in the lane of the participant responsible for it and follow sequence flow in the order the workflow states.
- Use gateways only for explicit branch semantics and finish every path with an end event.
