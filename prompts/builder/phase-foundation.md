## What this phase is: the foundation

Everything the pages stand on, built once, before any page:

- the data layer: every table or collection of the specification, with its model, validation and indexes, and the database connection;
- authentication and roles where the specification requires them, following the staged authentication guide;
- the shared layout, signed-in and signed-out navigation and theme, matching the prototype's `src/index.css` and Tailwind theme. Write each layout part (header, navigation, sidebar, footer) as its own component;
- project-authored shared controls such as `Button`, `Card` and `Input` using semantic HTML and the target stack's styles. Port the approved prototype's custom components when compatible and implement the same behavior in the target stack otherwise;
- configuration: `.env.example` with every variable the application will read, read only on the server;
- the application's own server wiring: its routes folder, error handling, and the places the pages' handlers will be added.

Do **not** build the pages themselves, seed the database, or write or run tests.
Those have their own phases. Stop when the foundation files are in place.
