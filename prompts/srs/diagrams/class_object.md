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
    +String id
    +String title
    -Date dueDate
    +assignTo(user: User) bool
    +markDone() void
  }
  ```
- Visibility is a real UML symbol, always present: `+` public, `-` private, `#` protected, `~` package. Never omit it.
- Relationship tokens (draw the one the SRS evidence actually supports — never default to plain association):
  - Inheritance / generalization: `Admin --|> User`
  - Interface realization: `TaskRepository ..|> Repository`
  - Composition (owner's lifetime controls the part): `Project *-- Task`
  - Aggregation (part can outlive the whole): `Team o-- User`
  - Plain association: `User --> Notification`
  - Dependency (uses, does not hold a reference): `TaskController ..> TaskService`
- Multiplicity sits on both ends of the line, in quotes: `Project "1" -- "many" Task`.
- An enumeration or interface gets a stereotype line as the first entry in the box: `<<interface>> Repository` or `<<enumeration>> Status`.
- The object view is a second class-like box for one instance, named `ClassName : instanceLabel` with concrete values instead of types, e.g. `class TeamTrack_Task1["task-482 : Task"] { title = "Ship v1" status = "open" }`, connected to nothing extra — it stands beside the class it instantiates.

## How to draw it

- Start with one compartmented class box per supported domain type from the database design.
- List typed attributes and operations only when they are present in the SRS model — do not invent getters/setters that are not implied by a requirement.
- Add association multiplicity, aggregation, composition, or inheritance only with supporting evidence in the specification.
