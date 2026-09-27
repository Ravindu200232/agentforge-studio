# System Context diagram

**What is a System Context Diagram?**

A system context diagram defines the software boundary and its externally visible relationships with people, external systems, and persistent data.

## Standard

- ISO/IEC/IEEE 29148:2018
- Mermaid form: `flowchart TB`

## Exact notation (use these tokens, not approximations)

- The system itself is exactly one node, visually distinct (thicker border via `classDef system` or a double box), centered: `sys[["TeamTrack"]]`.
- Human actors sit outside it as rounded or trapezoid nodes: `admin(["Admin"])`.
- External systems (a payment gateway, an email provider, anything outside this product's own code) sit outside it too, shaped differently from human actors so the two are never confused: `email[/"Email provider"/]`.
- Persistent data the system itself owns is drawn below or beside it as a cylinder: `db[(Database)]`.
- Every edge is a labeled arrow naming the actual interaction or data crossing the boundary: `admin -->|manages team via| sys`, `sys -->|sends invite| email`. An unlabeled edge is not acceptable at this diagram level.
- Nothing inside `sys` is decomposed here — no internal modules, no internal flow. That belongs to the component diagram.

## How to draw it

- Start with one central system boundary node and keep implementation detail inside it minimal — it is a single opaque box.
- Place human actors and external systems outside the boundary, shaped so the two kinds are visually distinguishable.
- Label every supported interaction or data relationship and omit unsupported integrations the SRS never mentions.
