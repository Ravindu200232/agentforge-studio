# Start one part of the app

The Studio's Ports view shows that one part of this app is not listening, and the customer pressed
its Start button. Nobody typed this message. Do not write a plan and do not ask questions. Start
that part, fix what stops it, and finish.

## The part

**{{part}}** ({{part_kind}}) should answer on port {{part_port}}. The app's runner starts it in
`{{part_cwd}}` as `{{part_command}}`, with its address variables set. Run it alone exactly that way,
in one command, from the project folder:

    {{part_run}}

What it printed in the current run (each of its lines starts with `[{{part}}]`):

```
{{part_log}}
```

## The whole app

The Studio runs `{{command}}` in the project folder with `PORT={{port}}` for the browser; that
runner starts every part and gives each one its own free port and the others' addresses. What the
Studio saw: {{detail}}

The end of the preview's output:

```
{{log}}
```

## What to do

1. Read the part's output above and the files it points at: the part's entry point, its config,
   its `package.json`, the runner that starts it, `.env.example`.
2. Run the part alone with the line above. A server never exits on its own, so give `run_command`
   a `timeout_seconds` of about 60. The tool stops it then and hands you its output: a line saying
   it listens on port {{part_port}} with no error after it means it started; a stack trace or an
   exit means it did not.
3. Fix the cause in the project: a missing install, a port it ignores or insists on, a missing
   variable that has a safe local default, a syntax or import error, a wrong path, a database it
   waits for forever. Change only what stops this part from starting - no features, no redesign,
   no new tests.
4. Run it again the same way until it starts cleanly. Leave nothing running: the Studio restarts
   the app's preview as soon as you finish and checks that {{part}} answers.

Never print a secret's value. A variable only the customer can supply (a real database address, a
provider key) is not yours to invent - say which one is missing instead.

Finish with one or two plain sentences for the customer: what stopped {{part}} and what you
changed. Nothing else.
