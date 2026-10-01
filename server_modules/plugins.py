"""Provider catalogue and per-user encrypted credentials."""
from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet

from . import config

SKILLS = config.ROOT / "server_modules" / "provider_catalog"
KEY = config.STATE / "plugin.key"
VAULT = config.STATE / "plugins.enc"
PROJECT_FILE = "plugins.json"
HANDOFF_FILE = "PLUGIN.md"


def _catalogue() -> dict:
    raw = json.loads((SKILLS / "plugins.json").read_text(encoding="utf-8"))
    for plugin in raw.get("plugins", []):
        setup_path = SKILLS / str(plugin.get("skill", "")) / "setup.json"
        setup = json.loads(setup_path.read_text(encoding="utf-8")) if setup_path.is_file() else {}
        choices = {choice.get("id"): choice for choice in setup.get("choices", [])}
        for mode in plugin.get("modes", []):
            mode["fields"] = choices.get(mode.get("choice"), {}).get("fields", [])
    return raw


def _cipher() -> Fernet:
    KEY.parent.mkdir(parents=True, exist_ok=True)
    if not KEY.is_file():
        KEY.write_bytes(Fernet.generate_key())
        try:
            os.chmod(KEY, 0o600)
        except OSError:
            pass
    return Fernet(KEY.read_bytes())


def _read() -> dict:
    if not VAULT.is_file():
        return {}
    return json.loads(_cipher().decrypt(VAULT.read_bytes()).decode("utf-8"))


def _write(rows: dict) -> None:
    VAULT.write_bytes(_cipher().encrypt(json.dumps(rows).encode("utf-8")))
    try:
        os.chmod(VAULT, 0o600)
    except OSError:
        pass


def saved() -> list[dict]:
    return [{"id": key, "mode": value["mode"], "configured": bool(value["values"]),
             "set": list(value["values"]),
             "hints": {name: f"…{str(secret)[-4:]}" for name, secret in value["values"].items()}}
            for key, value in _read().items()]


def listing() -> dict:
    data = _catalogue()
    return {"plugins": data.get("plugins", []), "groups": data.get("groups", []), "saved": saved()}


def save(plugin_id: str, mode_id: str, values: dict) -> list[dict]:
    data = _catalogue()
    plugin = next((p for p in data.get("plugins", []) if p.get("id") == plugin_id), None)
    if plugin is None:
        raise ValueError("unknown provider")
    mode = next((m for m in plugin.get("modes", []) if m.get("choice") == mode_id), None)
    if mode is None:
        raise ValueError("unknown provider mode")
    allowed = {field["key"] for field in mode.get("fields", [])}
    vault = _read()
    old = vault.get(plugin_id, {}).get("values", {})
    clean = {key: str(value).strip() for key, value in (values or {}).items()
             if key in allowed and str(value).strip()}
    merged = {**{key: value for key, value in old.items() if key in allowed}, **clean}
    missing = [f["label"] for f in mode.get("fields", [])
               if f.get("required", True) and not merged.get(f["key"])]
    if missing:
        raise ValueError("Missing: " + ", ".join(missing))
    vault[plugin_id] = {"mode": mode_id, "values": merged}
    _write(vault)
    return saved()


def forget(plugin_id: str) -> list[dict]:
    vault = _read()
    vault.pop(plugin_id, None)
    _write(vault)
    return saved()


def environment(enabled: list[str]) -> dict[str, str]:
    vault = _read()
    return {key: value for plugin_id in enabled for key, value in
            vault.get(plugin_id, {}).get("values", {}).items()}


