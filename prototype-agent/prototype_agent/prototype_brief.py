"""What a prototype page is given besides its own record.

The prototype used to be drawn page by page, each page from the whole wireframe, so it came out looking like the wireframe, with a
different shell on every page and no shared flow. This module is what makes it one product:

* the wireframe's *structure* without its look (its styles, classes and scripts are dropped, so nothing low-fidelity is left to copy);
* one shared kit, drawn once: `assets/app.css`, `assets/app.js` and the shell every page starts from;
* the flow: the journeys as "this page leads to that page", written into `assets/flow.js` so links cannot go to a page that is not there;
* one demo account per role, defined once, used by the sign-in page, by the kit and by the message to the customer;
* ideas from the web on how the best products of this kind look, and real sample photographs found by web search and checked alive.

Everything the model is asked is in `prompts/prototype/` and `prompts/research/`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import httpx

from server_modules import config, journeys as journey_module
from server_modules import llm, prompts, research

Say = Callable[[str], None]

_MARKER = re.compile(r"^=====\s*(assets/app\.css|assets/app\.js|shell\.html)\s*=====\s*$", re.MULTILINE)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n|\n```\s*$")
_PEXELS = re.compile(r"https?://(?:www\.)?pexels\.com/photo/[a-z0-9-]+-(\d+)/?$")


# --- the wireframe, as structure only ---------------------------------------------------------------------------------

def structure(html: str, limit: int = 14000) -> str:
    """A wireframe's markup without its look: no styles, scripts, drawings, comments, classes or inline styles."""
    text = re.sub(r"<!--.*?-->", "", html or "", flags=re.S)
    text = re.sub(r"<(style|script|svg|noscript|head)\b.*?</\1>", "", text, flags=re.S | re.I)
    text = re.sub(r"\s(?:class|style|id)=\"[^\"]*\"", "", text)
    text = re.sub(r"\s(?:class|style|id)='[^']*'", "", text)
    text = re.sub(r">\s+<", "><", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


# --- pages, roles, sign-in -------------------------------------------------------------------------------------------

def pages_of(doc: dict) -> list[dict]:
    return [p for p in (doc.get("public_pages") or []) + (doc.get("protected_pages") or []) if isinstance(p, dict) and p.get("route")]


def sign_in_route(doc: dict) -> str:
    """The sign-in page's route, or "" when the product has no sign-in."""
    pages = pages_of(doc)
    auth = doc.get("authentication_requirement") or {}
    if not (auth.get("login_required") or any(p.get("login_required") for p in pages)):
        return ""
    known = {str(p["route"]) for p in pages}
    if str(auth.get("sign_in_route") or "") in known:
        return str(auth["sign_in_route"])
    return next((r for r in sorted(known) if re.search(r"log-?in|sign-?in", r, re.IGNORECASE)), "")


def _names(role: dict) -> set[str]:
    return {str(role.get(k) or "").strip().lower() for k in ("role_key", "role_name", "name", "role") if str(role.get(k) or "").strip()}


def roles_of(doc: dict) -> list[dict]:
    """The roles that sign in: every specified role except a visitor who never does."""
    return [r for r in (doc.get("roles") or []) if isinstance(r, dict) and _names(r)
            and not (_names(r) & {"visitor", "guest", "anonymous", "public", "anyone", "everyone"})]


def can_open(doc: dict, role: dict) -> tuple[list[dict], list[dict]]:
    """The pages a role may open and the ones it may not, from the access matrix when there is one, else from the pages' roles."""
    names = _names(role)
    row = next((r for r in (doc.get("role_access_matrix") or []) if isinstance(r, dict) and str(r.get("role") or "").strip().lower() in names), None)
    allowed_names = {str(p).strip().lower() for p in (row or {}).get("allowed_pages") or []}
    yes, no = [], []
    for page in pages_of(doc):
        label = str(page.get("page_name") or page["route"])
        roles = {str(r).strip().lower() for r in page.get("allowed_roles") or []}
        if not page.get("login_required") or (row and label.strip().lower() in allowed_names) or (not row and (names & roles or roles & {"anyone", "all", "everyone"})):
            yes.append({"route": str(page["route"]), "name": label})
        else:
            no.append({"route": str(page["route"]), "name": label})
    return yes, no


# --- the flow ----------------------------------------------------------------------------------------------------------

def route_map(routes_out: list[dict]) -> list[dict]:
    return [{"route": r["route"], "file": r["file"], "name": r["name"], "roles": r.get("roles") or []} for r in routes_out]


def flow_of(doc: dict, routes_out: list[dict]) -> dict[str, Any]:
    """The journeys as paths through the pages, and for every page the pages it leads to."""
    by_route = {str(r["route"]): r for r in routes_out}
    leads: dict[str, list[dict]] = {route: [] for route in by_route}
    journeys = []
    for journey in journey_module.user_journeys_for(doc):
        steps = [s for s in journey["steps"] if s["route"] in by_route]
        journeys.append({"name": journey["workflow_name"], "who": journey["who"] or "",
                         "steps": [{"step": s["step"], "route": s["route"], "file": by_route[s["route"]]["file"]} for s in steps]})
        for here, there in zip(steps, steps[1:]):
            if here["route"] != there["route"] and there["route"] not in {x["route"] for x in leads[here["route"]]}:
                leads[here["route"]].append({"route": there["route"], "file": by_route[there["route"]]["file"], "name": by_route[there["route"]]["name"],
                                             "journey": journey["workflow_name"], "after": here["step"][:140]})
    return {"journeys": journeys, "leads_to": leads}


def page_flow(flow: dict, route: str) -> dict[str, Any]:
    return {"leads_to": flow["leads_to"].get(route, []),
            "journeys": [j["name"] for j in flow["journeys"] if any(s["route"] == route for s in j["steps"])]}


def _journey_text(flow: dict) -> str:
    return "\n".join(f"- {j['name']}" + (f" ({j['who']})" if j["who"] else "") + ": " + " → ".join(f"{s['step']} [{s['route']}]" for s in j["steps"])
                     for j in flow["journeys"]) or "(the specification lists no journeys)"


def _routes_text(routes_out: list[dict]) -> str:
    return "\n".join(f"- {r['route']} — {r['file']} — {r['name']}" + (f" — roles: {', '.join(map(str, r.get('roles') or []))}" if r.get("roles") else "")
                     for r in routes_out)


# --- demo accounts -----------------------------------------------------------------------------------------------------

def draw_accounts(doc: dict, routes_out: list[dict], flow: dict, system: str) -> list[dict]:
    """Create one stable fictitious account per signing-in role without an LLM round trip."""
    sign_in, roles = sign_in_route(doc), roles_of(doc)
    if not sign_in or not roles:
        return []
    out = []
    for index, role in enumerate(roles, start=1):
        label = str(role.get("role_name") or role.get("role_key") or f"User {index}").strip()
        key = str(role.get("role_key") or label).strip()
        slug = re.sub(r"[^a-z0-9]+", ".", key.lower()).strip(".") or f"user{index}"
        yes, no = can_open(doc, role)
        destinations = [str(page["route"]) for page in yes if str(page.get("route")) != sign_in]
        lands_on = destinations[0] if destinations else sign_in
        out.append({
            "role": label,
            "role_key": key,
            "display_name": f"Demo {label}",
            "email": f"{slug}@example.com",
            "password": "Demo!2026",
            "lands_on": lands_on,
            "can_open": yes,
            "cannot_open": no,
        })
    return out


def accounts_message(accounts: list[dict], routes_out: list[dict], sign_in: str) -> str:
    """What the customer is told when the prototype is finished: how to enter as each role, and what each role can open."""
    if not accounts:
        return ""
    page = next((r for r in routes_out if r["route"] == sign_in), {})
    names = {r["route"]: r["name"] for r in routes_out}
    lines = [f"**Demo accounts** — fictitious, made for reviewing the prototype. Sign in on **{page.get('name') or sign_in}** (`{sign_in}`): "
             f"use the Demo accounts panel, or type these.", ""]
    for a in accounts:
        opens = ", ".join(p["name"] for p in a["can_open"] if p["route"] != sign_in) or "—"
        blocked = ", ".join(p["name"] for p in a["cannot_open"]) or "nothing"
        lines += [f"- **{a['role']}** — `{a['email']}` / `{a['password']}`",
                  f"  lands on **{names.get(a['lands_on'], a['lands_on'])}**; can open: {opens}; cannot open: {blocked}"]
    return "\n".join(lines)


def flow_script(routes_out: list[dict], flow: dict, accounts: list[dict], sign_in: str) -> str:
    """`assets/flow.js`: the route map, the journeys and the demo accounts, as data the kit's script reads."""
    data = {"routes": route_map(routes_out),
            "signIn": next(({"route": r["route"], "file": r["file"]} for r in routes_out if r["route"] == sign_in), None),
            "accounts": [{"role": a["role"], "roleKey": a["role_key"], "name": a["display_name"], "email": a["email"], "password": a["password"],
                          "landsOn": a["lands_on"], "canOpen": [p["route"] for p in a["can_open"]]} for a in accounts],
            "journeys": flow["journeys"]}
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    # The prototype is opened from disk as well as through the Studio server.
    # Resolve every app route to a sibling HTML file; never let a model-created
    # `/rooms`, `fileC:/rooms` or Windows absolute path escape the prototype.
    navigation = r'''
(function () {
  var P = window.PROTOTYPE || {};
  function entry(path) {
    var rows = Array.isArray(P.routes) ? P.routes : [];
    var exact = rows.filter(function (r) { return r && r.route === path; })[0];
    if (exact) return exact;
    var wanted = String(path || '').split('/').filter(Boolean);
    return rows.filter(function (r) {
      var parts = String(r.route || '').split('/').filter(Boolean);
      return parts.length === wanted.length && parts.every(function (part, i) {
        return /^\\[.*\\]$/.test(part) || part === wanted[i];
      });
    })[0] || null;
  }
  function clean(value) {
    var v = String(value || '').trim();
    if (!v || /^(#|mailto:|tel:|https?:|javascript:|data:)/i.test(v)) return v;
    v = v.replace(/^filec?:[\\/]+/i, '/');
    try { if (/^file:/i.test(v)) v = new URL(v).pathname; } catch (ignore) {}
    var marker = v.toLowerCase().indexOf('/.agentforge/prototype/');
    if (marker >= 0) v = v.slice(marker + '/.agentforge/prototype/'.length);
    var found = entry(v);
    return found && found.file ? found.file : v;
  }
  function normalise(root) {
    (root || document).querySelectorAll('a[href], area[href], [data-go]').forEach(function (el) {
      var route = el.getAttribute('data-go');
      var value = route || el.getAttribute('href');
      if (!value || /^(#|mailto:|tel:|https?:|javascript:|data:)/i.test(value)) return;
      var href = clean(value);
      if (href) el.setAttribute('href', href);
    });
  }
  function go(route) {
    var href = clean(route);
    if (href) window.location.href = href;
  }
  document.addEventListener('DOMContentLoaded', function () { normalise(document); });
  document.addEventListener('click', function (event) {
    var el = event.target.closest && event.target.closest('[data-go]');
    if (!el) return;
    var route = el.getAttribute('data-go');
    if (route && route !== '#') { event.preventDefault(); event.stopImmediatePropagation(); go(route); }
  }, true);
})();
'''
    return "window.PROTOTYPE = Object.assign(window.PROTOTYPE || {}, " + payload + ");\n" + navigation


# --- photographs -------------------------------------------------------------------------------------------------------

def _subjects(data: Any) -> list[dict]:
    rows = data.get("subjects") if isinstance(data, dict) else data
    return [{"subject": " ".join(str(r.get("subject") or "").split()), "used_on": str(r.get("used_on") or "")}
            for r in rows or [] if isinstance(r, dict) and str(r.get("subject") or "").strip()][:6]


def _alive(url: str) -> bool:
    try:
        reply = httpx.get(url, timeout=15, headers={"Range": "bytes=0-1024"}, follow_redirects=True)
        return reply.status_code in (200, 206) and reply.headers.get("content-type", "").startswith("image/")
    except Exception:  # noqa: BLE001
        return False


def gather_images(product: str, pages: str, system: str, say: Say) -> list[dict]:
    """Real sample photographs: the model names the subjects, web search finds photo pages, the direct image is built and checked alive."""
    try:
        subjects = llm.complete_json(system=system, label="prototype_images", validator=_subjects,
                                     user=prompts.load("prototype/images", product=product, pages=pages))
    except Exception as exc:  # noqa: BLE001
        say(f"Could not plan the sample photographs ({str(exc)[:120]}); drawing without them.")
        return []
    found: list[dict] = []
    for item in subjects:
        say(f'Searched the web for photos of "{item["subject"]}"')
        for row in llm.web_search(f'{item["subject"]} free stock photo pexels', 8):
            match = _PEXELS.match(row["url"])
            if not match:
                continue
            url = f"https://images.pexels.com/photos/{match.group(1)}/pexels-photo-{match.group(1)}.jpeg?auto=compress&cs=tinysrgb&w=1200"
            if _alive(url):
                alt = re.sub(r"\s*[·|-]\s*Free Stock Photo.*$", "", row["title"], flags=re.IGNORECASE).strip()
                found.append({"subject": item["subject"], "used_on": item["used_on"], "url": url, "alt": alt or item["subject"]})
                break
    return found


# --- the kit -----------------------------------------------------------------------------------------------------------

def parse_kit(text: str) -> dict[str, str]:
    parts = _MARKER.split(text or "")
    blocks: dict[str, str] = {}
    for index in range(1, len(parts) - 1, 2):
        blocks[parts[index]] = _FENCE.sub("", parts[index + 1].strip()).strip()
    return blocks


def kit_problems(blocks: dict[str, str], tokens: dict) -> list[str]:
    problems = []
    for name in ("assets/app.css", "assets/app.js", "shell.html"):
        if not blocks.get(name):
            problems.append(f"the block `{name}` is missing")
    css, js, shell = blocks.get("assets/app.css", ""), blocks.get("assets/app.js", ""), blocks.get("shell.html", "")
    palette = (tokens or {}).get("light") or (tokens or {}).get("dark") or {}
    if css and len(css) < 3000:
        problems.append("the stylesheet is far too short for a complete design system")
    missing = [n for n in list(palette)[:6] if f"--{n}" not in css]
    if css and missing:
        problems.append(f"the stylesheet does not define the design's tokens as custom properties ({', '.join('--' + n for n in missing)})")
    if js and "PROTOTYPE" not in js:
        problems.append("the script does not use window.PROTOTYPE")
    if shell and ("page content" not in shell or "data-go" not in shell):
        problems.append("the shell must hold the `<!-- page content -->` marker and navigation written with data-go")
    return problems


def draw_kit(spec: dict, customization: dict, routes_out: list[dict], flow: dict, sign_in: str, accounts: list[dict], ideas: str,
             say: Say, project: str, workspace: Path, premium_skill_path: str, attempts: int = 1) -> dict[str, str]:
    """The stylesheet, the script and the shell every page shares, drawn once."""
    design_md_workspace_path = str(customization.get("design_md_workspace_path") or "")
    sign_in_text = (f"The sign-in page is `{sign_in}`. Demo accounts (role, name, email, password, lands on): "
                    + "; ".join(f"{a['role']}, {a['display_name']}, {a['email']}, {a['password']}, {a['lands_on']}" for a in accounts)) if sign_in else "The product has no sign-in."
    user = prompts.load("prototype/kit", design_spec_path=f"{config.RECORD_DIR}/design/design-spec.json",
                        design_md=(f"Read `{design_md_workspace_path}` yourself — the selected theme's own guidance "
                                   f"({customization.get('design_md_path')})." if design_md_workspace_path else ""),
                        customizer=(f"### Customer's design direction\n\n{customization['customizer_prompt']}" if customization.get("customizer_prompt") else ""),
                        routes=_routes_text(routes_out), sign_in=sign_in_text, journeys=_journey_text(flow),
                        ideas=ideas or "(none gathered — rely on the design contract and your own judgement)",
                        premium_frontend_skill_path=premium_skill_path)
    if customization.get("uploaded_site_images"):
        user += ("\n\n## User-uploaded site images\n"
                 "Prefer these for their named uses, including the shared logo or favicon. "
                 "Use each prototype_url as a relative asset URL.\n"
                 + json.dumps(customization["uploaded_site_images"], ensure_ascii=False, indent=2))
    system, previous, problems = prompts.load("prototype/kit-system"), "", []
    for attempt in range(max(1, attempts)):
        request = user if not problems else (
            user + "\n\n## Your last attempt\n\n" + (previous[:1500] or "(empty — you returned nothing at all)")
            + "\n\nIt was rejected: " + "; ".join(problems) + ". Do not call read_file, list_files or "
              "search_text again — you already read what you need. Return all three blocks now, complete.")
        # This call writes a concrete artifact. Hidden chain-of-thought adds a
        # long wait before the first visible file without improving the CSS/JS
        # contract enforced below.
        previous = llm.complete(system=system, user=request, think=False,
                                project=project, workspace=workspace)
        blocks = parse_kit(previous)
        problems = kit_problems(blocks, spec.get("tokens") or {})
        if not problems:
            return blocks
        say(f"The shared design system was not usable ({'; '.join(problems)[:200]}); drawing it again.")
    raise ValueError("could not draw the prototype's shared design system: " + "; ".join(problems))


_ID = re.compile(r"\b(?:FR|NFR|AC|TC|US|REQ)-\d+\b")


def kit_api(js: str) -> list[str]:
    """The names the kit's script defines on `PROTOTYPE`, read from the script itself."""
    aliases = {"PROTOTYPE"} | set(re.findall(r"\b(\w+)\s*=\s*(?:window\.)?PROTOTYPE\b", js))
    names: set[str] = set()
    for alias in aliases:
        names |= set(re.findall(rf"\b{re.escape(alias)}\.(\w+)\s*=", js))
    return sorted(names | {"routes", "accounts", "signIn", "journeys"})


def kit_reference(kit: dict[str, str]) -> dict[str, Any]:
    """What a page must know about the kit to use it as it is: its stylesheet (minus comments) and the script's API."""
    return {"stylesheet": re.sub(r"/\*.*?\*/", "", kit["assets/app.css"], flags=re.S).strip(), "script_api": kit_api(kit["assets/app.js"])}


def page_problems(html: str, kit: dict[str, str], routes: set[str], accounts: list[dict] | None = None) -> list[str]:
    """What is wrong with a page that a reader would only find by clicking: a kit function that is not there, a class the kit does not
    define (so the element renders unstyled), a route that is not a page, a demo account that does not exist (pass `accounts` for the
    sign-in page), and specification talk printed on the page."""
    problems = []
    defined = set(kit_api(kit["assets/app.js"]))
    missing = sorted({n for n in re.findall(r"PROTOTYPE\.(\w+)", html)} - defined)
    if missing:
        problems.append("the page calls " + ", ".join(f"PROTOTYPE.{n}" for n in missing) + ", which the kit does not define; the kit defines only: " + ", ".join(sorted(defined)))
    page_style = "".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S | re.I))
    known = set(re.findall(r"\.([A-Za-z_][\w-]*)", kit["assets/app.css"] + page_style))
    used: set[str] = set()
    for match in re.finditer(r'\sclass\s*=\s*"([^"]*)"', html):
        used |= set(match.group(1).split())
    unknown = sorted(c for c in used if c not in known and not c.startswith(("is-", "has-", "js-")))
    if len(unknown) >= 4:
        problems.append("these classes are defined neither by the kit nor by the page's own style, so the elements render unstyled: " + ", ".join(unknown[:12])
                        + " — use the kit's own class names")
    for go in sorted(set(re.findall(r'data-go\s*=\s*"([^"]*)"', html))):
        if (go.rstrip("/") or "/") not in routes:
            problems.append(f'data-go="{go}" is not a route of the prototype')
    own_scripts = "\n".join(re.findall(r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", html, flags=re.S | re.I))
    if re.search(r"\b(?:sessionStorage|localStorage)\b", own_scripts):
        problems.append("the page reads browser storage itself. The session, the signed-in user and who may open the page are the kit's job: it guards the "
                        "page, fills `data-user` fields and shows `data-roles` items. Remove the page's own session and access logic")
    visible = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", html, flags=re.S | re.I)
    ids = sorted(set(_ID.findall(visible)))
    if ids:
        problems.append("the page prints requirement ids (" + ", ".join(ids) + "): every word on a page belongs to the product, never to the specification")
    printed = sorted(r for r in routes if r != "/" and re.search(rf"(?<![\w./-]){re.escape(r)}(?![\w-])", visible))
    if printed:
        problems.append("the page prints route paths (" + ", ".join(printed) + "): a person never sees a route, so name the page instead")
    if accounts is not None:
        real = {str(a["email"]).lower() for a in accounts}
        invented = sorted({e.lower() for e in re.findall(r"[\w.+-]+@example\.com", html, flags=re.IGNORECASE)} - real)
        if invented:
            problems.append("the page shows demo accounts that do not exist (" + ", ".join(invented) + "); the only demo accounts are "
                            + ", ".join(sorted(real)) + ", one per role, and it shows exactly those")
    return problems


def ensure_assets(html: str) -> str:
    """A page always carries the kit, even if the model left a tag out."""
    if "assets/app.css" not in html:
        html = re.sub(r"</head>", '<link rel="stylesheet" href="assets/app.css">\n</head>', html, count=1, flags=re.IGNORECASE) if re.search(r"</head>", html, re.I) \
            else '<link rel="stylesheet" href="assets/app.css">\n' + html
    tail = "".join(f'<script src="assets/{name}.js"></script>\n' for name in ("flow", "app") if f"assets/{name}.js" not in html)
    if tail:
        html = re.sub(r"</body>", tail + "</body>", html, count=1, flags=re.IGNORECASE) if re.search(r"</body>", html, re.I) else html + "\n" + tail
    return html


# --- everything, once, before any page ------------------------------------------------------------------------------------

def prepare(doc: dict, spec: dict, customization: dict, routes_out: list[dict], structures: dict[str, str], say: Say,
           project: str, workspace: Path, premium_skill_path: str) -> dict[str, Any]:
    """Build the shared flow and kit directly from the approved artifacts.

    The wireframes already contain the chosen structure and image references.
    A second research and image-verification pass only delays the prototype and
    can make it drift from what the customer approved.
    """
    system = prompts.load("srs/system")
    ideas = ""
    flow = flow_of(doc, routes_out)
    sign_in = sign_in_route(doc)
    accounts = draw_accounts(doc, routes_out, flow, system)
    images: list[dict] = []
    kit = draw_kit(spec, customization, routes_out, flow, sign_in, accounts, ideas, say,
                   project=project, workspace=workspace, premium_skill_path=premium_skill_path,
                   attempts=3)
    return {"ideas": ideas, "flow": flow, "sign_in": sign_in, "accounts": accounts, "images": images, "kit": kit,
            "flow_js": flow_script(routes_out, flow, accounts, sign_in)}
