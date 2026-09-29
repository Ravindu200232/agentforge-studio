"""Signing in to GitHub, AWS, Vercel, Netlify and Azure through their own command line tools.

Each of these tools has a `login` that completes a sign-in in the browser and keeps the credential
where it always does (GitHub's keyring, AWS's login cache, Vercel's and Netlify's config files,
Azure's token cache). So that is what this drives: run the tool's login, show whatever it prints (a
code to type, a link to open), and when it finishes read what the deployment needs out of the
tool's own store. Nobody pastes a token, and nothing here ever sees a password.

Three more things follow from it. A tool that is not installed is not an error to hide: the studio
is told, with the command that installs it. A tool already signed in is used as it is, with no
browser at all (`use_existing`). And what is signed in is asked of the tool itself (`gh auth
status`, `az account show`, ...), so the studio shows the account a deployment will really use.

Azure is signed in but no service principal is created here: that gives an identity the deployment
can run as, and creating one changes the customer's tenant, so it stays a step they take on purpose.

Supabase does not belong here, on purpose, not by oversight: its CLI's `login` refuses to run at all
outside a real interactive terminal ("Cannot use automatic login flow inside non-TTY environments"),
which every provider above works around by having a device- or browser-code flow that needs no TTY.
Supabase has none - its only non-interactive path is a pasted personal access token
(`SUPABASE_ACCESS_TOKEN` / `supabase login --token`). That one credential is handled in
`supabase_connect.py` instead, the same paste-and-verify shape `DeployAccounts.jsx`'s
`HostedCredential` already uses for Netlify's and Azure's own tokens.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# How long a sign-in may stay open. The browser half is a person reading a page, so this is
# generous; the flow is dropped either way once it passes.
TTL_SECONDS = 600
# What the tools say about who is signed in is asked again after this long, not on every look.
IDENTITY_TTL = 20

HOME = Path.home()
AWS_PROFILE = "agentforge-console"
GITHUB_SCOPES = ("repo", "workflow")


def _first_file(*candidates: Path | None) -> Path | None:
    for path in candidates:
        if path and path.is_file():
            return path
    return None


def _where(name: str) -> str:
    """The tool's path, looking past whatever PATH this process inherited.

    `shutil.which` is right when the server was started from a shell the person also uses. It is
    wrong often enough not to rely on: a service, a launcher or a desktop shell can start the server
    with a PATH from before a tool was installed, and the studio would say it is not installed on a
    machine where it runs fine in a terminal.
    """
    found = shutil.which(name)
    if found:
        return found
    roots: list[Path] = []
    appdata, local = os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")
    programs = [Path(os.environ.get(key, default)) for key, default in
                (("ProgramFiles", "C:/Program Files"), ("ProgramFiles(x86)", "C:/Program Files (x86)"))]
    if appdata:
        roots.append(Path(appdata) / "npm")               # npm on Windows
    if local:
        roots += [Path(local) / "Programs" / "nodejs", Path(local) / "Programs" / "GitHub CLI"]
    for base in programs:
        roots += [base / "GitHub CLI", base / "Amazon" / "AWSCLIV2", base / "nodejs",
                  base / "Microsoft SDKs" / "Azure" / "CLI2" / "wbin"]
    roots += [HOME / ".npm-global" / "bin", HOME / ".local" / "bin", Path("/usr/local/bin"),
              Path("/opt/homebrew/bin"), Path("/opt/az/bin")]
    suffixes = (os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") + [""]
                if os.name == "nt" else [""])
    for root in roots:
        for suffix in suffixes:
            candidate = root / f"{name}{suffix.lower()}"
            if candidate.is_file():
                return str(candidate)
    return ""


def _run(command: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """A short command to completion. Its stderr is kept apart: some tools print hints there."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              shell=os.name == "nt", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              env={**os.environ, "NO_COLOR": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 124, "", str(exc))


# --- what each tool leaves behind ---------------------------------------------------------------

