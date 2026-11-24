## What this phase is: the foundation

Everything the pages stand on, built once, before any page:

- the root manifest, stack-specific framework configuration, application entry, and a short README for running and maintaining the application. Author missing files using the selected stack guide. Preserve application files that already work;
- the data layer: every table or collection of the specification, with its model, validation and indexes, and the database connection;
- authentication and roles where the specification requires them, following the staged authentication guide;
- the shared layout, signed-in and signed-out navigation and theme, matching the prototype's shared styles, using `assets/prototype.css` for HTML sources. Write each layout part (header, navigation, sidebar, footer) as its own component when it appears in the approved design;
- project-authored shared controls such as `Button`, `Card` and `Input` using semantic HTML and the target stack's styles. Port the approved prototype's custom components when compatible and implement the same behavior in the target stack otherwise;
- `.env.example` documenting the name and purpose of every variable used by the application. Keep credentials and server-only values out of browser code and out of files tracked in Git;
- the application's own server wiring: its routes folder, error handling, and the places the pages' handlers will be added.

Do **not** build the pages themselves, seed the database, or write or run tests.
Those have their own phases. Stop when the foundation files are in place.
