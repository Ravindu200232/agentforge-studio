# Component diagram

**What is a Component Diagram?**

A UML component diagram shows modular software parts, the interfaces or ports through which they collaborate, and the dependencies required to assemble the system.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart TB`

## How to draw it

- Start with presentation, application/domain, and data/external component groups.
- Give each component one clear responsibility and connect every displayed dependency through a port.
- Show provided or required interfaces only when the SRS identifies that service boundary.
