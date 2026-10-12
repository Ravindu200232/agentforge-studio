# Component diagram

**What is a Component Diagram?**

A UML component diagram shows modular software parts, the interfaces or ports through which they collaborate, and the dependencies required to assemble the system.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart LR`

## Exact notation (use these tokens, not approximations)

- Each component is a rectangle carrying the `<<component>>` stereotype in its label, on its own line: `c1["<<component>>\nTaskService"]`.
- For this compact architectural view, use one light-blue outer `subgraph` labelled `<<component>>\nMarketplace Platform`, with its inner components arranged left-to-right. External providers sit outside that boundary.
- A provided interface (the component offers this) is a small circle node connected to it — the "lollipop": `i1((ITaskService)) --- c1`.
- A required interface (the component needs this from elsewhere) is a socket, approximated as a half-circle label on the edge itself: `c1 -->|"requires ITaskService"| i1`.
- A dependency between components (one needs the other to compile/run, without a formal interface) is a **dashed** arrow: `c2 -.-> c1`. Never use a solid arrow for a dependency — a solid arrow in this diagram means a direct, hard connection through an actual interface.
- Only when the SRS actually describes a composite component made of nested sub-components (one module assembled from several inner ones, exactly like the reference's outer `Terminal` exposing ports to its inner `SafetyInspection`/`Staff`/`Map`): draw the outer component as a `subgraph` carrying the `<<component>>` stereotype, the inner components inside it, and a small square **port** node on the boundary for each externally exposed interface, wiring the port through to the specific inner component that actually implements it: `port1["▪"] --- inner1`. Do not add ports to an ordinary, non-nested component.

## How to draw it

- Start with the single platform boundary and exactly five inner components: storefront, seller/staff console, marketplace core, payment adapter, and fulfilment adapter. Do not draw a component for every screen, database table, provider, endpoint, or service.
- Give each component one clear responsibility and connect every displayed dependency through a port/interface or an explicit dashed dependency edge, never a bare unlabeled line.
- Show only 2–3 service boundaries that the SRS truly identifies: catalogue/order operations between the UI and core, payment gateway, and courier tracking. Do not invent one lollipop per component.
- Treat external payment and courier providers as labelled rectangles outside the platform boundary, not as extra internal components.
- Keep labels to a stereotype plus a short 1–4 word component name; put responsibilities in the walkthrough, not inside the node. Dependency labels must be 1–4 words such as `catalogue data`, `order state`, or `refund release`.
- Keep the single boundary balanced on one landscape canvas. Place the UI/console at the left, core in the centre, adapters at the right, and external providers immediately beyond their adapter. Do not create a tall list of features or long cross-boundary lines.
- Use the reference palette: component containers and component rectangles light blue `#75C5E8`, interface circles white with dark `#111827` outlines, dashed dependencies dark, and no gradients, shadows, emojis, or decorative legend arrows.
