"""One model context per project.

The five agents — SRS, prototype, builder, QA and deploy — are not five
conversations. They are five roles taking turns in the same one, against the same
workspace, with the same model. What the SRS agent learned in the interview is
still in front of the builder; what the builder did is still in front of the
deployer. That is the whole point of this file: `ProjectSession` owns the single
`Agent` instance and hands it to whichever stage is running.

Stages never talk to Ollama directly. They call `ask_json` for a decision or
`run_task` for work, and both go through here so that every token, tool call and
file write reaches the studio's event stream.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx
import ollama

from ollama_terminal.agent import Agent
from ollama_terminal.mcp_client import NAME_PREFIX as MCP_NAME_PREFIX
from ollama_terminal.tools import WorkspaceTools, describe_call

from . import bus, config, deploy_vars, live, plugins, prompts, stage_evidence, supabase_connect


class RunCancelled(Exception):
    """Raised inside a run when the studio asked for it to stop."""


class EngineUnavailable(RuntimeError):
    """Ollama could not be reached, or the model is not usable."""


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)

# The one stage whose agent may run the app's server itself: the preview did not start, and the
# agent is starting it to find out why.
PREVIEW_START = "preview_start"

# A build stage is a long conversation with a remote service, and remote
# services have bad minutes. Losing an hour of work to one 502 is not a model
# problem to reason about, it is a call to make again.
RETRY_ATTEMPTS = 10
RETRY_BACKOFF = (2, 4, 8, 15, 20, 30, 30, 30, 30)


def _transient(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in {408, 425, 429, 500, 502, 503, 504, 522, 524}
    # ollama's client raises through httpx, whose transport-level exceptions
    # (a connection reset, a read/write timeout, "server disconnected without
    # sending a response") are not Python's own ConnectionError/OSError/
    # TimeoutError — a real one slipped through here uncaught on a live run
    # (see commit history), which is exactly the "bad minute" this exists for.
    return isinstance(exc, (ConnectionError, TimeoutError, OSError, httpx.TransportError))


class _Failure:
    """An exception raised on a reading thread, carried to the thread that waits for the reply."""

    def __init__(self, error: BaseException):
        self.error = error


class RetryingClient:
    """The Ollama client, with `chat` retried through a bad minute.

    Everything else is passed straight through, so `show`, `list`, `web_search`
    and `web_fetch` behave exactly as the engine expects.
    """

    def __init__(self, inner: Any, announce: Callable[[str], None] | None = None,
                 cancelled: Callable[[], bool] | None = None,
                 wait_for_cancel: Callable[[float], bool] | None = None):
        self._inner = inner
        self._announce = announce
        self._cancelled = cancelled
        self._wait_for_cancel = wait_for_cancel

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _raise_if_cancelled(self) -> None:
        if self._cancelled and self._cancelled():
            raise RunCancelled("The run was stopped.")

    def _interruptible(self, call: Callable[[], Any]) -> Any:
        """One blocking model request, waited on so that Stop ends the wait at once.

        A model can take minutes on one reply, and Stop used to wait for all of it. The request runs on its own
        thread; this one watches for Stop every tenth of a second and walks away from it when pressed. The
        abandoned request finishes on its own and its answer is thrown away.
        """
        if not self._cancelled:
            return call()
        box: dict[str, Any] = {}
        done = threading.Event()

        def work() -> None:
            try:
                box["value"] = call()
            except BaseException as exc:  # noqa: BLE001 - handed back to the waiting thread
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=work, name="model-request", daemon=True).start()
        while not done.wait(0.1):
            self._raise_if_cancelled()
        if "error" in box:
            raise box["error"]
        return box["value"]

    def _interruptible_stream(self, stream: Any) -> Any:
        """A streamed reply read on its own thread, so Stop ends it between tokens - or before the first one."""
        if not self._cancelled or not hasattr(stream, "__iter__"):
            return stream
        items: queue.Queue = queue.Queue()
        stopped = threading.Event()
        end = object()

        def pump() -> None:
            try:
                for chunk in stream:
                    if stopped.is_set():
                        break
                    items.put(chunk)
            except BaseException as exc:  # noqa: BLE001 - handed back to the reading thread
                items.put(_Failure(exc))
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:  # noqa: BLE001 - the reply is being abandoned anyway
                        pass
                items.put(end)

        threading.Thread(target=pump, name="model-stream", daemon=True).start()

        def read() -> Any:
            try:
                while True:
                    try:
                        item = items.get(timeout=0.1)
                    except queue.Empty:
                        self._raise_if_cancelled()
                        continue
                    if item is end:
                        return
                    if isinstance(item, _Failure):
                        raise item.error
                    yield item
                    self._raise_if_cancelled()
            finally:
                stopped.set()

        return read()

    def chat(self, **kwargs: Any) -> Any:
        last: Exception | None = None
        for attempt in range(RETRY_ATTEMPTS):
            self._raise_if_cancelled()
            try:
                if kwargs.get("stream"):
                    return self._interruptible_stream(self._inner.chat(**kwargs))
                return self._interruptible(lambda: self._inner.chat(**kwargs))
            except RunCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - re-raised below when it is not transient
                self._raise_if_cancelled()
                if not _transient(exc) or attempt == RETRY_ATTEMPTS - 1:
                    raise
                last = exc
                pause = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                if self._announce:
                    self._announce(f"[retry] Connection to the model service was interrupted "
                                   f"({str(exc)[:120]}). Retrying attempt {attempt + 2} of "
                                   f"{RETRY_ATTEMPTS} in {pause}s.")
                # ``time.sleep`` made Stop appear broken while a cloud request was
                # backing off: the longest delay is 30 seconds.  A session supplies
                # its Event.wait here, which wakes immediately when the customer
                # presses Stop; simple clients keep the old sleep behaviour.
                if self._wait_for_cancel:
                    if self._wait_for_cancel(pause):
                        raise RunCancelled("The run was stopped.")
                else:
                    time.sleep(pause)
        raise last  # pragma: no cover - the loop either returns or raises above


def extract_json(text: str) -> Any:
    """The JSON object in a model reply, however it was wrapped."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("the model returned nothing")
    fenced = _JSON_BLOCK.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    # A reply that said something before or after its object still carries one.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except ValueError:
                continue
    raise ValueError("the model did not return JSON")


