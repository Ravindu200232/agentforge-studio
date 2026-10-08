"""The sign-in the prototype demonstrates: who the roles are, which pages each may open, and one fictitious account for each.

What is the same for every prototype is worked out here from the specification, without a model, so the accounts the prototype signs in
with (`src/demo.ts`, read by `src/lib/session.tsx`) are the same ones the finished application is seeded with (`demo-accounts.json`).
How the pages look is the agent's.
"""
from __future__ import annotations

import re
from typing import Any


# --- pages, roles, sign-in -------------------------------------------------------------------------------------------------

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


_PUBLIC_ROLES = {"visitor", "guest", "anonymous", "public", "anyone", "everyone", "all"}


def signed_in_page(page: dict) -> bool:
    """Whether a page is for signed-in people: its record says so, or, with no flag, only signing-in roles open it."""
    if "login_required" in page:
        return bool(page.get("login_required"))
    roles = {_norm(role) for role in _items(page.get("allowed_roles"))}
    return bool(roles) and not roles & _PUBLIC_ROLES


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
    return {"route": route, "name": pages[route]["name"], "role": account["role"], "role_key": account["role_key"]}


# --- demo accounts ---------------------------------------------------------------------------------------------------------

def draw_accounts(doc: dict) -> list[dict]:
    """One stable fictitious account for every role that signs in, without a model."""
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


def _some(pages: list[dict], skip: str = "", most: int = 6) -> str:
    """The first few page names of a list, and how many more there are: a list of seventy pages is not a message."""
    names = [p["name"] for p in pages if p["route"] != skip]
    if not names:
        return "nothing"
    return ", ".join(names[:most]) + (f" and {len(names) - most} more" if len(names) > most else "")


def accounts_message(accounts: list[dict], routes_out: list[dict], sign_in: str) -> str:
    """What the customer is told when the prototype is finished: how to enter as each role, and how much each role can open."""
    if not accounts:
        return ""
    page = next((r for r in routes_out if r["route"] == sign_in), {})
    names = {r["route"]: r["name"] for r in routes_out}
    lines = [f"**Demo accounts** — fictitious, made for reviewing the prototype. Sign in on **{page.get('name') or sign_in}** (`{sign_in}`): "
             f"use the demo buttons, or type these.", ""]
    for a in accounts:
        opens = [p for p in a["can_open"] if p["route"] != sign_in]
        lines += [f"- **{a['role']}** — `{a['email']}` / `{a['password']}` — lands on **{names.get(a['lands_on'], a['lands_on'])}**",
                  f"  can open {len(opens)} page{'s' if len(opens) != 1 else ''} ({_some(opens)}); "
                  f"cannot open {len(a['cannot_open'])}" + (f" ({_some(a['cannot_open'], most=4)})" if a["cannot_open"] else "")]
    return "\n".join(lines)
