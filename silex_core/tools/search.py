"""
Web Search Tool using DuckDuckGo.
"""

from __future__ import annotations

from ddgs import DDGS
from silex_core.tools.base import BaseTool
from silex_engine.memory.vector_store import VectorStore
from silex_core.utils.logger import setup_logger

log = setup_logger("silex.tools.search")

import httpx
import json
from silex_core.utils.config import get_search_secret, browser_actions_enabled


class WebSearchTool(BaseTool):
    name = "web_search"
    risk_level = "network"
    description = (
        "Searches the live internet for current facts, news, or general knowledge."
    )
    schema = {
        "query": "string (the exact search query to execute)",
        "max_results": "integer (optional, default 3, max 5)",
    }

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' argument is required."

        # Sanitize: cap query length to prevent abuse
        query = str(query)[:200]
        max_results = min(int(kwargs.get("max_results", 3)), 5)

        # 1. Try Tavily Search API
        tavily_key = get_search_secret("tavily")
        if tavily_key:
            log.info(f"Executing web_search via Tavily for: '{query}'")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": tavily_key,
                            "query": query,
                            "max_results": max_results,
                        },
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        if results:
                            formatted = (
                                f"Search Results for '{query}' (via Tavily):\n\n"
                            )
                            for i, r in enumerate(results[:max_results], 1):
                                formatted += f"[{i}] {r.get('title', 'No Title')}\n"
                                formatted += f"URL: {r.get('url', 'No URL')}\n"
                                formatted += (
                                    f"Snippet: {r.get('content', 'No Snippet')}\n\n"
                                )
                            return formatted.strip()
            except Exception as e:
                log.warning(f"Tavily API search failed: {e}. Falling back...")

        # 2. Try Brave Search API
        brave_key = get_search_secret("brave")
        if brave_key:
            log.info(f"Executing web_search via Brave for: '{query}'")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        params={"q": query, "count": max_results},
                        headers={
                            "Accept": "application/json",
                            "X-Subscription-Token": brave_key,
                        },
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("web", {}).get("results", [])
                        if results:
                            formatted = f"Search Results for '{query}' (via Brave):\n\n"
                            for i, r in enumerate(results[:max_results], 1):
                                formatted += f"[{i}] {r.get('title', 'No Title')}\n"
                                formatted += f"URL: {r.get('url', 'No URL')}\n"
                                formatted += (
                                    f"Snippet: {r.get('description', 'No Snippet')}\n\n"
                                )
                            return formatted.strip()
            except Exception as e:
                log.warning(f"Brave Search API failed: {e}. Falling back...")

        # 3. Fallback to free DuckDuckGo
        log.info(f"Executing web_search via DuckDuckGo for: '{query}'")
        ddg_error = None
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if results:
                formatted = f"Search Results for '{query}' (via DuckDuckGo):\n\n"
                for i, r in enumerate(results, 1):
                    formatted += f"[{i}] {r.get('title', 'No Title')}\n"
                    formatted += f"URL: {r.get('href', 'No URL')}\n"
                    formatted += f"Snippet: {r.get('body', 'No Snippet')}\n\n"
                return formatted.strip()
            else:
                ddg_error = "No results returned."

        except Exception as e:
            ddg_error = str(e)
            log.warning(f"DuckDuckGo search failed: {e}. Falling back...")

        # 4. Fallback to Playwright Browser HTML parser
        if browser_actions_enabled():
            log.info(f"Executing web_search via Browser Scraper for: '{query}'")
            try:
                from silex_core.tools.browser import BrowserTool

                browser = BrowserTool()
                try:
                    # Utilize HTML search endpoint of DuckDuckGo
                    search_url = f"https://html.duckduckgo.com/html/?q={query}"
                    nav_res = await browser.execute(action="navigate", url=search_url)
                    if "Error" not in nav_res:
                        scrape_res = await browser.execute(action="scrape", accessibility_tree=False)
                        if "BROWSER_OBSERVATION:" in scrape_res:
                            obs_data = json.loads(
                                scrape_res.replace("BROWSER_OBSERVATION:\n", "")
                            )
                            markdown = obs_data.get("result", "")
                            if len(markdown.strip()) > 200:
                                return (
                                    f"Search Results for '{query}' (via Browser Scraper):\n\n"
                                    + markdown[:3000].strip()
                                )
                finally:
                    await browser.close()
            except Exception as e:
                log.error(f"Browser search fallback failed: {e}")
                return f"Error executing search: DDG failed ({ddg_error}) and Browser failover failed ({e})"

        return f"Error executing search: DuckDuckGo failed ({ddg_error}) and Browser automation is disabled/failed."


class SemanticSearchTool(BaseTool):
    name = "semantic_search"
    risk_level = "read_only"
    description = "Search your local workspace using natural language. Useful for finding code patterns, related files, or old memories."
    schema = {
        "query": "string (the semantic query)",
        "n_results": "integer (optional, default 5, max 10)",
    }

    def __init__(self, vector_store: VectorStore):
        self.vs = vector_store

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' argument is required."

        n_results = min(int(kwargs.get("n_results", 5)), 10)
        log.info(f"Executing semantic_search for: '{query}'")

        if not getattr(self.vs, "is_active", False):
            return (
                "Semantic search is disabled: vector memory (ChromaDB) is not installed. "
                'Install with pip install "openyfai-kinthic[vector]" or `pip install chromadb`, then restart Kinthic.'
            )

        try:
            results = self.vs.search(query, n_results=n_results)

            if not results:
                return "No semantic matches found in the local workspace."

            formatted = f"Semantic Matches for '{query}':\n\n"
            for r in results:
                path = r["metadata"].get("path", "Unknown")
                formatted += f"FILE: {path}\n"
                formatted += f"CONTENT: {r['content'][:300]}...\n"
                formatted += "---"

            return formatted.strip()

        except Exception as e:
            log.error(f"Semantic search failed: {e}")
            return f"Error executing semantic search: {str(e)}"


class XSearchTool(BaseTool):
    name = "x_search"
    risk_level = "network"
    description = (
        "Searches X (formerly Twitter) for live posts, user profiles, or discussions using Grok's search index."
    )
    schema = {
        "query": "string (the search term or handle to look up on X)",
    }

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' argument is required."

        # Get the XAI API key
        import os
        xai_key = get_search_secret("xai") or os.getenv("XAI_API_KEY")
        if not xai_key:
            return (
                "Error: XAI_API_KEY is not set. Please add it to your environment or Kinthic secrets to use X search."
            )

        log.info(f"Executing X Search via xAI for: '{query}'")
        try:
            async with httpx.AsyncClient() as client:
                # We call the chat completions endpoint with the built-in x_search tool
                resp = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    json={
                        "model": "grok-2",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Search X for: '{query}'. Provide a summary of the latest posts, profiles, or discussions found.",
                            }
                        ],
                        "tools": [{"type": "x_search"}],
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {xai_key}",
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if answer:
                        return answer
                    return "No results returned from xAI Search."
                else:
                    return f"Error: xAI API returned status code {resp.status_code}: {resp.text}"
        except Exception as e:
            log.error(f"X Search via xAI failed: {e}")
            return f"Error executing X Search: {str(e)}"

