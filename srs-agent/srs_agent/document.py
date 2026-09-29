"""The specification itself.

Written as focused calls rather than as one agentic conversation, because the two
produce very different documents. A single run asked to write the document, the
diagrams and fourteen pages spends its output budget on the first few and
truncates the rest — which is how a wireframe ends up four hundred characters
long. So: one call for the document, one per diagram, one per page, and the
independent ones run at the same time.

Continuity does not come from a shared conversation here. It comes from the
artifacts: the approved plan bounds the document, the document bounds the
diagrams and the pages, and each call is given exactly the part it needs.
"""
from __future__ import annotations

import json
import hashlib
import re
import threading
import time
from pathlib import Path
from typing import Any

from server_modules import bus, config, journeys, llm, mermaid, prompts, reference_staging, store
from server_modules.session import ProjectSession, session_for
from server_modules.validation import completeness
from server_modules.validation import review as review_rules
from server_modules.validation import srs_schema

from . import handoff as handoff_files
from . import plan as plan_stage
from . import wireframe_brief

SRS_DIR = "srs"
DOCUMENT = (SRS_DIR, "srs.json")
HANDOFF = (SRS_DIR, "handoff.json")
USER_JOURNEYS = (SRS_DIR, "user-journeys.json")
WIREFRAME_INDEX = (SRS_DIR, "wireframes", "index.json")
WIREFRAME_SYSTEM = "wireframe-system"          # the web ideas and the shared layout the wireframes start from

# Every diagram the standards profile covers. Each is one call; the ones whose
# evidence is missing come back as NOT_APPLICABLE and are recorded as such.
DIAGRAM_KINDS = ("system_context", "use_case", "erd", "sequence", "activity",
                 "class_object", "state_machine", "dfd", "bpmn", "component",
                 "deployment")

# A notation reference is about the standard, not the project, so one search per
# kind is shared by every project this process draws for rather than repeated.
_reference_cache: dict[str, str] = {}
_reference_lock = threading.Lock()


def _diagram_reference(kind: str) -> str:
    """A short, real-world grounding note on standard notation for this diagram
    kind — never a source of actors, entities or flows, only of correct,
    recognizable notation for a {kind} diagram."""
    with _reference_lock:
        if kind in _reference_cache:
            return _reference_cache[kind]
    found = llm.web_search(f"UML {kind.replace('_', ' ')} diagram example correct notation", max_results=3)
    note = "\n".join(f"- {row['title']}: {row['content'][:300]}"
                     for row in found if row.get("content"))[:1200]
    with _reference_lock:
        _reference_cache[kind] = note
    return note


# The same grounding pattern as `_diagram_reference()`, applied to the document
# itself rather than to one diagram kind — one query is enough since "what
# makes a requirements document well-written" doesn't vary per project.
_srs_reference: str | None = None
_srs_reference_lock = threading.Lock()


def _srs_quality_reference() -> str:
    """A short, real-world grounding note on what makes a requirements
    specification well-written — never a source of this project's own
    requirements, only of what "well-written" looks like, so the review
    that follows judges against a real external reference instead of only
    the model's own untethered sense of quality."""
    global _srs_reference
    with _srs_reference_lock:
        if _srs_reference is not None:
            return _srs_reference
    found = llm.web_search(
        "IEEE 830 software requirements specification quality checklist "
        "ambiguity traceability well-written requirement examples", max_results=3)
    note = "\n".join(f"- {row['title']}: {row['content'][:300]}"
                     for row in found if row.get("content"))[:1200]
    with _srs_reference_lock:
        _srs_reference = note
    return note

NOT_APPLICABLE = "NOT_APPLICABLE"

WIREFRAME_APPROVAL_PROMPT = (
    "Use the approved /plan as the scope. Read the site map and the application spec at "
    ".agentforge/srs/handoff/ (sitemap.md, app.md). Before drawing anything, search the web "
    "(Ollama web search) for how good products of this kind lay out their screens, and take "
    "ideas from what you find. Then draw one creative, strictly black-and-white low-fidelity "
    "HTML wireframe for every planned screen, with no page limit. A screen is one page with one "
    "job: tables, forms and detail views each get a page of their own and are linked from the "
    "pages that lead to them, never piled into another page; use a popup only for a short "
    "contextual action. Draw the shared layout once and keep it identical on every page: the "
    "same navigation, header, sidebar and footer in the same position, and the same buttons, "
    "forms, cards, tables and status marks. Use realistic sample data and make the way from "
    "page to page obvious. Show the pages as a grid, one by one as they finish, and enable editing."
)


# --- reading ----------------------------------------------------------------

def document(project: str) -> dict[str, Any]:
    saved = session_for(project).read_record(*DOCUMENT, fallback=None)
    if not isinstance(saved, dict):
        return {}
    return saved if "srs_document" in saved else {"srs_document": saved}


def has_document(project: str) -> bool:
    return bool(document(project).get("srs_document"))


def _slug(route: str) -> str:
    cleaned = str(route or "/").strip("/")
    if not cleaned:
        return "home"
    stem = "".join(c if c.isalnum() else "_" for c in cleaned).strip("_") or "page"
    # /a-b and /a_b must never overwrite one another's HTML.
    return f"{stem}-{hashlib.sha1(str(route).encode('utf-8')).hexdigest()[:8]}"


def _pages_of(doc: dict) -> list[dict]:
    return [p for p in ((doc.get("public_pages") or []) + (doc.get("protected_pages") or []))
            if isinstance(p, dict) and str(p.get("route") or "").strip()]


def _wireframe_pages(doc: dict, approved: dict) -> list[dict]:
    """Every specified route, including a plan screen omitted by a draft SRS."""
    pages = list(_pages_of(doc))
    known = {str(p.get("route") or "").rstrip("/") or "/" for p in pages}
    for screen in approved.get("screens") or []:
        if not isinstance(screen, dict) or not str(screen.get("route") or "").strip():
            continue
        route = str(screen["route"]).rstrip("/") or "/"
        if route in known:
            continue
        pages.append({"route": route, "page_name": screen.get("name") or route,
                      "sections": [screen.get("purpose")] if screen.get("purpose") else [],
                      "functions": screen.get("functions") or [],
                      "allowed_roles": screen.get("who") or [],
                      "plan_screen": screen})
        known.add(route)
    return pages


# --- writing ----------------------------------------------------------------

