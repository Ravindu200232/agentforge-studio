"""What the prototype agent is given besides its own record, and the parts of the prototype that are code rather than drawing.

The agent reads three things and nothing else: the approved wireframes, the handoff's `app.md` and what Design Customize produced. It
plans silently and writes the prototype itself, the same way the builder works. What is the same for every prototype is prepared here:

* the wireframe's *structure* without its look (its styles, classes and scripts are dropped, so nothing low-fidelity is left to copy);
* the flow: the journeys as "this page leads to that page", written into `assets/flow.js` so links cannot go to a page that is not there;
* one demo account per role, defined once, used by the sign-in page's one-click demo login (in `assets/flow.js`) and by the message to
  the customer.

What the model is asked is in `prompts/prototype/generate.md`.
"""
from __future__ import annotations

import json
import re
from typing import Any

from server_modules import journeys as journey_module


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


def _norm(value: Any) -> str:
    """A role or page name compared loosely: `store_owner`, `Store Owner` and `store-owner` are one name."""
    return re.sub(r"[\s_-]+", " ", str(value or "")).strip().lower()


def _items(value: Any) -> list[str]:
    """Names given as a list, or as one string separated by commas, semicolons or bars."""
    items = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;|\n]+", str(value or ""))
    return [str(item).strip() for item in items if str(item).strip()]


def can_open(doc: dict, role: dict) -> tuple[list[dict], list[dict]]:
    """The pages a role may open and the ones it may not.

    A page is open to a role when it needs no sign-in, when the page's own roles name it, or when the access matrix lists the page
    for it by name or by route. Either source is enough: an access matrix that names pages differently from the page list must not
    take a role's own pages away from it.
    """
    names = {_norm(name) for name in _names(role)}
    row = next((r for r in (doc.get("role_access_matrix") or []) if isinstance(r, dict) and _norm(r.get("role")) in names), None)
    listed = _items((row or {}).get("allowed_pages"))
    listed_routes = {route.rstrip("/") or "/" for item in listed for route in re.findall(r"(?<![\w])/[\w\-\[\]/.]*", item)}
    listed_names = {_norm(item) for item in listed}
    yes, no = [], []
    for page in pages_of(doc):
        label = str(page.get("page_name") or page["route"])
        route = str(page["route"])
        roles = {_norm(r) for r in _items(page.get("allowed_roles"))}
        if (not page.get("login_required") or names & roles or roles & {"anyone", "all", "everyone"}
                or (route.rstrip("/") or "/") in listed_routes or _norm(label) in listed_names):
            yes.append({"route": route, "name": label})
        else:
            no.append({"route": route, "name": label})
    return yes, no


# --- the flow ----------------------------------------------------------------------------------------------------------

_PUBLIC_ROLES = {"visitor", "guest", "anonymous", "public", "anyone", "everyone", "all"}


def signed_in_page(page: dict) -> bool:
    """Whether a page is for signed-in people: its record says so, or, with no flag, only signing-in roles open it."""
    if "login_required" in page:
        return bool(page.get("login_required"))
    roles = {_norm(role) for role in _items(page.get("allowed_roles"))}
    return bool(roles) and not roles & _PUBLIC_ROLES


def route_map(routes_out: list[dict]) -> list[dict]:
    return [{"route": r["route"], "file": r["file"], "name": r["name"], "roles": r.get("roles") or [],
             "signedIn": bool(r.get("signed_in"))} for r in routes_out]


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


def journey_text(flow: dict) -> str:
    return "\n".join(f"- {j['name']}" + (f" ({j['who']})" if j["who"] else "") + ": " + " → ".join(f"{s['step']} [{s['route']}]" for s in j["steps"])
                     for j in flow["journeys"]) or "(the specification lists no journeys)"


def routes_text(routes_out: list[dict], wireframes: dict[str, str] | None = None) -> str:
    """The route table the agent writes against: one page file per route, and the wireframe it is drawn from."""
    wireframes = wireframes or {}
    rows = ["| Route | Write to | Page | Roles | Wireframe |", "|---|---|---|---|---|"]
    for r in routes_out:
        rows.append(f"| `{r['route']}` | `.agentforge/prototype/{r['file']}` | {r['name']} | "
                    f"{', '.join(map(str, r.get('roles') or [])) or 'anyone'} | "
                    + (f"`{wireframes[r['route']]}`" if wireframes.get(r["route"]) else "none — draw it from app.md") + " |")
    return "\n".join(rows)


