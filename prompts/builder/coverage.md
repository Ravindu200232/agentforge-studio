# Before this build is planned: how much should the unit tests cover?

The customer pressed Build. Before it is planned, they decide how much of the app the unit tests cover. It is theirs to decide: it sets how long the build takes and how much of the app a test guards. Nothing is built or changed now: you can read and search, not write or run anything.

Read what you need to put the question in terms of this project, as far as that needs and no further: `.agentforge/srs/handoff/app.md` and the rest of `.agentforge/srs/handoff/`, and the stack's build guides in `.agentforge/build/guides/`. The stack is **{{stack}}**.

{{direction}}

Ask exactly one question: how much of the app should the unit tests cover. Write it the way a careful engineer talks to a client, in plain words about this project. Name the project's own business rules and functions, the ones its specification is about (what a price, a booking, a stock level or a permission means here), so the customer can picture what is tested and what is not. Do not ask in general terms.

Give two to four options, your recommendation first, ranging from the business rules and the API alone to every function that has logic. Say what each option means for them: what is tested, what is not, and how much longer the build takes. When a coverage percentage is a good way to say it, put the figure in the option. What the build does when nothing is decided is a test file for every module that carries logic, with at least 70% of the lines covered overall and 80% in the logic modules: make that your recommendation unless this project is a reason to say otherwise.

Keep the question itself to two or three sentences and the `why` to one or two: the detail of what each option tests and leaves out goes in that option's `hint`, so the customer can read the choices at a glance.

Put in `assumption` what you will do if they leave it to you.

Reply with ONLY one JSON object:

{"question": "...", "why": "...", "options": [{"label": "...", "hint": "..."}], "assumption": "..."}
