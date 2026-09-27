# BPMN Process diagram

**What is a BPMN Process Diagram?**

A BPMN process diagram models a business process with events, tasks, gateways, and participant lanes that make responsibility and hand-offs explicit.

## Standard

- OMG BPMN 2.0.2
- Mermaid form: `flowchart LR`

## How to draw it

- Start with a named pool, horizontal responsibility lanes, and one start event.
- Place each task in the lane of the participant responsible for it and follow sequence flow.
- Use gateways only for explicit branch semantics and finish with an end event.
