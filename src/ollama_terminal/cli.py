"""Command line entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .agent import Agent


def _app_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file() and (candidate / "start.bat").is_file():
        return candidate
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oterm", description="Ollama terminal coding agent")
    parser.add_argument("prompt", nargs="*", help="One-shot prompt; omit for an interactive session")
    parser.add_argument("--model", help="Model name (default depends on --cloud)")
    parser.add_argument("--cloud", action="store_true", help="Use Ollama's direct cloud API")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                        help="Local Ollama server URL")
    parser.add_argument("--context", type=int, help="Context tokens; default uses model metadata")
    parser.add_argument("--workspace", type=Path, help="Project workspace (default: ./workspaces when run from the CLI folder)")
    parser.add_argument("--yes", action="store_true", help="Approve the plan automatically")
    parser.add_argument("--max-steps", type=int, default=20, help="Tool turns per prompt (default: 20)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.context is not None and args.context < 1024:
        print("--context must be at least 1024", file=sys.stderr)
        return 2
    if args.max_steps < 1:
        print("--max-steps must be positive", file=sys.stderr)
        return 2
    app_root = _app_root()
    workspace = (args.workspace or
                 (app_root / "workspaces" if app_root and Path.cwd().resolve() == app_root else Path.cwd())).resolve()
    if app_root and (workspace == app_root or app_root.is_relative_to(workspace)):
        print("Choose a project workspace separate from the CLI source.", file=sys.stderr)
        return 2
    if app_root and (workspace == app_root / "src" or workspace == app_root / "tests" or
                     workspace.is_relative_to(app_root / "src") or
                     workspace.is_relative_to(app_root / "tests")):
        print("The CLI source and tests cannot be used as the project workspace.", file=sys.stderr)
        return 2
    if args.workspace is None and app_root and workspace == app_root / "workspaces":
        workspace.mkdir(exist_ok=True)
    if not workspace.is_dir():
        print(f"Workspace does not exist: {workspace}", file=sys.stderr)
        return 2
    key = os.getenv("OLLAMA_API_KEY")
    if args.cloud and not key:
        print("--cloud requires OLLAMA_API_KEY", file=sys.stderr)
        return 2
    try:
        from ollama import Client
    except ImportError:
        print("Install dependencies: pip install -e .", file=sys.stderr)
        return 2
    host = "https://ollama.com" if args.cloud else args.host
    headers = {"Authorization": f"Bearer {key}"} if key else None
    client = Client(host=host, headers=headers)
    model = args.model or ("gpt-oss:120b" if args.cloud else "gpt-oss:120b-cloud")

    approved_plan_active = False
    pending_plan: tuple[str, str] | None = None

    def approve(question: str) -> bool:
        return approved_plan_active

    def confirm_plan() -> bool:
        if args.yes:
            return True
        if not sys.stdin.isatty():
            print("Plan awaiting approval. Rerun with --yes for non-interactive execution.")
            return False
        return input("\nApprove this plan and allow its commands and file edits? [y/start/N] ").strip().lower() in {"y", "yes", "start", "go"}

    agent = Agent(client, model, workspace, approve, context=args.context,
                  cloud=args.cloud, max_steps=args.max_steps, web_host=args.host,
                  protected_app_root=app_root)
    print(f"Ollama terminal | model={model} | host={host} | context={agent.context or 'server default'}")
    print("Web tools: local Ollama" if not args.cloud else "Web tools: Ollama cloud API")
    print(f"Project workspace: {workspace}")

    def run_approved_plan() -> str:
        nonlocal approved_plan_active, pending_plan
        if pending_plan is None:
            print("No plan to approve. Describe the task first.")
            return "no_plan"
        if not confirm_plan():
            print("Plan remains pending. Use /approve when ready.")
            return "waiting"
        request, plan = pending_plan
        approved_plan_active = True
        try:
            result = agent.execute_plan(request, plan)
            print(result.text)
            print(f"Plan status: {result.status} ({result.rounds} round(s))")
            if result.status == "complete":
                pending_plan = None
            return result.status
        finally:
            approved_plan_active = False
            agent.set_mode("plan")

    try:
        if args.prompt:
            request = " ".join(args.prompt)
            plan = agent.ask(request)
            print(plan)
            pending_plan = (request, plan)
            outcome = run_approved_plan()
            return 0 if outcome == "complete" else 3 if outcome == "waiting" else 1
        print("Type /help for commands, /exit to quit.")
        while True:
            try:
                prompt = input("\noterm> ").strip()
            except EOFError:
                break
            if prompt in {"/exit", "/quit"}:
                break
            if prompt == "/help":
                print("/models  list models | /model NAME  select model | /cloud  direct cloud API | "
                      "/local  local Ollama | /plan  make a plan | /approve or /act  approve and execute | "
                      "/context [N]  show/set context | /memory  show summary | /exit  quit")
                continue
            if prompt == "/plan":
                agent.set_mode("plan")
                print("Mode: plan. Describe the task; the plan will be shown for approval.")
                continue
            if prompt in {"/approve", "/act"}:
                run_approved_plan()
                continue
            if prompt == "/context":
                print(f"Model: {agent.model}; mode: {agent.mode}; context: "
                      f"{agent.context or 'server default'} tokens; estimated use: "
                      f"{agent.context_usage()} tokens; messages: {len(agent.messages)}")
                continue
            if prompt == "/memory":
                print(agent.memory_summary or "No summary yet; full conversation is still in context.")
                continue
            if prompt.startswith("/context "):
                try:
                    agent.set_context(int(prompt.split(maxsplit=1)[1]))
                    print(f"Context: {agent.context} tokens")
                except ValueError as exc:
                    print(f"Invalid context: {exc}")
                continue
            if prompt in {"/cloud", "/local"}:
                new_cloud = prompt == "/cloud"
                if new_cloud and not key:
                    print("/cloud requires OLLAMA_API_KEY")
                    continue
                new_host = "https://ollama.com" if new_cloud else args.host
                new_client = Client(host=new_host, headers=headers)
                new_model = "gpt-oss:120b" if new_cloud else "gpt-oss:120b-cloud"
                old_client = client
                client = new_client
                agent.set_model(client, new_model, new_cloud)
                old_client.close()
                print(f"Backend: {new_host}; model: {new_model}. Use /models to list choices.")
                continue
            if prompt == "/models" or prompt == "/model":
                try:
                    available = sorted({item.model or item.name for item in client.list().models
                                        if item.model or item.name})
                    for index, name in enumerate(available, 1):
                        print(f"{index:3}. {name}")
                    if not available:
                        print("No models reported by this backend.")
                    if prompt == "/model" and available:
                        choice = input("Choose a model number or name (Enter to cancel): ").strip()
                        if choice:
                            selected = available[int(choice) - 1] if choice.isdigit() else choice
                            if selected not in available:
                                print("Model not in list. Use /model NAME to select it directly.")
                            else:
                                agent.set_model(client, selected, agent.cloud)
                                print(f"Model: {selected}; context: {agent.context or 'server default'}")
                except (ValueError, IndexError):
                    print("Invalid model selection")
                except Exception as exc:
                    print(f"Cannot list models: {exc}")
                continue
            if prompt.startswith("/model "):
                selected = prompt[7:].strip()
                if selected:
                    agent.set_model(client, selected, agent.cloud)
                    print(f"Model: {selected}; context: {agent.context or 'server default'}")
                continue
            if prompt.startswith("/"):
                print("Unknown command. Type /help.")
                continue
            if prompt:
                plan = agent.ask(prompt)
                print(plan)
                pending_plan = (prompt, plan)
                run_approved_plan()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Ollama error: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
