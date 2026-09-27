# Focused business tests

Read the finished app and test its important business behavior: calculations, validation, permissions, state transitions, persistence rules and complete critical paths. Cover meaningful success and refusal cases. Use the scaffold helpers and isolated `<app>_test` database.

Do not create one test per page, component or file. Do not use inventory or coverage as a completion gate, and do not target 100% coverage. Run the focused suite once; after a repair rerun only the affected test, then refresh the final Vitest JSON once.
