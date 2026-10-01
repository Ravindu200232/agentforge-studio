# Deployment diagram

**What is a Deployment Diagram?**

A UML deployment diagram shows runtime nodes, the software artifacts hosted on them, and the communication paths that form the physical execution topology.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart LR`

## Exact notation (use these tokens, not approximations)

- Group nodes by physical location in a labeled boundary `subgraph`, exactly like the reference's "Clients" box and "Server" box: `subgraph SRV["Server"]` ... `end`, `subgraph CLI["Clients"]` ... `end`.
- Each node inside a boundary is its own box carrying a `<<processor>>` or `<<device>>` stereotype on its own line above the name, matching the reference exactly: `APP["<<processor>>\nApplication Server"]`, `CACHE["<<processor>>\nCaching Server"]`, `CONSOLE["Console"]`, `KIOSK["Kiosk"]`.
- A deployed software artifact is its **own separate box**, drawn *outside* the processor it runs on, never nested inside it — the reference always draws artifacts beside their processor, connected by an arrow, not nested inside its border: `A1["<<artifact>>\nhttp.exe"]`.
- Connect every artifact to the processor that runs it with a **dashed arrow labeled `<<deploy>>`**, pointing from the artifact to the processor it deploys onto, exactly as the reference shows: `A1 -.->|"<<deploy>>"| CACHE`.
- Connect nodes/boundaries that communicate at runtime with a plain solid line (no stereotype, no arrowhead needed unless direction matters): `CONSOLE --- CACHE`, `CACHE --- APP`.
- An external managed service the app depends on but does not deploy itself is its own node outside every boundary, distinguishable by the same `<<device>>`/`<<processor>>` stereotype convention.

## How to draw it

- Start with exactly three compact columns: a "Clients" boundary at left, a "Server" boundary in the centre, and an "External managed services" boundary at right.
- Place one processor/device node per real host inside its boundary, each carrying its stereotype line.
- Draw every deployed artifact as its own box beside (never inside) the processor it runs on, and connect it with a dashed `<<deploy>>` arrow into that processor — an artifact with no `<<deploy>>` arrow, or nested inside a processor's own box, is wrong.
- Connect boundaries/nodes that communicate at runtime with a plain line; label it only when a specific protocol matters (`HTTPS`, `PostgreSQL`).
- Model the executable topology, not every integration: use one browser client, application and database processors, and their three deployed artifacts. Inside the external-services boundary use exactly three nodes: identity provider; payments and seller payouts; courier, email and media services. Label the three app-to-external paths concisely. A reader must still trace where each artifact deploys and how nodes connect.
- Every artifact needs its `<<deploy>>` arrow: never return a deployment diagram with a disconnected artifact or a processor with no deployed artifact when the SRS names one.
- Use short artifact labels matching real build/service outputs (`web.exe`, `api.exe`, `db-admin.exe`); do not copy implementation paragraphs into a node.
- Keep the diagram balanced on one landscape canvas: client → application/database server → three external service nodes. Avoid long edge labels, a tall stack of provider nodes, and decorative or invisible layout edges.
- Use the reference palette: processor/device nodes and artifacts light blue `#75C5E8`, external providers pale yellow `#F8EE9C`, dark `#111827` outlines, and no gradients, shadows, emojis, or unconnected boxes.