def _vercel_auth() -> dict:
    """What `vercel login` wrote, wherever this platform keeps it: the token and when it lapses.

    The CLI keeps it in a `Data` folder beside its config (`%APPDATA%\\com.vercel.cli\\Data` on Windows), not
    in the folder itself, and an older CLI kept it in the folder itself, so both are looked at.
    """
    appdata, local = os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")
    found = _first_file(
        Path(appdata) / "com.vercel.cli" / "Data" / "auth.json" if appdata else None,
        Path(appdata) / "com.vercel.cli" / "auth.json" if appdata else None,
        Path(local) / "com.vercel.cli" / "Data" / "auth.json" if local else None,
        HOME / ".local" / "share" / "com.vercel.cli" / "auth.json",
        HOME / "Library" / "Application Support" / "com.vercel.cli" / "auth.json",
        HOME / ".vercel" / "auth.json",
    )
    if not found:
        return {}
    try:
        saved = json.loads(found.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    expires = saved.get("expiresAt")
    return {"token": str(saved.get("token") or ""),
            "expires_at": int(expires) if isinstance(expires, (int, float)) else None}


def _vercel_token() -> str:
    return _vercel_auth().get("token", "")


def _netlify_token() -> str:
    """The token `netlify login` wrote, from whichever user it signed in as."""
    appdata = os.environ.get("APPDATA", "")
    found = _first_file(
        Path(appdata) / "netlify" / "Config" / "config.json" if appdata else None,
        HOME / ".config" / "netlify" / "config.json",
        HOME / "Library" / "Preferences" / "netlify" / "config.json",
        HOME / ".netlify" / "config.json",
    )
    if not found:
        return ""
    try:
        saved = json.loads(found.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    users = saved.get("users")
    if isinstance(users, dict):
        # The most recently used account, which is the one just signed in.
        for record in reversed(list(users.values())):
            token = (((record or {}).get("auth") or {}).get("token")) if isinstance(record, dict) else ""
            if token:
                return str(token)
    return str(saved.get("accessToken") or "")


def _json_of(text: str) -> Any:
    start = (text or "").find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


# --- one provider: its login, who is signed in, and what a deployment takes from it ----------------

@dataclass
class Provider:
    key: str
    title: str
    tool: str
    install: str
    # identity(tool) -> {"account": "...", ...} when signed in, else None
    identity: Callable[[str], dict | None]
    # login(tool, options, identity) -> the command that starts a sign-in
    login: Callable[[str, dict, dict | None], list]
    # read(tool, options) -> {setting: value}: what to keep, read from the tool's own store
    read: Callable[[str, dict], dict]
    # Whether the tool opens the browser itself (the studio then only offers the link again).
    opens_browser: bool = False
    # Whether the tool prints a code to type at the link.
    shows_code: bool = True
    # note(values) -> something worth telling the person about what was kept, or ""
    note: Callable[[dict], str] | None = None


def _github_identity(tool: str) -> dict | None:
    done = _run([tool, "auth", "status", "--hostname", "github.com"], timeout=20)
    text = f"{done.stdout}\n{done.stderr}"
    account = re.search(r"Logged in to \S+ account (\S+)", text)
    if done.returncode != 0 or not account:
        return None
    scopes = re.search(r"Token scopes:\s*(.+)", text)
    have = [s.strip(" '\"") for s in scopes.group(1).split(",")] if scopes else []
    missing = [s for s in GITHUB_SCOPES if have and s not in have]
    return {"account": account.group(1), "scopes": have, "missing_scopes": missing}


def _github_login(tool: str, options: dict, identity: dict | None) -> list:
    scopes = ",".join(GITHUB_SCOPES)
    if identity and identity.get("missing_scopes"):
        # Already signed in, but without the permission to push workflows: add it rather than start over.
        return [tool, "auth", "refresh", "--hostname", "github.com", "--scopes", scopes]
    return [tool, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web",
            "--skip-ssh-key", "--scopes", scopes]


def _github_read(tool: str, options: dict) -> dict:
    done = _run([tool, "auth", "token", "--hostname", "github.com"], timeout=20)
    token = (done.stdout or "").strip()
    if not token:
        return {}
    identity = _github_identity(tool) or {}
    return {"github_token": token, "github_login": identity.get("account", "")}


def _aws_identity(tool: str) -> dict | None:
    profiles = _run([tool, "configure", "list-profiles"], timeout=20).stdout.split()
    if AWS_PROFILE not in profiles:
        return {"account": "", "profiles": profiles} if profiles else None
    who = _json_of(_run([tool, "sts", "get-caller-identity", "--profile", AWS_PROFILE, "--output", "json"],
                        timeout=25).stdout)
    if not who:
        return {"account": "", "profiles": profiles, "expired": True}
    return {"account": who.get("Arn", ""), "aws_account": who.get("Account", ""), "profile": AWS_PROFILE,
            "profiles": profiles}


def _aws_login(tool: str, options: dict, identity: dict | None) -> list:
    command = [tool, "login", "--profile", AWS_PROFILE]
    if options.get("region"):
        command += ["--region", str(options["region"])]
    return command


def _aws_read(tool: str, options: dict) -> dict:
    who = _json_of(_run([tool, "sts", "get-caller-identity", "--profile", AWS_PROFILE, "--output", "json"],
                        timeout=30).stdout)
    if not who:
        return {}
    values = {"aws_profile": AWS_PROFILE}
    if options.get("region"):
        values["aws_region"] = str(options["region"])
    return values


def _vercel_identity(tool: str) -> dict | None:
    if not _vercel_token():
        return None
    who = _run([tool, "whoami"], timeout=30)
    name = (who.stdout or "").strip().splitlines()[-1:] or [""]
    return {"account": name[0].strip()} if who.returncode == 0 and name[0].strip() else None


def _vercel_read(tool: str, options: dict) -> dict:
    auth = _vercel_auth()
    if auth.get("expires_at") and auth["expires_at"] - time.time() < 300:
        _run([tool, "whoami"], timeout=40)          # the CLI renews its own token when it is used
        auth = _vercel_auth()
        if auth.get("expires_at") and auth["expires_at"] <= time.time():
            return {}
    return {"vercel_token": auth["token"]} if auth.get("token") else {}


def _vercel_note(values: dict) -> str:
    """Vercel's browser sign-in issues a token that lapses; say so, and what to do where that matters."""
    expires = _vercel_auth().get("expires_at")
    if not expires:
        return ""
    hours = max(1, round((expires - time.time()) / 3600))
    return (f"Vercel's browser sign-in gives a token that lasts about {hours} hour{'s' if hours != 1 else ''}. "
            "The Vercel CLI renews it on this PC, so deployments started from here keep working. For a GitHub "
            "Actions secret that has to last, paste a personal access token instead.")


def _netlify_identity(tool: str) -> dict | None:
    if not _netlify_token():
        return None
    status = _json_of(_run([tool, "status", "--json"], timeout=30).stdout) or {}
    account = status.get("account") or {}
    return {"account": str(account.get("Name") or account.get("Email") or account.get("name") or "signed in")}


def _netlify_read(tool: str, options: dict) -> dict:
    token = _netlify_token()
    return {"netlify_token": token} if token else {}


def _azure_identity(tool: str) -> dict | None:
    shown = _json_of(_run([tool, "account", "show", "--output", "json"], timeout=40).stdout)
    if not shown:
        return None
    return {"account": str((shown.get("user") or {}).get("name") or ""), "subscription": shown.get("name", ""),
            "subscription_id": shown.get("id", ""), "tenant": shown.get("tenantId", "")}


def _azure_read(tool: str, options: dict) -> dict:
    who = _azure_identity(tool)
    return {"azure_account": json.dumps(who)} if who else {}


PROVIDERS: dict[str, Provider] = {
    "github": Provider("github", "GitHub", "gh", "winget install GitHub.cli  (or: brew install gh)",
                       _github_identity, _github_login, _github_read),
    "aws": Provider("aws", "AWS", "aws", "winget install Amazon.AWSCLI  (or: brew install awscli)",
                    _aws_identity, _aws_login, _aws_read, opens_browser=True, shows_code=False),
    "vercel": Provider("vercel", "Vercel", "vercel", "npm i -g vercel", _vercel_identity,
                       lambda tool, options, identity: [tool, "login"], _vercel_read, note=_vercel_note),
    "netlify": Provider("netlify", "Netlify", "netlify", "npm i -g netlify-cli", _netlify_identity,
                        lambda tool, options, identity: [tool, "login"], _netlify_read, shows_code=False),
    "azure": Provider("azure", "Azure", "az", "winget install Microsoft.AzureCLI  (or: brew install azure-cli)",
                      _azure_identity, lambda tool, options, identity: [tool, "login", "--use-device-code"],
                      _azure_read),
}

# What the tools print while they wait for the browser half.
_CODES = (
    re.compile(r"one-time code\s*\(([A-Z0-9-]{6,})\)", re.I),                 # gh: "! One-time code (ABCD-1234) copied"
    re.compile(r"first copy your one-time code:\s*([A-Z0-9-]{6,})", re.I),    # gh, older
    re.compile(r"enter the code\s+([A-Z0-9-]{6,})", re.I),                    # az: "... and enter the code ABCD1234"
    re.compile(r"[?&]user_code=([A-Z0-9-]{6,})", re.I),                       # vercel: ".../device?user_code=ABCD-EFGH"
    re.compile(r"\bcode:\s*([A-Z0-9-]{6,})\b", re.I),
)
_URL = re.compile(r"https://[^\s\"'<>]+")


def _run_netlify_ticket(tool: str) -> dict:
    """Netlify hands out a ticket and a link, and is asked later whether it was approved."""
    made = _json_of(_run([tool, "login", "--request", "AgentForge deployment sign-in", "--json"], timeout=40).stdout)
    if not made or not made.get("ticket_id"):
        raise ValueError("Netlify would not start a sign-in. Try `netlify login` in a terminal.")
    return {"ticket": str(made["ticket_id"]), "url": str(made.get("url") or "")}


@dataclass
class Signin:
    flow_id: str
    provider: str
    process: object = None
    options: dict = field(default_factory=dict)
    ticket: str = ""
    output: list = field(default_factory=list)
    user_code: str = ""
    verification_uri: str = ""
    started: float = field(default_factory=time.time)
    error: str = ""


class CliSignins:
    """Runs one `login` per person who asks, and reads the result back."""

    def __init__(self) -> None:
        self._flows: dict[str, Signin] = {}
        self._lock = threading.RLock()
        self._seen: dict[str, tuple[float, dict]] = {}

    # --- what is here and who is signed in --------------------------------------------------------

    def _look(self, provider: Provider) -> dict:
        tool = _where(provider.tool)
        row: dict[str, Any] = {"title": provider.title, "installed": bool(tool), "install": provider.install,
                               "opens_browser": provider.opens_browser, "shows_code": provider.shows_code,
                               "identity": None, "signed_in": False}
        if not tool:
            return row
        try:
            who = provider.identity(tool)
        except Exception:  # noqa: BLE001 - a tool that misbehaves is shown as signed out, not as an error
            who = None
        row["identity"] = who
        row["signed_in"] = bool(who and who.get("account"))
        return row

    def available(self, only: str = "", fresh: bool = False) -> dict:
        """Which tools are installed, and who each is signed in as. Cached briefly: asking is slow."""
        keys = [only] if only in PROVIDERS else list(PROVIDERS)
        now = time.time()
        out: dict[str, dict] = {}
        todo = []
        for key in keys:
            cached = self._seen.get(key)
            if cached and not fresh and now - cached[0] < IDENTITY_TTL:
                out[key] = cached[1]
            else:
                todo.append(key)
        if todo:
            with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                for key, row in zip(todo, pool.map(lambda k: self._look(PROVIDERS[k]), todo)):
                    self._seen[key] = (time.time(), row)
                    out[key] = row
        return out

    def use_existing(self, provider_key: str, options: dict | None = None) -> dict:
        """Keep the account the tool is already signed in as: no browser."""
        provider, tool = self._tool(provider_key)
        values = provider.read(tool, options or {})
        if not values:
            raise ValueError(f"{provider.title} is not signed in on this machine. Sign in first.")
        self._seen.pop(provider.key, None)
        return self._ready(provider, values)

    @staticmethod
    def _ready(provider: Provider, values: dict) -> dict:
        answer: dict[str, Any] = {"status": "ready", "values": values}
        note = provider.note(values) if provider.note else ""
        if note:
            answer["note"] = note
        return answer

    # --- signing in --------------------------------------------------------------------------------

    def _tool(self, provider_key: str) -> tuple[Provider, str]:
        provider = PROVIDERS.get(str(provider_key or "").strip())
        if not provider:
            raise ValueError(f"There is no command line sign-in for {provider_key!r}.")
        tool = _where(provider.tool)
        if not tool:
            raise ValueError(f"The {provider.title} command line tool is not installed on this machine. "
                             f"Install it with `{provider.install}` and try again.")
        return provider, tool

    def start(self, provider_key: str, options: dict | None = None) -> dict:
        provider, tool = self._tool(provider_key)
        options = dict(options or {})
        flow = Signin(flow_id="cli_" + secrets.token_urlsafe(14), provider=provider.key, options=options)
        if provider.key == "netlify":
            made = _run_netlify_ticket(tool)
            flow.ticket, flow.verification_uri = made["ticket"], made["url"]
        else:
            identity = self.available(provider.key, fresh=True)[provider.key].get("identity")
            command = provider.login(tool, options, identity)
            try:
                flow.process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    text=True, bufsize=1, shell=os.name == "nt", env={**os.environ, "NO_COLOR": "1"},
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                raise ValueError(f"{provider.title} could not be started: {exc}") from exc
            # Read on a thread: the tool prints as it goes, and a blocking read here would hold the
            # request until the person finished in the browser.
            threading.Thread(target=self._drain, args=(flow,), daemon=True).start()
        with self._lock:
            self._prune()
            self._flows[flow.flow_id] = flow
        return {"flow_id": flow.flow_id, "provider": provider.key, "title": provider.title,
                "shows_code": provider.shows_code, "opens_browser": provider.opens_browser,
                "verification_uri": flow.verification_uri}

    def _drain(self, flow: Signin) -> None:
        try:
            for line in flow.process.stdout:
                line = line.strip()
                if not line:
                    continue
                flow.output.append(line)
                if not flow.user_code:
                    for pattern in _CODES:
                        found = pattern.search(line)
                        if found:
                            flow.user_code = found.group(1)
                            break
                if not flow.verification_uri:
                    url = _URL.search(line)
                    if url:
                        flow.verification_uri = url.group(0).rstrip(".,)")
        except Exception as exc:  # noqa: BLE001 - the poll reports it
            flow.error = str(exc)[:300]

    def poll(self, flow_id: str) -> dict:
        with self._lock:
            self._prune()
            flow = self._flows.get(str(flow_id or ""))
        if not flow:
            raise ValueError("That sign-in is no longer running. Start it again.")
        provider = PROVIDERS[flow.provider]
        tool = _where(provider.tool)

        if flow.ticket:                                        # Netlify: ask whether the link was approved
            answer = _json_of(_run([tool, "login", "--check", flow.ticket, "--json"], timeout=40).stdout) or {}
            if str(answer.get("status") or "pending").lower() == "pending":
                return self._pending(flow, provider)
            return self._finish(flow, provider, tool)

        if flow.process.poll() is None:
            return self._pending(flow, provider)
        if flow.process.returncode not in (0, None):
            with self._lock:
                self._flows.pop(flow.flow_id, None)
            raise ValueError(self._why(provider, flow))
        return self._finish(flow, provider, tool)

    def _pending(self, flow: Signin, provider: Provider) -> dict:
        return {"status": "pending", "user_code": flow.user_code, "verification_uri": flow.verification_uri,
                "shows_code": provider.shows_code, "opens_browser": provider.opens_browser}

    def _finish(self, flow: Signin, provider: Provider, tool: str) -> dict:
        with self._lock:
            self._flows.pop(flow.flow_id, None)
        values = provider.read(tool, flow.options)
        if not values:
            raise ValueError(f"{provider.title} reported a successful sign-in but left no credential this could "
                             f"read. Paste a token instead.")
        self._seen.pop(provider.key, None)
        return self._ready(provider, values)

    def cancel(self, flow_id: str) -> dict:
        with self._lock:
            flow = self._flows.pop(str(flow_id or ""), None)
        if flow and flow.process is not None and flow.process.poll() is None:
            self._stop(flow.process)
        return {"status": "cancelled"}

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        """End the tool and whatever it started (a login waits on child processes too)."""
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                process.terminate()
        except OSError:
            pass

    def _why(self, provider: Provider, flow: Signin) -> str:
        """The tool's last words, which are more use than its exit code."""
        said = " ".join(flow.output[-3:])[:400].strip()
        return said or f"{provider.title} sign-in did not complete."

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, f in self._flows.items() if now - f.started > TTL_SECONDS]:
            dead = self._flows.pop(key, None)
            if dead and dead.process is not None and dead.process.poll() is None:
                self._stop(dead.process)


SIGNINS = CliSignins()
