# Class and Object diagram

**What is a Class & Object Diagram?**

A UML class diagram describes static types, their attributes, operations, and relationships; an object view shows an illustrative runtime instance of one of those classes.

## Standard

- OMG UML 2.5.1
- Mermaid form: `classDiagram`

## Exact notation (use these tokens, not approximations)

- One compartmented box per class:
  ```
  class Task {
    + id: UUID
    + title: String
    - dueDate: Date
    + assignTo(user: User): Boolean
    + markDone(): Void
  }
  ```
- A class name is mandatory and uses a singular domain noun in PascalCase. The second compartment contains attributes; type follows `:`. The third contains operations; each parameter is `name: Type` and the return type follows the closing `):`. Do not create a fake getter/setter merely to fill a compartment.
- If a requirement explicitly distinguishes an input, output, or in/out parameter, write its direction before the parameter name (`in filter: Filter`, `out result: Report`, `inout cursor: Cursor`). Otherwise omit the direction rather than guessing.
- Visibility is a real UML symbol, always present on every displayed attribute and operation: `+` public, `-` private, `#` protected, `~` package. Never omit it.
- Relationship tokens (draw the one the SRS evidence actually supports — never default to plain association):
  - Inheritance / generalization: `Admin --|> User`
  - Interface realization: `TaskRepository ..|> Repository`
  - Composition (owner's lifetime controls the part): `Project *-- Task`
  - Aggregation (part can outlive the whole): `Team o-- User`
  - Plain association: `User --> Notification`
  - Dependency (uses, does not hold a reference): `TaskController ..> TaskService`
- Generalization means “is a”; draw the hollow triangle at the general class end. Realization is a dashed hollow triangle from a concrete class to its interface. Aggregation has an unfilled diamond at the whole; composition has a filled diamond at the whole. Do not use either diamond merely because two entities are related.
- Relationship labels are short domain verbs/verb phrases after `:` — for example `Order "1" *-- "1..*" OrderLine : contains`. Never label an edge `has`, `uses`, or the relationship type itself.
- When the SRS states cardinality, write an exact multiplicity at **both** ends in quotes. Use only `0..1`, `1`, `0..*`, `1..*`, `*`, or a stated fixed number/range — never vague labels such as `many`. If the SRS does not establish cardinality, omit it rather than inventing it.
- An enumeration or interface gets a stereotype line as the first entry in the box: `<<interface>> Repository` or `<<enumeration>> Status`.
- When the design genuinely separates analysis-level responsibilities — a screen or external-facing surface, a coordinating workflow, a persistent domain record — stereotype each class accordingly with `<<boundary>>`, `<<control>>`, or `<<entity>>` as its first compartment line, exactly like the reference's `Window`/`DialogBox` (`<<boundary>>`), `DrawingContext` (`<<control>>`) and `Shape`/`Circle` (`<<entity>>`). Only apply this when the SRS/design actually distinguishes these roles; a plain domain model needs no stereotype at all.
- A short clarifying note on one class uses Mermaid's own note syntax, attached by a dashed line exactly like the reference: `note for Window "The main window of the application."`. Use a note only for something not already obvious from the class's own name/members — never to restate the class name.
- Add a second object view only if the SRS gives a useful concrete example. Mark it `<<object>>`, label it `instanceName : ClassName`, and show concrete values instead of attribute types, e.g. `class Task482["task-482 : Task"] { <<object>>\n title = Ship v1 }`. It is illustrative, not another domain class.

## How to draw it

- Choose the **conceptual** perspective for a requirements SRS: model stable domain concepts and their responsibilities, not framework classes, controllers, database adapters, or every implementation field. Use specification detail only where the SRS explicitly gives it.
- Start with one compartmented class box per supported domain type from the database design and requirements. Keep a readable single view: group inheritance hierarchies, avoid crossing connectors, and use `direction LR` for a wider model where it materially improves legibility.
- Use the renderer's restrained default UML presentation: no gradients, shadows, emojis, icons, click actions, colour coding, `classDef`, or theme directives. Relationship meaning must come from UML connector end symbols and labels, not presentation styling.
- List typed attributes and operations only when they are present in the SRS model — do not invent getters/setters that are not implied by a requirement.
- Add association multiplicity, aggregation, composition, inheritance, realization, or dependency only with supporting evidence in the specification. Every connector needs its relationship label.
- Before returning, audit each class for name → attributes → operations order, each member for visibility and type/signature, each connector for the exact UML relationship meaning, and every stated cardinality for two valid end labels.
- Use **exactly 8–10** stable domain classes in one readable model; never output an eleventh class. Do not duplicate the ERD wholesale: omit framework, transport, and persistence implementation classes, and show an object snapshot only when it clarifies a real requirement example.
- Keep the primary class view compact, with no more than 5 attributes and 3 operations per class unless the SRS explicitly requires more. Show at least three short, SRS-supported public operations across the classes that participate in documented workflows; do not invent getters/setters. Use short domain names and signatures; do not paste SRS prose into compartments.
- Use `direction LR` and a balanced hierarchy to minimize crossed connectors. If an object snapshot is justified, show at most 2 small `<<object>>` instances beside the classes they instantiate.
- Match the supplied reference's restrained UML palette through the renderer: light-blue class boxes `#75C5E8`, dark `#111827` borders/text, no gradients, shadows, emojis, or explanatory arrows.
