"""
Web Extract Tool.
Fetches HTML pages and uses map-reduce LLM summarization for massive pages.
"""

from __future__ import annotations

import asyncio
import re
import httpx
import ipaddress
import socket
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from silex_core.tools.base import BaseTool
from silex_core.utils.logger import setup_logger

log = setup_logger("silex.tools.web_extract")

ALLOWED_SCHEMES = {"http", "https"}


def _validate_public_url(url: str) -> str:
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


class SafeAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        _validate_public_url(url_str)
        return await super().handle_async_request(request)


def _check_socket_peername(resp: httpx.Response):
    stream = resp.extensions.get("network_stream")
    if stream:
        sock = stream.get_extra_info("socket")
        if sock:
            peer = sock.getpeername()
            if peer:
                ip_str = peer[0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                    raise ValueError(f"Refusing to browse private or local network address: {ip_str}")


class WebExtractTool(BaseTool):
    name = "web_extract"
    risk_level = "network"
    description = "Fetches the full text of a webpage. Automatically compresses massive pages to fit context limits."
    schema = {"url": "string (the full HTTP/HTTPS url to extract)"}

    def __init__(self, llm=None):
        self.llm = llm

    def _html_to_markdown(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        # Remove script and style tags
        for script in soup(["script", "style", "noscript", "iframe"]):
            script.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse multiple newlines
        text = re.sub(r"\n+", "\n", text)
        return text

    async def execute(self, **kwargs) -> str:
        url = kwargs.get("url")
        if not url:
            return "Error: 'url' is required."

        if not url.startswith("http"):
            url = "https://" + url

        try:
            _validate_public_url(url)
        except ValueError as e:
            return f"Error: {e}"

        log.info(f"Executing web_extract for: {url}")

        try:
            transport = SafeAsyncHTTPTransport()
            async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
                resp = await client.get(url, timeout=15.0)
                _check_socket_peername(resp)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            return f"Error fetching {url}: {e}"

        markdown = self._html_to_markdown(html)
        markdown = re.sub(
            r"(?i)(system instruction|critical instruction|ignore previous|you are now|system override|forget all)",
            "[REDACTED]",
            markdown,
        )
        char_count = len(markdown)

        log.info(f"Web Extract: Fetched {char_count} chars from {url}")

        # 1. Raw Return Threshold
        if char_count < 5000:
            return markdown

        # 2. Hard Rejection Threshold
        if char_count > 2_000_000:
            return f"Error: Page too large to extract ({char_count} chars). Please use a more specific URL or search query."

        if not self.llm:
            log.warning(
                "No LLM available for compression. Returning truncated raw text."
            )
            return markdown[:5000]

        # 3. Compression Prompt Setup
        system_prompt = (
            "You are an auxiliary extraction model. Your job is to compress this web page chunk into a dense, "
            "factual summary. Keep exact quotes, code blocks, and crucial data points. Do NOT hallucinate. "
            "Output valid markdown."
        )

        # 4. Single-Pass LLM Summarization
        if char_count < 500_000:
            log.info("Web Extract: Running Single-Pass LLM Compression")
            try:
                # LLM execution
                res = await self.llm.think(
                    system_prompt,
                    f"URL: {url}\n\nCONTENT:\n{markdown[:150_000]}",  # Soft cap to prevent API max tokens
                )
                return f"--- EXTRACTED & COMPRESSED ({url}) ---\n" + res.response
            except Exception as e:
                log.error(f"Compression failed: {e}")
                return markdown[:5000]

        # 5. Map-Reduce Chunking (ULTRATHINK)
        log.info("Web Extract: Running Map-Reduce Chunked Compression")
        CHUNK_SIZE = 100_000
        chunks = [
            markdown[i : i + CHUNK_SIZE] for i in range(0, char_count, CHUNK_SIZE)
        ]
        # Cap chunks to avoid rate limits on insane pages
        chunks = chunks[:10]

        tasks = []
        for i, chunk in enumerate(chunks):
            tasks.append(
                self.llm.think(
                    system_prompt,
                    f"URL: {url} | CHUNK {i + 1}/{len(chunks)}\n\nCONTENT:\n{chunk}",
                )
            )

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            synthesized_chunks = []
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    log.error(f"Chunk {i} failed: {res}")
                else:
                    synthesized_chunks.append(res.response)

            combined_text = "\n\n--- CHUNK SEPARATOR ---\n\n".join(synthesized_chunks)

            # Final synthesis pass if it's still large
            if len(combined_text) > 10000:
                final_res = await self.llm.think(
                    "You are synthesizing multiple chunk summaries into a final coherent page summary. Retain important code blocks and facts.",
                    f"URL: {url}\n\nSUMMARIES:\n{combined_text[:150_000]}",
                )
                return f"--- EXTRACTED & SYNTHESIZED ({url}) ---\n" + final_res.response
            else:
                return f"--- EXTRACTED & SYNTHESIZED ({url}) ---\n" + combined_text

        except Exception as e:
            log.error(f"Map-Reduce compression failed: {e}")
            return markdown[:5000]
