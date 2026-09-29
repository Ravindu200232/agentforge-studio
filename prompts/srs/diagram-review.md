# Cloud diagram comparison gate

Review the proposed **{{kind}}** Mermaid diagram against the checked external
notation sources below and the project's curated SRS slice. This is a quality
gate after Mermaid has rendered it; do not rewrite the diagram and do not add
facts that are absent from the SRS.

## Checked source catalogue

{{sources}}

## Proposed Mermaid source

```mermaid
{{source}}
```

## Project evidence

Read `{{document}}` with `read_file`. It is the only source for project actors,
entities, workflows, operations, states, interfaces, deployment nodes and data.

## Review rules

- Compare source notation to the accepted symbols and image-derived visual rules
  in the catalogue. Check names, stereotypes, connector type/direction, labels,
  cardinality, boundaries, and required diagram-kind symbols.
- Compare every project-specific item to the SRS. Never approve a plausible but
  unsupported entity, relationship, state, integration, branch, field, protocol,
  or operation.
- Reject mixed notation systems, decorative directives, unlabelled mandatory
  connectors, incorrect control/data flow, or an unreadable direction.
- Mermaid's renderer is the final syntax authority. Do not request a source
  feature Mermaid cannot render; request the nearest standards-preserving repair.

Return JSON only:

```json
{"diagram_review":{"verdict":"pass","checks":["one verified check"],"findings":[]}}
```

For `repair`, list only concrete, source-grounded corrections in `findings`.
