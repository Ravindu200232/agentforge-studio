"""What a wireframe is given besides its own page record.

Three things, all prompt-driven:

* the handoff, without the parts a drawing does not need (who may open a screen, how sign-in is seeded, how the server is built).
  The files on disk are never touched; only the copy a wireframe prompt carries is cleaned, by the rules in
  `prompts/srs/wireframe-context.json`;
* ideas gathered from the web before anything is drawn (Ollama web search, queries written by the model);
* one shared layout, drawn once, that every page starts from, so the shell and the components are the same on every page.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from server_modules import llm, prompts

Say = Callable[[str], None]

_SEPARATOR = re.compile(r"[\s:\-|]+")


def rules() -> dict[str, Any]:
    return prompts.data("srs/wireframe-context")


def _patterns(rule: dict) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in rule.get("omit_patterns") or []]


def _matches(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _items(cell: str, patterns: list[re.Pattern[str]]) -> str:
    """A table cell that lists things ("a, b, c") without the ones that are left out."""
    if not _matches(cell, patterns):
        return cell
    return ", ".join(part.strip() for part in cell.split(",") if not _matches(part, patterns))


_BULLET = re.compile(r"^(\s*(?:[-*]|\d+\.)\s+)?(.*?)\s*$")
# Where a line can be cut into clauses: a sentence end, a semicolon, a comma, " and ", a dash.
_JOINT = re.compile(r";\s+|,\s+and\s+|,\s+|\s+and\s+|\s+—\s+|(?<=[.!?])\s+")


def _clauses(text: str) -> list[tuple[str, str]]:
    """`[(what came before it, the clause)]`, cutting only outside brackets, backticks and bold."""
    parts, last, joint = [], 0, ""
    for match in _JOINT.finditer(text):
        before = text[:match.start()]
        if before.count("(") > before.count(")") or before.count("`") % 2 or before.count("**") % 2 or before.count("_[") > before.count("]_"):
            continue
        parts.append((joint, text[last:match.start()]))
        joint, last = match.group(0), match.end()
    parts.append((joint, text[last:]))
    return parts


def _trim(line: str, patterns: list[re.Pattern[str]]) -> str:
    """A line without the clauses the rules leave out. The line's own lead (its label, its requirement id) is never trimmed:
    when the lead itself is what the rules leave out, the whole line goes."""
    marker, body = _BULLET.match(line).groups()
    parts = _clauses(body)
    if _matches(parts[0][1], patterns):
        return ""
    kept = [(joint, text) for joint, text in parts if not _matches(text, patterns)]
    rebuilt = "".join(joint + text for joint, text in kept)
    if body.rstrip().endswith((".", "!", "?")) and not rebuilt.rstrip().endswith((".", "!", "?")):
        rebuilt = rebuilt.rstrip() + "."
    return (marker or "") + rebuilt


def clean(markdown: str, rule: dict | None = None) -> str:
    """The markdown without the sections, table columns, clauses and lines the rules leave out."""
    rule = rule or rules()
    patterns = _patterns(rule)
    strips = [re.compile(p) for p in rule.get("strip_patterns") or []]
    sections = {s.strip().lower() for s in rule.get("omit_sections") or []}
    columns = {c.strip().lower() for c in rule.get("omit_columns") or []}
    out: list[str] = []
    skipping, in_table, dropped = 0, False, []
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            if skipping and level <= skipping:
                skipping = 0
            if not skipping and heading.group(2).strip("` ").lower() in sections:
                skipping = level
            in_table = False
            if not skipping:
                out.append(line)
            continue
        if skipping:
            continue
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not in_table:
                in_table, dropped = True, [i for i, c in enumerate(cells) if c.lower() in columns]
            kept = [c if _SEPARATOR.fullmatch(c) else _items(c, patterns) for i, c in enumerate(cells) if i not in dropped]
            if kept:
                out.append("| " + " | ".join(kept) + " |")
            continue
        in_table = False
        for strip in strips:
            line = strip.sub("", line)
        if line.strip() and _matches(line, patterns):
            line = _trim(line, patterns)
            if not line.strip():
                continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def context(docs: dict[str, str], rule: dict | None = None) -> str:
    """The handoff files a wireframe reads, cleaned, in the order the rules name them."""
    rule = rule or rules()
    parts = []
    for name in rule.get("files") or list(docs):
        body = clean(docs.get(name, ""), rule).strip() if docs.get(name) else ""
        if body:
            parts.append(f"### .agentforge/srs/handoff/{name}\n\n{body}")
    return "\n\n".join(parts)


def page_facts(page: dict, rule: dict | None = None) -> dict:
    """One page's record without the fields the rules leave out, and without list items they match."""
    rule = rule or rules()
    patterns, dropped = _patterns(rule), set(rule.get("omit_page_fields") or [])
    out: dict[str, Any] = {}
    for key, value in page.items():
        if key in dropped:
            continue
        if isinstance(value, dict):
            value = page_facts(value, rule)
        elif isinstance(value, list):
            value = [v for v in value if not (isinstance(v, str) and _matches(v, patterns))]
        out[key] = value
    return out


