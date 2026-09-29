"""Read a running local app in a real browser without touching it.

The coding agent normally has file and terminal tools, which are not enough to
tell whether a real rendered page has overflow, broken images or controls that
have collapsed out of view. This helper opens only a loopback URL in an
isolated headless Playwright browser, captures a screenshot for the Testing
screen, and returns compact layout/accessibility facts to the model.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


VIEWPORTS = {"desktop": (1440, 1000), "mobile": (390, 844)}
MAX_BROWSER_SECONDS = 45


# Every generated app already has @playwright/test for its journey suite.
# `node -e` resolves it from the inspected workspace, so AgentForge itself
# never downloads a browser merely because an agent was offered this tool.
_PLAYWRIGHT_SCRIPT = r"""
const input = JSON.parse(process.argv[1]);
let chromium;
try { ({ chromium } = require('@playwright/test')); }
catch (_) { ({ chromium } = require('playwright')); }
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: input.viewport, deviceScaleFactor: 1 });
  const consoleErrors = [], pageErrors = [];
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 300)); });
  page.on('pageerror', error => pageErrors.push(String(error.message || error).slice(0, 300)));
  // Navigation stays inside the local app. Static image/font/stylesheet assets
  // are allowed so the screenshot reflects the UI the visitor actually sees;
  // scripts and document navigation from another origin stay blocked.
  await page.route('**/*', route => {
    try {
      const target = new URL(route.request().url());
      if (target.protocol === 'data:' || target.protocol === 'blob:' || ['127.0.0.1', 'localhost', '::1'].includes(target.hostname)) return route.continue();
      if (['image', 'font', 'stylesheet'].includes(route.request().resourceType())) return route.continue();
    } catch (_) {}
    return route.abort();
  });
  const response = await page.goto(input.url, { waitUntil: 'domcontentloaded', timeout: 25000 });
  // A DOM-ready page can still be painting its photos. Give images a bounded
  // chance to finish so a slow but healthy image is not reported as broken.
  await page.waitForFunction(() => [...document.images].every(image => image.complete), { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(150);
  const observed = await page.evaluate(() => {
    // These run in the rendered page, so keep them inside evaluate rather
    // than relying on Node's separate execution context.
    const visible = element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    };
    const label = element => (element.getAttribute('aria-label') || element.getAttribute('alt') || element.getAttribute('title') || element.innerText || element.textContent || '')
      .replace(/\s+/g, ' ').trim().slice(0, 160);
    const interactive = [...document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"]')]
      .filter(visible).slice(0, 80).map(element => {
        const rect = element.getBoundingClientRect();
        return { tag: element.tagName.toLowerCase(), name: label(element), x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) };
      });
    const clipped = [...document.querySelectorAll('button, a, label, p, h1, h2, h3, span')]
      .filter(visible).filter(element => element.scrollWidth > element.clientWidth + 2 || element.scrollHeight > element.clientHeight + 2)
      .slice(0, 12).map(label).filter(Boolean);
    const images = [...document.images];
    const pendingImages = images.filter(image => !image.complete).slice(0, 12)
      .map(image => ({ src: String(image.currentSrc || image.src || '').slice(0, 220), alt: image.alt || '' }));
    const brokenImages = images.filter(image => image.complete && !image.naturalWidth).slice(0, 12)
      .map(image => ({ src: String(image.currentSrc || image.src || '').slice(0, 220), alt: image.alt || '' }));
    const missingAlt = images.filter(image => !image.hasAttribute('alt')).slice(0, 12)
      .map(image => String(image.currentSrc || image.src || '').slice(0, 220));
    const landmarks = [...document.querySelectorAll('header, nav, main, footer, [role="main"], [role="navigation"]')]
      .filter(visible).slice(0, 16).map(element => ({ tag: element.tagName.toLowerCase(), label: label(element) }));
    const root = document.documentElement, body = document.body;
    const viewportWidth = window.innerWidth;
    const overflowElements = [...document.body.querySelectorAll('*')]
      .filter(visible)
      .filter(element => {
        const rect = element.getBoundingClientRect();
        return rect.right > viewportWidth + 1 || rect.left < -1;
      })
      // Parents of an overflowing control also extend off-screen. Prefer the
      // concrete leaf controls/text that tell the model what to repair.
      .filter(element => ![...element.children].some(child => {
        const rect = child.getBoundingClientRect();
        return visible(child) && (rect.right > viewportWidth + 1 || rect.left < -1);
      }))
      .slice(0, 16).map(element => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName.toLowerCase(), id: element.id || '',
          className: String(element.className || '').slice(0, 120), name: label(element),
          x: Math.round(rect.x), width: Math.round(rect.width), right: Math.round(rect.right),
        };
      });
    return {
      text: (body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 5000), landmarks, interactive,
      layout: {
        viewportWidth, viewportHeight: window.innerHeight,
        documentWidth: Math.max(root.scrollWidth, body?.scrollWidth || 0), documentHeight: Math.max(root.scrollHeight, body?.scrollHeight || 0),
        horizontalOverflow: Math.max(root.scrollWidth, body?.scrollWidth || 0) > window.innerWidth + 1,
        clippedLabels: clipped, smallControls: interactive.filter(item => item.width < 24 || item.height < 24),
        brokenImages, pendingImages, missingAlt, overflowElements,
      },
    };
  });
  await page.screenshot({ path: input.screenshot, fullPage: true, animations: 'disabled' });
  const output = { url: page.url(), status: response ? response.status() : 0, title: await page.title(),
                   screenshot: input.relativeScreenshot, viewport: input.viewport, ...observed, consoleErrors, pageErrors };
  await browser.close();
  console.log(JSON.stringify(output));
})().catch(error => { console.error(String(error.stack || error)); process.exitCode = 1; });
"""


def _local_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("browser_inspect accepts an http://localhost or 127.0.0.1 preview URL only")
    if parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("browser_inspect can inspect only a local preview, never a remote website")
    return parsed.geturl()


def inspect_local_page(root: Path, url: str, viewport: str = "desktop") -> dict[str, Any]:
    """Capture one local page and return the facts a text model can act on."""
    checked_url = _local_url(url)
    choice = str(viewport or "desktop").strip().lower()
    if choice not in VIEWPORTS:
        raise ValueError("viewport must be desktop or mobile")
    root = root.resolve()
    digest = hashlib.sha256(f"{checked_url}|{choice}".encode("utf-8")).hexdigest()[:12]
    relative = Path(".agentforge") / "qa" / "shots" / f"browser-{choice}-{digest}.png"
    screenshot = root / relative
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    payload = {"url": checked_url, "viewport": {"width": VIEWPORTS[choice][0], "height": VIEWPORTS[choice][1]},
               "screenshot": str(screenshot), "relativeScreenshot": relative.as_posix()}
    try:
        done = subprocess.run(
            ["node", "-e", _PLAYWRIGHT_SCRIPT, json.dumps(payload)], cwd=root, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=MAX_BROWSER_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=os.environ.copy(), check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("Node.js is required for the local browser inspection tool") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"browser inspection timed out after {MAX_BROWSER_SECONDS} seconds") from exc
    if done.returncode != 0:
        lines = (done.stderr or done.stdout or "Playwright could not open the preview").strip().splitlines()
        detail = "\n".join(lines[-8:])
        raise ValueError(f"browser inspection failed: {detail[:1200]}")
    try:
        result = json.loads((done.stdout or "").strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise ValueError("browser inspection returned no readable result") from exc
    if not isinstance(result, dict) or not screenshot.is_file():
        raise ValueError("browser inspection did not save its screenshot")
    return result