def _write_document(session: ProjectSession, project: str, record: dict,
                    approved: dict) -> dict:
    """One call for the whole specification, validated against the schema.

    The approved plan and the interview are on disk at `.agentforge/plan.json`
    and `.agentforge/interview.json`; the model reads them itself rather than
    having them pasted in here.
    """
    bus.phase(project, "srs:document", "Writing the requirements",
              detail="Decomposing the approved plan into testable requirements.")
    # The focused call has no conversation of its own, so the project's memory
    # is handed to it. That is what keeps one context across all six stages
    # while still writing each artifact in its own call.
    memory = session.memory_digest()
    envelope = llm.complete_json(
        system=prompts.load("srs/system")
        + (f"\n\n## What this project already knows\n\n{memory}" if memory else ""),
        user=prompts.load("srs/document",
                          project_name=(str(approved.get("app_name") or "").strip()
                                        or record.get("name") or project),
                          stack=record.get("stack", ""),
                          language=record.get("language", "English")),
        validator=srs_schema.srs_validator,
        label="srs_document",
        project=project, workspace=session.workspace)
    doc = envelope["srs_document"]
    named = str((doc.get("app_summary") or {}).get("app_name") or "").strip()
    if named and str(doc.get("project_name") or "").strip() in ("", project):
        doc["project_name"] = named
    return envelope


def _write_record_visible(session: ProjectSession, project: str, parts: tuple,
                          data: Any) -> None:
    """Write a record and announce it, so the chat shows the file as it lands."""
    path = session.write_record(*parts, data=data)
    body = path.read_text(encoding="utf-8", errors="replace")
    bus.file_written(project, path.relative_to(session.workspace).as_posix(), body,
                     note="written")


def _write_user_journeys(session: ProjectSession, project: str, doc: dict) -> dict[str, Any]:
    """Save the SRS workflows as the one canonical journey list for E2E coverage."""
    contract = journeys.journey_contract_for(doc)
    _write_record_visible(session, project, USER_JOURNEYS, contract)
    bus.log(project, "SUCCESS", f"{len(contract['journeys'])} user journeys saved for E2E coverage.")
    return contract


def _draw_diagram(session: ProjectSession, project: str, doc: dict,
                  kind: str) -> dict | None:
    """One diagram: its source, and its SVG when a renderer is installed."""
    try:
        guidance = prompts.load(f"srs/diagrams/{kind}")
    except prompts.MissingPrompt:
        return None

    # Trimmed a whole field at a time from the low-priority end, never by
    # slicing the serialized string — a character cut lands mid-value on a
    # document this size and hands the model broken JSON it can only report
    # as truncated, not draw from. `read_file` itself caps at MAX_OUTPUT
    # (24000 chars), so this stays safely under that.
    fields = ["app_summary", "roles", "authentication_requirement", "main_modules",
             "database_design", "business_workflows", "api_design",
             "public_pages", "protected_pages"]
    digest = json.dumps({k: doc.get(k) for k in fields if doc.get(k)}, ensure_ascii=False)
    while len(digest) > 20000 and len(fields) > 1:
        fields.pop()
        digest = json.dumps({k: doc.get(k) for k in fields if doc.get(k)}, ensure_ascii=False)
    # Staged rather than pasted in: the model reads its own curated slice of
    # the specification with its read tool, and the read shows in the chat.
    # fresh=False: every kind's digest lands in this same shared folder, in
    # parallel (`llm.in_lanes`) — clearing it per kind would race the other
    # kinds' files still waiting to be read.
    context_path, = reference_staging.stage(
        session.workspace, f"{config.RECORD_DIR}/{SRS_DIR}/diagram-context",
        {f"{kind}.json": digest}, fresh=False)

    reference = _diagram_reference(kind)

    def _ask(extra: str = "") -> str:
        return mermaid.clean(llm.complete(
            system=prompts.load("srs/system"),
            user=prompts.load("srs/diagram", kind=kind, standard=kind, guidance=guidance,
                              document=context_path, reference=reference or "(no external reference found — follow the standard above)")
            + extra,
            project=project, workspace=session.workspace))

    bus.agent_msg(project, f"Generating the {kind.replace('_', ' ')} diagram from the specification.",
                  title="SRS diagram", kind="narration")
    source = _ask()

    if source.upper().startswith(NOT_APPLICABLE):
        return {"id": f"DIA-{kind}", "kind": kind, "title": kind.replace("_", " ").title(),
                "format": "mermaid", "source": "", "applicable": False,
                "applicability_note": source.split(":", 1)[-1].strip()[:240]}

    # Two separate checks drive this loop: `mermaid.problems()` (empty source, wrong
    # opener, unbalanced brackets — a static check that costs nothing and needs no
    # renderer) and, only when a renderer is installed, an actual render. A source
    # can fail the first without ever reaching the second, and it must still be
    # retried — an empty response is exactly the case a renderer-gated retry never
    # sees, which is how a diagram went missing with no repair attempt at all.
    mmd = session.record_path(SRS_DIR, "diagrams", f"{kind}.mmd")
    svg = session.record_path(SRS_DIR, "diagrams", f"{kind}.svg")
    rendered, why = False, "no renderer"

    for attempt in range(3):
        wrong = mermaid.problems(kind, source)
        if not wrong and mermaid.available():
            bus.agent_msg(project, f"Render {kind.replace('_', ' ')} diagram with Mermaid CLI.",
                          title="Rendering diagram", kind="command")
            rendered, why = mermaid.render(source, svg)
            bus.agent_msg(project, "SVG rendered successfully." if rendered else why,
                          title="Mermaid output", kind="command_output")
            if rendered:
                break
            wrong = [why]
        if not wrong or attempt == 2:
            break
        source = _ask(f"\n\n## Your last attempt\n\n```\n{source[:4000]}\n```\n\n"
                      f"It was rejected: {'; '.join(wrong)}\n\n"
                      f"Return corrected Mermaid source only.")

    mmd.write_text(source, encoding="utf-8")
    bus.file_written(project, mmd.relative_to(session.workspace).as_posix(), source,
                     note="drawn")
    bus.log(project, "SUCCESS" if rendered else "INFO",
            f"Diagram · {kind.replace('_', ' ')}"
            + ("" if rendered else f" (source only — {why[:80]})"))
    entry = {
        "id": f"DIA-{kind}", "kind": kind,
        "title": kind.replace("_", " ").title(),
        "format": "mermaid", "source": source, "applicable": True,
        "mmd_path": mmd.relative_to(session.workspace).as_posix(),
    }
    if rendered:
        entry["svg"] = svg.read_text(encoding="utf-8", errors="replace")
        entry["svg_path"] = svg.relative_to(session.workspace).as_posix()
        entry["rendered_by"] = "mermaid_cli"
        entry["format"] = "svg+mermaid-source"
    elif mermaid.available():
        entry["render_error"] = why[:240]
    return entry


def _page_instruction(project: str, doc: dict, page: dict, docs: dict[str, str], request: str = "",
                      ideas: str = "", layout: str = "") -> str:
    """The prompt one wireframe is drawn from.

    The site map and application spec are no longer pasted in: the model reads
    them itself with its read tool from `.agentforge/srs/handoff/`, so this
    holds no rules about what a page contains: the specification says it, in
    its own words, for whatever product it describes.
    """
    route = str(page.get("route") or "/")
    if not docs:
        raise ValueError("the SRS handoff files are missing; wireframes need the approved contract")
    instruction = prompts.load("srs/wireframe-page",
                               route=route,
                               page_name=str(page.get("page_name") or route),
                               sections=", ".join(wireframe_brief.page_lines(page.get("sections"))) or "(not listed)",
                               functions=", ".join(wireframe_brief.page_lines(page.get("functions"))) or "(not listed)",
                               app_summary=json.dumps(doc.get("app_summary") or {}, ensure_ascii=False),
                               page_contract=json.dumps(wireframe_brief.page_facts(page), ensure_ascii=False, indent=2),
                               ideas=ideas or "(none gathered — draw from the specification and your own judgement)",
                               layout=layout or "(none drawn — keep the shell and the components consistent from the site map)",
                               plan=wireframe_brief.clean(plan_stage.markdown(project)))
    if request:
        instruction += "\n\n## Approved wireframe request\n\n" + request
    return instruction


