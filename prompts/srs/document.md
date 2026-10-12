# Write the specification

Produce the complete software requirements specification for this product as one
JSON object. Return only the JSON — no prose, no markdown fence.

## Before you write anything

Read these two files yourself with your `read_file` tool — they are not
pasted in here:

   - `.agentforge/plan.json` — the approved plan; this is the SRS's boundary,
     and it is the record you write the document from.
   - `.agentforge/interview.json` — the interview, in full. If this file does
     not exist, there was no interview; proceed from the approved plan alone.

## Project setup

- Product name: {{project_name}}
- Stack: {{stack}}
- Document language: {{language}}

## Coverage is a release gate

Completeness matters more than hitting an arbitrary count. Do not pad the SRS
with duplicated requirements. Decompose each approved capability into atomic,
testable requirements and cover **every item** in the approved plan before you
return the JSON. In particular:

1. **Authentication** — signing in, signing out, session expiry, failed
   attempts, password rules, how accounts come to exist. One requirement each.
2. **Authorization** — the server-side role check on every request, what a
   signed-out visitor gets, what the wrong role gets. One requirement each.
3. **Per role** — every distinct thing each role may do, and the things it must
   not. One requirement per capability, not one per role.
4. **Per stored entity** — create, read, update, delete, list, search and filter,
   plus its own business rules. One requirement each, for each entity.
5. **Per page** — what that page must display, what it must let a person do, and
   what it must refuse. Two or three requirements each.
6. **Per workflow** — the happy path, and separately each rule, exception,
   cutoff, conflict and failure the interview raised.
7. **API** — the contract each endpoint honours.
8. **UI states** — loading, empty, error and success, where they are load-bearing.

Every requirement is one testable sentence in the form "The system shall …",
about one thing. A requirement containing "and" that could be two requirements
is two requirements. Give each one a `verification_method` — `Functional Test`,
`Test / Inspection`, `Demonstration / Inspection` or `Analysis` — and a
`rationale` naming the approved capability it serves. Use stable sequential IDs.

Before returning, check the same evidence an independent reviewer will check:
both requirement sets exist; every ID is unique and shaped `FR-###` or
`NFR-###`; every statement contains `shall`; every row has an approved
verification method; each functional row has a rationale; each non-functional
row has a measurable threshold or named standard; and each functional row has
exactly one traceability row with a `test_case`. These checks make the SRS
testable without copying another product's requirements or expanding scope.

Non-functional requirements follow the same rule and carry a **measurable
threshold**: twelve to twenty of them across performance, scalability,
availability, security, accessibility, usability, maintainability and
observability. "Fast" is not a requirement; "responds within 200 ms at the 95th
percentile under 50 concurrent users" is.

Every workflow in the approved plan must appear by name in
`business_workflows`, with its role and ordered end-to-end steps. Do not omit
workflows simply because the same capability appears in a requirement.

Each workflow also carries `step_routes`: exactly one route per step, in the
same order — the page that step happens on. Use only routes from
`public_pages` and `protected_pages`, and only pages the workflow's `who` can
open: a page without sign-in is open to everyone, a signed-in page only to the
roles in its `allowed_roles`, and someone who never signs in opens no signed-in
page. A step that names a page is on that page. A step that continues where the
person already is (filling a form, choosing an option, the system answering)
repeats the route of the step before it. Never pick a page because it shares a
word with the step.

Every screen in the approved plan must appear in exactly one of
`public_pages` or `protected_pages`, with its route, roles, sections and
functions. Every planned record must have a semantically matching database
table, including audit/history and message-log records. Preserve the approved
record names even when the table uses a conventional plural (for example,
"Booking History Entry" -> `booking_history_entries`).

Every functional requirement gets exactly one row in
`requirement_traceability_matrix` naming the pages and tables it touches and
the test case that proves it. The matrix has as many rows as there are
functional requirements. Every plan feature and every role capability must be
covered by at least one functional requirement or workflow.

Before returning the JSON, perform a silent completeness check against the
approved plan: count and match all screens, workflows, records, features and
role actions; check that every functional requirement has traceability; check
that the arrays are populated; and check that every identifier is unique. Fix
any omission in this response. Never leave `business_workflows` empty when the
plan has workflows. Do not emit diagrams yet; those are generated only after
this main SRS has passed validation.

## The boundary

- Do NOT introduce a record, role, screen or capability the plan does not
  contain. Detail and sharpen what is there; never widen it. This is the one
  thing that outranks the counts above: depth inside the plan, never scope
  outside it.
- If the plan has no sign-in, the product has no accounts — do not mention users,
  roles, permissions, admins or audit logs anywhere.
