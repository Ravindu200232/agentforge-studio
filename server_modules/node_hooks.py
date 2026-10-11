"""The `--require` hooks the Studio loads into the Node processes it starts for a project.

`dns-fallback.cjs` goes into every one of them (the agent's commands, the end-to-end runs, the preview): a cluster name this
computer's DNS could not look up is asked again and then of public DNS, as the Studio's own connection check already does.
`frame-headers.cjs` goes into the preview only (`preview_runtime.py`).
"""
from __future__ import annotations

from pathlib import Path

HOOKS = Path(__file__).resolve().with_name("preview_hooks")
DNS_FALLBACK = HOOKS / "dns-fallback.cjs"


def add(env: dict[str, str], *hooks: Path) -> dict[str, str]:
    """`env` with each hook appended to its NODE_OPTIONS once (what is already there is kept). Returns `env`."""
    options = str(env.get("NODE_OPTIONS") or "")
    for hook in hooks:
        flag = f'--require "{hook.as_posix()}"'
        if hook.is_file() and flag not in options:
            options = f"{options} {flag}".strip()
    if options:
        env["NODE_OPTIONS"] = options
    return env