def _draw_page(session: ProjectSession, project: str, doc: dict, page: dict,
               docs: dict[str, str] | None = None, request: str = "",
               system: dict[str, str] | None = None, quiet: bool = False,
               stream: bool = False) -> dict:
    """One wireframe: a complete HTML document for one route.

    `stream` is only ever true for a single-page draw (one route, never the
    whole-set `llm.in_lanes` fan-out) — the studio's live file buffer is one
    slot, and three pages streaming into it at once would interleave into
    garbage. A bulk draw stays exactly as before: silent until the page is
    whole, then one `file_written`.
    """
    route = str(page.get("route") or "/")
    if not quiet:
        bus.agent_msg(project, f"Drawing {page.get('page_name') or route} ({route}) from the approved specification and handoff.",
                      title="Wireframe page", kind="narration")
    docs = docs if docs is not None else handoff_docs(session)
    system = system or {}                     # made once for the whole run by `_generate_wireframes`
    sections = page.get("sections") or []
    functions = page.get("functions") or []
    weight = max(1, len(sections) + len(functions) // 2)

    slug = _slug(route)
    path = session.record_path(SRS_DIR, "wireframes", f"{slug}.html")
    relative = path.relative_to(session.workspace).as_posix()
    writer = bus.StreamWriter(project, agent=bus.DEVELOPER) if stream else None
    on_start = (lambda: writer.start(relative)) if stream else None
    on_token = writer.token if stream else None

    instruction = _page_instruction(project, doc, page, docs, request,
                                    ideas=system.get("ideas", ""), layout=system.get("layout", ""))
    minimum = max(completeness.WIREFRAME_FLOOR,
                  weight * completeness.WIREFRAME_CHARS_PER_SECTION)
    html = llm.complete_html(system=prompts.load("srs/system"), user=instruction,
                             minimum=minimum, label=f"wireframe:{route}",
                             project=project, workspace=session.workspace, role=bus.DEVELOPER,
                             on_stream_start=on_start, on_stream_token=on_token)
    gaps = completeness.wireframe_depth([(route, html)], doc)
    if gaps:
        html = llm.complete_html(
            system=prompts.load("srs/system"), minimum=minimum,
            user=instruction + "\n\nYour last draft failed these wireframe checks:\n"
                 + completeness.as_instructions(gaps)
                 + "\n\nReturn a complete corrected HTML page, with its inline CSS.",
            label=f"wireframe_repair:{route}",
            project=project, workspace=session.workspace, role=bus.DEVELOPER,
            on_stream_start=on_start, on_stream_token=on_token)
        gaps = completeness.wireframe_depth([(route, html)], doc)
        if gaps:
            raise ValueError("; ".join(gaps)[:400])

    path.write_text(html, encoding="utf-8")
    if stream:
        writer.end(relative, html)
    if not quiet:
        bus.file_written(project, relative, html, note="drawn")
        bus.log(project, "SUCCESS",
                f"Wireframe · {page.get('page_name') or route} ({len(html):,} characters)")
    return {"route": route, "name": str(page.get("page_name") or route), "slug": slug,
            "file": relative}


def _wireframe_system(session: ProjectSession, project: str, doc: dict, docs: dict[str, str], fresh: bool,
                      quiet: bool = False) -> dict[str, Any]:
    """The web ideas and the shared layout every page is drawn from.

    Kept with the project, so redrawing one page reuses them; made anew when every page is drawn again.
    """
    have = {} if fresh else {
        "ideas": session.read_record(SRS_DIR, WIREFRAME_SYSTEM, "ideas.md", fallback="") or "",
        "layout": session.read_record(SRS_DIR, WIREFRAME_SYSTEM, "layout.html", fallback="") or "",
    }
    made = wireframe_brief.prepare(doc, docs, have,
                                   (lambda _text: None) if quiet else lambda text: bus.log(project, "INFO", text))
    for name, file in (("ideas", "ideas.md"), ("layout", "layout.html")):
        if name in made["new"]:
            path = session.record_path(SRS_DIR, WIREFRAME_SYSTEM, file)
            path.write_text(made[name], encoding="utf-8")
            if not quiet:
                bus.file_written(project, path.relative_to(session.workspace).as_posix(), made[name], note="written")
    return made


def handoff_docs(session: ProjectSession) -> dict[str, str]:
    """The handoff markdown, read off disk.

    Every stage after the specification works from these rather than from the
    specification being pasted into its prompt again — which is what keeps the
    wireframes, the prototype and the build reading the same contract.
    """
    folder = session.record / SRS_DIR / "handoff"
    out: dict[str, str] = {}
    for name in handoff_files.HANDOFF_FILES:
        path = folder / name
        if path.is_file():
            out[name] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _write_handoff(session: ProjectSession, project: str, doc: dict, record: dict) -> dict:
    """What every later stage consumes, derived from the document it must honour."""
    from prototype_agent import design as design_stage

    stack = str(record.get("stack") or "")
    design = design_stage.approved_spec(project) or None

    # app.md and sitemap.md are projections, not model output. A document the
    # model writes can truncate, and these are the contract the build reads.
    for name, body in handoff_files.render_all(doc, stack, design).items():
        path = session.record_path(SRS_DIR, "handoff", name)
        path.write_text(body, encoding="utf-8")
        bus.file_written(project, path.relative_to(session.workspace).as_posix(),
                         body, note="written")
        bus.log(project, "SUCCESS", f"Handoff · {name} ({len(body):,} characters)")
    session.write_record(SRS_DIR, "handoff", "manifest.json",
                         data=handoff_files.manifest(doc, stack))

    pages = _pages_of(doc)
    handoff = {
        "app_name": (doc.get("app_summary") or {}).get("app_name") or record.get("name"),
        "stack": record.get("stack", ""),
        "routes": [{"route": p.get("route"), "name": p.get("page_name"),
                    "roles": p.get("allowed_roles") or [],
                    "login_required": bool(p.get("login_required")),
                    "sections": p.get("sections") or [],
                    "functions": p.get("functions") or []} for p in pages],
        "collections": [{"name": t.get("table_name"),
                         "fields": [f.get("name") for f in (t.get("fields") or [])]}
                        for t in ((doc.get("database_design") or {}).get("tables") or [])],
        "relationships": (doc.get("database_design") or {}).get("relationships") or [],
        "roles": [r.get("role_name") for r in (doc.get("roles") or [])],
        "authentication": doc.get("authentication_requirement") or {},
        "api": doc.get("api_design") or [],
        "workflows": doc.get("business_workflows") or [],
        "validation_rules": doc.get("validation_rules") or [],
        "notification_rules": doc.get("notification_rules") or [],
        "acceptance": [a.get("criterion") for a in (doc.get("acceptance_criteria") or [])],
        "requirements": doc.get("functional_requirements") or [],
        "non_functional": doc.get("non_functional_requirements") or [],
    }
    handoff["prompt"] = llm.complete(
        system=prompts.load("srs/system"),
        user=("Write the single instruction the build agent works from. Name every "
              "page, role, record, workflow and acceptance proof it must deliver, "
              "in the order it should build them. Prose, no JSON, no preamble.\n\n"
              + json.dumps(handoff, ensure_ascii=False)[:30000]))
    handoff["files"] = {"BUILD.md": handoff["prompt"]}
    session.write_record(*HANDOFF, data=handoff)
    session.write_record(SRS_DIR, "BUILD.md", data=handoff["prompt"])
    return handoff


def _render_markdown(doc: dict) -> str:
    """The document as a readable specification. No model call — it is a projection."""
    out: list[str] = [f"# {doc.get('document_title', 'Software Requirements Specification')}", ""]
    summary = doc.get("app_summary") or {}
    out += [f"**{summary.get('app_name', doc.get('project_name', ''))}** — "
            f"version {doc.get('version', '1.0.0')} — {doc.get('document_language', 'English')}", ""]

    def block(title: str, rows: Any, render) -> None:
        items = [render(r) for r in (rows or []) if r]
        if items:
            out.extend([f"## {title}", ""] + items + [""])

    if summary:
        out += ["## 1. Introduction", "",
                str(summary.get("short_description", "")), "",
                f"**Business goal.** {summary.get('business_goal', '')}", "",
                "**Intended users.** " + ", ".join(summary.get("target_users") or []), ""]

    block("2. Roles", doc.get("roles"),
          lambda r: f"- **{r.get('role_name')}** (`{r.get('role_key')}`) — {r.get('description')}")
    block("3. Pages", _pages_of(doc),
          lambda p: f"- **{p.get('page_name')}** (`{p.get('route')}`) — "
                    f"{'sign-in required' if p.get('login_required') else 'public'}; "
                    f"roles: {', '.join(p.get('allowed_roles') or []) or 'anyone'}")
    block("4. Modules", doc.get("main_modules"), lambda m: f"- {m}")

    tables = (doc.get("database_design") or {}).get("tables") or []
    if tables:
        out += ["## 5. Data design", ""]
        for table in tables:
            out += [f"### `{table.get('table_name')}`", "",
                    str(table.get("description") or ""), "",
                    "| Field | Type | Key | Null | Unique | References |",
                    "|---|---|---|---|---|---|"]
            for field in (table.get("fields") or []):
                out.append(f"| {field.get('name')} | {field.get('type')} | "
                           f"{'PK' if field.get('primary_key') else ''} | "
                           f"{'yes' if field.get('nullable') else 'no'} | "
                           f"{'yes' if field.get('unique') else 'no'} | "
                           f"{field.get('references') or ''} |")
            out.append("")

    block("6. API", doc.get("api_design"),
          lambda a: f"- `{a.get('method')} {a.get('path')}` — {a.get('description')}"
                    f"{' (auth)' if a.get('auth_required') else ''}")
    block("7. Functional requirements", doc.get("functional_requirements"),
          lambda f: f"- **{f.get('id')}** [{f.get('priority', 'medium')}] "
                    f"({f.get('module')}) {f.get('requirement')}")
    block("8. Non-functional requirements", doc.get("non_functional_requirements"),
          lambda n: f"- **{n.get('id')}** ({n.get('category')}) {n.get('requirement')}")
    block("9. Business workflows", doc.get("business_workflows"),
          lambda w: f"- **{w.get('workflow_name')}** ({w.get('who') or 'anyone'}): "
                    + " → ".join(w.get("steps") or []))
    block("10. Validation rules", doc.get("validation_rules"),
          lambda v: f"- `{v.get('field')}` — {v.get('rule')}")
    block("11. Security", doc.get("security_requirements"), lambda s: f"- {s}")
    block("12. Acceptance criteria", doc.get("acceptance_criteria"),
          lambda a: f"- {a.get('criterion')}")
    block("13. Traceability", doc.get("requirement_traceability_matrix"),
          lambda t: f"- {t.get('requirement_id')} → pages: "
                    f"{', '.join(t.get('pages') or []) or '—'}; tables: "
                    f"{', '.join(t.get('tables') or []) or '—'}; test: {t.get('test_case') or '—'}")
    block("14. Assumptions", doc.get("assumptions"), lambda a: f"- {a}")
    block("15. Constraints", doc.get("constraints"), lambda c: f"- {c}")
    block("16. Ambiguities", doc.get("ambiguities"),
          lambda a: f"- **{a.get('id')}** ({a.get('area')}) {a.get('description')} "
                    f"— assumed: {a.get('assumption_made')}")
    block("17. Risks", doc.get("risk_priority"),
          lambda r: f"- **{r.get('id')}** [{r.get('severity')}] ({r.get('area')}) "
                    f"{r.get('risk')} — {r.get('mitigation')}")
    return "\n".join(out)


# --- the stage --------------------------------------------------------------

def generate(project: str) -> dict[str, Any]:
    record = store.require(project)
    approved = plan_stage.approved_plan(project)
    if not approved:
        raise ValueError("approve the plan before generating the specification")

    session = session_for(project)
    session.begin("srs", role=bus.DEVELOPER)
    # The studio blurs the SRS tab and shows the generating animation for as
    # long as this says the specification is being written.
    bus.sync_state(project, "running", "Writing the specification",
                   source="srs", srs_status="running")
    started = time.time()

    try:
        bus.agent_msg(project, "Writing the specification from the approved plan and interview answers.",
                      title="SRS generation", kind="narration")
        envelope = _write_document(session, project, record, approved)
        doc = envelope["srs_document"]
        _write_record_visible(session, project, DOCUMENT, envelope)
        bus.log(project, "SUCCESS",
                f"{len(doc.get('functional_requirements') or [])} functional and "
                f"{len(doc.get('non_functional_requirements') or [])} non-functional "
                f"requirements written.")

        # Validate and reconcile the main SRS against its approved plan before
        # spending model calls on diagrams. The diagrams are downstream
        # artifacts and must never mask a missing workflow or a broken SRS.
        envelope = _close_gaps(session, project, envelope, approved)
        bus.agent_msg(project, "Reviewing the requirements against the approved plan and SRS standards.",
                      title="SRS review", kind="narration")
        envelope = _review_loop(session, project, envelope, approved)
        envelope = _close_gaps(session, project, envelope, approved)
        srs_schema.srs_validator(envelope)
        _write_record_visible(session, project, DOCUMENT, envelope)

        doc = envelope["srs_document"]
        bus.phase(project, "srs:draw", "Drawing the diagrams",
                  detail=f"{len(DIAGRAM_KINDS)} diagrams, each on its own call.")

        drawn = llm.in_lanes(
            list(DIAGRAM_KINDS),
            lambda kind: _draw_diagram(session, project, doc, kind),
            on_error=lambda kind, exc: {"id": f"DIA-{kind}", "kind": kind,
                                        "title": kind.replace("_", " ").title(),
                                        "format": "mermaid", "source": "",
                                        "applicable": False,
                                        "applicability_note": f"drawing failed: {exc}"[:240]})
        doc["diagrams"] = [d for d in drawn if d]
        rendered = sum(1 for d in doc["diagrams"] if d.get("svg"))
        bus.log(project, "SUCCESS" if rendered else "WARN",
                f"{sum(1 for d in doc['diagrams'] if d.get('applicable'))} diagrams drawn, "
                f"{rendered} rendered to SVG."
                + ("" if mermaid.available() else
                   " Install @mermaid-js/mermaid-cli to see them as pictures."))

        doc = envelope["srs_document"]
        doc["approved_plan_markdown"] = plan_stage.markdown(project)
        doc["approved_plan"] = approved
        _write_record_visible(session, project, DOCUMENT, envelope)
        _write_record_visible(session, project, (SRS_DIR, "SRS.md"), _render_markdown(doc))
        _write_user_journeys(session, project, doc)

        # Draw from the final reviewed specification and handoff, not a draft
        # that a later repair may have changed. Each page appears independently.
        _write_handoff(session, project, doc, record)
        summary = srs_schema.summarize_srs(envelope)
        store.update(project, status="specified", spec_only=True)
        store.advance(project, "srs")
        named = str((doc.get("app_summary") or {}).get("app_name") or "").strip()
        if named and named != record.get("name"):
            store.rename(project, named)

        elapsed = int(time.time() - started)
        bus.agent_msg(project,
                      f"The specification is written in {elapsed}s: "
                      f"{summary['functional']} functional and {summary['non_functional']} "
                      f"non-functional requirements, {summary['tables']} tables, "
                      f"{summary['diagrams']} diagrams. Approve it to draw the wireframes.",
                      title="Specification ready")
        session.note(
            f"The specification is written and is now the contract. "
            f"{summary['functional']} functional and {summary['non_functional']} "
            f"non-functional requirements, {summary['tables']} tables, "
            f"{summary['roles']} roles, {summary['diagrams']} diagrams. "
            f"The handoff documents are at .agentforge/srs/handoff/ — app.md, "
            f"sitemap.md, prototype.md and builder.md. Read those rather than "
            f"asking for the specification again.")
        session.finish(f"Specification written in {elapsed}s.")
        bus.sync_state(project, "clean", "Specification written",
                       source="srs", srs_status="completed")
        return {"srs": envelope, "summary": summary}
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        bus.sync_state(project, "failed", str(exc)[:300], error=str(exc)[:300],
                       source="srs", srs_status="failed")
        raise


def _forget_stale_wireframes(session: ProjectSession, screens: list[dict]) -> None:
    """Delete drawings whose route the specification no longer has.

    A regenerated specification renames and drops routes, and the pages drawn for
    the old ones stay on disk looking like part of the current set.
    """
    folder = session.record / SRS_DIR / "wireframes"
    if not folder.is_dir():
        return
    keep = {str(row.get("file") or "").rsplit("/", 1)[-1] for row in screens}
    keep.add("index.json")
    for path in folder.iterdir():
        if path.is_file() and path.name not in keep:
            try:
                path.unlink()
            except OSError:
                pass


def _drawn_pages(session: ProjectSession) -> list[tuple[str, str]]:
    index = session.read_record(*WIREFRAME_INDEX, fallback=None) or {}
    out: list[tuple[str, str]] = []
    for row in (index.get("screens") or []):
        path = session.workspace / str(row.get("file") or "")
        if path.is_file():
            out.append((str(row.get("route") or ""),
                        path.read_text(encoding="utf-8", errors="replace")))
    return out


def _slug_words(value: str) -> list[str]:
    return [word for word in re.split(r"[^a-z0-9]+", str(value or "").lower()) if word]


def _new_table_name(label: str) -> str:
    """Turn an approved record label into a conventional plural table name."""
    words = list(completeness._entity_words(label))
    if not words:
        return "records"
    last = words[-1]
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        words[-1] = last[:-1] + "ies"
    elif last.endswith(("s", "x", "ch", "sh")):
        words[-1] = last + "es"
    else:
        words[-1] = last + "s"
    return "_".join(words)


def _next_requirement_id(requirements: list[dict]) -> str:
    numbers = [int(match.group(1)) for row in requirements
               if (match := re.fullmatch(r"FR-(\d+)", str(row.get("id") or "")))]
    return f"FR-{max(numbers, default=0) + 1:03d}"


def _append_plan_requirement(doc: dict, requirement: str, actor: str = "",
                              rationale: str = "") -> None:
    rows = doc.setdefault("functional_requirements", [])
    role_names = {str(row.get("role_name") or "").casefold(): str(row.get("role_name") or "")
                  for row in doc.get("roles") or []}
    normalized_actor = role_names.get(actor.casefold(), actor) if actor else ""
    rows.append({
        "id": _next_requirement_id(rows),
        "module": "Plan Coverage" if not actor else f"{actor} Capabilities",
        "requirement": requirement,
        "priority": "high",
        "allowed_roles": [normalized_actor] if normalized_actor else [],
        "verification_method": "Functional Test",
        "rationale": rationale or requirement,
    })


def _synchronize_plan_contract(envelope: dict, approved: dict) -> dict[str, int]:
    """Deterministically fill plan omissions without another full-document LLM rewrite.

    The approved plan is already structured and approved by the user. Copying a
    missing journey or route from it is safer than asking a model to regenerate
    a 100KB JSON document; actual feature gaps get small, traceable requirements.
    """
    doc = envelope["srs_document"]
    added = {"pages": 0, "tables": 0, "workflows": 0, "requirements": 0,
             "traceability": 0}

    # The plan's routes are authoritative. Keep the model's richer page details
    # when present; only fill routes it omitted.
    page_lists = (doc.setdefault("public_pages", []), doc.setdefault("protected_pages", []))
    existing_routes = {str(page.get("route") or "").rstrip("/") or "/"
                      for rows in page_lists for page in rows}
    for screen in approved.get("screens") or []:
        if not isinstance(screen, dict):
            continue
        route = str(screen.get("route") or "").strip()
        if not route or (route.rstrip("/") or "/") in existing_routes:
            continue
        roles = [str(role) for role in screen.get("who") or [] if str(role).strip()]
        public = not roles or any(role.casefold() == "visitor" for role in roles)
        page = {
            "page_name": str(screen.get("name") or route),
            "route": route,
            "page_type": "public" if public else "protected",
            "login_required": not public,
            "allowed_roles": roles,
            "sections": [str(screen.get("purpose") or "")],
            "functions": [str(screen.get("purpose") or "")],
        }
        page_lists[0 if public else 1].append(page)
        existing_routes.add(route.rstrip("/") or "/")
        added["pages"] += 1

    # Match normalized singular entity names, so e.g. "Booking History Entry"
    # correctly matches `booking_history_entries` instead of prompting a rewrite.
    database = doc.setdefault("database_design", {})
    tables = database.setdefault("tables", [])
    existing_entities = {completeness._entity_words(row.get("table_name") or "")
                         for row in tables}
    for record in approved.get("records") or []:
        if not isinstance(record, dict):
            continue
        label = str(record.get("name") or "").strip()
        entity = completeness._entity_words(label)
        if not entity or entity in existing_entities:
            continue
        fields = [{"name": "id", "type": "uuid", "primary_key": True,
                   "nullable": False, "unique": True}]
        seen_fields = {"id"}
        for kept in record.get("keeps") or []:
            field_name = "_".join(_slug_words(str(kept)))
            if not field_name or field_name in seen_fields:
                continue
            seen_fields.add(field_name)
            field_type = ("date" if "date" in field_name else
                          "number" if any(term in field_name for term in
                                          ("amount", "price", "revenue")) else
                          "integer" if any(term in field_name for term in
                                           ("count", "number", "maximum")) else
                          "string")
            fields.append({"name": field_name, "type": field_type,
                           "nullable": True})
        table_name = _new_table_name(label)
        tables.append({"table_name": table_name,
                       "description": f"Approved plan record: {label}.",
                       "fields": fields})
        existing_entities.add(entity)
        added["tables"] += 1

    # The workflow list is part of the approved plan. Copy only missing
    # journeys, preserving all ordered steps and the user's exact scope.
    workflows = doc.setdefault("business_workflows", [])
    workflow_names = {str(row.get("workflow_name") or "").strip().casefold()
                      for row in workflows if isinstance(row, dict)}
    for flow in approved.get("workflows") or []:
        if not isinstance(flow, dict):
            continue
        name = str(flow.get("name") or "").strip()
        if name and name.casefold() not in workflow_names:
            workflows.append({"workflow_name": name,
                              "who": str(flow.get("who") or ""),
                              "steps": [str(step) for step in flow.get("steps") or []]})
            workflow_names.add(name.casefold())
            added["workflows"] += 1

    # Add a specific, testable FR only when neither the model's requirements
    # nor the now-complete plan workflows speak to an approved item.
    for gap in completeness.requirement_coverage(doc, approved):
        feature_match = re.match(r"no functional requirement covers the plan feature: (.+)$", gap)
        action_match = re.match(r"no functional requirement covers what (.+?) can do: (.+)$", gap)
        if feature_match:
            feature = feature_match.group(1).strip("'")
            sentence = ("The system shall support the approved capability: "
                        f"{feature.rstrip('.')}.")
            _append_plan_requirement(doc, sentence, rationale=f"Approved plan feature: {feature}")
            added["requirements"] += 1
        elif action_match:
            actor, action = action_match.groups()
            action = action.strip("'")
            sentence = (f"The system shall allow {actor} to "
                        f"{action.rstrip('.')}.")
            _append_plan_requirement(doc, sentence, actor=actor,
                                     rationale=f"Approved {actor} capability: {action}")
            added["requirements"] += 1

    # Trace every requirement exactly once; never send a missing trace row back
    # through a fragile whole-document generation call.
    matrix = doc.setdefault("requirement_traceability_matrix", [])
    traced = {str(row.get("requirement_id") or "") for row in matrix
              if isinstance(row, dict)}
    pages = (doc.get("public_pages") or []) + (doc.get("protected_pages") or [])
    tables = database.get("tables") or []
    for row in doc.get("functional_requirements") or []:
        req_id = str(row.get("id") or "")
        if not req_id or req_id in traced:
            continue
        haystack = f"{row.get('module') or ''} {row.get('requirement') or ''}".casefold()
        related_pages = [str(page.get("route") or "") for page in pages
                         if any(word in haystack for word in
                                completeness._entity_words(page.get("page_name") or ""))]
        related_tables = [str(table.get("table_name") or "") for table in tables
                          if any(word in haystack for word in
                                 completeness._entity_words(table.get("table_name") or ""))]
        matrix.append({"requirement_id": req_id,
                       "module": str(row.get("module") or "Plan Coverage"),
                       "pages": related_pages,
                       "tables": related_tables,
                       "test_case": f"TC-{len(matrix) + 1:03d}"})
        traced.add(req_id)
        added["traceability"] += 1

    return added


def _close_gaps(session: ProjectSession, project: str, envelope: dict,
                approved: dict) -> dict:
    """Run the first-pass plan validator and deterministically close omissions."""
    srs_schema.srs_validator(envelope)
    doc = envelope["srs_document"]
    doc.setdefault("diagrams", [])
    added = _synchronize_plan_contract(envelope, approved)
    srs_schema.srs_validator(envelope)
    gaps = completeness.check_document(doc, approved)
    if gaps:
        doc.setdefault("requirements_quality_review", {})["coverage_gaps"] = gaps
        raise ValueError("The SRS did not pass approved-plan coverage validation: "
                         + "; ".join(gaps[:8]))
    doc.setdefault("requirements_quality_review", {})["coverage_gaps"] = []
    session.write_record(*DOCUMENT, data=envelope)
    repaired = sum(added.values())
    if repaired:
        bus.log(project, "WARN",
                "First-pass validator aligned the SRS with the approved plan: "
                f"{added['workflows']} workflows, {added['pages']} screens, "
                f"{added['tables']} records, {added['requirements']} requirements, "
                f"and {added['traceability']} traceability rows completed.")
    bus.log(project, "SUCCESS",
            f"Main SRS passed plan validation: {len(doc.get('public_pages') or []) + len(doc.get('protected_pages') or [])} screens, "
            f"{len(doc.get('business_workflows') or [])} workflows, "
            f"{len((doc.get('database_design') or {}).get('tables') or [])} records, "
            f"{len(doc.get('functional_requirements') or [])} traced requirements.")
    return envelope


def _review_loop(session: ProjectSession, project: str, envelope: dict,
                 approved: dict) -> dict:
    """Audit the draft against the standards, and send it back while that helps."""
    cap = max(0, int(config.setting("srs_review_max_iterations", 2)))
    previous: int | None = None

    for round_no in range(cap + 1):
        doc = envelope["srs_document"]
        if not doc.get("functional_requirements"):
            review_rules.stamp(doc, "skipped", round_no, "there was nothing to review")
            return envelope

        bus.phase(project, "srs:review", "Reviewing the specification",
                  detail=f"Against the requirements standards (round {round_no + 1}).")
        structure = completeness.section_completeness(doc)
        ambiguity = completeness.ambiguity_resolution(doc)
        structure_readout = (
            f"- populated: {', '.join(structure['populated']) or '(none)'}\n"
            f"- empty: {', '.join(structure['empty']) or '(none)'}\n"
            f"- ambiguities flagged: {ambiguity['total']}, resolved: {ambiguity['resolved']} "
            f"({ambiguity['rate']:.0%})")
        try:
            reference = _srs_quality_reference()
        except Exception:  # noqa: BLE001 - grounding is a bonus, never a blocker
            reference = ""
        try:
            verdict = llm.complete_json(
                system=prompts.load("srs/review",
                                    standards=prompts.skills("srs", only=review_rules.AUDIT_SKILLS,
                                                             budget=5000),
                                    document=review_rules.digest(doc),
                                    reference=reference or "(unavailable this run)",
                                    structure=structure_readout),
                user="Report against the standards above. Judge how the requirements "
                     "are written, not what the product does.",
                validator=review_rules.review_validator(doc), label="srs_review")
        except Exception as exc:  # noqa: BLE001 - a critic must never block the draft
            bus.log(project, "WARN", f"Review skipped ({exc}) — keeping the draft.")
            review_rules.stamp(doc, "skipped", round_no, "the review did not complete")
            return envelope

        blocking = review_rules.blockers(verdict)
        session.write_record(SRS_DIR, "reviews", f"round-{round_no + 1}.json", data=verdict)

        if review_rules.satisfied(verdict):
            bus.log(project, "SUCCESS", f"Specification accepted after {round_no + 1} round(s).")
            review_rules.stamp(doc, "accepted", round_no + 1,
                               "the draft met the standards", verdict,
                               structural={"sections": structure, "ambiguity": ambiguity})
            return envelope

        if round_no >= cap:
            review_rules.stamp(doc, "capped", round_no + 1,
                               f"the {cap}-round review limit was reached", verdict,
                               structural={"sections": structure, "ambiguity": ambiguity})
            return envelope

        if previous is not None and len(blocking) >= previous:
            review_rules.stamp(doc, "stalled", round_no + 1, "a round made no progress", verdict)
            return envelope

        previous = len(blocking)
        bus.log(project, "WARN", f"{len(blocking)} blocking finding(s) — rewriting.")
        try:
            repaired = llm.complete_json(
                system=prompts.load("srs/system"),
                user=prompts.load("srs/repair",
                                  findings=review_rules.findings_text(verdict),
                                  plan=json.dumps(approved, ensure_ascii=False, indent=2),
                                  document=json.dumps(envelope, ensure_ascii=False, indent=2)),
                validator=srs_schema.srs_validator, label="srs_review_repair")
            repaired["srs_document"]["diagrams"] = doc.get("diagrams") or []
            envelope = repaired
            session.write_record(*DOCUMENT, data=envelope)
        except Exception as exc:  # noqa: BLE001
            bus.log(project, "WARN", f"The rewrite failed ({exc}); keeping the draft.")
            review_rules.stamp(doc, "stalled", round_no + 1, "a repair round failed", verdict)
            return envelope
    return envelope


# --- what the studio reads --------------------------------------------------

def diagrams(project: str) -> dict[str, Any]:
    doc = document(project).get("srs_document", {})
    return {"diagrams": doc.get("diagrams") or []}


def handoff(project: str) -> dict[str, Any]:
    saved = session_for(project).read_record(*HANDOFF, fallback=None)
    return saved if isinstance(saved, dict) else {}


def agent_handoff(project: str) -> dict[str, Any]:
    data = handoff(project)
    files = dict(data.get("files") or {})
    if data.get("prompt") and "BUILD.md" not in files:
        files["BUILD.md"] = data["prompt"]
    return {"files": files, "prompt": data.get("prompt", "")}


def wireframes(project: str) -> dict[str, Any]:
    """The drawings and the journeys, in the shape the studio's screens read.

    `pages` with `page_name` and `has_html` feeds the wireframe grid; `journeys`
    feeds the User Journey view, which shows nothing at all without it.
    """
    session = session_for(project)
    index = session.read_record(*WIREFRAME_INDEX, fallback=None)
    rows = (index or {}).get("screens") or []
    doc = document(project).get("srs_document", {})
    by_route = {str(p.get("route")): p for p in _wireframe_pages(
        doc, plan_stage.approved_plan(project))}
    indexed = {str(row.get("route")): row for row in rows}
    drawing = bool((index or {}).get("drawing") and session.stage in ("srs", "wireframes"))

    pages = []
    for route, page in by_route.items():
        row = indexed.get(route, {})
        file = session.workspace / str(row.get("file")) if row.get("file") else None
        has_html = bool(file and file.is_file() and file.stat().st_size)
        pages.append({
            "route": route,
            "page_name": row.get("name") or page.get("page_name") or route,
            "page_type": page.get("page_type") or "",
            "login_required": bool(page.get("login_required")),
            "roles": page.get("allowed_roles") or [],
            "functions": page.get("functions") or [],
            "slug": row.get("slug") or _slug(route),
            "has_html": has_html,
            "have": has_html,
            "drawing": bool(drawing and row.get("drawing")),
            "error": row.get("error") or "",
        })
    return {"pages": pages, "wireframes": pages, "screens": pages, "drawing": drawing,
            "journeys": journeys.user_journeys_for(doc),
            "version": doc.get("version", ""), "generated_from": "srs"}


def wireframe_html(project: str, route: str) -> str:
    session = session_for(project)
    index = session.read_record(*WIREFRAME_INDEX, fallback=None) or {}
    wanted = str(route or "/")
    for row in (index.get("screens") or []):
        if str(row.get("route")) == wanted:
            path = session.workspace / str(row.get("file") or "")
            if path.is_file():
                return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"no wireframe for {wanted}")


