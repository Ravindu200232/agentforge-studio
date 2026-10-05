## What this phase is: connecting everything

Every page is built. Now make the whole application run as one:

- anything that connects the parts (a gateway or proxy to the services, the application's own routing, the places the pages' handlers were added) works end to end;
- the seed script: it fills the database with the prototype's demo accounts (real hashed passwords) and the demo data the pages show, and can be run again without harm;
- `.env.example` lists every variable the code reads;
- run the minimum build command that compiles the application, and fix what it reports.

{{phase1}}
