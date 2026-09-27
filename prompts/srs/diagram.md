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

## The specification

Read `{{document}}` yourself with your `read_file` tool before drawing — it
is the curated slice of the specification this diagram needs, not pasted in
here.
