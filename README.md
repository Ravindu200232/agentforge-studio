# AgentForge on the Ollama terminal agent

A studio for taking a product from a sentence to a deployed application:
interview → plan → specification → design → prototype → build → test → deploy.

The interface is the AgentForge Studio, copied unchanged from `RP-SE-009`. The
engine underneath it is this repository's own Ollama terminal agent. Nothing in
between is hard-coded: every stage is a prompt pack on disk, and the only things
that say "no" to a model are the validation rules ported from `RP-SE-009`.

## Running it

```powershell
./studio.bat
```

That starts the backend and the studio together and prints where to open it. The
first run installs the studio's npm packages. To run beside another instance:

```powershell
./studio.ps1 -ApiPort 7924 -WsPort 7925 -UiPort 3100
```

You also still have the plain terminal agent:

```powershell
./start.bat
oterm --model qwen3-coder "Find and fix the bug"
```

Requirements: Python 3.10+, Node 20+, and Ollama. Pick a model in the studio's
settings before starting a project — the backend does not choose one for you.

## One context, five agents

The five agents — **SRS**, **prototype**, **builder**, **QA** and **deploy** —
are not five conversations. They are five roles taking turns in one, against one
workspace, with one model:

```
workspaces/<project>/           the application being built
  .agentforge/
    context.json                THE conversation, all five agents share it
    events.jsonl                what the studio's chat stream replays
    interview.json  plan.json  design.json
    srs/        srs.json, SRS.md, diagrams/*.mmd, handoff/{app,builder}.md, handoff.json
    wireframe/  app/   a React app: src/pages/<page>.tsx for every screen, and bundle.html
    prototype/  app/   the wireframe app, edited into the prototype; routes.json, demo-accounts.json
    skills/     web-artifacts-builder   Anthropic's skill, staged for the agent to read
    build/      report.json
    qa/         report.json
    deploy/     run.json, events.jsonl
```

What the SRS agent learned in the interview is still in front of the builder;
what the builder did is still in front of the deployer. Agents do not re-read
their way back to a shared understanding — they never lost it. They read a file
when they need an exact value, not to re-learn something they were told.

`context.json` is written after every turn, so closing the app does not lose the
conversation. When the window fills, the engine summarises the oldest turns into
a running memory; if the model returns nothing for a summary, a mechanical
digest of the paths, commands and requests is kept instead. A thin memory is
survivable; losing the session is not.

Each stage runs **silent plan mode**: the agent plans the work and immediately
carries it out, because the studio approved the stage by starting it. What it
leaves behind is files. A message typed into the chat stream afterwards edits
those same files through `write_file` and `replace_text`.

## Wireframes and prototype: one React app, edited

