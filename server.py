#!/usr/bin/env python3
"""Start the studio's backend.

Two listeners: the API on 7824 and the live feed on 7825, which is exactly what
`studio/next.config.js` proxies `/__agentforge/api` and `/__agentforge/ws` to.
Run the studio itself with `npm run dev` inside `studio/`.

`server.py --stdio` is the desktop app's backend instead: nothing listens, and the app
talks to it over stdin/stdout (server_modules/stdio_bridge.py).
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

if "--stdio" in sys.argv:
    # Decided before anything is imported: what a project's own commands can reach depends on it.
    os.environ["AGENTFORGE_TRANSPORT"] = "stdio"

ROOT = Path(__file__).resolve().parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent",
               "qa-agent", "deploy-agent"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

# `.deps` is where this workspace keeps its packages when it was not pip-installed.
_deps = ROOT / ".deps"
if _deps.is_dir() and str(_deps) not in sys.path:
    sys.path.insert(0, str(_deps))

from server_modules import config, httpd, runs, wsd  # noqa: E402


def main() -> int:
    config.STATE.mkdir(parents=True, exist_ok=True)
    config.WORKSPACES.mkdir(parents=True, exist_ok=True)

    if config.TRANSPORT == "stdio":
        from server_modules import stdio_bridge

        return stdio_bridge.serve()

    feed = wsd.FeedServer(handler=runs.handle, port=config.WS_PORT)
    feed.start()

    api = httpd.serve(config.API_PORT)
    threading.Thread(target=api.serve_forever, name="api", daemon=True).start()

    print(f"AgentForge backend")
    print(f"  API   http://127.0.0.1:{config.API_PORT}{config.API_PREFIX}")
    print(f"  Feed  ws://127.0.0.1:{config.WS_PORT}")
    print(f"  Work  {config.WORKSPACES}")
    print(f"  Prompts {config.PROMPTS}")
    print()
    print("Now start the studio:  cd studio && npm run dev")
    print("Then open:             http://127.0.0.1:3000/__agentforge")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        feed.stop()
        api.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
