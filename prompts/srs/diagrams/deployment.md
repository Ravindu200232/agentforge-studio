# Deployment diagram

**What is a Deployment Diagram?**

A UML deployment diagram shows runtime nodes, the software artifacts hosted on them, and the communication paths that form the physical execution topology.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart TB`

## How to draw it

- Start with client, application host, and data host nodes required by the approved stack.
- Nest deployed software artifacts inside the node on which they execute.
- Label communication protocols and add external service nodes only when required by the SRS.
