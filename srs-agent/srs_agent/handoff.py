"""The handoff documents every later stage reads.

There are two, and they are not alike.

`app.md` is small and has no technical detail: what the customer asked for, in their own words, who uses the product and
the site map (every screen, who may open it, what is on it, and how people move through them). The wireframe and the
prototype are made from it, so they are drawn from what the customer said and not from a specification.

`builder.md` is the developer's: the specification in full (roles, access, data, API, requirements, workflows, rules),
what done means and the traceability. The build, the tests and the deployment read it.

Both are projections of what is already written, pure functions without a model call. That matters: a document a model
writes can truncate, and these are the contract.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

HANDOFF_FILES = ("app.md", "builder.md")


def _rows(doc: dict, key: str) -> list[dict]:
    return [r for r in (doc.get(key) or []) if isinstance(r, dict)]


def _cell(value: Any) -> str:
    """One table cell, with nothing in it that would break the row."""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def spec_md(doc: dict) -> str:
    """The specification as prose: everything technical, for the developer."""
    summary = doc.get("app_summary") or {}
    auth = doc.get("authentication_requirement") or {}
    database = doc.get("database_design") or {}
    out: list[str] = ["## Identity", ""]

    out += [f"- **App name**: {summary.get('app_name') or doc.get('project_name', '')}",
            f"- **Description**: {summary.get('short_description', '')}",
            f"- **Business goal**: {summary.get('business_goal', '')}",
            f"- **System category**: {doc.get('system_category', '')}",
            f"- **Target users**: {', '.join(summary.get('target_users') or [])}", ""]

    out += ["## Authentication", "",
            f"- **Login required**: {bool(auth.get('login_required'))}",
            f"- **Sign-in route**: {auth.get('sign_in_route') or '—'}",
            f"- **Registration mode**: {auth.get('registration_mode') or 'none'}"]
    if auth.get("identity_fields"):
        out.append(f"- **Signs in with**: {', '.join(auth['identity_fields'])}")
    if auth.get("registration_role"):
        out.append(f"- **Public sign-up creates**: {auth['registration_role']}")
    if auth.get("provisioning_role"):
        out.append(f"- **Accounts are created by**: {auth['provisioning_role']}")
    out += [f"- **Signed-out access to a protected page**: "
            f"{auth.get('signed_out_protected_access') or 'redirect to sign-in'}",
            f"- **Wrong role**: {auth.get('wrong_role_access') or '403'}", ""]

    if _rows(doc, "roles"):
        out += ["## Roles", ""]
        for role in _rows(doc, "roles"):
            out.append(f"- **{role.get('role_name')}** (`{role.get('role_key')}`) — "
                       f"{role.get('description', '')}")
        out.append("")

    if _rows(doc, "role_access_matrix"):
        out += ["## Access", "",
                "| Role | May open | May not open | May do | May not do |",
                "|---|---|---|---|---|"]
        for row in _rows(doc, "role_access_matrix"):
            out.append(f"| {_cell(row.get('role'))} | {_cell(row.get('allowed_pages'))} "
                       f"| {_cell(row.get('restricted_pages'))} "
                       f"| {_cell(row.get('allowed_functions'))} "
                       f"| {_cell(row.get('restricted_functions'))} |")
        out.append("")

    if doc.get("main_modules"):
        out += ["## Modules", ""] + [f"- {m}" for m in doc["main_modules"]] + [""]

    tables = _rows(database, "tables")
    if tables:
        out += ["## Data", ""]
        for table in tables:
            out += [f"### `{table.get('table_name')}`", "",
                    str(table.get("description") or ""), "",
                    "| Field | Type | Key | Required | Unique | References |",
                    "|---|---|---|---|---|---|"]
            for field in (table.get("fields") or []):
                out.append(
                    f"| {_cell(field.get('name'))} | {_cell(field.get('type'))} "
                    f"| {'PK' if field.get('primary_key') else ''} "
                    f"| {'no' if field.get('nullable') else 'yes'} "
                    f"| {'yes' if field.get('unique') else 'no'} "
                    f"| {_cell(field.get('references'))} |")
            out.append("")
        if _rows(database, "relationships"):
            out += ["### Relationships", ""]
            for link in _rows(database, "relationships"):
                out.append(f"- `{link.get('from')}` → `{link.get('to')}` "
                           f"({link.get('type')}) {link.get('description') or ''}")
            out.append("")

    if _rows(doc, "api_design"):
        out += ["## API", "", "| Method | Path | Auth | Roles | Description |",
                "|---|---|---|---|---|"]
        for row in _rows(doc, "api_design"):
            out.append(f"| {_cell(row.get('method'))} | `{_cell(row.get('path'))}` "
                       f"| {'yes' if row.get('auth_required') else 'no'} "
                       f"| {_cell(row.get('allowed_roles'))} "
                       f"| {_cell(row.get('description'))} |")
        out.append("")

    if _rows(doc, "functional_requirements"):
        out += ["## Functional requirements", ""]
        for row in _rows(doc, "functional_requirements"):
            roles = ", ".join(row.get("allowed_roles") or []) or "anyone"
            out.append(f"- **{row.get('id')}** [{row.get('priority', 'medium')}] "
                       f"({row.get('module')}, {roles}) {row.get('requirement')}")
        out.append("")

    if _rows(doc, "non_functional_requirements"):
        out += ["## Non-functional requirements", ""]
        for row in _rows(doc, "non_functional_requirements"):
            out.append(f"- **{row.get('id')}** ({row.get('category')}) "
                       f"{row.get('requirement')}")
        out.append("")

    if _rows(doc, "business_workflows"):
        out += ["## Workflows", ""]
        for flow in _rows(doc, "business_workflows"):
            out.append(f"### {flow.get('workflow_name')} "
                       f"({flow.get('who') or 'anyone'})")
            steps = flow.get("steps") or []
            routes = flow.get("step_routes") or []
            routes = routes if len(routes) == len(steps) else []
            out += [""] + [f"{i}. {step}" + (f" — on `{routes[i - 1]}`" if routes and routes[i - 1] else "")
                           for i, step in enumerate(steps, 1)] + [""]

    for title, key, render in (
        ("Validation rules", "validation_rules",
         lambda r: f"- `{r.get('field')}` — {r.get('rule')}"),
        ("Notifications", "notification_rules",
         lambda r: f"- on **{r.get('event')}** → {', '.join(r.get('recipients') or [])} "
                   f"via {', '.join(r.get('channels') or [])}"),
        ("Reporting", "reporting_requirements",
         lambda r: f"- **{r.get('report_name')}** — filters: "
                   f"{', '.join(r.get('filters') or []) or '—'}; exports: "
                   f"{', '.join(r.get('exports') or []) or '—'}"),
        ("Integrations", "integration_requirements",
         lambda r: f"- **{r.get('name')}** ({r.get('type')}) {r.get('description')}"),
        ("Acceptance criteria", "acceptance_criteria",
         lambda r: f"- {r.get('criterion')}"),
        ("Ambiguities", "ambiguities",
         lambda r: f"- **{r.get('id')}** ({r.get('area')}) {r.get('description')} — "
                   f"assumed: {r.get('assumption_made')}"),
    ):
        if _rows(doc, key):
            out += [f"## {title}", ""] + [render(r) for r in _rows(doc, key)] + [""]

    for title, key in (("Security", "security_requirements"),
                       ("Assumptions", "assumptions"), ("Constraints", "constraints")):
        if doc.get(key):
            out += [f"## {title}", ""] + [f"- {v}" for v in doc[key]] + [""]

    if doc.get("ui_ux_requirements"):
        out += ["## UI and UX", ""]
        for name, value in (doc["ui_ux_requirements"] or {}).items():
            out.append(f"- **{name}**: {value}")
        out.append("")

    return "\n".join(out)


def _site_map(doc: dict) -> list[str]:
    """Every screen, as the two tables the later stages read routes from."""
    out: list[str] = []
    public = _rows(doc, "public_pages")
    if public:
        out += ["### Public pages", "", "| Page | Route | Sections | What people can do |",
                "|------|-------|----------|--------------------|"]
        for page in public:
            out.append(f"| {_cell(page.get('page_name'))} | `{_cell(page.get('route'))}` "
                       f"| {_cell(page.get('sections'))} | {_cell(page.get('functions'))} |")
        out.append("")
    protected = _rows(doc, "protected_pages")
    if protected:
        out += ["### Pages people sign in to", "",
                "| Page | Route | Who can open it | Sections | What people can do |",
                "|------|-------|-----------------|----------|--------------------|"]
        for page in protected:
            out.append(f"| {_cell(page.get('page_name'))} | `{_cell(page.get('route'))}` "
                       f"| {_cell(page.get('allowed_roles'))} "
                       f"| {_cell(page.get('sections'))} | {_cell(page.get('functions'))} |")
        out.append("")
    return out


def app_md(doc: dict, idea: str = "", said: str = "") -> str:
    """What the product is, in the customer's words, and its site map. Small, and nothing technical in it.

    `idea` is what the customer first asked for and `said` the interview as they answered it; both are theirs, so they are
    quoted as they are.
    """
    summary = doc.get("app_summary") or {}
    name = summary.get("app_name") or doc.get("project_name") or "The application"
    out: list[str] = [f"# {name}", ""]
    if summary.get("short_description"):
        out += [str(summary["short_description"]).strip(), ""]

    if str(idea or "").strip():
        out += ["## What the customer asked for", "", str(idea).strip(), ""]
    if str(said or "").strip() and str(said).strip() != "(nothing yet)":
        out += ["## What the customer said when asked", "", str(said).strip(), ""]

    users = ", ".join(str(u) for u in (summary.get("target_users") or []) if str(u).strip())
    roles = _rows(doc, "roles")
    if users or roles:
        out += ["## Who uses it", ""]
        if users:
            out += [users, ""]
        out += [f"- **{role.get('role_name')}** — {role.get('description', '')}".rstrip(" —") for role in roles]
        if roles:
            out.append("")

    site_map = _site_map(doc)
    if site_map:
        out += ["## Site map", ""] + site_map

    workflows = _rows(doc, "business_workflows")
    if workflows:
        out += ["## How people move through it", ""]
        for flow in workflows:
            out.append(f"### {flow.get('workflow_name')} ({flow.get('who') or 'anyone'})")
            steps = flow.get("steps") or []
            routes = flow.get("step_routes") or []
            routes = routes if len(routes) == len(steps) else []
            out += [""] + [f"{i}. {step}" + (f" — on `{routes[i - 1]}`" if routes and routes[i - 1] else "")
                           for i, step in enumerate(steps, 1)] + [""]
    return "\n".join(out)


def builder_md(doc: dict, stack: str) -> str:
    """What the build and QA stages work from."""
    summary = doc.get("app_summary") or {}
    out = ["# Developer and QA Handoff", "", "",
           f"**Selected stack**: {stack}.", "",
           "Read `app.md` for what the product is and its site map, then the specification below, then the approved "
           "prototype: a React app in `.agentforge/prototype/app/`, its pages under `src/`. Build the application in "
           "the selected stack from that specification and the approved prototype. Preserve its screens, "
           "navigation, layout, content and interactions while connecting the real "
           "data. The planning and specification reviews have already happened; "
           "proceed with implementation without producing another product plan. Use "
           "environment variables for credentials. Implement the specified access "
           "rules, validation and error handling. Verify what you changed with unit, "
           "integration and browser checks, repair actionable failures, and stop with "
           "a clear explanation if the same failure repeats without progress.", "",
           f"## What is being built", "",
           f"{summary.get('short_description', '')}", "",
           f"**Business goal.** {summary.get('business_goal', '')}", ""]
    out += ["# The specification", ""] + spec_md(doc).splitlines() + [""]

    if _rows(doc, "acceptance_criteria"):
        out += ["## Done means", ""]
        out += [f"- {r.get('criterion')}" for r in _rows(doc, "acceptance_criteria")]
        out.append("")

    if _rows(doc, "requirement_traceability_matrix"):
        out += ["## Traceability", "",
                "| Requirement | Module | Pages | Tables | Test |",
                "|---|---|---|---|---|"]
        for row in _rows(doc, "requirement_traceability_matrix"):
            out.append(f"| {_cell(row.get('requirement_id'))} | {_cell(row.get('module'))} "
                       f"| {_cell(row.get('pages'))} | {_cell(row.get('tables'))} "
                       f"| {_cell(row.get('test_case'))} |")
        out.append("")
    return "\n".join(out)


def manifest(doc: dict, stack: str) -> dict[str, Any]:
    body = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"source": hashlib.sha256(body).hexdigest(), "stack": stack,
            "files": list(HANDOFF_FILES)}


def render_all(doc: dict, stack: str, idea: str = "", said: str = "") -> dict[str, str]:
    """Every handoff document, keyed by its filename."""
    return {
        "app.md": app_md(doc, idea, said),
        "builder.md": builder_md(doc, stack),
    }
