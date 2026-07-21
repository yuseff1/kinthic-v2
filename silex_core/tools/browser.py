"""
Browser Tool — provides KINTHIC with visual agency and web browsing capabilities.

Uses Playwright for stealthy, headless browsing and html2text for markdown extraction.
Supports navigation, scraping, clicking, typing, and 1080p screenshots.
"""

import asyncio
import asyncio
import io
import json
import ipaddress
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import re
from PIL import Image, ImageDraw

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    import html2text
except ImportError:
    async_playwright = None
    html2text = None

try:
    from playwright_stealth import stealth_async
except ImportError:
    stealth_async = None

from silex_core.tools.base import BaseTool
from silex_core.utils.config import browser_actions_enabled, WORKSPACE_DIR
from silex_core.utils.logger import setup_logger

log = setup_logger("silex.tools.browser")
BROWSER_OUTPUT_DIR = WORKSPACE_DIR / "browser"
ALLOWED_SCHEMES = {"http", "https"}


BUILD_ACCESSIBILITY_TREE_JS = """
(function() {
    const interactiveRoles = new Set([
        'button', 'link', 'checkbox', 'radio', 'textbox', 
        'combobox', 'listbox', 'menuitem', 'option', 'tab', 
        'switch', 'searchbox', 'spinbutton'
    ]);
    const interactiveTags = new Set([
        'a', 'button', 'input', 'select', 'textarea', 'option'
    ]);

    function getImplicitRole(el) {
        const tag = el.tagName.toLowerCase();
        if (tag === 'a' && el.hasAttribute('href')) return 'link';
        if (tag === 'button') return 'button';
        if (tag === 'input') {
            const type = el.getAttribute('type') || 'text';
            if (type === 'button' || type === 'submit' || type === 'image' || type === 'reset') return 'button';
            if (type === 'checkbox') return 'checkbox';
            if (type === 'radio') return 'radio';
            return 'textbox';
        }
        if (tag === 'select') return 'combobox';
        if (tag === 'textarea') return 'textbox';
        return null;
    }

    function isVisible(el) {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        
        const vw = window.innerWidth || document.documentElement.clientWidth;
        const vh = window.innerHeight || document.documentElement.clientHeight;
        if (rect.right < 0 || rect.bottom < 0 || rect.left > vw || rect.top > vh) {
            return false;
        }

        let parent = el.parentElement;
        while (parent && parent !== document.body) {
            const pStyle = window.getComputedStyle(parent);
            if (pStyle.overflow === 'hidden' || pStyle.overflowX === 'hidden' || pStyle.overflowY === 'hidden') {
                const pRect = parent.getBoundingClientRect();
                if (rect.left > pRect.right || rect.right < pRect.left || 
                    rect.top > pRect.bottom || rect.bottom < pRect.top) {
                    return false;
                }
            }
            parent = parent.parentElement;
        }
        return true;
    }

    function getAccessibleName(el) {
        if (el.hasAttribute('kinthic-label')) return el.getAttribute('kinthic-label').trim();
        const labelledBy = el.getAttribute('kinthic-labelledby');
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) return labelEl.innerText.trim();
        }
        if (el.placeholder) return el.placeholder.trim();
        if (el.title) return el.title.trim();
        if (el.tagName.toLowerCase() === 'input' && el.type === 'image') return el.alt || '';
        
        if (el.id) {
            const labels = document.querySelectorAll('label[for="' + el.id + '"]');
            if (labels.length > 0) return labels[0].innerText.trim();
        }
        const parentLabel = el.closest('label');
        if (parentLabel) return parentLabel.innerText.replace(el.innerText || '', '').trim();

        return el.innerText ? el.innerText.trim() : '';
    }

    let refCount = 0;
    const elementsMap = {};

    function traverse(node) {
        if (node.nodeType !== Node.ELEMENT_NODE) return null;
        if (!isVisible(node)) return null;

        const role = node.getAttribute('role') || getImplicitRole(node);
        const style = window.getComputedStyle(node);
        const isInteractive = interactiveRoles.has(role) || 
                              interactiveTags.has(node.tagName.toLowerCase()) || 
                              node.hasAttribute('onclick') || 
                              style.cursor === 'pointer';

        let nodeId = null;
        let rectData = null;
        if (isInteractive) {
            refCount++;
            nodeId = 'e' + refCount;
            node.setAttribute('data-kinthic-ref', nodeId);
            const rect = node.getBoundingClientRect();
            rectData = {
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height
            };
            elementsMap[nodeId] = rectData;
        }

        const children = [];
        for (let child of node.children) {
            const childTree = traverse(child);
            if (childTree) children.push(childTree);
        }

        if (isInteractive || children.length > 0) {
            const item = {
                role: role || node.tagName.toLowerCase(),
                name: getAccessibleName(node),
                children: children
            };
            if (nodeId) {
                item.id = nodeId;
            }
            return item;
        }
        return null;
    }

    const oldTags = document.querySelectorAll('[data-kinthic-ref]');
    for (let el of oldTags) {
        el.removeAttribute('data-kinthic-ref');
    }

    const tree = traverse(document.body);
    return {
        tree: tree,
        elements: elementsMap
    };
})()
"""

