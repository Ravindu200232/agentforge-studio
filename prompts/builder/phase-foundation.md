## What this phase is: the foundation

Everything the pages stand on, built once, before any page:

- the data layer: every table or collection of the specification, with its model, validation and indexes, and the database connection;
- authentication and roles exactly as the authentication guide describes, with the roles the specification names and the prototype's demo accounts ready to be seeded;
- the shared layout, navigation (signed-in and signed-out), theme and the shared UI components (`Button`, `Card`, `Input`, …) ported once from the prototype's `src/index.css`, Tailwind theme and shared components (the prototype is a React app with shadcn/ui: a component can be reused as it is where the stack is React);
- configuration: `.env.example` with every variable the application will read, read only on the server;
- the application's own server wiring: its routes folder, error handling, and the places the pages' handlers will be added.

Do **not** build the pages themselves: they come in the next phases, a few at a time, and every one of them is built. Leave the application compiling, and keep the scaffold and any existing application work.
