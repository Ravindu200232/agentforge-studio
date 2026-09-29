# Draw one diagram

Produce the Mermaid source for one **{{kind}}** diagram of the system described
below. Return only the Mermaid source — no commentary, no markdown fence, no
explanation.

## The standard

{{standard}}

{{guidance}}

## Notation reference (style only — never a source of content)

{{reference}}

Use this only to confirm you are using real, recognizable notation for this
diagram kind — correct arrow types, correct shapes, correct keywords. Every
actor, entity, message, state and flow you draw must still trace only to the
specification below. Never copy an actor, entity or step from this reference;
it may describe a different product entirely.

## Rules

- Draw only what the specification supports. Every actor, entity, message, state
  and flow must trace to something in the document below. Do not invent a
  participant to make the picture look complete.
- If the document genuinely lacks the evidence for this diagram — a state machine
  with no lifecycle field, a sequence with no workflow — return exactly
  `NOT_APPLICABLE: <one sentence naming the missing evidence>` instead of a
  guess.
- Use the notation the standard prescribes, and nothing outside it.
- Label every edge with what actually moves along it, not with a control word.
- Keep identifiers valid Mermaid: no unescaped quotes, parentheses or newlines
  inside node labels.
- The source must parse on its own. Nothing downstream repairs it.

## Professional presentation contract

- Treat this as an engineering-document figure, not a colourful flowchart: use the diagram kind's standard shapes and connectors, white background, restrained dark linework, readable labels, and generous whitespace. Do not add gradients, shadows, emojis, icons, decorative colours, click/action links, or a legend that repeats obvious notation.
- Choose the supplied orientation deliberately. Keep the primary reading flow consistent (left-to-right or top-to-bottom); group related elements, minimize crossed connectors, and never let an edge run through a node label.
- Do not make a diagram look more complete by inventing entities, branches, external systems, interfaces, fields, protocol names, state transitions, or cardinalities. Correct notation only improves the presentation of evidence already in the SRS.
- Before returning, perform the diagram-kind audit in the guidance: check every required start/end, boundary, participant, relationship, key, label, cardinality, stereotype, or transition for this specific kind. Return source only after that audit.

## The specification

Read `{{document}}` yourself with your `read_file` tool before drawing — it
is the curated slice of the specification this diagram needs, not pasted in
here.
