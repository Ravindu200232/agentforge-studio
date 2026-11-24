# Build references

Stack: {{stack}}. The SRS handoff at `.agentforge/srs/handoff.json` defines
data, permissions, and behavior. The approved prototype route map is at
`.agentforge/prototype/routes.json`. The mapped page and its imports define
the approved visual and interaction details. Read the sources this phase
needs, preserve the approved scope and assets, and keep existing implementation
that satisfies it. Earlier page phases recorded their output files in
`.agentforge/build/progress/`.
Use `.agentforge/design/design-spec.json` and `media/IMAGES.md` where present
for the approved design and image sources the phase touches.

When present, `.agentforge/build/journey-contract.json` gives the approved actions, actors, routes and known expected outcomes. A first-journey phase tests one real flow before the remaining page phases. Its established helpers and browser spec are available to later phases.

{{workspace}}

Use real data in the app. Enforce authorization and validate writes on the
server. Keep secrets on the server and out of rendered pages, examples, and logs.
Scope queries, keep related writes atomic, and paginate large collections.
Where the approved scope leaves an implementation detail open, use a safe
default and record material assumptions in the build report.
Use the stack guides for the part you are implementing. For a specific API or
tool question the guides cannot answer, consult its official documentation.
Keep loading, empty, and error states wherever the phase implements a screen.

- Build report template: `{{report_template}}`
- Read the shared UI guidance in `{{ui_skill}}/SKILL.md` when implementing a screen. Author components in the target stack and preserve the prototype's design. Do not install or copy component kits.
- Stack guides:
{{guides}}

{{auth}}
{{design}}
{{decisions}}
{{direction}}
{{design_motion}}