def save_wireframe_html(project: str, route: str, html: str) -> dict[str, Any]:
    session = session_for(project)
    index = session.read_record(*WIREFRAME_INDEX, fallback=None) or {}
    for row in (index.get("screens") or []):
        if str(row.get("route")) == str(route):
            path = session.workspace / str(row.get("file") or "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            bus.file_written(project, str(row.get("file")), html,
                             note="edited", agent=bus.DESIGNER)
            return {"ok": True, "route": route}
    raise FileNotFoundError(f"no wireframe for {route}")


def _generate_wireframes(session: ProjectSession, project: str, doc: dict,
                         approved: dict, route: str = "", request: str = "", quiet: bool = False) -> int:
    """Draw every approved route, saving progress after each independent page."""
    pages = _wireframe_pages(doc, approved)
    previous = session.read_record(*WIREFRAME_INDEX, fallback=None) or {}
    old = {str(row.get("route")): row for row in previous.get("screens") or []}
    selected = [p for p in pages if not route or str(p.get("route")) == route]
    if not selected:
        raise FileNotFoundError(f"no page to draw for {route or 'this project'}")
    docs = handoff_docs(session)
    if not docs:
        raise ValueError("the SRS handoff files are missing")

    selected_routes = {str(p["route"]) for p in selected}
    rows = []
    for page in pages:
        page_route = str(page["route"])
        row = dict(old.get(page_route) or {})
        row.update({"route": page_route, "name": page.get("page_name") or page_route,
                    "slug": row.get("slug") or _slug(page_route),
                    "file": row.get("file") or
                    f".agentforge/srs/wireframes/{_slug(page_route)}.html"})
        if page_route in selected_routes:
            row.update({"drawing": True, "error": ""})
        rows.append(row)
    state = {"screens": rows, "drawing": True}
    lock = threading.Lock()
    session.write_record(*WIREFRAME_INDEX, data=state)
    if not quiet:
        bus.phase(project, "wireframes", "Drawing the wireframes",
                  detail=f"{len(selected)} page(s) from the approved plan and SRS handoff.")
        bus.agent_msg(project, f"Drawing {len(selected)} wireframe page(s) from the approved SRS and handoff.",
                      title="Wireframe generation", kind="narration")

    def update(page: dict, result: dict | None = None, error: Exception | None = None) -> None:
        with lock:
            row = next(r for r in rows if r["route"] == str(page["route"]))
            if result:
                row.update(result)
            row["drawing"] = False
            row["error"] = str(error)[:300] if error else ""
            session.write_record(*WIREFRAME_INDEX, data=state)

    system: dict[str, str] = {}
    # Only a single-route draw can safely stream — see _draw_page's own note.
    stream_this = len(selected) == 1

    def draw(page: dict) -> dict | None:
        try:
            result = _draw_page(session, project, doc, page, docs, request, system,
                                quiet=quiet, stream=stream_this)
            update(page, result=result)
            return result
        except Exception as exc:  # one failed route must not hide the others
            update(page, error=exc)
            if not quiet:
                bus.log(project, "WARN", f"Wireframe {page.get('route')} failed: {exc}")
            return None

    try:
        # Before any page: ideas from the web and the one layout every page starts from (kept when a single page is redrawn).
        if not quiet:
            bus.phase(project, "wireframes", "Preparing the design system",
                      detail="Looking up how products like this lay out their screens, then drawing the shared layout.")
        system.update(_wireframe_system(session, project, doc, docs, fresh=not route, quiet=quiet))
        results = llm.in_lanes(selected, draw)
    finally:
        state["drawing"] = False
        session.write_record(*WIREFRAME_INDEX, data=state)
        if not route:
            _forget_stale_wireframes(session, rows)
    count = sum(bool(result) for result in results)
    if not quiet:
        bus.phase(project, "wireframes", "Drawing the wireframes", status="complete",
                  detail=f"{count} of {len(selected)} pages drawn.")
        bus.agent_msg(project, f"{count} of {len(selected)} wireframes are ready in the "
                               f"Wireframe tab. Open a page to edit it."
                               + (" Retry any page that failed." if count < len(selected) else ""),
                      title="Wireframes ready" if count == len(selected) else "Wireframes need attention")
    return count


