# Write the {{title}} section of the specification

Return one JSON object with the exact keys shown below. Fill each key completely
for the approved scope, omit all other keys, and return no prose or code fence.

- Product name: {{project_name}}
- Stack: {{stack}}
- Document language: {{language}}

## Scope and checks

The approved plan is the boundary. Use the interview to clarify its details.
Cover every approved item that belongs to this section. Include no unapproved
roles, screens, records, capabilities, accounts, or payments. Record genuine
assumptions in the section that owns `ambiguities`.

Apply these rules only to the fields you are returning:

- **Scope and screens.** Include each planned screen exactly once, with its
  route, allowed roles, sections and functions. Take sign-in and registration
  rules from the approved plan. Keep the allowed pages and role capabilities consistent.
- **Data.** Cover every planned record, including approved history and audit
  records. Preserve the shared table names and reference keys as `table.id`.
- **API.** Describe only the distinct operations needed by approved screens or
  workflows. Use one contract per method and path. State authentication and
  allowed roles. Keep validation rules tied to the approved fields or operations.
- **Functional requirements.** Write one testable `The system shall …` statement
  per requirement, with a unique sequential `FR-###` ID, rationale, verification
  method and exactly one traceability row naming the pages, tables and test case.
  Include the approved workflow exceptions and roles' capabilities.
- **Quality and workflows.** Write eight to twelve testable `NFR-###` requirements
  with measurable thresholds or named standards and a verification method.
  Include each planned workflow by name, with the approved role, ordered steps
  and one allowed `step_routes` entry per step. Repeat a route when the action
  stays on the same screen.

Use verification methods from this set: Functional Test, Test / Inspection,
Demonstration / Inspection, Analysis.

## JSON shape

```json
{{example}}
```

## Names every part uses

So the parts fit together, every part uses exactly these names.

Pages (route — roles):
{{routes}}

Tables (one per planned record):
{{tables}}

## The approved plan (`.agentforge/plan.json`)

```json
{{plan}}
```

## The interview

{{interview}}
