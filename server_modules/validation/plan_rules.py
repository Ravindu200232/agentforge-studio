"""The approval plan's depth floor.

Ported from RP-SE-009 `srs-agent/srs_agent/app/agents/plan_rules.py`.

The check that matters is not "is there enough of it" in the abstract — a
calculator with six tables is worse than a calculator with one. It is: does every
thing the plan claims to have actually carry what makes it that thing. A screen
with no purpose, a record with no fields, a role with nothing it can do — each of
those is a hole that the specification, the build and the tests all fall through.
"""
from __future__ import annotations

import re
from typing import Any, Callable

PRIVILEGED = ("admin", "manager", "owner", "staff", "cashier", "operator", "moderator")
REGISTRATION_MODES = {"open", "admin_created", "invite", "request", "none"}
# A product with one screen and no stored records is a real product; it just is
# not the kind this depth floor is about.
THIN_ARCHETYPES = {"landing-single-page", "single-tool", "marketing"}

MIN_INTENT_CHARS = 120


def _named(rows: Any, key: str = "name") -> list[dict]:
    return [r for r in (rows or [])
            if isinstance(r, dict) and str(r.get(key) or "").strip()]


def _filled(values: Any) -> list[str]:
    return [str(v) for v in (values or []) if str(v).strip()]


def plan_validator(pack: dict[str, Any] | None = None) -> Callable[[dict], None]:
    """A depth floor, sized to the kind of app this is."""
    pack = pack or {}
    thin = str(pack.get("archetype") or "") in THIN_ARCHETYPES
    wants_auth = str(pack.get("auth_policy") or "") == "required"

    def validate(plan: dict) -> None:
        if not isinstance(plan, dict):
            raise ValueError("plan must be a JSON object")

        intent = str(plan.get("product_intent") or "").strip()
        if len(intent) < MIN_INTENT_CHARS:
            raise ValueError(
                "'product_intent' must be a full paragraph saying what this is "
                "and who it is for — one line is not enough for someone to approve")

        screens = _named(plan.get("screens"))
        if not screens:
            raise ValueError("provide at least one screen, each with a 'name' and a 'purpose'")

        blank = [s["name"] for s in screens if not str(s.get("purpose") or "").strip()]
        if blank:
            raise ValueError(
                "every screen needs a 'purpose' naming the job it exists for; "
                f"missing on: {', '.join(str(b) for b in blank[:5])}")

        if not _filled(plan.get("features")):
            raise ValueError(
                "provide the product capabilities the customer actually requested; "
                "do not invent features to satisfy a count")

        if thin:
            return

        records = _named(plan.get("records"))
        if not records:
            raise ValueError(
                "this record-based app needs at least one named business record; "
                "use only records supported by the customer's answers")

        empty = [r["name"] for r in records if not _filled(r.get("keeps"))]
        if empty:
            raise ValueError(
                "every record needs at least 2 things it 'keeps'; empty on: "
                f"{', '.join(str(e) for e in empty[:5])}")

        shallow = [r["name"] for r in records if len(_filled(r.get("keeps"))) < 2]
        if shallow:
            raise ValueError(
                "these records keep only one thing, which is not a record: "
                f"{', '.join(str(s) for s in shallow[:5])}")

        flows = [w for w in (plan.get("workflows") or [])
                 if isinstance(w, dict) and len(_filled(w.get("steps"))) >= 2]
        if not flows:
            raise ValueError("provide at least one 'workflow' with 2 or more steps — "
                             "a whole job from start to finish")

        if not wants_auth:
            return

        able = [u for u in (plan.get("users") or [])
                if isinstance(u, dict) and len(_filled(u.get("can_do"))) >= 2]
        if not able:
            raise ValueError("this app has people who sign in, so at least one entry "
                             "in 'users' needs 2 or more 'can_do' lines")

        policy = plan.get("account_policy")
        if not isinstance(policy, dict) or not policy.get("accounts_required"):
            raise ValueError("account_policy is required for an app with sign-in")

        mode = str(policy.get("registration_mode") or "").strip()
        if mode not in REGISTRATION_MODES:
            raise ValueError("account_policy.registration_mode must say how accounts are created")

        if mode == "open":
            role = str(policy.get("registration_role") or "").strip()
            if not role:
                raise ValueError("public sign-up needs one explicit registration_role")
            key = re.sub(r"[^a-z0-9]+", "_", role.lower()).strip("_")
            if any(word in key for word in PRIVILEGED):
                raise ValueError("public sign-up cannot create a privileged role")

        if mode in {"admin_created", "invite", "request"} and not str(
                policy.get("provisioning_role") or "").strip():
            raise ValueError(f"{mode} account creation needs one explicit provisioning_role")

    return validate


def wants_auth(plan: dict) -> bool:
    """Whether this plan has accounts at all — the gate everything downstream reads."""
    policy = plan.get("account_policy")
    if isinstance(policy, dict):
        return bool(policy.get("accounts_required"))
    return bool(plan.get("users"))


def archetype_pack(plan: dict) -> dict[str, Any]:
    """What the depth floor needs to know about this plan, derived from the plan."""
    screens = _named(plan.get("screens"))
    records = _named(plan.get("records"))
    thin = len(screens) <= 1 and not records
    return {
        "archetype": "single-tool" if thin else "record-based",
        "auth_policy": "required" if wants_auth(plan) else "none",
    }