def sign_up_of(doc: dict, routes_out: list[dict], accounts: list[dict]) -> dict | None:
    """The sign-up page and the demo account a new sign-up becomes, when people may create their own account."""
    auth = doc.get("authentication_requirement") or {}
    if not isinstance(auth, dict) or not accounts:
        return None
    mode = str(auth.get("registration_mode") or "").strip().lower()
    if not (auth.get("self_registration") or mode == "open"):
        return None
    pages = {str(r["route"]): r for r in routes_out}
    route = str(auth.get("sign_up_route") or "").strip()
    if route not in pages:
        route = next((r for r in pages if re.search(r"sign-?up|register|create-?account", r, re.IGNORECASE)), "")
    if not route:
        return None
    wanted = [_norm(auth.get("registration_role"))] + [_norm(name) for name in _items(auth.get("registration_roles"))]
    account = next((a for name in wanted if name for a in accounts if name in {_norm(a["role"]), _norm(a["role_key"])}),
                   accounts[0])
    return {"route": route, "file": pages[route]["file"], "name": pages[route]["name"],
            "role": account["role"], "role_key": account["role_key"]}


def sign_in_text(accounts: list[dict], sign_in: str, routes_out: list[dict], sign_up: dict | None = None) -> str:
    """What the agent is told about signing in: one-click role-based demo login, already provided by `assets/flow.js`."""
    if not sign_in or not accounts:
        return "This product has no sign-in. Draw no sign-in form and no account menu."
    page = next((r for r in routes_out if r["route"] == sign_in), {"file": sign_in, "name": sign_in})
    lines = [f"The sign-in page is **{page['name']}** (`.agentforge/prototype/{page['file']}`). Signing in is a role-based demo "
             "login, and `assets/flow.js` already does all of it:", "",
             "- On the sign-in page draw a polished form marked `<form data-sign-in>` with an email field (`type=\"email\"`) and a "
             "password field (`type=\"password\"`), and directly under it an empty `<div data-demo-login></div>`. flow.js fills that "
             "block with one \"continue as\" button per role, signs in with one click and opens that role's own first page; typing a "
             "demo email and password works too. Do not write the accounts into the page and do not write your own sign-in script.",
             "- Every other form that signs someone in — a separate sign-in for staff or administrators, a sign-in step inside "
             "checkout — is built the same way: `<form data-sign-in>` with the empty `<div data-demo-login></div>` under it.",
             "- Never decide where signing in goes: no `data-next`, redirect, link or `data-go` on a sign-in form or its button, and "
             "no submit handler for it in app.js. Each role has its own first page below, and flow.js sends it there.",
             "- Wherever the signed-in person shows, write `<span data-user=\"name\"></span>` (or `\"email\"`, `\"role\"`).",
             "- Every Sign out — in the account menu, in the phone menu, the confirm button of a sign-out dialog — is a "
             "`<button type=\"button\" data-sign-out>`: flow.js ends the demo session and opens the sign-in page. Never a plain "
             "link to the sign-in page, no `data-roles` on it (everyone who is signed in can sign out) and no sign-out code in "
             "app.js.",
             "- The account menu and every dropdown open inside the screen at every width: aligned to their button's edge, "
             "never wider than the screen; on a phone the account menu and Sign out sit inside the menu.",
             "- app.js never keeps a signed-in state or a user of its own: it asks `window.PROTOTYPE.user()`.",
             "- Two navigation states. Anything only a signed-in person sees — the signed-in navigation, the account menu, \"Go to my "
             "dashboard\" — carries `data-auth=\"in\"`; anything only a signed-out person sees — Sign in, Sign up, \"Create account\" — "
             "carries `data-auth=\"out\"`. A public page carries both headers, the public one marked `data-auth=\"out\"` and the "
             "signed-in one `data-auth=\"in\"`; a signed-in page carries only its role's navigation. flow.js shows the right one.",
             "- An element only some roles use carries `data-roles=\"role_key\"` (comma-separated for several); when someone is "
             "signed in, flow.js hides it from the other roles.",
             "- Each role's first page below is that role's own dashboard: draw it as its real home — a greeting with the person's "
             "name, that role's own figures, what is waiting on them and shortcuts to its main tasks — with that role's sample data.",
             "- The sign-in form shows its error in an element marked `data-sign-in-error` with the `hidden` attribute; flow.js "
             "reveals it after a wrong attempt.",
             "- `window.PROTOTYPE.user()`, `.login(email, password)`, `.loginAs(role)`, `.logout()` and `.canOpen(route)` are "
             "there if app.js needs them.", "", "The demo accounts:", ""]
    lines += [f"- **{a['role']}** (`{a['role_key']}`) — {a['email']} / {a['password']} — opens "
              f"`{next((r['file'] for r in routes_out if r['route'] == a['lands_on']), a['lands_on'])}` first" for a in accounts]
    if sign_up:
        lines += ["", f"Signing up: the sign-up page is **{sign_up['name']}** (`.agentforge/prototype/{sign_up['file']}`), and a "
                  f"new account is a **{sign_up['role']}**. `assets/flow.js` does the signing up too:", "",
                  "- Its form is `<form data-sign-up>` with the fields its wireframe has (the name, the email, the password and "
                  "the rest). Once the form is valid, flow.js creates the demo account from the typed name and email, signs it "
                  f"in as {sign_up['role']} and opens that role's first page.",
                  "- So no success panel, no \"check your email\" step, no `data-next`, `data-success`, redirect, link or "
                  "`data-go` on the form or its button, and no submit handler for it in app.js. Inline validation messages "
                  "under the fields are yours, as on every form."]
    return "\n".join(lines)


