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
