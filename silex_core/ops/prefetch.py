"""
Prefetch helper for pre-warming embedding models during onboarding.
"""

from __future__ import annotations
import logging

log = logging.getLogger("silex.ops.prefetch")


def prefetch_embedding_model() -> str:
    """Pre-warm embedding model or vector store during setup.

    Returns a status string to display to the user.
    """
    try:
        from silex_core.tools.rag_index import RAGIndexTool

        log.info("Initializing vector store prefetch...")
        tool = RAGIndexTool()
        return "✓ Semantic memory index ready."
    except Exception as e:
        log.warning(f"Embedding prefetch skipped: {e}")
        return "✓ Semantic memory index will initialize on first query."