- If the plan has no payment, there is no checkout, no order total and no
  gateway.
- Each `table_name` is the plain plural of what it holds: `books`, `classes`,
  `bookings`. Never pluralise a plural — `bookingses` is not a word, and the
  builder will create the collection under exactly the name you write.
- Reference foreign keys with the exact `table.id` form.
- Where the plan left something genuinely open, record it in `ambiguities` with
  the assumption you proceeded on. Never resolve one silently.

## The shape

```json
{
  "srs_document": {
    "document_title": "Software Requirements Specification",
    "project_name": "...",
    "version": "1.0.0",
    "document_language": "{{language}}",
    "system_category": "...",
    "prepared_for": "Full App Build Requirement",
    "standards_profile": {"srs": "ISO/IEC/IEEE 29148:2018", "uml": "OMG UML 2.5.1", "bpmn": "OMG BPMN 2.0.2", "erd": "Crow's Foot ERD"},
    "document_control": {"author": "AgentForge SRS Agent", "date": "...", "status": "draft"},
    "app_summary": {"app_name": "...", "short_description": "...", "business_goal": "...", "target_users": ["..."]},
    "app_type": {"primary_type": "...", "supported_types": ["..."], "frontend_type": "...", "backend_type": "...", "database_type": "...", "example_stack": {}},
    "authentication_requirement": {"login_required": true, "sign_in_route": "/login", "identity_fields": ["email", "password"], "registration_fields": [], "registration_mode": "open | admin_created | invite | request | none", "self_registration": false, "sign_up_route": null, "registration_role": null, "registration_roles": [], "provisioning_role": null, "password_reset_required": false, "signed_out_protected_access": "redirect to sign-in", "wrong_role_access": "403 page", "auth_transport": "provider_managed"},
    "roles": [{"role_key": "snake_case", "role_name": "...", "description": "..."}],
    "role_access_matrix": [{"role": "...", "allowed_pages": ["/..."], "restricted_pages": ["/..."], "allowed_functions": ["..."], "restricted_functions": ["..."]}],
    "public_pages": [{"page_name": "...", "route": "/...", "page_type": "...", "login_required": false, "allowed_roles": ["Visitor"], "sections": ["..."], "functions": ["..."]}],
    "protected_pages": [{"page_name": "...", "route": "/...", "page_type": "...", "login_required": true, "allowed_roles": ["..."], "sections": ["..."], "functions": ["..."]}],
    "main_modules": ["..."],
    "database_design": {"data_type_standards": {"uuid": "36-character string primary key"}, "tables": [{"table_name": "plural_snake_case", "description": "...", "fields": [{"name": "id", "type": "uuid", "primary_key": true, "nullable": false, "unique": true}]}], "relationships": [{"from": "table.col", "to": "table.id", "type": "many_to_one", "description": "..."}]},
    "api_design": [{"method": "GET", "path": "/api/...", "description": "...", "auth_required": true, "allowed_roles": ["..."]}],
    "functional_requirements": [{"id": "FR-001", "module": "...", "requirement": "The system shall ...", "priority": "high", "allowed_roles": ["..."], "verification_method": "Functional Test", "rationale": "..."}],
    "non_functional_requirements": [{"id": "NFR-001", "category": "Performance", "requirement": "...", "verification_method": "Analysis"}],
    "business_workflows": [{"workflow_name": "...", "who": "...", "steps": ["...", "..."], "step_routes": ["/...", "/..."]}],
    "validation_rules": [{"field": "table.field", "rule": "..."}],
    "notification_rules": [{"event": "...", "recipients": ["..."], "channels": ["email"]}],
    "security_requirements": ["..."],
    "ui_ux_requirements": {"theme": "...", "responsive": true, "accessibility": "WCAG 2.1 AA"},
    "reporting_requirements": [{"report_name": "...", "filters": ["..."], "exports": ["PDF", "Excel"]}],
    "integration_requirements": [{"name": "...", "type": "...", "description": "...", "required": true}],
    "assumptions": ["..."],
    "constraints": ["..."],
    "ambiguities": [{"id": "AMB-001", "area": "...", "description": "...", "assumption_made": "...", "needs_clarification": true}],
    "risk_priority": [{"id": "RISK-001", "area": "...", "risk": "...", "severity": "High", "reason": "...", "mitigation": "..."}],
    "acceptance_criteria": [{"id": "AC-001", "criterion": "..."}],
    "requirement_traceability_matrix": [{"requirement_id": "FR-001", "module": "...", "pages": ["/..."], "tables": ["..."], "test_case": "TC-001"}]
  }
}
```

Leave `diagrams` out entirely — each diagram is drawn separately from this
document once it exists.