def _selected(enabled: list[str]) -> list[dict]:
    """Catalogue rows enriched with the selected mode and field contract."""
    catalogue = _catalogue()
    by_id = {str(row.get("id")): row for row in catalogue.get("plugins", [])}
    vault = _read()
    rows = []
    for plugin_id in dict.fromkeys(str(item) for item in enabled):
        plugin = by_id.get(plugin_id)
        if not plugin:
            continue
        saved_row = vault.get(plugin_id, {})
        mode_id = str(saved_row.get("mode") or "")
        mode = next((item for item in plugin.get("modes", [])
                     if str(item.get("choice")) == mode_id), None)
        if mode is None:
            mode = (plugin.get("modes") or [{}])[0]
            mode_id = str(mode.get("choice") or "")
        values = saved_row.get("values", {}) if isinstance(saved_row.get("values"), dict) else {}
        rows.append({**plugin, "selected_mode": mode_id, "mode": mode,
                     "configured_keys": set(values)})
    return rows


def handoff(enabled: list[str]) -> str:
    """Create a temporary, secret-free contract the build agent may read."""
    rows = _selected(enabled)
    if not rows:
        return ""
    lines = [
        "# Plugin integration handoff",
        "",
        "This temporary handoff was generated from the plugins selected in AgentForge.",
        "Credential values are not stored here. Never print them, read them from a secret file,",
        "copy them into source code, commit them, or return them in chat. AgentForge supplies",
        "configured values to commands and the managed preview through the process environment.",
        "",
        "Integrate every plugin below. Use its environment-variable names, add names and safe examples",
        "only to `.env.example`, preserve server/client boundaries, provide a clear unconfigured state",
        "for missing values, and create or update the relevant unit and E2E tests.",
        "",
    ]
    for plugin in rows:
        mode = plugin.get("mode") or {}
        lines.extend([
            f"## {plugin.get('name') or plugin.get('id')}",
            "",
            f"- Plugin id: `{plugin.get('id')}`",
            f"- Category: {plugin.get('group') or 'Integration'}",
            f"- Purpose: {plugin.get('what') or 'External service integration'}",
            f"- Selected mode: {mode.get('label') or plugin.get('selected_mode')}",
        ])
        if mode.get("hint"):
            lines.append(f"- Mode guidance: {mode['hint']}")
        fields = mode.get("fields") or []
        if fields:
            lines.append("- Environment contract:")
            for field in fields:
                key = str(field.get("key") or "")
                if not key:
                    continue
                visibility = "server-only secret" if field.get("secret") else "configuration value"
                required = "required" if field.get("required", True) else "optional"
                status = "configured" if key in plugin["configured_keys"] else "not configured"
                detail = str(field.get("hint") or "").strip()
                suffix = f" — {detail}" if detail else ""
                lines.append(f"  - `{key}` — {visibility}; {required}; {status}{suffix}")
        else:
            lines.append("- Environment contract: no credential fields are required for this mode.")
        lines.append("")
    lines.extend([
        "## Completion rule",
        "",
        "After every selected plugin is integrated, its tests have run, and `.env.example` contains",
        "variable names without live values, remove `.agentforge/PLUGIN.md`. If work is blocked or",
        "fails, leave this file in place so the next approved run can continue it.",
        "",
    ])
    return "\n".join(lines)


def configure_project(project: str, enabled: list[str]) -> list[str]:
    """Persist a multi-plugin selection and refresh its temporary handoff."""
    available = {str(row.get("id")) for row in _catalogue().get("plugins", [])}
    clean = list(dict.fromkeys(str(item) for item in enabled if str(item) in available))
    record = config.record_dir(project)
    record.mkdir(parents=True, exist_ok=True)
    (record / PROJECT_FILE).write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    page = handoff(clean)
    target = record / HANDOFF_FILE
    if page:
        target.write_text(page, encoding="utf-8")
    else:
        target.unlink(missing_ok=True)
    return clean


def consume_handoff(project: str) -> None:
    """Successful integration consumes the handoff; failures retain it."""
    try:
        (config.record_dir(project) / HANDOFF_FILE).unlink(missing_ok=True)
    except OSError:
        # A temporary handoff must never turn an otherwise successful build or
        # chat update into a failed run (for example, during a brief antivirus
        # file lock on Windows). The next successful run can consume it.
        pass
