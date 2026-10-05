# Focused business tests

Read the finished app and test its important behavior, across both halves of it — not business logic alone. For each kind below, cover the representative and critical cases that actually exist in this app, not every instance of the kind:

- **Pure functions and utility/helper functions** — calculations, formatting, parsing: exact inputs to exact outputs, plus the edge cases (empty, zero, negative, boundary).
- **Forms and inputs** — validation rules (both accepted and refused input), submission, and the error state a bad submission leaves on screen.
- **Tables and lists** — sorting, filtering, pagination, and the empty-state a list renders with nothing in it.
- **Custom hooks / state-management logic** — a hook's own transitions (loading → success/error, a reducer's actions), tested through the hook or the component that owns the state, not by re-implementing it.
- **UI components with real logic** (buttons with a loading/disabled state, modals with open/close and focus behavior, cards with conditional content) — the behavior, not the markup; a component that only renders static content needs no test of its own.
- **API services / data-fetching layers** — a service function's request shape and its handling of a success and a failure response, mocked at the fetch/client boundary.
- Server-side business behavior as before: permissions, state transitions, persistence rules and complete critical paths, with meaningful success and refusal cases, using the scaffold helpers and isolated test database/schema.

Do not create one test per page, component or file — a presentational component with no logic of its own (it only renders props) still needs none. Do not use inventory or coverage as a completion gate, and do not target 100% coverage. Run the focused suite once; after a repair rerun only the affected test, then refresh the final Vitest JSON once.
