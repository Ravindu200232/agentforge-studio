# Entity-Relationship diagram

**What is an Entity-Relationship Diagram?**

An ER diagram is a database blueprint showing persistent entities, their attributes, keys, relationships, and supported cardinalities.

## Standard

- Crow's Foot ERD
- Mermaid form: `erDiagram`

## Exact notation (use these tokens, not approximations)

- One block per entity, with typed, keyed attributes:
  ```
  TASK {
    string id PK
    string project_id FK
    string title
    date due_date
  }
  ```
  Every primary key gets `PK` after its type and name; every foreign key gets `FK`. An attribute with neither is a plain field.
- Crow's-foot cardinality is a literal token between the two entity names — pick the exact one the relationship needs, never a generic `--`:
  - Exactly one to exactly one: `||--||`
  - One to zero-or-one: `||--o|`
  - One to many (each parent has zero-or-more children): `||--o{`
  - One to many (each parent has one-or-more children): `||--|{`
  - Many to many: `}o--o{`
  Read the crow's-foot side nearest an entity as that entity's own cardinality constraint, not the other one's.
- Label the relationship with the verb that connects them: `PROJECT ||--o{ TASK : "contains"`.

## How to draw it

- Start from the approved persistent entities and list their typed PK and FK attributes exactly as the database design states them.
- Connect only explicit relationships or resolvable foreign-key references — a `project_id FK` on TASK implies a `PROJECT ||--o{ TASK` edge; do not invent one that has no such reference.
- Show one, many, and optionality with the crow's-foot markers above only when supported by the schema, and never fall back to a plain undecorated line.
- Produce a logical/physical schema view, not an application architecture: entity blocks must be domain nouns, attributes must carry real schema types, and PK/FK notation plus crow's-foot ends must do the explanatory work. Keep junction entities visible for many-to-many relationships rather than drawing an unsupported direct many-to-many link.
- Keep one readable schema canvas: include the 8–16 most important entities and omit audit-only or duplicate support tables unless they explain a relationship. Use short attribute names and no prose descriptions inside entity blocks.
- Each entity should normally have 3–8 attributes: its PK, only the FKs needed to explain connectors, and the most important domain fields. Never paste requirement sentences into an entity or relationship label.
- Prefer a balanced left-to-right layout with junction entities between their parents and minimal crossing connectors. Use the reference ERD palette: entity blocks orange `#F8B666`, dark `#111827` borders/text, and no gradients, shadows, icons, or decorative legends.
