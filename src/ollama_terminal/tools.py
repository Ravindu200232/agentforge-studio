"""Workspace tools exposed through Ollama's native tool calling."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
from typing import Any, Callable

import httpx

from .browser_inspect import inspect_local_page
from .guard import SourceGuard
from .mcp_client import MCPManager


MAX_OUTPUT = 24_000
MAX_READ = 32_000
MAX_COMMAND_SECONDS = 600
SERVER_COMMAND_SECONDS = 75

# A CLI that colours its own output (netlify, vercel, npm...) still does so once piped,
# leaving raw escape codes ("[32m...[39m") in what both the model and the chat card see.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


# What a web-app build/test/deploy stage legitimately runs. Not a security
# sandbox on its own (a shell string can still be obfuscated past a prefix
# check) — this is a defense-in-depth floor against a command that is simply
# not one of these things: an accidental `rm -rf`, a project's own compromised
# script, or a prompt-injected instruction from a file the model read.
_ALLOWED_PROGRAMS = {
    "npm", "npx", "node", "yarn", "pnpm", "corepack",
    "git", "gh",
    "python", "python3", "pip", "pip3",
    "tsc", "vitest", "playwright", "prisma", "mongosh",
    "vercel", "netlify", "aws", "az",
    "mkdir", "rmdir", "rm", "del", "mv", "move", "cp", "copy", "touch",
    "cat", "type", "echo", "printf", "cd", "pwd", "dir", "ls", "chmod",
    "curl", "wget", "grep", "findstr", "find", "sleep",
    "which", "where", "test", "true", "false", "exit", "set", "export",
    "sh", "bash", "cmd", "powershell", "pwsh",
}
# PowerShell's own Verb-Noun cmdlets (Set-Content, Copy-Item, Get-ChildItem,
# ...) are allowed generically by that naming shape rather than enumerated —
# except this explicit set, which can run arbitrary code or another process.
_DANGEROUS_CMDLETS = {"invoke-expression", "invoke-command", "invoke-item",
                      "start-process", "new-object", "add-type"}
_CMDLET_SHAPE = re.compile(r"^[a-z]+-[a-z]+$")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_DENY_PATTERNS = (
    (re.compile(r"\bsudo\b|\bsu\s+-"), "sudo/su is not allowed"),
    (re.compile(r"\b(curl|wget|invoke-webrequest|iwr)\b[^|;&\n]*\|\s*"
               r"(sh|bash|zsh|powershell|pwsh|cmd)\b"),
     "piping a download straight into a shell is not allowed"),
    (re.compile(r"\biex\b|invoke-expression"), "Invoke-Expression is not allowed"),
    (re.compile(r"\brm\s+-rf\s+(/(?:\s|$)|~(?:\s|$)|\*\s*$)"),
     "recursive delete of the filesystem root/home is not allowed"),
    (re.compile(r"\bformat\s+[a-z]:"), "formatting a drive is not allowed"),
    (re.compile(r"(id_rsa|\.ssh/|\.aws[/\\]credentials|\.netrc)\b"
               r"[^\n]*\b(curl|wget|nc\s|ftp\s)"),
     "reading a credential file into a network command is not allowed"),
)


def _split_top_level(command: str) -> list[str]:
    """`command` split on `&&`/`||`/`;`/`|`-style separators, but never inside a quoted string.

    Found live: `node -p "const r=JSON.parse(...); r.complete"` was cut in two at the JS
    statement's own semicolon (perfectly ordinary inside a one-liner passed to `node -p`/`python
    -c`), leaving `r.complete"` to be checked as if it were its own command — which it plainly is
    not one of. A shell separator inside quotes is not a separator; only a quote-aware split can
    tell the difference between the two.
    """
    segments: list[str] = []
    current: list[str] = []
    quote = ""  # "" outside any quote, else the quote character currently open
    i, length = 0, len(command)
    while i < length:
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < length:
                i += 1
                current.append(command[i])  # an escaped char inside "..." never closes the quote
            elif ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            current.append(ch)
            i += 1
            continue
        if command[i:i + 2] in ("&&", "||"):
            segments.append("".join(current))
            current = []
            i += 2
            continue
        if ch in ";\n":
            segments.append("".join(current))
            current = []
            i += 1
            continue
        if ch == "|":  # a lone pipe: a real `||` was already consumed by the check above
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return segments


def _segment_program(segment: str) -> str:
    """The leading executable of one `&&`/`||`/`;`/`|`-separated shell segment."""
    segment = segment.strip().lstrip("(")
    if not segment:
        return ""
    try:
        tokens = shlex.split(segment, posix=(os.name != "nt"))
    except ValueError:
        tokens = segment.split()
    idx = 0
    while idx < len(tokens) and _ENV_ASSIGNMENT.match(tokens[idx]):
        idx += 1
    if idx >= len(tokens):
        return ""
    name = Path(tokens[idx]).name.lower()
    for suffix in (".exe", ".cmd", ".ps1", ".sh", ".bat"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def _command_problem(command: str) -> str | None:
    """Why `command` is blocked, or `None` when it is fine to run."""
    lowered = command.lower()
    for pattern, message in _DENY_PATTERNS:
        if pattern.search(lowered):
            return message
    for segment in _split_top_level(command):
        program = _segment_program(segment)
        if not program or program in _ALLOWED_PROGRAMS:
            continue
        if program in _DANGEROUS_CMDLETS:
            return f"'{program}' is not allowed"
        if _CMDLET_SHAPE.match(program):
            continue  # an unlisted PowerShell Verb-Noun cmdlet — allowed by shape
        return (f"'{program}' is not one of the commands a build/test/deploy "
                f"stage runs (npm/git/node/python/vercel/... and their usual "
                f"companions) — use one of those instead")
    return None


def tools_unsupported(exc: Exception) -> bool:
    """True for an Ollama error whose message says the model can't take tools.

    Duck-typed on the exception's shape rather than `isinstance(exc,
    ollama.ResponseError)`, so this file does not need to import `ollama`
    just for this one check, and callers in either package (this one, or
    `server_modules`, which already depends on it) can use it the same way.
    """
    return (type(exc).__name__ == "ResponseError"
            and getattr(exc, "status_code", None) == 400
            and "tool" in str(getattr(exc, "error", "") or exc).lower())


def describe_call(name: str, args: dict[str, Any]) -> str:
    """A short human label for a tool call, e.g. `read_file(srs/spec.md)`.

    Used only for logging a *failed* call to the studio's activity feed —
    the success path already has its own per-tool phrasing ("Listed X",
    "Read X (N lines)", ...). Without this, a WARN line for a failure was
    just the bare exception text ("Tool error: Not a directory") with no
    way to tell which call produced it, even though the model recovers on
    its own next turn.
    """
    if name in ("list_files", "write_file", "replace_text"):
        return f"{name}({args.get('path') or '.'})"
    if name == "read_file":
        return f"read_file({args.get('path') or ''})"
    if name == "search_text":
        return f'search_text("{args.get("query") or ""}", {args.get("path") or "."})'
    if name == "run_command":
        return f"run_command({str(args.get('command') or '')[:80]})"
    if name == "web_search":
        return f'web_search("{args.get("query") or ""}")'
    if name == "web_fetch":
        return f"web_fetch({args.get('url') or ''})"
    if name == "browser_inspect":
        return f"browser_inspect({args.get('url') or 'managed preview'}, {args.get('viewport') or 'desktop'})"
    return f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOL_SCHEMAS = [
    _schema("list_files", "List files in a workspace directory (up to 200 entries).",
            {"path": {"type": "string", "description": "Directory relative to workspace; use . for root"}}, ["path"]),
    _schema("read_file", "Read a UTF-8 text file in the workspace, optionally by line range.",
            {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, ["path"]),
    _schema("search_text", "Search workspace text files for a literal string.",
            {"query": {"type": "string"}, "path": {"type": "string"}}, ["query"]),
    _schema("write_file", "Create or replace a UTF-8 file in the workspace after plan approval.",
            {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _schema("replace_text", "Replace one exact occurrence of text in a workspace file after plan approval.",
            {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, ["path", "old", "new"]),
    _schema("run_command", "Run any terminal command from the project workspace after plan approval.",
            {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}}, ["command"]),
    _schema("web_search", "Search the live web through Ollama. Local Ollama needs no API key.",
            {"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
    _schema("web_fetch", "Fetch a web page through Ollama. Local Ollama needs no API key.",
            {"url": {"type": "string"}}, ["url"]),
    _schema("browser_inspect", "Open one local running app page in a real browser. Returns rendered text, layout/accessibility findings (including elements that overflow the viewport) and saves a screenshot for UI review. Use desktop and mobile before declaring a UI complete; it never clicks, types, signs in or navigates away from the local preview.",
            {"url": {"type": "string", "description": "Optional http://127.0.0.1 or http://localhost preview URL. Studio agents default to their managed preview."},
             "viewport": {"type": "string", "enum": ["desktop", "mobile"], "description": "desktop (1440px) or mobile (390px)"}}, []),
]


class WorkspaceTools:
    def __init__(self, root: Path, client: Any, approve: Callable[[str], bool], shell: str | None = None,
                 web_host: str = "http://localhost:11434", use_local_web: bool = True,
                 protected_app_root: Path | None = None, mcp: MCPManager | None = None):
        self.root = root.resolve()
        self.client = client
        self.approve = approve
        self.shell = shell or ("powershell" if os.name == "nt" else "/bin/sh")
        self.web_host = web_host.rstrip("/")
        self.use_local_web = use_local_web
        # Only a workspace inside the app can reach the app's own source by a relative path; a project
        # folder elsewhere (C:\Projects\shop) cannot, and guarding it only risks undoing the app's own updates.
        self.source_guard = (SourceGuard(protected_app_root)
                             if protected_app_root and self.root.is_relative_to(Path(protected_app_root).resolve())
                             else None)
        self.mcp = mcp

    def _local_web_request(self, endpoint: str, payload: dict[str, Any]) -> str:
        response = httpx.post(f"{self.web_host}/api/experimental/{endpoint}",
                              json=payload, timeout=30)
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)[:MAX_OUTPUT]

    def _path(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Path escapes the workspace")
        return candidate

    def execute(self, name: str, args: dict[str, Any]) -> str:
        try:
            if self.mcp is not None and self.mcp.is_mcp_tool(name):
                return self.mcp.call(name, args)[:MAX_OUTPUT]
            method = getattr(self, f"tool_{name}", None)
            if method is None or name not in {s["function"]["name"] for s in TOOL_SCHEMAS}:
                raise ValueError(f"Unknown tool: {name}")
            return str(method(**args))[:MAX_OUTPUT]
        except Exception as exc:
            return f"Tool error: {exc}"

    # The base tool is useful outside the studio too. These hooks let the
    # studio stream command activity without coupling the terminal package to
    # its event bus.
    def command_started(self, _command: str, _timeout: int) -> None:
        pass

    def command_output(self, _text: str) -> None:
        pass

    def command_heartbeat(self, _command: str, _elapsed: int) -> None:
        pass

    def command_finished(self, _command: str, _exit_code: int, _timed_out: bool) -> None:
        pass

    def tool_list_files(self, path: str = ".") -> str:
        directory = self._path(path)
        if not directory.exists():
            parent = directory.parent
            nearby = (", ".join(sorted(p.name for p in parent.iterdir()))[:300]
                      if parent.is_dir() else "")
            raise ValueError(f"{path!r} does not exist" +
                             (f" - {parent.relative_to(self.root) or '.'} has: {nearby}" if nearby else ""))
        if not directory.is_dir():
            raise ValueError(f"{path!r} is a file, not a directory - use read_file instead")
        entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())[:200]
        return "\n".join(("dir  " if p.is_dir() else "file ") + str(p.relative_to(self.root)) for p in entries)

    def tool_read_file(self, path: str, start_line: int = 1, end_line: int = 0) -> str:
        if start_line < 1:
            raise ValueError(f"start_line must be 1 or more, got {start_line}")
        if end_line < 0:
            raise ValueError(f"end_line must be 0 (meaning \"to the end\") or a positive line number, got {end_line}")
        if end_line and end_line < start_line:
            raise ValueError(f"end_line ({end_line}) must be >= start_line ({start_line})")
        file = self._path(path)
        if not file.is_file():
            raise ValueError(f"{path!r} is not a file" + (" (it's a directory - use list_files)" if file.is_dir() else " - it does not exist"))
        if file.stat().st_size > 2_000_000:
            raise ValueError("File is too large (2 MB limit)")
        raw = file.read_bytes()
        encoding = ("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else
                    "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8")
        lines = raw.decode(encoding).splitlines()
        if start_line > len(lines):
            raise ValueError(f"start_line ({start_line}) is past the end of the file, which has {len(lines)} lines")
        selected = lines[start_line - 1:end_line or None]
        return "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start_line))[:MAX_READ]

    def tool_search_text(self, query: str, path: str = ".") -> str:
        if not query:
            raise ValueError("Empty query")
        base = self._path(path)
        files = [base] if base.is_file() else base.rglob("*")
        hits = []
        for file in files:
            if not file.is_file() or any(part in {".git", ".venv", ".deps", "__pycache__", "node_modules"} for part in file.parts):
                continue
            if not file.resolve().is_relative_to(self.root):
                continue
            if file.stat().st_size > 1_000_000:
                continue
            try:
                for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                    if query.lower() in line.lower():
                        hits.append(f"{file.relative_to(self.root)}:{number}: {line[:300]}")
                        if len(hits) >= 100:
                            return "\n".join(hits)
            except (UnicodeError, OSError):
                continue
        return "\n".join(hits) or "No matches"

    def tool_write_file(self, path: str, content: str) -> str:
        file = self._path(path)
        if not self.approve(f"Write {file} ({len(content)} characters)?"):
            return "Denied by user"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return f"Wrote {file.relative_to(self.root)}"

    def tool_replace_text(self, path: str, old: str, new: str) -> str:
        if not old:
            raise ValueError("old text must not be empty")
        file = self._path(path)
        content = file.read_text(encoding="utf-8")
        if content.count(old) != 1:
            raise ValueError(f"Expected exactly one match; found {content.count(old)}")
        if not self.approve(f"Edit {file} (replace {len(old)} characters)?"):
            return "Denied by user"
        file.write_text(content.replace(old, new, 1), encoding="utf-8")
        return f"Edited {file.relative_to(self.root)}"

    def tool_run_command(self, command: str, timeout_seconds: int = 600) -> str:
        if not command.strip():
            raise ValueError("Empty command")
        problem = _command_problem(command)
        if problem:
            raise ValueError(f"Command blocked: {problem}")
        # A generated app may own one or more Node processes. Killing every
        # `node.exe` also kills the Studio, unrelated previews and the build
        # itself. Commands must target a known PID when cleanup is needed.
        if ("taskkill" in command.lower() and "/im" in command.lower()
                and "node.exe" in command.lower()) or "stop-process -name node" in command.lower():
            raise ValueError("Do not terminate every node.exe process. Target a known child PID instead.")
        server_command = any(token in command.lower() for token in
                             ("next dev", "next start", "npm run dev", "npm run start", "start /b"))
        # The Studio has one managed preview process and takes care of its
        # port, environment and lifecycle.  Letting an agent run a server in a
        # foreground terminal always looks successful ("Ready in 439ms") but
        # never exits, consuming the build turn until it times out.
        if server_command and getattr(self, "managed_preview", False):
            raise ValueError("Do not run a development or production server from the agent. "
                             "The Studio starts the managed preview automatically after the build.")
        if not self.approve(f"Run in {self.root}: {command} ?"):
            return "Denied by user"
        timeout = min(max(int(timeout_seconds), 1), MAX_COMMAND_SECONDS)
        if server_command:
            timeout = min(timeout, SERVER_COMMAND_SECONDS)
        shell_args = [self.shell, "-NoProfile", "-Command", command] if os.name == "nt" else [self.shell, "-c", command]
        before = self.source_guard.snapshot() if self.source_guard else None
        output = ""
        output_parts: list[str] = []
        process: subprocess.Popen | None = None
        timed_out = False
        stopped_at = 0.0
        exit_code = 1
        # The host can ask a running command to stop (the Stop button): it is checked while the command runs,
        # so Stop does not wait for a build or a test run to finish on its own.
        stop_requested = getattr(self, "stop_requested", None)

        def append(text: str) -> None:
            if not text:
                return
            clean = _ANSI.sub("", text.replace("\r", ""))
            if not clean:
                return
            used = sum(len(part) for part in output_parts)
            if used < MAX_OUTPUT:
                output_parts.append(clean[:MAX_OUTPUT - used])

        def stop_tree(child: subprocess.Popen) -> None:
            if child.poll() is not None:
                return
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               capture_output=True, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                # The command runs in its own process group, so the shell's children (npm, node, a test
                # runner) stop with it instead of holding the output open after the shell is gone.
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except OSError:
                    child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except OSError:
                        child.kill()

        try:
            process = subprocess.Popen(shell_args, cwd=self.root, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                       # A child's stdout is UTF-8 (npm/Next.js/Node all emit it once
                                       # piped, not a TTY) regardless of the Windows console's own active
                                       # code page. `text=True` without this decoded with that code page
                                       # instead - every box-drawing/checkmark character npm and Next.js
                                       # print came out as mojibake ("â–²" for "▲", "Æ’" for "ƒ").
                                       text=True, encoding="utf-8", errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                       start_new_session=os.name != "nt",
                                       env=getattr(self, "command_env", None))
            self.command_started(command, timeout)
            lines: queue.Queue[str | None] = queue.Queue()

            def read_output() -> None:
                assert process is not None and process.stdout is not None
                for line in iter(process.stdout.readline, ""):
                    lines.put(line)
                lines.put(None)

            threading.Thread(target=read_output, daemon=True).start()
            started = time.monotonic()
            heartbeat = 0
            reader_done = False
            while process.poll() is None or not reader_done:
                if stopped_at and process.poll() is not None and time.monotonic() - stopped_at > 2:
                    break  # stopped: a grandchild still holding the output open is not waited for
                try:
                    line = lines.get(timeout=0.25)
                    if line is None:
                        reader_done = True
                    else:
                        append(line)
                        self.command_output(line)
                except queue.Empty:
                    pass
                if (not stopped_at and callable(stop_requested) and stop_requested()
                        and process.poll() is None):
                    stopped_at = time.monotonic()
                    stop_tree(process)
                    append("Stopped: the run was stopped, and this command's process tree with it.\n")
                elapsed = int(time.monotonic() - started)
                if elapsed >= timeout and process.poll() is None:
                    timed_out = True
                    stop_tree(process)
                    append(f"Command timed out after {timeout} seconds; its child process tree was stopped.\n")
                if elapsed >= heartbeat + 8 and process.poll() is None:
                    heartbeat = elapsed
                    self.command_heartbeat(command, elapsed)
            exit_code = process.wait()
            self.command_finished(command, exit_code, timed_out)
            output = f"exit_code={exit_code}\n" + "".join(output_parts)
        except BaseException:
            # Interrupted while it ran (Ctrl+C in the terminal): its own process group would outlive us.
            if process is not None:
                stop_tree(process)
            raise
        finally:
            if self.source_guard and before is not None:
                changed = self.source_guard.restore(before)
                if changed:
                    output = (output + "\nProtected CLI source changes were reverted: " +
                              ", ".join(changed))[:MAX_OUTPUT]
                elif self.source_guard.left_alone:
                    output = (output + "\nThe app's own repository moved to a new commit while this command ran "
                              "(a pull or checkout), so its changed files were left as they are: " +
                              ", ".join(self.source_guard.left_alone[:20]))[:MAX_OUTPUT]
        return output[:MAX_OUTPUT]

    def tool_web_search(self, query: str, max_results: int = 3) -> str:
        max_results = min(max(int(max_results), 1), 10)
        if self.use_local_web:
            return self._local_web_request("web_search", {"query": query, "max_results": max_results})
        response = self.client.web_search(query=query, max_results=max_results)
        return json.dumps(response.model_dump(), ensure_ascii=False)[:MAX_OUTPUT]

    def tool_web_fetch(self, url: str) -> str:
        if not url.startswith(("https://", "http://")):
            raise ValueError("Only HTTP(S) URLs are supported")
        if self.use_local_web:
            return self._local_web_request("web_fetch", {"url": url})
        response = self.client.web_fetch(url=url)
        return json.dumps(response.model_dump(), ensure_ascii=False)[:MAX_OUTPUT]

    def tool_browser_inspect(self, url: str = "", viewport: str = "desktop") -> str:
        """Render a local preview without interacting with it or the outside web."""
        default_url = getattr(self, "browser_url", lambda: "")()
        if not url and not default_url:
            raise ValueError("No managed local preview is running. Start the Studio preview and try again.")
        result = inspect_local_page(self.root, url or default_url, viewport)
        return json.dumps(result, ensure_ascii=False)