INJECT_SOM_OVERLAYS_JS = """
(function() {
    let style = document.getElementById('kinthic-som-styles');
    if (!style) {
        style = document.createElement('style');
        style.id = 'kinthic-som-styles';
        style.innerHTML = `
            .kinthic-som-highlight {
                position: absolute !important;
                border: 2px solid red !important;
                box-sizing: border-box !important;
                pointer-events: none !important;
                z-index: 2147483647 !important;
            }
            .kinthic-som-label {
                position: absolute !important;
                background: red !important;
                color: white !important;
                font-family: monospace !important;
                font-size: 10px !important;
                font-weight: bold !important;
                padding: 1px 3px !important;
                border-radius: 2px !important;
                pointer-events: none !important;
                z-index: 2147483647 !important;
                white-space: nowrap !important;
            }
        `;
        document.head.appendChild(style);
    }

    const elementsMap = window.kinthicElementsMap || {};
    for (const [refId, rect] of Object.entries(elementsMap)) {
        const highlight = document.createElement('div');
        highlight.className = 'kinthic-som-highlight';
        highlight.style.left = (window.scrollX + rect.x) + 'px';
        highlight.style.top = (window.scrollY + rect.y) + 'px';
        highlight.style.width = rect.width + 'px';
        highlight.style.height = rect.height + 'px';

        const label = document.createElement('div');
        label.className = 'kinthic-som-label';
        label.innerText = refId;
        label.style.left = (window.scrollX + rect.x) + 'px';
        label.style.top = (window.scrollY + Math.max(0, rect.y - 14)) + 'px';

        document.body.appendChild(highlight);
        document.body.appendChild(label);
    }
})();
"""

CLEANUP_SOM_OVERLAYS_JS = """
(function() {
    const style = document.getElementById('kinthic-som-styles');
    if (style) style.remove();
    const overlays = document.querySelectorAll('.kinthic-som-highlight, .kinthic-som-label');
    for (const el of overlays) {
        el.remove();
    }
})();
"""