Neither is hand-drawn HTML. Both are a small **React** app (TypeScript, Vite, Tailwind CSS, shadcn/ui, Lucide icons, Recharts) that
the project's agent writes with its own file tools, following Anthropic's official
[`web-artifacts-builder`](https://github.com/anthropics/skills/tree/main/skills/web-artifacts-builder) skill, which is kept unchanged in
`prompts/skills/web-artifacts-builder/` and staged where the agent can read it.

The handoff the agent works from is two files in `.agentforge/srs/handoff/`: a small **`app.md`**, which is what the customer asked
for in their own words, who uses it and the site map, with nothing technical in it; and the developer's **`builder.md`**, the full
specification, which the build, the tests and the deployment read.

- **Wireframes**: the agent reads the skill and `app.md` and writes `src/pages/<page>.tsx` for every screen of the site map, in
  low fidelity. The Studio only creates the app (the skill's first step: `server_modules/web_app.py`, from `server_modules/web_kit/`) and,
  when the agent is done, bundles it with Vite into one self-contained `bundle.html` (the skill's last step), which the Wireframe tab frames.
- **Prototype**: a new app is set up, and the agent reads the skill, the approved wireframes (every page and what it imports),
  `app.md` and the approved design, plans the prototype, and writes a high-fidelity, animated page for every screen. The wireframes stay
  as they were. When the product has sign-in, the prototype signs in with one fictitious account for each role (`src/demo.ts`), the same
  accounts the build is seeded with (`demo-accounts.json`). A screen with no page leaves the run resumable instead of handed over.
- The packages (about 180 MB) are installed once into `<state>/web-kit` and linked into every app as `node_modules`; Node.js is the only
  thing a computer needs. An app that does not bundle is given to the agent, with what the bundler said, to fix.

## Scaffold-first build and evidence

After prototype approval, the builder installs the selected stack's template —
Next.js, Vite or Remix on Supabase; Next.js, Vite, Remix or MERN on MongoDB alone (no Supabase
account needed); or those MongoDB stacks with a Supabase Storage bucket for uploaded files — from `builder-agent/builder_agent/assets/templates/` into an
empty project workspace.
It never overwrites an existing application. Before it plans, the builder's
model may ask the customer what it cannot settle itself - a decision with no safe
default, or a value only they have - in its own words and only when it is really
needed. Once the plan starts the build never stops to ask: it runs straight
through on the project's connected database and records whatever it could not
settle as a gap in the build report. The stack and testing guides in `_guides/` and the
authentication guide (`prompts/shared/authentication.md`) are staged under
`.agentforge/build/guides/` and passed into the build plan along with the SRS
handoff, approved design customization and prototype. The build records its
installed files in `.agentforge/build/scaffold.json`.

QA uses the copied Vitest, Playwright, axe and Lighthouse configuration and the
ZAP CI example. It saves runner JSON and actual screenshots under the project;
the Studio's **Testing → Scaffold QA** view reads those artifacts. Unavailable
tools, missing routes and incomplete requirements are reported as gaps, not
counted as passing tests.

## Everything is a prompt

`prompts/` holds every instruction this product gives a model. Changing how a
stage behaves is editing a file:

| Pack | What it drives |
|---|---|
| `shared/engine.md` | the contract every stage runs under |
| `shared/authentication.md` | sessions, roles and sign-in, read by the wireframes, prototype and builder |
| `interview/` | the question format, the interview standard, what to cover |
| `plan/` | the approval plan a customer signs off, and its revisions |
| `srs/` | the specification, its review and its repairs |
| `srs/skills/` | the requirements standards, ported from `RP-SE-009` |
| `skills/web-artifacts-builder/` | Anthropic's skill for building React apps (React, Vite, Tailwind, shadcn/ui), unchanged |
| `wireframe/` | two short prompts: draw the wireframes, change them |
| `design/` | the design contract; `design/themes/` holds 70 themes |
| `prototype/` | two short prompts: make the prototype from the wireframes, change it |
| `builder/` | the application build |
| `testing/` | verification and its evidence |
| `deployment/` | the deployment pipeline; `deployment/skills/` per target |
| `changes/` | a change request: its plan, its questions and its execution |
| `chat/` | a mid-project message from the customer |

The interview has no topic catalogue and no fixed question list. The model picks
each question from what is still unknown, so a one-screen tool finishes in a
handful and a multi-role system does not.

## What says no

Four gates stand between a model's output and the next stage. They are the
ported `RP-SE-009` rules, and they are the only judgement not delegated:

**The plan's depth floor** (`validation/plan_rules.py`) — every screen has a
purpose, every record keeps at least two things, every signed-in role has two
things it can do, public sign-up cannot create a privileged role.

**The specification's schema** (`validation/srs_schema.py`) — the pydantic model
the studio's own views read, with its floors on requirements and roles.

**Coverage** (`validation/completeness.py`) — the gate the other two cannot see.
Each artifact can be individually valid while the specification quietly covers a
third of the product. This one counts the plan against the specification: a
screen that was promised and dropped, a record with no table, a feature with no
requirement, a requirement with no trace. What the plan already states is
aligned into the document; anything still missing stops the stage and is
recorded on the document.

**The standards review** (`validation/review.py`) — a reviewer audits the draft
against the requirements skills. Python decides whether it passed, not the model:
a reviewer asked to judge its own judgement tends to accept.

On this repository's bakery test project the coverage gate took the first draft
from 1 diagram to 7 and from 3 functional requirements to 6.

## Layout

```
server.py                 starts the API (7824) and the live feed (7825)
studio.ps1 / studio.bat   starts the backend and the studio together
server_modules/           the shared runtime: bus, session, prompts, store,
                          validation, HTTP and WebSocket
srs-agent/                interview, plan, specification, diagrams, the handoff, the wireframes
prototype-agent/          design contract and the React prototype
builder-agent/            the application build
qa-agent/                 verification and its evidence
deploy-agent/             deployment and its pipeline record
src/ollama_terminal/      the engine: conversation, tools, source guard
prompts/                  every instruction, as markdown
studio/                   the AgentForge Studio, unchanged
tests/                    every test: Python at the top, studio checks in tests/studio/
tools/                    the SRS corpus fetcher
srs-test-sources/         reference SRS documents and diagram sources
workspaces/               one directory per project
```

The studio proxies `/__agentforge/api` to the API port and `/__agentforge/ws` to
the feed port; both come from `STUDIO_API` and `STUDIO_WS`, which `studio.ps1`
sets to match.

## Tests

```powershell
python -m unittest discover -s tests -v
node --test tests/*.mjs tests/studio/*.mjs
```

`test_agent.py` covers the engine — tool round trips, path escapes, plan mode,
the source guard, and context summarisation including a model that answers in
`thinking` or returns nothing at all. `test_studio.py` covers the backend — the
prompt packs, all four validation gates, the event shapes the studio's reducer
reads, event persistence across a restart, and the route table. The `.mjs` files
check the studio's own modules — preview addresses, the chat
display, progress, attachments and uploads — without a browser.

## What has been run end to end

Against a real model (`gpt-oss:120b-cloud`) on a bakery ordering project:
interview, plan, plan revision and approval, specification generation with its
diagrams and wireframes, the coverage and review repair loops, design selection,
and the prototype — rendered in the studio and served to its preview pane. The
build, test and deploy stages are wired the same way and their endpoints answer,
but they have not been driven to completion against a model here; a full Next.js
build and deployment needs your own credentials and a good deal of time.
