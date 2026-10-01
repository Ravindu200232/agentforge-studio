# Activity diagram

**What is an Activity Diagram?**

A UML activity diagram models a workflow as actions connected by control flow, including supported choices, loops, and concurrent work.

## Standard

- OMG UML 2.5.1
- Mermaid form: `flowchart TD`

## Exact notation (use these tokens, not approximations)

- Initial node: a small filled circle, approximated as `start((●))`.
- Final node(s): `stop((◉))` — every path must end at one, even a path that exits early via a decision.
- An action is a rounded rectangle, not a sharp-cornered box: `a1(Validate order)`.
- A decision (one path in, multiple guarded paths out) is a diamond, and **every** outgoing edge from it carries its guard as a label: `d1{Payment valid?} -->|yes| a2` / `d1 -->|no| a3`. A merge (multiple paths back to one) is a second diamond with no label needed on its incoming edges.
- Fork and join (true parallel activities, not just two separate steps) use a thick bar, approximated with a wide subgraph or explicit fork/join labels: `fork1[/"fork"/]` splitting into branches that both reconnect at `join1[\"join"\]` — only when the requirements explicitly say the actions happen concurrently, not merely in either order.
- A swimlane per responsible role, when the SRS names more than one actor in the workflow: `subgraph Admin_Lane["Admin"]` … `end`.

## How to draw it

- Start at one initial node, follow the ordered SRS workflow, and finish at a final node — every branch must reach one.
- Use a decision and merge only for an explicit guarded alternative the workflow states, and always label both outgoing edges.
- Use fork and join bars only when the requirements explicitly allow parallel activities; a workflow with a strict, single order gets none.
- When more than one responsible role appears, use one clear swimlane per role and put each action in the lane that owns it. Keep the main path readable from top to bottom; a guarded error path may rejoin or terminate, but must never cross a lane without an explicit hand-off.
- Keep the rendered diagram compact enough to read on one landscape canvas: use no more than 3 swimlanes, keep each lane in a single `subgraph`, and keep the main workflow to 8–14 action/decision nodes. Combine adjacent micro-steps into one concise action instead of copying full requirement sentences.
- Action labels must be short phrases (ideally 2–7 words, never a paragraph); move details such as totals, refund rules, tracking fields, or screen names into the plain-English walkthrough, not into node labels. Edge guards should be 1–4 words.
- Do not make three long vertical columns by placing independent role subgraphs one after another. Use one compact left-to-right lane composition when possible, or connect the role hand-offs so the diagram has balanced width and height with minimal empty space.
- Use `classDef` to preserve the reference palette: action nodes light blue `#75C5E8`, decision diamonds light blue, lane backgrounds white, dark `#111827` outlines, and no gradients, shadows, icons, or decorative labels.
