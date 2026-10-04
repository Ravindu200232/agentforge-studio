"""A picture of a page, taken silently with a browser that is already on the computer.

Nothing is installed or driven. A page on disk, or a local preview URL, is shown to a headless Chromium with its own empty
profile and a picture is asked for: no window opens and nothing the person is signed in to is touched. The browsers tried,
best first: Playwright's headless shell (which the installer puts on the computer, and which is made for this), Edge or
Chrome (Windows always has Edge), a Chromium on the PATH, and last the full Chromium Playwright also ships, because that
build was seen never to finish in new headless mode here. Each is tried once on a tiny page, so one that hangs costs a few
seconds, once, and is never used again.

A page that wrote its own height into its title (`MEASURE`) is photographed whole, however tall; any other page, a viewport.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844)}
# The whole page is photographed, taller than the window when it scrolls, but not without end.
MAX_HEIGHT = {"desktop": 4200, "mobile": 3400}
MIN_HEIGHT = 300
SECONDS = 40
PROBE_SECONDS = 15

HEIGHT_MARK = "AF_H:"
# Put at the end of a page's body: once it has loaded, the page's height is written into its title for `shoot` to read.
MEASURE = ("<script>window.addEventListener('load',function(){setTimeout(function(){document.title='" + HEIGHT_MARK
           + "'+Math.max(document.documentElement.scrollHeight,document.body?document.body.scrollHeight:0)},400)})</script>")


def _glob_first(base: Path, pattern: str) -> str:
    try:
        found = sorted(base.glob(pattern), reverse=True)
    except OSError:
        return ""
    return str(next((p for p in found if p.is_file()), ""))


def find_browsers() -> list[tuple[str, str]]:
    """The browsers this computer has that might take pictures, best first, as (path, how): "chrome" understands
    `--headless=new`, "shell" is a headless-only build."""
    override = os.environ.get("AGENTFORGE_BROWSER", "").strip()
    found: list[tuple[str, str]] = [(override, "chrome")] if override and Path(override).is_file() else []
    home = Path.home()
    local = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else None
    cache_roots = [Path(p) for p in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),) if p]
    cache_roots += [local / "ms-playwright"] if local else []
    cache_roots += [home / ".cache" / "ms-playwright", home / "Library" / "Caches" / "ms-playwright"]
    for root in cache_roots:
        for pattern in ("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell.exe",
                        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
                        "chromium_headless_shell-*/chrome-*/headless_shell.exe", "chromium_headless_shell-*/chrome-*/headless_shell"):
            path = _glob_first(root, pattern)
            if path:
                found.append((path, "shell"))
    program_dirs = [Path(os.environ.get(key, default)) for key, default in
                    (("ProgramFiles", "C:/Program Files"), ("ProgramFiles(x86)", "C:/Program Files (x86)"))]
    for base in program_dirs + ([local] if local else []):
        for relative in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
            if (base / relative).is_file():
                found.append((str(base / relative), "chrome"))
    for mac in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(mac).is_file():
            found.append((mac, "chrome"))
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        path = shutil.which(name)
        if path:
            found.append((path, "chrome"))
    for root in cache_roots:
        for pattern in ("chromium-*/chrome-win*/chrome.exe", "chromium-*/chrome-linux*/chrome",
                        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"):
            path = _glob_first(root, pattern)
            if path:
                found.append((path, "chrome"))
    seen: set[str] = set()
    return [(path, how) for path, how in found if not (path.lower() in seen or seen.add(path.lower()))]


_working: dict[str, tuple[str, str] | None] = {}
_working_lock = threading.Lock()


def working_browser(refresh: bool = False) -> tuple[str, str] | None:
    """The first browser that really takes a picture of a page here, found by trying each on a tiny page once. None when
    there is no browser, or none of them works."""
    with _working_lock:
        if not refresh and "chosen" in _working:
            return _working["chosen"]
        probe = Path(tempfile.mkdtemp(prefix="agentforge-probe-"))
        chosen = None
        try:
            page = probe / "probe.html"
            page.write_text("<!doctype html><title>probe</title><h1>probe</h1>" + MEASURE, encoding="utf-8")
            for candidate in find_browsers():
                try:
                    shoot(page, probe / "probe.png", "mobile", candidate, seconds=PROBE_SECONDS)
                    chosen = candidate
                    break
                except (ValueError, OSError):
                    continue
        finally:
            shutil.rmtree(probe, ignore_errors=True)
        _working["chosen"] = chosen
        return chosen


def local_url(value: str) -> str:
    """`value` when it is an http address on this computer (a running preview), else an error: never a remote site."""
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("a screenshot URL must be an http://localhost or 127.0.0.1 preview address")
    if parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("only a local preview can be photographed, never a remote website")
    return parsed.geturl()


def _run(command: list[str], seconds: int = SECONDS) -> subprocess.CompletedProcess:
    """The command to its end, or - after `seconds` - stopped together with every process it started (a browser starts
    several, and only the one this started is ever touched: never another Chrome or Edge the person has open)."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                               encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                               start_new_session=os.name != "nt")
    try:
        stdout, stderr = process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            try:
                os.killpg(process.pid, 9)
            except OSError:
                process.kill()
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _flags(how: str, profile: str, width: int, height: int) -> list[str]:
    return [("--headless=new" if how == "chrome" else "--headless"), "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={width},{height}", "--virtual-time-budget=6000",
            "--allow-file-access-from-files", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
            "--disable-background-networking", f"--user-data-dir={profile}"]


def shoot(source: Path | str, out: Path, viewport: str = "desktop", browser: tuple[str, str] | None = None,
          seconds: int = SECONDS) -> Path:
    """One picture of `source` (an HTML file on disk, or a local preview URL) at `viewport`, saved to `out`."""
    if viewport not in VIEWPORTS:
        raise ValueError("viewport must be desktop or mobile")
    browser = browser or working_browser()
    if not browser:
        raise ValueError("no browser to take the screenshots with (Edge, Chrome or Chromium)")
    path, how = browser
    width, height = VIEWPORTS[viewport]
    is_url = isinstance(source, str) and source.startswith("http")
    url = local_url(source) if is_url else Path(source).resolve().as_uri()
    name = url if is_url else Path(source).name
    out.parent.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="agentforge-shot-")
    try:
        tall = height
        if not is_url:
            # First how tall the page is, then a window that tall. The measure is a title the page writes once it has loaded.
            measured = _run([path, *_flags(how, profile, width, height), "--dump-dom", url], seconds)
            found = re.search(re.escape(HEIGHT_MARK) + r"(\d+)", measured.stdout or "")
            tall = max(MIN_HEIGHT, min(int(found.group(1)) if found else height, MAX_HEIGHT[viewport]))
        out.unlink(missing_ok=True)
        _run([path, *_flags(how, profile, width, tall), f"--screenshot={out}", url], seconds)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"the browser took longer than {seconds} seconds to draw {name}") from exc
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not out.is_file() or out.stat().st_size < 500:
        raise ValueError(f"the browser saved no picture of {name}")
    return out