def page_lines(values: list, rule: dict | None = None) -> list[str]:
    """A page's sections or functions as text, without the ones the rules leave out."""
    patterns = _patterns(rule or rules())
    return [str(v) for v in values or [] if not _matches(str(v), patterns)]


# --- the web, and the layout ------------------------------------------------------------------------------------------

def _queries(data: Any) -> list[str]:
    rows = data.get("queries") if isinstance(data, dict) else data
    found = [" ".join(str(q).split()) for q in (rows or []) if str(q).strip()]
    if not found:
        raise ValueError('give one to three search queries as {"queries": ["…"]}')
    return found[:3]


def gather_ideas(app_summary: str, site_map: str, say: Say, project: str = "") -> str:
    """Search the web for how products like this lay out their screens, and write down what the results are good for."""
    system = prompts.load("srs/system")
    try:
        queries = llm.complete_json(system=system, label="wireframe_research", validator=_queries, project=project,
                                    user=prompts.load("srs/wireframe-research", app_summary=app_summary, site_map=site_map))
    except Exception as exc:  # noqa: BLE001 - drawing goes on without ideas
        say(f"Could not plan the web search ({str(exc)[:120]}); drawing without web ideas.")
        return ""
    found, seen = [], set()
    for query in queries:
        say(f'Searched the web for "{query}"')
        for row in llm.web_search(query, 4):
            if row["url"] and row["url"] not in seen:
                seen.add(row["url"])
                found.append(row)
    if not found:
        say("The web search returned nothing; drawing without web ideas.")
        return ""
    results = "\n\n".join(f"### {r['title']}\n{r['content']}" for r in found[:10])
    try:
        return llm.complete(system=system, user=prompts.load("srs/wireframe-ideas", app_summary=app_summary, site_map=site_map,
                                                             results=results), project=project).strip()
    except Exception as exc:  # noqa: BLE001
        say(f"Could not write the ideas up ({str(exc)[:120]}); drawing without web ideas.")
        return ""


def draw_layout(app_summary: str, site_map: str, ideas: str, say: Say, plan: str = "", project: str = "") -> str:
    """The layout every page starts from: its shells and its components, drawn once, as the wireframe plan sets them out."""
    try:
        return llm.complete_html(system=prompts.load("srs/system"), label="wireframe_layout", minimum=2500, project=project,
                                 user=prompts.load("srs/wireframe-layout", app_summary=app_summary, site_map=site_map,
                                                   ideas=ideas or "(none gathered)",
                                                   plan=plan or "(no wireframe plan — set the shells out from the site map)"))
    except Exception as exc:  # noqa: BLE001
        say(f"Could not draw the shared layout ({str(exc)[:120]}); the pages are drawn from the rules alone.")
        return ""


def prepare(doc: dict, docs: dict[str, str], have: dict[str, str], say: Say, plan: str = "",
            project: str = "") -> dict[str, Any]:
    """The ideas and the layout: what is already kept is reused, what is missing is made. `new` names what was just made.
    `project` only reports each call's context to the chat's meter."""
    summary = json.dumps(doc.get("app_summary") or {}, ensure_ascii=False)
    site_map = clean(docs.get("sitemap.md", "")).strip()[:8000]
    ideas, layout, new = have.get("ideas", ""), have.get("layout", ""), []
    if not ideas:
        ideas = gather_ideas(summary, site_map, say, project)
        if ideas:
            new.append("ideas")
    if not layout:
        layout = draw_layout(summary, site_map, ideas, say, plan=plan, project=project)
        if layout:
            new.append("layout")
    return {"ideas": ideas, "layout": layout, "new": new}
