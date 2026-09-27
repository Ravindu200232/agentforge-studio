# Component diagram

**What is a Component Diagram?**

A UML component diagram shows modular software parts, the interfaces or ports through which they collaborate, and the dependencies required to assemble the system.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart TB`

## Exact notation (use these tokens, not approximations)

- Each component is a rectangle carrying the `<<component>>` stereotype in its label, on its own line: `c1["<<component>>\nTaskService"]`.
- Group components into the three bands the standard expects, as subgraphs: `subgraph Presentation`, `subgraph Application_Domain`, `subgraph Data_External`.
- A provided interface (the component offers this) is a small circle node connected to it — the "lollipop": `i1((ITaskService)) --- c1`.
- A required interface (the component needs this from elsewhere) is a socket, approximated as a half-circle label on the edge itself: `c1 -->|"requires ITaskService"| i1`.
- A dependency between components (one needs the other to compile/run, without a formal interface) is a **dashed** arrow: `c2 -.-> c1`. Never use a solid arrow for a dependency — a solid arrow in this diagram means a direct, hard connection through an actual interface.

## How to draw it

- Start with presentation, application/domain, and data/external component groups as three subgraphs.
- Give each component one clear responsibility and connect every displayed dependency through a port or an explicit dashed dependency edge, never a bare unlabeled line.
- Show provided or required interfaces only when the SRS identifies that service boundary — do not invent an interface for every component.
