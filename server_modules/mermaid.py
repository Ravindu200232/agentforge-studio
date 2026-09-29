"""Rendering a diagram to SVG.

The studio's diagram viewer injects an SVG string; a `.mmd` source alone shows a
file path where a picture should be. Mermaid's own CLI is the renderer, found
once and reused. When it is not installed the source is still written and the
diagram is marked unrendered, which is a diagram you can copy rather than one
that silently is not there.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()
# Without this every mmdc/npx/Chromium launch flashes a console window on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_cli: list[str] | None | bool = False   # False = not looked for yet

# Mermaid needs a browser; on a headless machine it needs to be told it may run
# without a sandbox. Written next to the call rather than into the project.
_PUPPETEER = {"args": ["--no-sandbox", "--disable-setuid-sandbox"]}
_STUDIO_ROOT = Path(__file__).resolve().parents[1] / "studio"


def _installed_browser() -> str | None:
    """Use Puppeteer's browser when present, otherwise a system Chrome/Edge."""
    candidates = [
        Path(os.environ.get("PUPPETEER_EXECUTABLE_PATH", "")),
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            return str(candidate)
    return None


def _find_cli() -> list[str] | None:
    """The first mermaid-cli invocation that actually works, or None."""
    global _cli
    with _lock:
        if _cli is not False:
            return _cli  # type: ignore[return-value]
        _cli = None
        candidates: list[list[str]] = []
        node = shutil.which("node") or shutil.which("node.exe")
        local_cli = (_STUDIO_ROOT / "node_modules" / "@mermaid-js"
                     / "mermaid-cli" / "src" / "cli.js")
        if node and local_cli.is_file():
            candidates.append([node, str(local_cli)])
        for name in ("mmdc", "mmdc.cmd"):
            found = shutil.which(name)
            if found:
                candidates.append([found])
        for candidate in candidates:
            try:
                probe = subprocess.run([*candidate, "--version"], capture_output=True,
                                       text=True, timeout=180, check=False,
                                       cwd=str(_STUDIO_ROOT), creationflags=_NO_WINDOW)
                if probe.returncode == 0:
                    _cli = candidate
                    break
            except (OSError, subprocess.SubprocessError):
                continue
        return _cli  # type: ignore[return-value]


def available() -> bool:
    return _find_cli() is not None


def render(source: str, out_path: Path, timeout: int = 180) -> tuple[bool, str]:
    """Draw one Mermaid source to `out_path`.

    Returns whether an SVG landed and, when it did not, what Mermaid said about
    it. That message is the only reliable parser there is — a hand-written
    syntax check passes `Member --> (Login)`, which Mermaid rejects — so it goes
    back to the model as the repair instruction.
    """
    cli = _find_cli()
    if not cli:
        return False, "no mermaid renderer is installed"
    if not str(source or "").strip():
        return False, "the source is empty"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        mmd = work / "diagram.mmd"
        mmd.write_text(source, encoding="utf-8")
        config = work / "puppeteer.json"
        puppeteer_config = dict(_PUPPETEER)
        browser = _installed_browser()
        if browser:
            puppeteer_config["executablePath"] = browser
        config.write_text(json.dumps(puppeteer_config), encoding="utf-8")
        try:
            done = subprocess.run(
                [*cli, "-i", str(mmd), "-o", str(out_path), "-b", "white",
                 "-p", str(config)],
                capture_output=True, text=True, timeout=timeout, check=False,
                cwd=str(_STUDIO_ROOT), creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            return False, f"the renderer timed out after {timeout}s"
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"the renderer could not run: {exc}"
        if done.returncode != 0 or not out_path.is_file():
            noise = ((done.stderr or "") + "\n" + (done.stdout or "")).strip()
            return False, _readable_error(noise)
    return (out_path.stat().st_size > 0, "")


_NOISE = re.compile(r"^\s*(at |\s*\^+\s*$|Store is a function|\(node:|Generating)")


def _readable_error(text: str) -> str:
    """Mermaid's complaint, without the Node stack trace around it."""
    lines = [line.rstrip() for line in (text or "").splitlines()
             if line.strip() and not _NOISE.match(line)]
    keep = [line for line in lines
            if any(word in line.lower() for word in
                   ("error", "expecting", "parse", "unexpected", "got '", "syntax"))]
    return " | ".join((keep or lines)[:6])[:600] or "the renderer failed without a message"


_FENCE = re.compile(r"```(?:mermaid)?\s*(.+?)```", re.DOTALL)

# Mermaid deliberately accepts a broad textual subset of class-diagram syntax.
# The generator, however, promises recognizable UML rather than merely a
# parseable graph.  These checks make the Visual Paradigm / UML conventions
# actionable before an SVG is accepted.  They cannot infer product facts (that
# remains the SRS traceability review), but they catch notation drift such as a
# missing visibility symbol or the vague multiplicity "many".
_CLASS_BLOCK = re.compile(r"^\s*class\s+[^\s{]+(?:\s*\[[^\]]+\])?\s*\{(?P<body>.*?)^\s*\}",
                          re.MULTILINE | re.DOTALL)
_CLASS_MEMBER = re.compile(r"^\s*([+\-#~])\s*[^\s:].*", re.MULTILINE)
_CLASS_STEREOTYPE = re.compile(r"^\s*<<(?:interface|enumeration|object)>>\s*$", re.IGNORECASE)
_INLINE_MEMBER = re.compile(r"^\s*[^\s:]+\s*:\s*([+\-#~])\s*\S+", re.MULTILINE)
_RELATION = re.compile(
    r"^\s*[^\s:]+(?:\s+\"[^\"]+\")?\s*"
    r"(?P<token><\|--|--\|>|\.\.\|>|<\|\.\.|\*--|--\*|o--|--o|-->|<--|\.\.>|<\.\.|--|\.\.)"
    r"\s*(?:\"(?P<right>[^\"]+)\"\s*)?[^\s:]+(?:\s*:\s*(?P<label>.+))?\s*$",
    re.MULTILINE)
_MULTIPLICITY = re.compile(r"^(?:0\.\.1|1|0\.\.\*|1\.\.\*|\*|[2-9]\d*|(?:0|1)\.\.[2-9]\d*)$")
def _diagram_notation_problems(kind: str, text: str) -> list[str]:
    """Small, deterministic guards for the defining notation of every kind.

    Mermaid verifies grammar.  These checks verify the semantic *shape* that
    grammar alone cannot see (for example, a sequence source can parse without
    a return arrow, and a context diagram can parse without a system boundary).
    They intentionally never invent project content or require optional parts.
    """
    found: list[str] = []

    if re.search(r"^\s*(?:click|action)\b", text, re.IGNORECASE | re.MULTILINE):
        found.append("customer-facing SRS diagrams must not contain interactive `click` or `action` directives")

    if kind == "use_case":
        if not re.search(r"\bsubgraph\b", text, re.IGNORECASE):
            found.append("a use-case diagram needs one named system-boundary `subgraph`")
        if not re.search(r"\w+\s*\(\[", text):
            found.append("use cases must use Mermaid stadium/oval approximation `id([\"Goal\"])`")
    elif kind == "activity":
        if not re.search(r"\(\(●\)\)", text):
            found.append("an activity diagram needs the initial node `((●))`")
        if not re.search(r"\(\(◉\)\)", text):
            found.append("every activity path must finish at a final node `((◉))`")
    elif kind == "bpmn":
        if not re.search(r"\bsubgraph\b", text, re.IGNORECASE):
            found.append("a BPMN diagram needs a named pool/lane `subgraph`")
        # BPMN defines an event by its circle, not by the English words
        # "Start" and "End".  Mermaid approximates the start event with a
        # double circle and the end event with a triple circle; accept any
        # evidence-based label in those shapes rather than rejecting a
        # customer-domain label such as "Order received".
        has_start = bool(re.search(r"(?<!\()\(\(\s*(?!\()[^)]+\)\)(?!\))", text))
        has_end = bool(re.search(r"(?<!\()\(\(\(\s*[^)]+\)\)\)(?!\))", text))
        if not has_start or not has_end:
            found.append("a BPMN diagram needs a single-circle start-event approximation `id((\"event\"))` and a double-circle end-event approximation `id(((\"event\")))`")
    elif kind == "erd":
        if not re.search(r"^\s*[A-Z][A-Z0-9_]*\s*\{", text, re.MULTILINE):
            found.append("an ERD needs at least one uppercase entity block with typed attributes")
        if re.search(r"^\s*\S+\s+--\s+\S+", text, re.MULTILINE):
            found.append("an ERD relationship must use Crow's Foot cardinality, not a plain `--` line")
    elif kind == "sequence":
        lifelines = re.findall(r"^\s*(?:actor|participant)\s+", text, re.IGNORECASE | re.MULTILINE)
        if len(lifelines) < 2:
            found.append("a sequence diagram needs at least two declared actor/participant lifelines")
        if not re.search(r"(?:->>|-->>)", text):
            found.append("a sequence diagram needs at least one message arrow")
    elif kind == "state_machine":
        if not re.search(r"\[\*\]\s*-->", text):
            found.append("a state machine needs an initial pseudostate `[*] --> State`")
        if not re.search(r"-->\s*\[\*\]", text):
            found.append("a state machine needs a terminal transition `State --> [*]`")
    elif kind == "dfd":
        if not re.search(r"\(\(\s*[\"']?\s*\d+\.\s*[^)]+\)\)", text):
            found.append("a DFD needs a numbered verb-noun process such as `((1. Validate order))`")
        for line in text.splitlines():
            if "-->" in line and "|" not in line:
                found.append("every DFD data flow must have a named-data label between `|` characters")
                break
    elif kind == "component":
        if "<<component>>" not in text.lower():
            found.append("a component diagram needs `<<component>>`-stereotyped components")
        if not re.search(r"\bsubgraph\b", text, re.IGNORECASE):
            found.append("a component diagram needs responsibility-band `subgraph` groups")
    elif kind == "deployment":
        if not re.search(r"<<(?:device|execution environment)>>", text, re.IGNORECASE):
            found.append("a deployment diagram needs `<<device>>` or `<<execution environment>>` nodes")
        if "<<artifact>>" not in text.lower():
            found.append("a deployment diagram needs at least one deployed `<<artifact>>`")
    elif kind == "system_context":
        if not re.search(r"\[\[.+?\]\]", text):
            found.append("a system-context diagram needs exactly one visually distinct system-boundary node `sys[[\"System\"]]`")
        for line in text.splitlines():
            if "-->" in line and "|" not in line:
                found.append("every system-context interaction must have a label between `|` characters")
                break
    return found


def _class_object_problems(text: str) -> list[str]:
    """Return UML-notation faults which Mermaid's syntax parser cannot know."""
    problems: list[str] = []
    blocks = list(_CLASS_BLOCK.finditer(text))
    if not blocks:
        return ["a class/object diagram needs at least one compartmented `class Name { ... }` box"]

    for block in blocks:
        body = block.group("body")
        header = block.group(0).split("{", 1)[0]
        # An object compartment holds concrete slot values rather than class
        # attributes/operations, so UML visibility is not meaningful there.
        if re.search(r"<<object>>", body, re.IGNORECASE):
            continue
        if "[" in header and ":" in header:
            problems.append("an object-instance label `instance : Class` must include the `<<object>>` stereotype")
        if re.search(r"<<enumeration>>", body, re.IGNORECASE):
            # Enumeration literals are not classifier attributes or operations;
            # UML writes their names plainly below the enumeration stereotype.
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped or _CLASS_STEREOTYPE.match(stripped):
                    continue
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stripped):
                    problems.append("an enumeration contains plain literal names only, below `<<enumeration>>`")
                    break
            continue
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("%%") or _CLASS_STEREOTYPE.match(stripped):
                continue
            if not _CLASS_MEMBER.match(line):
                problems.append("every class attribute and operation must begin with UML visibility "
                                "(`+`, `-`, `#`, or `~`)")
                break
            if "(" in stripped:
                if not re.search(r"\)\s*:\s*\S+", stripped):
                    problems.append("every class operation must use `operation(parameter: Type): ReturnType`")
                    break
            elif ":" not in stripped:
                problems.append("every class attribute must use `visibility name: Type`")
                break

    # Mermaid also permits Class : member declarations outside a compartment.
    # Keep the same visibility rule there.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("class ", "%%")) or ":" not in stripped:
            continue
        if _RELATION.match(line):
            continue
        if re.match(r"^\s*[^\s:]+\s*:", line) and not _INLINE_MEMBER.match(line):
            problems.append("every inline class member must begin with UML visibility "
                            "(`+`, `-`, `#`, or `~`)")
            break

    for match in _RELATION.finditer(text):
        line = match.group(0)
        quoted = re.findall(r'"([^\"]+)"', line)
        if len(quoted) == 1:
            problems.append("a relationship with multiplicity must state a valid multiplicity at both ends")
        elif len(quoted) >= 2:
            for value in quoted[:2]:
                if not _MULTIPLICITY.match(value.strip()):
                    problems.append("use exact UML multiplicity (`0..1`, `1`, `0..*`, `1..*`, `*`, or a fixed range), "
                                    f"not {value!r}")
                    break
        if not (match.group("label") or "").strip():
            problems.append("every class relationship needs a short domain verb/verb-phrase label after `:`")
    return list(dict.fromkeys(problems))

# What each kind's source has to open with for Mermaid to parse it at all.
OPENERS = {
    "erd": ("erdiagram",),
    "sequence": ("sequencediagram",),
    "class_object": ("classdiagram",),
    "state_machine": ("statediagram", "statediagram-v2"),
    "use_case": ("flowchart", "graph"),
    "activity": ("flowchart", "graph"),
    "dfd": ("flowchart", "graph"),
    "bpmn": ("flowchart", "graph"),
    "system_context": ("flowchart", "graph"),
    "component": ("flowchart", "graph"),
    "deployment": ("flowchart", "graph"),
}


def clean(source: str) -> str:
    """The Mermaid source out of whatever the model wrapped it in."""
    raw = str(source or "").strip()
    fenced = _FENCE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    return raw


def problems(kind: str, source: str) -> list[str]:
    """Why this source will not parse, in terms the model can act on."""
    text = clean(source)
    if not text:
        return ["the source is empty"]
    first = text.splitlines()[0].strip().lower()
    wanted = OPENERS.get(kind, ())
    if wanted and not first.startswith(wanted):
        return [f"a {kind} diagram must start with one of "
                f"{', '.join(wanted)}; this starts with {first[:40]!r}"]
    if text.count("(") != text.count(")"):
        return ["unbalanced parentheses in a node label"]
    if text.count("[") != text.count("]"):
        return ["unbalanced square brackets in a node label"]
    if kind == "class_object":
        return _class_object_problems(text)
    return _diagram_notation_problems(kind, text)
