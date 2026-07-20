"""
silex/tools/rag_query.py — RAG search tool for the LLM.

The LLM calls this tool when it needs to look up information from
the user's locally indexed files.
"""

from __future__ import annotations
from silex_core.tools.base import BaseTool


class RAGQueryTool(BaseTool):
    name = "rag_query"
    description = (
        "Search the indexed local file knowledge base for relevant code, "
        "documentation, or configuration. Use when the user asks about their "
        "codebase, project files, or local documents."
    )
    risk_level = "read_only"
    requires_approval = False
    schema = {
        "query": "string (what to search for in the indexed files)",
        "n_results": "integer (optional, number of results to return, default 5)",
    }

    def __init__(self, file_indexer=None):
        self._indexer = file_indexer

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' argument is required."

        try:
            n_results = int(kwargs.get("n_results", 5))
        except (ValueError, TypeError):
            n_results = 5

        if not self._indexer:
            return (
                "File index not available. Run /index <path> to index a folder first."
            )

        results = self._indexer.search(query, n_results=n_results)
        if not results:
            return "No relevant files found in the index for that query."

        out = [f"Found {len(results)} relevant file chunks:\n"]
        for i, r in enumerate(results, 1):
            out.append(f"[{i}] {r['path']} (line {r['start_line']})")
            out.append(r["content"][:400])
            out.append("---")
        return "\n".join(out)