# --- demo accounts -----------------------------------------------------------------------------------------------------

def draw_accounts(doc: dict, routes_out: list[dict], flow: dict, system: str) -> list[dict]:
    """Create one stable fictitious account per signing-in role without an LLM round trip."""
    sign_in, roles = sign_in_route(doc), roles_of(doc)
    if not sign_in or not roles:
        return []
    protected = {str(page["route"]): page for page in pages_of(doc)}
    out = []
    for index, role in enumerate(roles, start=1):
        label = str(role.get("role_name") or role.get("role_key") or f"User {index}").strip()
        key = str(role.get("role_key") or label).strip()
        slug = re.sub(r"[^a-z0-9]+", ".", key.lower()).strip(".") or f"user{index}"
        yes, no = can_open(doc, role)
        destinations = [str(page["route"]) for page in yes if str(page.get("route")) != sign_in]
        # A role signs in to the top of its own area — the dashboard or account page it came for — not to the public home page:
        # of the signed-in pages it may open, the one with the shortest fixed route.
        own = [route for route in destinations if (protected.get(route) or {}).get("login_required")]
        lands_on = (min(own, key=lambda route: ("[" in route, len([part for part in route.split("/") if part])))
                    if own else (destinations or [sign_in])[0])
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


def flow_script(routes_out: list[dict], flow: dict, accounts: list[dict], sign_in: str, sign_up: dict | None = None) -> str:
    """`assets/flow.js`: the route map, the journeys and the demo accounts, as data the kit's script reads."""
    data = {"routes": route_map(routes_out),
            "signIn": next(({"route": r["route"], "file": r["file"]} for r in routes_out if r["route"] == sign_in), None),
            "signUp": ({"route": sign_up["route"], "file": sign_up["file"], "roleKey": sign_up["role_key"]}
                       if sign_up and accounts else None),
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
    // Signing out or in is the demo session's to do (below): it ends or starts the session, then goes on itself.
    if (el.closest('[data-sign-out], [data-login-as]') || /^(sign|log)\s*-?\s*out$/i.test(String(el.textContent || '').trim())) return;
    var route = el.getAttribute('data-go');
    if (route && route !== '#') { event.preventDefault(); event.stopImmediatePropagation(); go(route); }
  }, true);
})();
'''
    return "window.PROTOTYPE = Object.assign(window.PROTOTYPE || {}, " + payload + ");\n" + navigation + DEMO_SESSION


# The demo sign-in is the same on every prototype, so it is code rather than something each model run re-invents: one click per
# role on the sign-in page, the typed demo email and password also work, signing up as the role sign-ups get, sign-out, the
# signed-in user's fields and role-only items.
DEMO_SESSION = r'''
(function () {
  var P = window.PROTOTYPE = window.PROTOTYPE || {};
  var KEY = 'agentforge.prototype.user';
  var PROFILE = KEY + '.profile';
  // A sign-out control, by its words, for a page that left out `data-sign-out`.
  var SIGN_OUT = /^(sign|log)\s*-?\s*out$/i;
  function accounts() { return Array.isArray(P.accounts) ? P.accounts : []; }
  function fileFor(route) {
    var row = (P.routes || []).filter(function (r) { return r && r.route === route; })[0];
    return row && row.file ? row.file : 'index.html';
  }
  function read() {
    try { var saved = window.localStorage.getItem(KEY); if (saved) return saved; } catch (ignore) {}
    return String(window.name || '').indexOf(KEY + '=') === 0 ? window.name.slice(KEY.length + 1) : '';
  }
  function write(email) {
    try { if (email) window.localStorage.setItem(KEY, email); else window.localStorage.removeItem(KEY); } catch (ignore) {}
    window.name = email ? KEY + '=' + email : '';
  }
  // The name and email someone typed when signing up, shown instead of the demo account's own.
  function profile() {
    try { return JSON.parse(window.localStorage.getItem(PROFILE) || 'null') || {}; } catch (ignore) { return {}; }
  }
  function keepProfile(value) {
    try { if (value) window.localStorage.setItem(PROFILE, JSON.stringify(value)); else window.localStorage.removeItem(PROFILE); } catch (ignore) {}
  }
  function find(value) {
    var key = String(value || '').trim().toLowerCase();
    return accounts().filter(function (a) {
      return [a.roleKey, a.role, a.email].some(function (v) { return String(v || '').toLowerCase() === key; });
    })[0] || null;
  }
  P.user = function () {
    var account = find(read());
    if (!account) return null;
    var own = profile();
    return Object.assign({}, account, own.name ? { name: own.name } : {}, own.email ? { email: own.email } : {});
  };
  P.loginAs = function (roleOrEmail) {
    var account = find(roleOrEmail);
    if (!account) return null;
    keepProfile(null);
    write(account.email);
    window.location.href = fileFor(account.landsOn);
    return account;
  };
  P.login = function (email, password) {
    var account = find(email);
    return account && account.password === String(password || '') ? P.loginAs(account.email) : null;
  };
  // A new account: the role sign-ups get, under the name and email that were typed, opening that role's first page.
  P.register = function (name, email) {
    var account = find((P.signUp || {}).roleKey) || accounts()[0];
    if (!account) return null;
    write(account.email);
    keepProfile({ name: String(name || '').trim(), email: String(email || '').trim() });
    window.location.href = fileFor(account.landsOn);
    return account;
  };
  P.logout = function () {
    write('');
    keepProfile(null);
    window.location.href = P.signIn && P.signIn.file ? P.signIn.file : 'index.html';
  };
  P.canOpen = function (route) {
    var user = P.user();
    return !user || (user.canOpen || []).indexOf(route) >= 0;
  };
  function here() { return decodeURIComponent(window.location.pathname.split('/').pop() || 'index.html'); }
  function onSignIn() { return !!(P.signIn && P.signIn.file === here()); }
  function onSignUp() { return !!(P.signUp && P.signUp.file === here()); }
  function signOutControl(target) {
    var marked = target.closest && target.closest('[data-sign-out]');
    if (marked) return marked;
    var el = target.closest && target.closest('a, button, [role="menuitem"]');
    // A Sign out that only opens a confirmation is not the sign-out itself: its dialog's button is.
    if (!el || el.hasAttribute('data-dialog-open') || el.hasAttribute('aria-haspopup') || el.hasAttribute('aria-controls')) return null;
    return SIGN_OUT.test(String(el.textContent || '').replace(/\s+/g, ' ').trim()) ? el : null;
  }
  function typedName(form) {
    function pick(selector) { var el = form.querySelector(selector); return el && el.value ? String(el.value).trim() : ''; }
    var full = pick('input[autocomplete="name"]') || pick('input[name="name" i], input[id="name" i]')
      || pick('input[name*="full" i], input[id*="full" i]');
    if (full) return full;
    return [pick('input[autocomplete="given-name"], input[name*="first" i], input[id*="first" i]'),
            pick('input[autocomplete="family-name"], input[name*="last" i], input[id*="last" i]')].filter(Boolean).join(' ');
  }
  function page() { return (P.routes || []).filter(function (r) { return r && r.file === here(); })[0] || null; }
  function demoLogin() {
    var list = accounts();
    if (!list.length) return;
    var slots = Array.prototype.slice.call(document.querySelectorAll('[data-demo-login]'));
    if (!slots.length && onSignIn()) {
      var slot = document.createElement('div');
      slot.setAttribute('data-demo-login', '');
      var form = document.querySelector('form');
      if (form && form.parentNode) form.parentNode.insertBefore(slot, form.nextSibling);
      else (document.querySelector('main') || document.body).appendChild(slot);
      slots = [slot];
    }
    slots.forEach(function (slot) {
      if (slot.querySelector('[data-login-as]')) return;
      slot.classList.add('demo-login');
      var title = document.createElement('p');
      title.className = 'demo-login__title';
      title.textContent = 'Demo login \u2014 continue as';
      slot.appendChild(title);
      list.forEach(function (a) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary demo-login__btn';
        button.setAttribute('data-login-as', a.roleKey || a.role);
        var role = document.createElement('strong');
        role.textContent = a.role;
        var email = document.createElement('span');
        email.textContent = a.email + ' \u00b7 ' + a.password;
        button.appendChild(role);
        button.appendChild(email);
        slot.appendChild(button);
      });
    });
  }
  function signedIn() {
    var user = P.user();
    var row = page();
    // No guards: a signed-in page opened while signed out still shows as its role sees it.
    var state = user || (row && row.signedIn) ? 'in' : 'out';
    if (!document.getElementById('agentforge-hidden')) {
      var style = document.createElement('style');
      style.id = 'agentforge-hidden';
      style.textContent = '[hidden]{display:none!important}';
      (document.head || document.documentElement).appendChild(style);
    }
    document.documentElement.setAttribute('data-signed-in', user ? (user.roleKey || user.role) : '');
    document.documentElement.setAttribute('data-session', state);
    document.querySelectorAll('[data-auth]').forEach(function (el) {
      var want = String(el.getAttribute('data-auth') || '').trim().toLowerCase();
      if (want === 'in' || want === 'out') el.hidden = want !== state;
    });
    document.querySelectorAll('[data-user]').forEach(function (el) {
      if (!user) return;
      var field = el.getAttribute('data-user') || 'name';
      var value = { name: user.name, email: user.email, role: user.role }[field];
      if (value) el.textContent = value;
    });
    document.querySelectorAll('[data-roles]').forEach(function (el) {
      if (!user) { if (state === 'out') el.hidden = true; return; }
      var roles = el.getAttribute('data-roles').toLowerCase().split(/[\s,]+/).filter(Boolean);
      var mine = [user.roleKey, user.role].map(function (v) { return String(v || '').toLowerCase(); });
      if (roles.length && !roles.some(function (r) { return mine.indexOf(r) >= 0; })) el.hidden = true;
    });
  }
  // flow.js loads at the end of the body: switch the page before it is painted, and again once it is complete.
  function ready() { demoLogin(); signedIn(); }
  ready();
  document.addEventListener('DOMContentLoaded', ready);
  document.addEventListener('click', function (event) {
    var as = event.target.closest && event.target.closest('[data-login-as]');
    if (as) { event.preventDefault(); event.stopImmediatePropagation(); P.loginAs(as.getAttribute('data-login-as')); return; }
    var out = signOutControl(event.target);
    if (out) { event.preventDefault(); event.stopImmediatePropagation(); P.logout(); }
  }, true);
  document.addEventListener('submit', function (event) {
    var form = event.target;
    var password = form.querySelector && form.querySelector('input[type="password"]');
    if (accounts().length && (form.hasAttribute('data-sign-up') || (onSignUp() && password && !form.hasAttribute('data-sign-in')))) {
      // What the form asks for is the page's own check: an incomplete form (no real email, a password shorter than the
      // sign-up rule's 8 characters) is left to the page to show its messages.
      var typed = form.querySelector('input[type="email"], input[name*="email" i], input[autocomplete="email"]');
      if (form.checkValidity && !form.checkValidity()) return;
      if ((typed && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(typed.value || '').trim()))
          || (password && String(password.value || '').length < 8)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      P.register(typedName(form), typed && typed.value);
      return;
    }
    if (!accounts().length || !(form.hasAttribute('data-sign-in') || (onSignIn() && password))) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    var email = form.querySelector('input[type="email"], input[name*="email" i], input[autocomplete="username"]');
    if (P.login(email && email.value, password && password.value)) return;
    var note = form.querySelector('[data-sign-in-error]');
    if (!note) {
      note = document.createElement('p');
      note.setAttribute('data-sign-in-error', '');
      note.setAttribute('role', 'alert');
      note.className = 'form-error';
      form.appendChild(note);
    }
    note.hidden = false;
    note.textContent = 'That email and password do not match a demo account. Use a Demo login button.';
  }, true);
})();
'''


def ensure_assets(html: str) -> str:
    """A page always carries the kit, even if the model left a tag out."""
    if "assets/app.css" not in html:
        html = re.sub(r"</head>", '<link rel="stylesheet" href="assets/app.css">\n</head>', html, count=1, flags=re.IGNORECASE) if re.search(r"</head>", html, re.I) \
            else '<link rel="stylesheet" href="assets/app.css">\n' + html
    tail = "".join(f'<script src="assets/{name}.js"></script>\n' for name in ("flow", "app") if f"assets/{name}.js" not in html)
    if tail:
        html = re.sub(r"</body>", tail + "</body>", html, count=1, flags=re.IGNORECASE) if re.search(r"</body>", html, re.I) else html + "\n" + tail
    return html