def redraw(project: str, route: str = "", quiet: bool = False) -> dict[str, Any]:
    """Draw one page again, or every page, each on its own call."""
    session = session_for(project)
    doc = document(project).get("srs_document", {})
    if not quiet:
        session.begin("wireframes", role=bus.DEVELOPER)
    try:
        request = prompts.load("srs/wireframe-redraw", route=route) if quiet and route else ""
        count = _generate_wireframes(session, project, doc,
                                     plan_stage.approved_plan(project), route=route,
                                     request=request, quiet=quiet)
        if not quiet:
            session.finish(f"{count} wireframe(s) drawn.")
        return wireframes(project)
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            session.fail(str(exc))
        raise


def detail(project: str) -> dict[str, Any]:
    record = store.require(project)
    envelope = document(project)
    plan_state = plan_stage.current(project)
    return {
        "project": {
            "id": project,
            "name": record.get("name") or project,
            "status": record.get("status", "planning"),
            "stage": record.get("stage", "interview"),
            "stack": record.get("stack", ""),
            "language": record.get("language", "English"),
            "current_version": (envelope.get("srs_document") or {}).get("version", ""),
        },
        "srs": envelope or None,
        "summary": srs_schema.summarize_srs(envelope) if envelope else None,
        "versions": plan_state.get("versions", []),
        "plan": plan_state.get("markdown", ""),
    }


