## What this phase is: connecting everything

Every page is built. Now make the whole application run as one:

- anything that connects the parts (a gateway or proxy to the services, the application's own routing, the places the pages' handlers were added) works end to end;
- the seed script: it fills the database with an account for each role (real hashed passwords) and the sample data the prototype's pages show, and can be run again without harm. On a MongoDB stack run it once with the `MONGODB_URI` your commands already have, and that is the whole database check: do not look for, start or test a MongoDB on this computer, and do not copy the connection into a `.env` file;
- `.env.example` lists every variable the code reads (names only, no real value);
- run the minimum build command that compiles the application, and fix what it reports.

{{phase1}}