def _validate_public_url(url: str) -> str:
    """Validate that a URL points to a public internet address.

    This resolves the hostname and checks if the IP is private.
    Returns the first resolved valid public IP address string.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise ValueError("Only http and https URLs with a hostname are allowed.")

    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValueError("Could not resolve URL hostname.") from None

    resolved_ip = None
    for address in addresses:
        ip_str = address[4][0]
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise ValueError("Refusing to browse private or local network addresses.")
        if not resolved_ip:
            resolved_ip = ip_str

    if not resolved_ip:
        raise ValueError("Could not resolve URL hostname to a valid IP address.")
    return resolved_ip


def _resolve_screenshot_path(filepath: str) -> Path:
    BROWSER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidate = Path(filepath)
    if not candidate.is_absolute():
        candidate = BROWSER_OUTPUT_DIR / candidate.name
    resolved = candidate.resolve()
    try:
        resolved.relative_to(BROWSER_OUTPUT_DIR)
    except ValueError:
        raise ValueError("Screenshot path must stay inside workspace/browser.")
    return resolved


def _format_accessibility_tree(tree: dict, depth: int = 0) -> str:
    if not tree:
        return ""
    indent = "  " * depth
    node_id = f" [{tree['id']}]" if "id" in tree else ""
    role = tree.get("role", "element")
    name = tree.get("name", "").replace("\n", " ").strip()
    name_str = f' "{name}"' if name else ""
    line = f"{indent}-{role}{node_id}{name_str}\n"
    for child in tree.get("children", []):
        line += _format_accessibility_tree(child, depth + 1)
    return line


class BrowserTool(BaseTool):
    """
    A tool that allows KINTHIC to interact with the web.
    """

    name = "browser"
    risk_level = "network"
    description = "Browse the web, scrape content as markdown, and take screenshots."
    schema = {
        "action": "str: 'navigate', 'scrape', 'screenshot', 'click', 'type'",
        "url": "str, optional: for navigate",
        "selector": "str, optional: for click/type",
        "text": "str, optional: for type",
        "filepath": "str, optional: for screenshot (default: kinthic_vision_capture.png)",
        "accessibility_tree": "bool, optional: for scrape (default: True)",
    }

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.elements_map: dict = {}

    async def _route_handler(self, route, request):
        url = request.url
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
                log.warning(f"Blocking request with invalid scheme/hostname: {url}")
                await route.abort("blockedbyclient")
                return

            # Resolve hostname using asyncio.to_thread to avoid blocking event loop
            addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None)
            for address in addresses:
                ip_str = address[4][0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                    log.warning(f"Blocking private/local request: {url} ({ip_str})")
                    await route.abort("blockedbyclient")
                    return
        except Exception as e:
            log.warning(f"Blocking request due to resolution failure: {url} - {e}")
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async def _ensure_started(self):
        """Lazy initialization of the browser."""
        if self.page is not None:
            return

        log.info("Starting headless Chromium instance...")
        self.playwright = await async_playwright().start()

        # Load X (Twitter) session state if present to keep the browser logged in
        cookies_path = Path.home() / ".kinthic" / "x_cookies.json"
        self.browser = await self.playwright.chromium.launch(headless=True)
        
        if cookies_path.exists():
            try:
                log.info("Loading saved X.com storage state into browser context.")
                self.context = await self.browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    storage_state=str(cookies_path)
                )
            except Exception as e:
                log.warning(f"Failed to load storage state: {e}. Falling back to clean context.")
                self.context = await self.browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                )
        else:
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            )
        
        # Register Playwright Request Firewall on context
        await self.context.route("**/*", self._route_handler)
        
        self.page = await self.context.new_page()

        if stealth_async:
            await stealth_async(self.page)

    async def execute(self, **kwargs) -> str:
        """
        Execute a browser action.
        """
        if not browser_actions_enabled():
            return (
                "Error: Browser automation is disabled by KINTHIC_ENABLE_BROWSER_ACTIONS."
            )

        if async_playwright is None or html2text is None:
            return (
                "Error: Browser dependencies are missing. "
                "Please run `pip install -e '.[browser]' && playwright install` in your environment, then restart the server."
            )

        action = kwargs.get("action")

        try:
            if action == "navigate":
                url = kwargs.get("url")
                if not url:
                    return "Error: Missing 'url' for navigate action."
                _validate_public_url(url)
                await self._ensure_started()
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Auto-extract elements map on first navigation
                try:
                    tree_data = await self.page.evaluate(BUILD_ACCESSIBILITY_TREE_JS)
                    self.elements_map = tree_data.get("elements", {})
                except Exception:
                    self.elements_map = {}
                return await self._observation(
                    "navigate", f"Successfully navigated to {url}"
                )

            else:
                await self._ensure_started()

            if action == "scrape":
                accessibility_tree = kwargs.get("accessibility_tree", True)
                if accessibility_tree:
                    # Build tree and map
                    try:
                        tree_data = await self.page.evaluate(BUILD_ACCESSIBILITY_TREE_JS)
                        self.elements_map = tree_data.get("elements", {})
                        tree_text = _format_accessibility_tree(tree_data.get("tree"))
                    except Exception as e:
                        self.elements_map = {}
                        tree_text = f"Failed to extract accessibility tree: {e}"
                else:
                    self.elements_map = {}
                    tree_text = ""

                html_content = await self.page.content()
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0
                markdown = h.handle(html_content)
                # Strip known prompt injection keywords
                markdown = re.sub(
                    r"(?i)(system instruction|critical instruction|ignore previous|you are now|system override|forget all)",
                    "[REDACTED]",
                    markdown,
                )
                if accessibility_tree:
                    output_text = f"ACCESSIBILITY TREE:\n{tree_text}\n\nPAGE CONTENT (MARKDOWN):\n{markdown[:6000]}"
                else:
                    output_text = markdown[:8000]
                return await self._observation("scrape", output_text)

            elif action == "screenshot":
                filepath = kwargs.get("filepath", "kinthic_vision_capture.png")
                safe_path = _resolve_screenshot_path(filepath)
                
                # If we have parsed elements, inject the visual SoM overlays
                if self.elements_map:
                    try:
                        # 1. Bind elements map to page global scope
                        await self.page.evaluate("window.kinthicElementsMap = arguments[0];", self.elements_map)
                        # 2. Inject CSS & HTML overlay nodes
                        await self.page.evaluate(INJECT_SOM_OVERLAYS_JS)
                        # 3. Take native screenshot
                        await self.page.screenshot(path=str(safe_path), full_page=False)
                        # 4. Remove injected overlay nodes
                        await self.page.evaluate(CLEANUP_SOM_OVERLAYS_JS)
                    except Exception as som_err:
                        log.warning(f"DOM overlay screenshot failed, falling back to raw screenshot: {som_err}")
                        # Clean up best effort
                        try:
                            await self.page.evaluate(CLEANUP_SOM_OVERLAYS_JS)
                        except Exception:
                            pass
                        await self.page.screenshot(path=str(safe_path), full_page=False)
                else:
                    await self.page.screenshot(path=str(safe_path), full_page=False)

                return await self._observation(
                    "screenshot",
                    f"Screenshot saved to {safe_path}",
                    screenshot_path=str(safe_path),
                )

            elif action == "click":
                selector = kwargs.get("selector")
                if not selector:
                    return "Error: Missing 'selector' for click action."
                
                # If target is a Ref ID (e.g. "e12") and exists in map
                if selector.startswith("e") and selector in self.elements_map:
                    resolved_selector = f"[data-kinthic-ref='{selector}']"
                    await self.page.click(resolved_selector, timeout=5000)
                else:
                    await self.page.click(selector, timeout=5000)
                return await self._observation("click", f"Clicked element: {selector}")

            elif action == "type":
                selector = kwargs.get("selector")
                text = kwargs.get("text")
                if not selector or text is None:
                    return "Error: Missing 'selector' or 'text' for type action."
                
                if selector.startswith("e") and selector in self.elements_map:
                    resolved_selector = f"[data-kinthic-ref='{selector}']"
                    await self.page.fill(resolved_selector, text, timeout=5000)
                else:
                    await self.page.fill(selector, text, timeout=5000)
                return await self._observation("type", f"Typed text into: {selector}")

            else:
                return f"Error: Unknown browser action '{action}'."

        except Exception as e:
            log.error(f"Browser action '{action}' failed: {str(e)}")
            return f"Error executing browser action: {str(e)}"

    async def close(self):
        """Cleanup."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

    async def _page_state(self) -> dict:
        if not self.page:
            return {}
        title = await self.page.title()
        try:
            visible_text = await self.page.locator("body").inner_text(timeout=2000)
        except Exception:
            visible_text = ""
        return {
            "url": self.page.url,
            "title": title,
            "visible_text_preview": visible_text[:1000],
        }

    async def _observation(self, action: str, result: str, **extra) -> str:
        payload = {
            "action": action,
            "result": result,
            "page": await self._page_state(),
            **extra,
        }
        return "BROWSER_OBSERVATION:\n" + json.dumps(payload, indent=2)
