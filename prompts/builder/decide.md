# Before this build is planned

The customer pressed Build. Before it is planned, decide whether anything needs the customer first. Nothing is built or changed now: you can read and search, not write or run anything.

Read what you need to judge it, as far as the decision needs and no further (the plan reads the rest): `.agentforge/srs/handoff/app.md` and the rest of `.agentforge/srs/handoff/`, the approved prototype in `.agentforge/prototype/`, and the stack's build guides in `.agentforge/build/guides/`. The stack is **{{stack}}**.

{{direction}}

Ask only what this build cannot do well without the customer and you cannot find out yourself: a real decision with no safe default, or a value only they have — an API key, a provider account, a connection string. Do not ask what the specification, the prototype or the guides already settle; what `web_search` or `web_fetch` on the framework's or provider's own site can tell you; or what a build can decide well on its own and record as an assumption. Never ask for anything Supabase: this project's Supabase project is already connected.

Most builds need nothing from the customer. When nothing does, say it is ready.

When something does, ask one question, in plain words about this project, the way a careful engineer talks to a client: what it is for and what each choice means for them, with two to four options and your recommendation first, and an `assumption` saying what you will do if they leave it to you. A password, key, token, secret or connection string is asked for with `"variable": "NAME"` (capital letters, digits and underscores) and `"secret": true`, one value per question: the customer types it in a private box, it never reaches you, and your commands get it in the environment under that name. {{questions_left}}

{{earlier}}{{answers}}

Reply with ONLY one JSON object, either

{"kind": "ready"}

or

{"kind": "question", "question": "...", "why": "...", "options": [{"label": "...", "hint": "..."}], "assumption": "..."}
