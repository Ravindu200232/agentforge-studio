"""Catch demo credentials accidentally rendered on generated sign-in pages."""
from __future__ import annotations

import re
from pathlib import Path


_DEMO_UI = re.compile(
    r"demo\s+(?:accounts?|logins?|credentials?|passwords?|emails?)|"
    r"<DemoAccounts\b|\bDEMO_ACCOUNTS\s*\.\s*map\s*\(|"
    r"(?:useState\s*\(|\b(?:value|defaultValue|placeholder)\s*=\s*)\s*[({]?\s*['\"]"
    r"(?!you@|name@)[^'\"]+@example\.com|Demo!2026",
    re.IGNORECASE,
)


def issues(files: list[Path]) -> list[str]:
    """Return login UI files with visible demo hints, ignoring comments and generic placeholders."""
    found = []
    for path in files:
        if not path.is_file() or path.suffix.lower() not in {".tsx", ".jsx", ".html"}:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        source = re.sub(r"/\*.*?\*/|<!--.*?-->|^\s*//[^\n]*", "", source, flags=re.DOTALL | re.MULTILINE)
        if _DEMO_UI.search(source):
            found.append(str(path))
    return found
