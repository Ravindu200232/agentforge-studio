# Deployment diagram

**What is a Deployment Diagram?**

A UML deployment diagram shows runtime nodes, the software artifacts hosted on them, and the communication paths that form the physical execution topology.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart TB`

## Exact notation (use these tokens, not approximations)

- Each physical or execution-environment node is a box carrying its stereotype: `n1["<<device>>\nClient browser"]`, `n2["<<execution environment>>\nApplication server"]`, `n3["<<device>>\nDatabase host"]`.
- A deployed software artifact sits **inside** the node that runs it, as a nested subgraph or a nested node connected only within that box: 
  ```
  subgraph n2["<<execution environment>>\nApplication server"]
    a1["<<artifact>>\nnextjs-app"]
  end
  ```
- A communication path between nodes is a plain labeled edge naming the protocol: `n1 -->|HTTPS| n2`, `n2 -->|MongoDB Wire Protocol| n3`.
- An external managed service (a hosted database, an email API) the app depends on at runtime but does not deploy itself is its own node, shaped or coloured distinctly from a node the team deploys: `n4["<<device>>\nExternal: Email provider"]`.

## How to draw it

- Start with client, application host, and data host nodes required by the approved stack, each labeled with its stereotype.
- Nest deployed software artifacts inside the node on which they execute — an artifact floating outside every node is wrong.
- Label communication protocols on every path and add external service nodes only when required by the SRS.