def results(project: str) -> dict[str, Any]:
    from . import interview

    envelope = document(project)
    doc = envelope.get("srs_document", {})
    handoff_data = handoff(project)
    plan_text = doc.get("approved_plan_markdown") or plan_stage.markdown(project)
    transcript = interview.snapshot(project)
    drawn = wireframes(project)
    journey_contract = session_for(project).read_record(*USER_JOURNEYS, fallback=None)
    diagram_rows = [d for d in (doc.get("diagrams") or [])
                    if isinstance(d, dict) and d.get("applicable") is not False]

    return {
        "project": project,
        "document": doc,
        "srs": envelope or None,
        "summary": srs_schema.summarize_srs(envelope) if envelope else None,
        "diagrams": doc.get("diagrams") or [],
        "plan": plan_text,
        "handoff": handoff_data,
        "interview": transcript,
        "wireframes": drawn["pages"],
        "journeys": drawn["journeys"],
        "journey_contract": journey_contract if isinstance(journey_contract, dict) else None,
        "versions": plan_stage.current(project).get("versions", []),
        "status": (store.get(project) or {}).get("status", ""),
        "version": doc.get("version", ""),
        "have": {
            "document": bool(doc),
            "plan": bool(str(plan_text).strip()),
            "handoff": bool(handoff_data.get("prompt")),
            "interview": bool(transcript.get("transcript")),
            "diagrams": bool(diagram_rows),
            "wireframes": bool(drawn["pages"]),
            "pdf": bool(doc),
        },
    }


