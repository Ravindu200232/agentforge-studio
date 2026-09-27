# Write the whole specification into the workspace

You are being run as a working agent with real file tools. Produce the complete
specification for this project as files under `.agentforge/srs/`. Nothing is
returned as chat text — the files ARE the deliverable, and the studio reads them
straight off disk.

## The approved plan

{{plan}}

## The interview, in full

{{transcript}}

## Project setup

- Project name: {{project_name}}
- Stack: {{stack}}
- Specification language: {{language}}

## Every file you must write

### 1. `.agentforge/srs/srs.json`

One JSON object, `{"srs_document": { … }}`, matching this shape exactly. It is
schema-validated after you write it and you will be asked to repair anything that
fails.

```json
{
  "srs_document": {
    "document_title": "Software Requirements Specification",
    "project_name": "…",
    "version": "1.0.0",
    "document_language": "{{language}}",
    "system_category": "…",
    "prepared_for": "Full App Build Requirement",
    "standards_profile": {"srs": "ISO/IEC/IEEE 29148:2018", "uml": "OMG UML 2.5.1", "bpmn": "OMG BPMN 2.0.2", "erd": "Crow's Foot ERD"},
    "document_control": {"author": "AgentForge SRS Agent", "date": "…", "status": "draft"},
    "app_summary": {"app_name": "…", "short_description": "…", "business_goal": "…", "target_users": ["…"]},
    "app_type": {"primary_type": "…", "supported_types": ["…"], "frontend_type": "…", "backend_type": "…", "database_type": "…", "example_stack": {}},
    "authentication_requirement": {
      "login_required": true,
      "sign_in_route": "/login",
      "identity_fields": ["email", "password"],
      "registration_fields": ["full_name", "email", "password"],
      "registration_mode": "open | admin_created | invite | request | none",
      "self_registration": true,
      "sign_up_route": "/register",
      "registration_role": "…",
      "registration_roles": ["…"],
      "provisioning_role": "…",
      "password_reset_required": false,
      "signed_out_protected_access": "redirect to sign-in",
      "wrong_role_access": "403 page",
      "auth_transport": "provider_managed"
    },
    "roles": [{"role_key": "snake_case", "role_name": "…", "description": "…"}],
    "role_access_matrix": [{"role": "…", "allowed_pages": ["/…"], "restricted_pages": ["/…"], "allowed_functions": ["…"], "restricted_functions": ["…"]}],
    "public_pages": [{"page_name": "…", "route": "/…", "page_type": "…", "login_required": false, "allowed_roles": ["Visitor"], "sections": ["…"], "functions": ["…"]}],
    "protected_pages": [{"page_name": "…", "route": "/…", "page_type": "…", "login_required": true, "allowed_roles": ["…"], "sections": ["…"], "functions": ["…"]}],
    "main_modules": ["…"],
    "database_design": {
      "data_type_standards": {"uuid": "36-character string primary key"},
      "tables": [{"table_name": "plural_snake_case", "description": "…", "fields": [{"name": "id", "type": "uuid", "primary_key": true, "nullable": false, "unique": true}]}],
      "relationships": [{"from": "table.col", "to": "table.id", "type": "many_to_one", "description": "…"}]
    },
    "api_design": [{"method": "GET", "path": "/api/…", "description": "…", "auth_required": true, "allowed_roles": ["…"]}],
    "functional_requirements": [{"id": "FR-001", "module": "…", "requirement": "The system shall …", "priority": "high", "allowed_roles": ["…"]}],
    "non_functional_requirements": [{"id": "NFR-001", "category": "Performance", "requirement": "…"}],
    "business_workflows": [{"workflow_name": "…", "who": "…", "steps": ["…"]}],
    "validation_rules": [{"field": "table.field", "rule": "…"}],
    "notification_rules": [{"event": "…", "recipients": ["…"], "channels": ["email"]}],
    "security_requirements": ["…"],
    "ui_ux_requirements": {"theme": "…", "responsive": true, "accessibility": "WCAG 2.1 AA"},
    "reporting_requirements": [{"report_name": "…", "filters": ["…"], "exports": ["PDF", "Excel"]}],
    "integration_requirements": [{"name": "…", "type": "…", "description": "…", "required": true}],
    "assumptions": ["…"],
    "constraints": ["…"],
    "ambiguities": [{"id": "AMB-001", "area": "…", "description": "…", "assumption_made": "…", "needs_clarification": true}],
    "risk_priority": [{"id": "RISK-001", "area": "…", "risk": "…", "severity": "High", "reason": "…", "mitigation": "…"}],
    "acceptance_criteria": [{"id": "AC-001", "criterion": "…"}],
    "requirement_traceability_matrix": [{"requirement_id": "FR-001", "module": "…", "pages": ["/…"], "tables": ["…"], "test_case": "TC-001"}],
    "diagrams": [{"id": "DIA-001", "kind": "use_case", "title": "…", "format": "mermaid", "source": "…", "standard": "OMG UML 2.5.1", "applicable": true, "mmd_path": ".agentforge/srs/diagrams/use_case.mmd"}]
  }
}
```

