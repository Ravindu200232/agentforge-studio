# Activity diagram

**What is an Activity Diagram?**

A UML activity diagram models a workflow as actions connected by control flow, including supported choices, loops, and concurrent work.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart TD`

## How to draw it

- Start at one initial node, follow the ordered SRS workflow, and finish at a final node.
- Use a decision and merge only for an explicit guarded alternative.
- Use fork and join bars only when the requirements explicitly allow parallel activities.