def approve(project: str, prompt: str = "") -> dict[str, Any]:
    if not has_document(project):
        raise ValueError("there is no specification to approve yet")
    session = session_for(project)
    if session.stage in ("srs", "wireframes"):
        raise ValueError("wait for the current specification or wireframe run to finish")
    request = str(prompt or WIREFRAME_APPROVAL_PROMPT).strip()
    store.update(project, status="approved")
    store.advance(project, "design")
    bus.log(project, "SUCCESS", "SRS approved — drawing HTML wireframes from the plan and handoff files.")
    session.begin("wireframes", role=bus.DEVELOPER)
    bus.sync_state(project, "running", "Drawing approved wireframes", source="wireframe")
    try:
        doc = document(project)["srs_document"]
        drawn = _generate_wireframes(session, project, doc,
                                     plan_stage.approved_plan(project),
                                     request=request)
        total = wireframes(project)["pages"]
        ready = sum(bool(row["has_html"]) for row in total)
        session.finish(f"{ready} of {len(total)} wireframe(s) ready.")
        bus.sync_state(project, "clean", "Wireframes ready", source="wireframe")
        return {"ok": True, "project": project, "drawn": drawn,
                "ready": ready, "total": len(total)}
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        bus.sync_state(project, "failed", str(exc)[:300], source="wireframe",
                       error=str(exc)[:300])
        raise