Hard floors the validator enforces: at least three `functional_requirements`, at
least three `non_functional_requirements`, at least one role, and `app_summary`,
`app_type` and `database_design` all present.

Those are floors, not targets. The real measure is coverage, and it is checked:
**every** feature in the plan, **every** workflow, and **every** `can_do` line of
**every** role needs a functional requirement that speaks to it, and every
requirement needs a row in `requirement_traceability_matrix`. A seven-screen
product specified with three requirements is six screens nobody agreed on, and it
will be sent straight back to you with the gaps listed.

### 2. `.agentforge/srs/SRS.md`

The same document as a readable specification, in {{language}}, with numbered
sections in the ISO/IEC/IEEE 29148 order: Introduction, Overall Description,
Specific Requirements, External Interfaces, Data Design, Non-Functional
Requirements, Traceability, Assumptions and Constraints, Appendices.

### 3. `.agentforge/srs/diagrams/<kind>.mmd`

One Mermaid source per diagram, and the same source inline in the `diagrams`
array of `srs.json`. Read
`prompts/srs/skills/diagram-crafting/SKILL.md` and
`prompts/srs/PROFESSIONAL_DIAGRAMS_V4.md` first.

Cover `use_case`, `sequence`, `erd`, `activity`, `class_object`,
`state_machine`, `dfd`, `bpmn` and `system_context`.

Draw the ones your own document gives you the evidence for, and mark only the
rest `"applicable": false` with an `applicability_note` naming the missing
evidence. A state machine for a product with no lifecycle field is a guess, and
saying so is the right answer. But `"applicable": false` on a diagram whose
evidence is sitting in the document is not a judgement, it is a skipped job — and
it is checked:

- tables in `database_design` ⇒ `erd` and `dfd` are answerable;
- entries in `business_workflows` ⇒ `activity` and `sequence` are answerable;
- entries in `roles` ⇒ `use_case` and `system_context` are answerable.

### 4. `.agentforge/srs/wireframes/<slug>.html`

One wireframe per page in `public_pages` and `protected_pages`. The slug is the
route with `/` replaced by `_`, and `home` for `/`.

**Read `prompts/srs/skills/wireframe-generation/SKILL.md` before you draw the
first one.** It defines a design system that already exists — `.wf-box`,
`.wf-img`, `.wf-btn`, `.wf-input`, `.wf-label-sm`, `.wf-tag`, `.sk` — and the
studio's wireframe shell only styles those. Class names you invent, such as
`wf-header` or `wf-card`, render as unstyled text and the reviewer sees a list of
sentences where a screen should be.

Follow it exactly: only `<section>` elements, in reading order, Tailwind for
layout but never for colour, monochrome, real sample data, no `<html>`, no
`<style>`, no `<script>`, no `<svg>`.

Draw the whole screen, at the depth a real screen has: every section the
specification lists for that page, the table with real rows, the form with its
labelled inputs and a plausible typed value in each, the actions, the status
tags. A wireframe of four lines tells a reviewer nothing about whether the screen
is right, and it will be sent back to you.

### 5. `.agentforge/srs/wireframes/index.json`

```json
{"screens": [{"route": "/…", "name": "…", "slug": "…", "file": ".agentforge/srs/wireframes/….html"}]}
```

### 6. `.agentforge/srs/handoff.json`

What the builder consumes:

```json
{
  "prompt": "one complete instruction to the build agent, naming every page, role, record and workflow it must deliver",
  "app_name": "…",
  "stack": "{{stack}}",
  "routes": [{"route": "/…", "name": "…", "roles": ["…"], "login_required": false}],
  "collections": [{"name": "…", "fields": ["…"]}],
  "roles": ["…"],
  "workflows": [{"name": "…", "who": "…", "steps": ["…"]}],
  "acceptance": ["…"],
  "files": {"BUILD.md": "the same instruction as markdown the builder can read from disk"}
}
```

## How to work

1. The plan and the interview are already in this conversation — do not re-read
   them. Read a skill page under `prompts/srs/skills/` only when you are about to
   write that part and do not already hold its rules.
2. Write `srs.json` first — everything else derives from it.
3. Then `SRS.md`, then the diagrams, then the wireframes, then `handoff.json`.
4. After each `write_file`, read back anything you are unsure about. A wireframe
   that does not parse is a wireframe the studio shows blank.
5. Do not run package managers, do not install anything, do not start a server.
   This stage writes documents.
6. Finish only when every file above exists.
