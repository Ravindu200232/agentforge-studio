# Start the app

The Studio's live preview of this app did not start. Nobody typed this message: it was sent when
the customer pressed "Start with agent" under the failed preview. Do not write a plan and do not
ask questions. Start the app, fix what stops it, and finish.

## How the Studio starts it

The Studio runs this in the project folder:

    {{command}}

with `PORT={{port}}`, `HOST=127.0.0.1` and `BROWSER=none` added to the environment, and waits
for {{url}} to answer with a status below 500. `PORT` is the one port a browser opens; anything
else the app starts (an API server, a gateway, services) has to find its own free port and tell
the others where it is. The app must never insist on a fixed port, refuse the port it was given,
or kill whatever else is listening.

What the Studio saw: {{detail}}

The end of the preview's output:

```
{{log}}
```

## What to do

1. Read the output above and the files it points at (`package.json` scripts, the start scripts,
   the framework config, the server entry points, `.env.example`).
2. Run it yourself exactly the way the Studio does, in one command:

       {{run}}

   A server never exits on its own, so give `run_command` a `timeout_seconds` of about 60. The
   tool stops it then and hands you its output: a line saying it is listening on port {{port}}
   with no error after it means it started; a stack trace or an exit means it did not.
3. Fix the cause in the project: a missing install (`npm install`), a script or config that ignores
   `PORT` or demands a fixed one, a missing variable that has a safe local default, a syntax or
   import error, a wrong path. Change only what stops the app from starting - no features, no
   redesign, no new tests.
4. Run it again the same way until it starts cleanly. Leave nothing running: the Studio starts its
   own preview as soon as you finish.

Never print a secret's value. A variable only the customer can supply (a real database address, a
provider key) is not yours to invent - say which one is missing instead.

Finish with one or two plain sentences for the customer: what stopped the app and what you
changed. Nothing else.