class StudioTools(WorkspaceTools):
    """The engine's own tools, with every action reported to the studio."""

    def __init__(self, *args: Any, project: str, role_of: Callable[[], str], **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.project = project
        self._role_of = role_of
        # A Studio agent must never own a long-running web server.  Preview
        # startup is handled by preview_runtime, which assigns the stack's preview port.
        self.managed_preview = True

    def browser_url(self) -> str:
        """The local preview this project's browser tool may inspect."""
        from . import preview_runtime

        state = preview_runtime.status(self.project)
        return str(state.get("url") or "") if state.get("status") in {"starting", "running"} else ""

    def _relative(self, path: str) -> str | None:
        try:
            return self._path(path).relative_to(self.root).as_posix()
        except Exception:  # noqa: BLE001 - a bad path is the tool's error to report
            return None

    def _before(self, path: str) -> str | None:
        try:
            file = self._path(path)
            return file.read_text(encoding="utf-8") if file.is_file() else ""
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _display_command(command: str) -> str:
        """Keep terminal cards useful without ever copying a credential into chat."""
        return re.sub(r"(?i)(password|secret|token|api[_-]?key)\s*=\s*[^\s;&|]+",
                      r"\1=<hidden>", command)

    def command_started(self, command: str, timeout: int) -> None:
        role = self._role_of()
        bus.agent_state(self.project, "run_command", agent=role)
        bus.agent_msg(self.project, self._display_command(command), title=f"Running command · up to {timeout}s",
                      kind="command", agent=role)

    # command_output() is left at WorkspaceTools' own no-op: it used to echo
    # every line as its own `bus.log` INFO row - a raw, un-decoded, choppy
    # wall of third-party tool output (npm/Next.js's own box-drawing and
    # checkmark characters, which a plain terminal renders fine but a chat
    # bubble does not) duplicating the one clean `command_output`-kind card
    # `execute()` already posts below once the command finishes.
    # command_heartbeat() below is the "is it still alive" signal while a
    # long command runs; the complete output belongs in that one final card.

    def command_finished(self, command: str, exit_code: int, timed_out: bool) -> None:
        # Whatever the command streamed to the preview is over with it.
        live.finish(self.project)

    def command_heartbeat(self, command: str, elapsed: int) -> None:
        bus.log(self.project, "INFO",
                f"Command still running ({elapsed}s): {self._display_command(command)[:180]}",
                agent=self._role_of())

    def execute(self, name: str, args: dict[str, Any]) -> str:
        role = self._role_of()
        path = str(args.get("path") or "")
        previous = self._before(path) if name in {"write_file", "replace_text"} else None

        if name == "run_command":
            enabled = config.record_dir(self.project) / "plugins.json"
            choices = json.loads(enabled.read_text(encoding="utf-8")) if enabled.is_file() else []
            # A generated app's Playwright run streams what its browser shows to this
            # address (or, with no port to post to, this folder), and the studio's
            # preview displays it while the test runs.
            self.command_env = {**os.environ, **plugins.environment(choices),
                                **live.channel_for(self.project)}
            # A Supabase-stack project gets the one real project `supabase_connect` made for it,
            # in build, test and deploy alike - unlike the old studio-wide MongoDB setting, there is
            # no separate "the studio's own" database to fall back to here.
            self.command_env.update(supabase_connect.env_for(self.project))
            stage = session_for(self.project).stage
            # Starting the app is that stage's whole job (the preview would not start); everywhere
            # else the Studio's preview runtime owns the app's server.
            self.managed_preview = stage != PREVIEW_START
            if stage.startswith("deploy") or stage in {"build", "build-edit", PREVIEW_START}:
                # A deployment may also override with what the customer saved for it explicitly
                # (pointing production at a different Supabase project, or an unrelated variable);
                # a build/update needs the same saved values (a database connection string, a key the
                # customer gave before the plan) reachable by its own commands and the preview.
                self.command_env.update(deploy_vars.environment())
        result = super().execute(name, args)

        relative = self._relative(path) if path else None
        sensitive = bool(relative and (Path(relative).name in {".env", ".env.local", ".env.production"}
                                       or Path(relative).name.endswith(".secret")))
        if result.startswith("Tool error"):
            bus.log(self.project, "WARN", f"{describe_call(name, args)} — {result}", agent=role)
        elif relative and sensitive and name in {"write_file", "replace_text"}:
            bus.log(self.project, "INFO", f"Written {relative} (content hidden)", agent=role)
        elif relative and name in {"write_file", "replace_text"} and not result.startswith("Tool error"):
            after = self._before(path)
            if after is not None:
                bus.file_written(self.project, relative, after, old=previous,
                                 note="written" if name == "write_file" else "patched",
                                 agent=role)
        elif relative and name == "read_file" and not sensitive and not result.startswith("Tool error"):
            bus.file_read(self.project, relative, result, agent=role)
            bus.log(self.project, "INFO",
                    f"Read {relative} ({len(result.splitlines())} lines)", agent=role)
        elif name == "list_files":
            bus.log(self.project, "INFO", f"Listed {path or '.'}", agent=role)
        elif name == "search_text":
            query = str(args.get("query") or "")
            where = str(args.get("path") or ".")
            bus.log(self.project, "INFO", f'Searched for "{query}" in {where}', agent=role)
        elif name == "web_search":
            bus.log(self.project, "INFO",
                    f'Searched the web for "{str(args.get("query") or "")}"', agent=role)
        elif name == "web_fetch":
            bus.log(self.project, "INFO",
                    f'Read web page {str(args.get("url") or "")}', agent=role)
        elif name == "browser_inspect":
            try:
                inspected = json.loads(result)
                layout = inspected.get("layout") or {}
                bus.agent_msg(self.project,
                              f"{inspected.get('title') or inspected.get('url') or 'Page'} · "
                              f"{args.get('viewport') or 'desktop'} · screenshot saved\n"
                              f"overflow: {bool(layout.get('horizontalOverflow'))}; "
                              f"broken images: {len(layout.get('brokenImages') or [])}; "
                              f"pending images: {len(layout.get('pendingImages') or [])}; "
                              f"clipped labels: {len(layout.get('clippedLabels') or [])}",
                              title="Browser inspection", kind="browser_inspection", agent=role)
            except (TypeError, ValueError):
                bus.log(self.project, "WARN", "Browser inspection returned an unreadable result.", agent=role)
        elif name.startswith(MCP_NAME_PREFIX) and not result.startswith("Tool error"):
            bus.agent_msg(self.project, result[:2000], title=f"MCP · {name[len(MCP_NAME_PREFIX):]}",
                          kind="mcp_result", agent=role)
        elif name == "run_command":
            exit_code = result.split("\n", 1)[0] if result.startswith("exit_code=") else ""
            output = result.split("\n", 1)[1] if "\n" in result else result
            bus.agent_msg(self.project, output or "(No output)",
                          title=f"Command output · {exit_code or 'not started'}",
                          kind="command_output", agent=role)
        session = session_for(self.project)
        if session._agent is not None:
            session.report_memory()
        return result


class ProjectSession:
    """The one conversation, the one workspace, the one model, for one project."""

    def __init__(self, project: str):
        self.project = project
        self.workspace = config.workspace_for(project)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.record = self.workspace / config.RECORD_DIR
        self.record.mkdir(parents=True, exist_ok=True)

        self.lock = threading.RLock()
        self.role = bus.DEVELOPER
        self.stage = "idle"
        self._cancel = threading.Event()
        # A deleted project can still have a model request unwinding in a
        # background thread.  Marking its session disposed makes every later
        # write a no-op/cancellation instead of quietly recreating its folder.
        self._discarded = threading.Event()
        self._agent: Agent | None = None
        self._model = ""
        self._thinking_level = ""
        self._turn_started_at = 0
        self._turn_prompt_base = 0
        self._turn_completion_base = 0
        # Stage notes recorded before anything opened the conversation — the
        # interview runs long before a tool-using stage creates the agent. Kept on
        # disk as well: a backend restart between the interview and the prototype
        # used to lose every one of them.
        self._pending_notes: list[str] = self._load_pending_notes()

    # --- the engine ---------------------------------------------------------

    def _client(self) -> Any:
        saved = config.settings()
        if saved.get("cloud"):
            from . import ollama_cloud

            try:
                inner = ollama_cloud.for_engine(saved)
            except ValueError as exc:
                raise EngineUnavailable(str(exc)) from exc
        else:
            inner = ollama.Client(host=saved.get("ollama_host") or "http://localhost:11434")
        return RetryingClient(inner, announce=self._announce,
                              cancelled=lambda: self.cancelled,
                              wait_for_cancel=self._cancel.wait)

    def _announce(self, line: str) -> None:
        """What the engine narrates, as the studio's own log and state."""
        if self.cancelled:
            raise RunCancelled(self.project)
        text = str(line or "")
        if text.startswith("[tool] "):
            tool = text[7:].split(" ", 1)[0]
            # In plan mode an inspection tool is part of the live reasoning
            # trail.  Keep the planning indicator alive while the readable
            # file/search event below carries the exact path or query.
            planning = bool(self._agent is not None and self._agent.mode == "plan")
            bus.agent_state(self.project, tool, thinking=planning, agent=self.role)
            # Inspection tools are announced after execution with a clean,
            # human-readable path/query and, for files, an expandable read card.
            if tool not in {"read_file", "list_files", "search_text", "web_search", "web_fetch"}:
                bus.log(self.project, "INFO", text, agent=self.role)
        elif text.startswith("[result] "):
            # StudioTools reports the useful result (file read, search, write,
            # command, or error). Raw result excerpts duplicate it and can leak
            # hundreds of characters of code into the conversation stream.
            return
        elif text.startswith("[assistant] "):
            answer = text[12:].strip()
            if answer:
                bus.agent_msg(self.project, answer, title="Agent update", kind="narration",
                              agent=self.role)
        elif text.startswith("[thinking]"):
            bus.agent_state(self.project, "thinking", thinking=True, agent=self.role)
        elif text.startswith("[compacting] "):
            # The history is being summarized to fit the model's window: no model turn, no tool, often
            # minutes. How far along it is ("12/35", "merging 35") is what keeps it from looking stuck.
            bus.agent_state(self.project, "compacting", thinking=True, agent=self.role, detail=text[13:].strip())
        elif text.startswith("[usage]"):
            # This is emitted only after the provider has returned its exact
            # counters for a response.  It keeps the visual meter truthful.
            self.report_memory()
        elif text.startswith("[progress] ") or text.startswith("[context] "):
            bus.log(self.project, "INFO", text, agent=self.role)
        else:
            bus.log(self.project, "INFO", text, agent=self.role)

    def _saved_context_preferences(self) -> tuple[str, str]:
        """Read only the persisted choices, never treating a bad checkpoint as fatal."""
        try:
            saved = json.loads(self._context_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "", ""
        if not isinstance(saved, dict):
            return "", ""
        model = str(saved.get("model") or "").strip()
        level = str(saved.get("thinking_level") or "").strip().lower()
        return model, level if level in config.THINKING_LEVELS else ""

    def _apply_effort(self, agent: Agent, level: str) -> None:
        """Keep provider reasoning and our explicit verification rule aligned."""
        agent.set_reasoning_level(level)
        agent.think = config.thinking_enabled({"thinking_level": level})
        agent.base_system = self._system(level)
        agent.messages[0]["content"] = agent._system_message()

    def agent(self, model: str = "", thinking_level: str = "") -> Agent:
        """The single agent for this project, created once and then reused."""
        saved = config.settings()
        saved_model, saved_level = self._saved_context_preferences() if self._agent is None else ("", "")
        wanted = (model or (saved_model if self._agent is None else "") or saved.get("model") or "").strip()
        requested_level = str(thinking_level or "").strip().lower()
        level = (requested_level if requested_level in config.THINKING_LEVELS
                 else (saved_level if self._agent is None and saved_level else config.thinking(saved)))
        if not wanted:
            raise EngineUnavailable(
                "No model is selected. Pick one in the studio before starting.")

        with self.lock:
            if self._agent is None:
                client = self._client()
                context = int(saved.get("context") or 0) or None
                self._agent = Agent(
                    client=client,
                    model=wanted,
                    workspace=self.workspace,
                    approve=lambda _question: not self.cancelled,
                    context=context,
                    cloud=bool(saved.get("cloud")),
                    max_steps=int(saved.get("max_steps") or 40),
                    announce=self._announce,
                    web_host=saved.get("ollama_host") or "http://localhost:11434",
                    protected_app_root=config.ROOT,
                    mcp_servers=saved.get("mcp_servers") or None,
                    on_summarize=self._archive_summary,
                )
                self._agent.tools = StudioTools(
                    self.workspace, client,
                    lambda _question: not self.cancelled,
                    web_host=saved.get("ollama_host") or "http://localhost:11434",
                    use_local_web=not bool(saved.get("cloud")),
                    protected_app_root=config.ROOT,
                    project=self.project,
                    role_of=lambda: self.role,
                    mcp=self._agent.mcp,
                )
                # A command running when Stop is pressed is stopped with its process tree, not waited for.
                self._agent.tools.stop_requested = lambda: self.cancelled
                self._apply_effort(self._agent, level)
                self._model = wanted
                self._thinking_level = level
                self._restore_context()
                # Everything the earlier stages recorded before this existed. The
                # interview and the specification run long before any tool-using
                # stage opens the conversation.
                for note in self._pending_notes:
                    self._agent.messages.append({"role": "user", "content": note})
                    self._agent.messages.append({"role": "assistant", "content": "Noted."})
                if self._pending_notes:
                    self._pending_notes.clear()
                    self.save_context()
                    self._save_pending_notes()
            elif wanted != self._model:
                # Switching the model keeps the conversation: the context is the
                # project's, not the model's.
                self._agent.set_model(self._client(), wanted, bool(saved.get("cloud")))
                self._model = wanted
            self._thinking_level = level
            self._apply_effort(self._agent, level)
            return self._agent

    def _system(self, thinking_level: str = "") -> str:
        guidance = ("8. Verify with a read tool before you answer or act — check the file, "
                    "the current route, the actual data — rather than proceeding on an assumption."
                    if config.thinking_encourages_tools({"thinking_level": thinking_level or config.thinking()}) else "")
        if thinking_level == "xhigh":
            guidance += ("\n9. EXTRA-HIGH EFFORT: after implementation, independently re-read the changed "
                         "files and run the smallest relevant verification before reporting success.")
        return (prompts.load("shared/engine", workspace=str(self.workspace), thinking_guidance=guidance)
                + f"\n\nWorkspace: {self.workspace}\nProject: {self.project}")

    # --- keeping the one context across restarts ---------------------------

    def _context_file(self) -> Path:
        return self.record / "context.json"

    def _restore_context(self) -> None:
        """Bring back the conversation a previous run of the server was having.

        The whole design is one context per project, and a context that only
        exists in memory is one the customer loses by closing the app. The
        system message is rebuilt rather than restored, so an edited prompt pack
        takes effect on the next start.
        """
        saved = self._context_file()
        if not saved.is_file() or self._agent is None:
            return
        try:
            data = json.loads(saved.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return
        kept = [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]
        self._agent.messages = [self._agent.messages[0]] + kept
        self._agent.memory_summary = str(data.get("memory_summary") or "")
        self._agent.tool_call_count = int(data.get("tool_calls") or 0)
        bus.log(self.project, "INFO",
                f"Picked the conversation back up ({len(kept)} earlier turns).",
                agent=self.role)

    def _archive_path(self) -> Path:
        return self.record / "context-archive.jsonl"

    def _archive_summary(self, old: list[dict]) -> None:
        """Keep what context compression is about to delete, somewhere that never gets trimmed.

        The live conversation has to fit the active model's window, so `_summarize_history()`
        condenses older turns into a short `memory_summary` and deletes the originals from
        `self.messages` — correct for keeping the conversation usable, but without this it is
        also the one point where the project's own history (the interview's exact answers, the
        SRS's exact wording, an earlier stage's exact decision) becomes unrecoverable. This
        appends the deleted turns, verbatim, to one growing file per project, so the detail
        survives model switches and long projects even though the working conversation does not
        carry it forward turn by turn.
        """
        if self._is_discarded() or not old:
            return
        try:
            self._archive_path().parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps({"at": time.time(), "stage": self.stage, "model": self._model,
                               "messages": old}, ensure_ascii=False, default=str)
            with self._archive_path().open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except (OSError, TypeError, ValueError):
            # Same posture as save_context(): a line that cannot be written is not a
            # reason to break the turn that is already in progress.
            pass

    def save_context(self) -> None:
        if self._agent is None or self._is_discarded():
            return
        try:
            self._context_file().parent.mkdir(parents=True, exist_ok=True)
            self._context_file().write_text(json.dumps({
                "model": self._model,
                "thinking_level": self._thinking_level,
                "memory_summary": self._agent.memory_summary,
                "tool_calls": self._agent.tool_call_count,
                "messages": self._agent.messages,
            }, ensure_ascii=False, default=str), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            # A context that cannot be written is a context this run still has.
            pass

    # --- running ------------------------------------------------------------

    def begin(self, stage: str, role: str = bus.DEVELOPER, run_id: str = "") -> None:
        if self._is_discarded():
            raise RunCancelled(self.project)
        self._cancel.clear()
        from . import llm

        llm.bind_stop(self._cancel)  # the direct model calls this run makes honour its Stop too
        if stage_evidence.was_interrupted(self.project, stage):
            bus.log(self.project, "WARN",
                    f"the previous {stage.replace('_', ' ')} run did not finish "
                    f"(the server stopped mid-run) — starting a fresh one now.", agent=role)
        stage_evidence.begin(self.project, stage)
        self.stage = stage
        self.role = role
        self._turn_started_at = int(time.time() * 1000)
        existing = self._agent
        self._turn_prompt_base = int(getattr(existing, "prompt_tokens", 0) or 0)
        self._turn_completion_base = int(getattr(existing, "completion_tokens", 0) or 0)
        bus.run_state(self.project, "running", run_id=run_id or stage, agent=role)
        bus.phase(self.project, stage, stage.replace("_", " ").title(), status="active")

    def finish(self, text: str = "") -> None:
        if self.cancelled:
            self.stage = "idle"
            raise RunCancelled(self.project)
        stage_evidence.finish(self.project, self.stage, text)
        bus.phase(self.project, self.stage, self.stage.replace("_", " ").title(),
                  status="complete")
        bus.done(self.project, text, agent=self.role)
        self.save_context()
        self.stage = "idle"

    def fail(self, text: str) -> None:
        # Cancellation is an expected pause, not a failed build.  The outer
        # worker turns it into the single durable ``cancelled`` event.
        if self.cancelled:
            self.stage = "idle"
            if not self._is_discarded():
                self.save_context()
            return
        stage_evidence.fail(self.project, self.stage, text)
        bus.phase(self.project, self.stage, self.stage.replace("_", " ").title(),
                  status="failed", detail=text[:300])
        bus.failed(self.project, text, agent=self.role)
        self.save_context()
        self.stage = "idle"

    def cancel(self) -> None:
        self._cancel.set()

    def _is_discarded(self) -> bool:
        """Whether deletion retired this session.

        A few narrow integrations construct a lightweight ``ProjectSession``
        via ``__new__`` and provide only the fields they exercise. Treating a
        missing deletion flag as active keeps those non-persistent planning
        paths compatible while regular sessions still get the deletion guard.
        """
        discarded = getattr(self, "_discarded", None)
        return bool(discarded and discarded.is_set())

    def discard(self) -> None:
        """Permanently stop this in-memory session after project deletion."""
        self._discarded.set()
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set() or self._is_discarded()

    def report_memory(self) -> None:
        agent = self._agent
        if not agent:
            return
        prompt_total = int(getattr(agent, "prompt_tokens", 0) or 0)
        completion_total = int(getattr(agent, "completion_tokens", 0) or 0)
        bus.memory(self.project, agent.model, agent.context_usage(),
                   agent.context or 0, agent.tool_call_count, agent=self.role,
                   turn_started_at=int(getattr(self, "_turn_started_at", 0) or 0),
                   turn_input_tokens=max(0, prompt_total - int(getattr(self, "_turn_prompt_base", 0) or 0)),
                   turn_output_tokens=max(0, completion_total - int(getattr(self, "_turn_completion_base", 0) or 0)))

    def note(self, text: str, role: str = "") -> None:
        """Record something into the project's memory without asking the model.

        Most of what a project knows is not produced by the shared conversation
        any more: the interview, the plan, the specification, the diagrams and
        the wireframes are focused calls, because one conversation writing
        fourteen pages truncates them. But they are still this project's
        knowledge, and the stages that DO use the conversation — the prototype,
        the build, the tests, the deployment — have to inherit it.

        So each stage writes its outcome here as a plain turn. It costs no model
        call, it persists with the rest of the context, and it is what makes the
        one context span all six stages rather than only the tool-using ones.
        """
        body = str(text or "").strip()
        if not body or self._is_discarded():
            return
        agent = self._agent
        if agent is None:
            # Nothing has opened the conversation yet; keep it for when it does.
            self._pending_notes.append(body)
            self._save_pending_notes()
            return
        with self.lock:
            agent.messages.append({"role": "user", "content": body})
            agent.messages.append(
                {"role": "assistant", "content": "Noted."})
        self.save_context()
        self.report_memory()
        bus.log(self.project, "DEBUG", f"[memory] {body[:160]}",
                agent=role or self.role)

    def _pending_file(self) -> Path:
        return self.record / "pending-notes.json"

    def _load_pending_notes(self) -> list[str]:
        try:
            saved = json.loads(self._pending_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [str(note) for note in saved if str(note).strip()] if isinstance(saved, list) else []

    def _save_pending_notes(self) -> None:
        """The notes still waiting for the conversation, or no file once there are none."""
        try:
            if self._pending_notes:
                self._pending_file().write_text(json.dumps(self._pending_notes, ensure_ascii=False),
                                                encoding="utf-8")
            else:
                self._pending_file().unlink(missing_ok=True)
        except OSError:
            # Same posture as save_context(): the notes are still held in memory.
            pass

    def memory_digest(self, limit: int = 24000) -> str:
        """What this project knows, for a focused call that has no conversation.

        The focused calls are stateless by design. This is how they still get the
        project's own history — the same text the shared conversation holds,
        trimmed to what fits.
        """
        agent = self._agent
        parts: list[str] = []
        if agent is not None:
            if agent.memory_summary:
                parts.append(agent.memory_summary)
            for message in agent.messages[1:]:
                if message.get("role") == "user":
                    content = str(message.get("content") or "").strip()
                    if content and content != "Noted.":
                        parts.append(content)
        parts.extend(self._pending_notes)
        joined = "\n\n".join(parts[-40:]).strip()
        return joined[-limit:] if len(joined) > limit else joined

    def ask_text(self, prompt: str, model: str = "") -> str:
        """One turn in the shared conversation, answered in prose."""
        agent = self.agent(model)
        with self.lock:
            answer = agent.ask(prompt)
        self.report_memory()
        self.save_context()
        return answer or ""

    def ask_json(self, prompt: str, validator: Callable[[Any], Any] | None = None,
                 model: str = "", attempts: int = 3) -> Any:
        """One turn answered as JSON, repaired in-context when it is not.

        The repair stays in the same conversation on purpose: the model sees its
        own broken answer and what was wrong with it, which is what makes the
        second attempt different from the first.
        """
        agent = self.agent(model)
        message = prompt
        last = ""
        for attempt in range(max(1, attempts)):
            if self.cancelled:
                raise RunCancelled(self.project)
            with self.lock:
                last = agent.ask(message) or ""
            self.report_memory()
            self.save_context()
            try:
                data = extract_json(last)
            except ValueError as exc:
                message = (f"That was not valid JSON ({exc}). Return ONLY the JSON "
                           "object this task asked for — no prose, no markdown "
                           "fence, nothing before or after it.")
                continue
            if validator is None:
                return data
            try:
                checked = validator(data)
            except Exception as exc:  # noqa: BLE001 - the validator's message is the repair
                message = (f"That JSON did not pass validation: {exc}\n\n"
                           "Fix exactly that and return the corrected JSON object "
                           "in full.")
                continue
            return data if checked is None else checked
        raise ValueError(f"the model could not produce valid JSON after "
                         f"{attempts} attempts: {last[:300]}")

    def run_task(self, request: str, model: str = "", thinking_level: str = "", plan_directory: str = "",
                 audit: bool = False, parallel_write_limit: int = 1) -> dict[str, Any]:
        """Plan silently, then carry the plan out.

        The CLI shows its plan and waits for a person. Here nobody is waiting: the
        studio already approved this stage by starting it, so the plan is produced
        and immediately executed in the same conversation. Callers may skip the
        extra audit pass when later phases already provide the relevant checks.
        """
        # Keep the one-argument call shape for lightweight adapters/tests that
        # provide an ``agent(model)`` callable. A real chat turn passes the
        # explicit level; all older stage callers continue to use the saved
        # preference without a compatibility break.
        agent = self.agent(model, thinking_level) if thinking_level else self.agent(model)
        if self.cancelled:
            raise RunCancelled(self.project)

        bus.agent_state(self.project, "planning", thinking=True, agent=self.role)
        bus.log(self.project, "INFO",
                "Planning: reviewing the project context and choosing the files to inspect.",
                agent=self.role)
        with self.lock:
            agent.set_mode("plan")
            plan = agent.ask(request) or ""
        if self.cancelled:
            raise RunCancelled(self.project)
        plan_file = ""
        if plan_directory and plan.strip():
            # Keep each run's plan in the output app. A restarted run still plans
            # afresh, but the earlier plan remains available to inspect.
            folder = self.workspace / plan_directory
            folder.mkdir(parents=True, exist_ok=True)
            versions = [int(match.group(1)) for path in folder.glob("developmentplan*.md")
                        if (match := re.fullmatch(r"developmentplan([1-9][0-9]*)\.md", path.name))]
            path = folder / f"developmentplan{max(versions, default=0) + 1}.md"
            path.write_text(plan, encoding="utf-8")
            plan_file = path.relative_to(self.workspace).as_posix()
        self.report_memory()
        self.save_context()
        bus.log(self.project, "INFO", "Plan ready — carrying it out.", agent=self.role)

        if self.cancelled:
            raise RunCancelled(self.project)

        bus.agent_state(self.project, "building", agent=self.role)
        with self.lock:
            execution_request = request
            if plan_file:
                execution_request += ("\n\nThis run's approved plan is saved at " + plan_file
                                      + ". Read it once before execution. At a milestone boundary, "
                                      "reopen only the relevant section when the next requirement is "
                                      "uncertain. After the final milestone, do not reopen the plan; "
                                      "finish the task immediately.")
            result = agent.execute_plan(execution_request, plan, audit=audit,
                                        parallel_write_limit=parallel_write_limit)
        self.report_memory()
        self.save_context()
        bus.agent_state(self.project, "", agent=self.role)
        return {"plan": plan, "plan_file": plan_file, "status": result.status,
                "text": result.text, "rounds": result.rounds}

    def execute_approved(self, request: str, plan: str, model: str = "") -> dict[str, Any]:
        """Carry out a plan the customer has already approved.

        `run_task` plans and executes in one go because nobody is waiting on the plan.
        Here somebody was: the plan was shown, revised and approved in the chat, so
        only the second half runs.
        """
        agent = self.agent(model)
        if self.cancelled:
            raise RunCancelled(self.project)
        bus.agent_state(self.project, "building", agent=self.role)
        try:
            with self.lock:
                result = agent.execute_plan(request, plan, audit=False)
        finally:
            bus.agent_state(self.project, "", agent=self.role)
            self.report_memory()
            self.save_context()
        if self.cancelled:
            raise RunCancelled(self.project)
        return {"status": result.status, "text": result.text, "rounds": result.rounds}

    def run_direct(self, request: str, model: str = "") -> dict[str, Any]:
        """Carry out a small approved update without creating a separate plan.

        Prototype and wireframe edits are already scoped by the page or artifact
        the customer is editing. Planning them again adds latency and produces a
        noisy stream without changing the decision, so these edits go straight
        to execution.
        """
        result = self.run_unplanned(
            "Apply this approved update directly in the workspace. Use the file tools, "
            "keep the scope exact, do not create or run tests, and do not perform a "
            "separate verification pass.\n\n" + request, model)
        return {**result, "text": result["text"] or "Update applied."}

    def run_unplanned(self, request: str, model: str = "") -> dict[str, Any]:
        """One turn with every tool and no plan: the request already says exactly what to do."""
        agent = self.agent(model)
        if self.cancelled:
            raise RunCancelled(self.project)
        bus.agent_state(self.project, "building", agent=self.role)
        try:
            with self.lock:
                agent.set_mode("act")
                text = agent.ask(request)
        finally:
            bus.agent_state(self.project, "", agent=self.role)
            self.report_memory()
            self.save_context()
        if self.cancelled:
            raise RunCancelled(self.project)
        return {"status": "complete", "text": text or "", "rounds": 1}

    def plan_focused_task(self, request: str, model: str = "", subject: str = "the pages") -> str:
        """Use the agent's /plan mode before a focused, per-file generation run.

        The caller executes the approved plan with independent model calls, so
        large multi-page outputs are not constrained by the tool-agent step cap.
        """
        agent = self.agent(model)
        if self.cancelled:
            raise RunCancelled(self.project)
        bus.agent_state(self.project, "planning", thinking=True, agent=self.role)
        bus.log(self.project, "INFO",
                "Planning: reviewing the handoff context and choosing the files to inspect.",
                agent=self.role)
        with self.lock:
            agent.set_mode("plan")
            try:
                plan = agent.ask(request) or ""
            finally:
                agent.set_mode("act")
        if self.cancelled:
            raise RunCancelled(self.project)
        self.report_memory()
        self.save_context()
        if self.cancelled:
            raise RunCancelled(self.project)
        if not plan.strip():
            raise ValueError("the plan was empty")
        bus.log(self.project, "INFO", f"Plan ready — approved automatically; drawing {subject}.",
                agent=self.role)
        return plan

    # --- the project's own record ------------------------------------------

    def record_path(self, *parts: str) -> Path:
        if self.cancelled:
            raise RunCancelled(self.project)
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def read_record(self, *parts: str, fallback: Any = None) -> Any:
        path = self.record.joinpath(*parts)
        if not path.is_file():
            return fallback
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return fallback
        if path.suffix == ".json":
            try:
                return json.loads(text)
            except ValueError:
                return fallback
        return text

    def write_record(self, *parts: str, data: Any) -> Path:
        path = self.record_path(*parts)
        payload = (json.dumps(data, ensure_ascii=False, indent=2)
                   if path.suffix == ".json" else str(data))
        # Readers run in separate HTTP threads.  Replacing a fully-written
        # sibling is atomic, unlike writing straight into the live JSON file,
        # so a refresh can never parse an incomplete interview (or any other
        # project record) while another request is saving it.
        temporary = path.with_name(f".{path.name}.{threading.get_ident()}.{time.time_ns()}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        try:
            os.replace(temporary, path)
        finally:
            # os.replace removes it on success.  Keep a failed save from
            # accumulating hidden files without ever touching the last good
            # record.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return path


_sessions: dict[str, ProjectSession] = {}
_sessions_lock = threading.RLock()
_discarded_projects: set[str] = set()


def session_for(project: str) -> ProjectSession:
    with _sessions_lock:
        # A stale worker may call a helper that looks the session up again
        # after deletion.  Refuse instead of creating a brand-new workspace.
        if project in _discarded_projects:
            raise RunCancelled(project)
        found = _sessions.get(project)
        if found is None:
            found = ProjectSession(project)
            _sessions[project] = found
        return found


def drop(project: str) -> None:
    with _sessions_lock:
        found = _sessions.pop(project, None)
        if found is not None:
            found.discard()
        _discarded_projects.add(project)
    bus.forget(project)
