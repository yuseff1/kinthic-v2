"""
Stealth Multi-Platform Browser Session Manager Plugin.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from silex_core.tools.base import BaseTool

log = logging.getLogger("silex.plugins.browser_session_manager")

PLATFORM_URLS = {
    "x": {"login": "https://x.com/i/flow/login", "home": "https://x.com/home"},
    "twitter": {"login": "https://x.com/i/flow/login", "home": "https://x.com/home"},
    "linkedin": {"login": "https://www.linkedin.com/login", "home": "https://www.linkedin.com/feed/"},
    "github": {"login": "https://github.com/login", "home": "https://github.com"},
    "reddit": {"login": "https://www.reddit.com/login", "home": "https://www.reddit.com/"},
}


class BrowserSessionManagerTool(BaseTool):
    name = "browser_session_manager"
    risk_level = "network"
    description = (
        "Stealth multi-platform browser session manager for LinkedIn, Reddit, GitHub, X (Twitter), or custom URLs. "
        "Actions: 'list_sessions' (lists all stored sessions), 'interactive_login' (opens visible browser for manual login), "
        "'check_session' (verifies session state), and 'fetch_page' (fetches page content using authenticated session)."
    )
    schema = {
        "action": "string (required: 'list_sessions', 'interactive_login', 'check_session', 'fetch_page')",
        "platform": "string (required for session ops: 'linkedin', 'reddit', 'github', 'x', or 'custom')",
        "url": "string (optional: URL to navigate or fetch for 'fetch_page' or 'custom' platform)",
    }

    def _get_sessions_dir(self) -> Path:
        sess_dir = Path.home() / ".kinthic" / "browser_sessions"
        os.makedirs(sess_dir, exist_ok=True)
        return sess_dir

    def _get_cookie_path(self, platform: str) -> Path:
        plat = platform.lower().strip()
        return self._get_sessions_dir() / f"{plat}_cookies.json"

    async def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "").lower()
        if not action:
            return "Error: 'action' argument is required. Choose 'list_sessions', 'interactive_login', 'check_session', or 'fetch_page'."

        platform = kwargs.get("platform", "").lower().strip()
        url = kwargs.get("url", "").strip()

        if action == "list_sessions":
            return self._list_sessions()

        if not platform:
            return "Error: 'platform' argument is required for this action."

        if action == "interactive_login":
            return await self._interactive_login(platform, url)
        elif action == "check_session":
            return await self._check_session(platform, url)
        elif action == "fetch_page":
            return await self._fetch_page(platform, url)
        else:
            return f"Error: Unknown action '{action}'."

    def _list_sessions(self) -> str:
        sess_dir = self._get_sessions_dir()
        files = list(sess_dir.glob("*_cookies.json"))
        if not files:
            return f"No active browser sessions found in {sess_dir}."

        lines = [f"Stored Browser Sessions ({len(files)}):"]
        for f in files:
            plat = f.name.replace("_cookies.json", "").upper()
            mtime = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            size_kb = f.stat().st_size / 1024.0
            lines.append(f"• {plat}: {f.name} ({size_kb:.1f} KB, last modified {mtime})")

        return "\n".join(lines)

    async def _interactive_login(self, platform: str, custom_url: str) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return "Error: Playwright library is not installed."

        cookie_path = self._get_cookie_path(platform)
        login_url = custom_url or PLATFORM_URLS.get(platform, {}).get("login") or f"https://{platform}.com/login"

        try:
            async with async_playwright() as p:
                log.info(f"Launching browser for {platform} interactive login...")
                launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                try:
                    browser = await p.chromium.launch(headless=False, args=launch_args)
                except Exception:
                    log.warning("Visible browser launch failed (no X11 display server). Falling back to headless mode...")
                    browser = await p.chromium.launch(headless=True, args=launch_args)
                
                if cookie_path.exists():
                    try:
                        context = await browser.new_context(
                            viewport={"width": 1280, "height": 800},
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                            storage_state=str(cookie_path)
                        )
                    except Exception:
                        context = await browser.new_context(
                            viewport={"width": 1280, "height": 800},
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
                        )
                else:
                    context = await browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
                    )

                page = await context.new_page()
                await page.goto(login_url)

                success = False
                for _ in range(150):  # Wait up to 5 minutes
                    await asyncio.sleep(2)
                    if page.is_closed():
                        break
                    # Detect successful login via URL change or storage mutation
                    curr_url = page.url.lower()
                    if "login" not in curr_url and "auth" not in curr_url and "signin" not in curr_url:
                        success = True
                        await context.storage_state(path=str(cookie_path))
                        break

                await browser.close()
                if success:
                    return f"SUCCESS: Logged into platform '{platform}' and saved session state to {cookie_path}."
                else:
                    return f"Error: Login for '{platform}' timed out or window was closed before completion."
        except Exception as e:
            return f"Error during interactive login for platform '{platform}': {e}"

    async def _check_session(self, platform: str, custom_url: str) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return "Error: Playwright library is not installed."

        cookie_path = self._get_cookie_path(platform)
        if not cookie_path.exists():
            return f"No saved session state found for platform '{platform}' at {cookie_path}."

        home_url = custom_url or PLATFORM_URLS.get(platform, {}).get("home") or f"https://{platform}.com"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state=str(cookie_path))
                page = await context.new_page()
                await page.goto(home_url)
                await page.wait_for_timeout(3000)

                title = await page.title()
                final_url = page.url
                await browser.close()

                is_login = any(term in final_url.lower() for term in ["login", "signin", "auth"])
                if is_login:
                    return f"Session for platform '{platform}' is EXPIRED or invalid (redirected to {final_url})."
                else:
                    return f"Session for platform '{platform}' is VALID. Page Title: '{title}' (URL: {final_url})."
        except Exception as e:
            return f"Error checking session for platform '{platform}': {e}"

    async def _fetch_page(self, platform: str, url: str) -> str:
        if not url:
            url = PLATFORM_URLS.get(platform, {}).get("home", "")
        if not url:
            return f"Error: 'url' parameter is required to fetch a page for platform '{platform}'."

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return "Error: Playwright library is not installed."

        cookie_path = self._get_cookie_path(platform)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                if cookie_path.exists():
                    context = await browser.new_context(storage_state=str(cookie_path))
                else:
                    context = await browser.new_context()

                page = await context.new_page()
                await page.goto(url)
                await page.wait_for_timeout(3000)

                title = await page.title()
                content = await page.inner_text("body")
                await browser.close()

                snippet = content.strip()[:1000].replace("\n\n", "\n")
                return f"Page Title: '{title}'\nURL: {url}\n\nContent Snippet:\n{snippet}"
        except Exception as e:
            return f"Error fetching page '{url}' for platform '{platform}': {e}"
