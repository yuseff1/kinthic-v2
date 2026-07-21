"""
silex_core/tools/hybrid_retriever.py — Phase 3 Hybrid Retrieval & RRF Fusion

Combines sparse search (FTS5), dense search (VectorStore), and causal graph walks,
fusing results using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import logging
from typing import Any
from silex_engine.storage.database import Database
from silex_engine.memory.vector_store import VectorStore

log = logging.getLogger("silex.core.hybrid_retriever")


class HybridRetriever:
    """Retrieves context using multi-channel sparse/dense/graph fusion."""

    def __init__(self, db: Database, vector_store: VectorStore | None = None):
        self.db = db
        # If vector_store is not provided, initialize a default one
        self.vector_store = vector_store or VectorStore()

    async def retrieve_hybrid(self, query: str, top_n: int = 5) -> list[dict[str, Any]]:
        """
        Query three channels:
        Channel 1: SQLite FTS5 (Sparse keywords)
        Channel 2: ChromaDB (Dense embeddings)
        Channel 3: CPG / Knowledge Graph connectivity
        Fuse results using Reciprocal Rank Fusion (RRF).
        """
        # Channel 1: Sparse (FTS5 / LIKE fallback)
        sparse_results = await self._query_sparse(query)

        # Channel 2: Dense (Vector Store)
        dense_results = await self._query_dense(query)

        # Channel 3: Graph context
        graph_results = await self._query_graph(query)

        # Reciprocal Rank Fusion (RRF)
        # Compute RRF score: RRF(d) = sum(1 / (60 + rank))
        rrf_scores: dict[str, float] = {}
        doc_details: dict[str, dict] = {}

        channels = [sparse_results, dense_results, graph_results]
        for channel_list in channels:
            for rank_idx, doc in enumerate(channel_list):
                doc_id = doc["id"]
                rank = rank_idx + 1  # 1-based ranking
                score = 1.0 / (60.0 + rank)
                
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + score
                if doc_id not in doc_details:
                    doc_details[doc_id] = doc

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        
        final_results = []
        for doc_id in sorted_ids[:top_n]:
            detail = doc_details[doc_id]
            final_results.append({
                **detail,
                "rrf_score": rrf_scores[doc_id]
            })

        return final_results

    async def _query_sparse(self, query: str) -> list[dict[str, Any]]:
        """Query SQLite virtual table memories_fts or fallback to LIKE."""
        results = []
        # Try FTS5 MATCH
        try:
            rows = await self.db.fetch_all(
                "SELECT id, content FROM memories_fts WHERE content MATCH ? LIMIT 10",
                (query,),
            )
            for r in rows:
                results.append({"id": r["id"], "content": r["content"], "source": "sparse_fts"})
        except Exception:
            # Fallback to standard LIKE match
            try:
                rows = await self.db.fetch_all(
                    "SELECT id, content FROM memories WHERE content LIKE ? LIMIT 10",
                    (f"%{query}%",),
                )
                for r in rows:
                    results.append({"id": r["id"], "content": r["content"], "source": "sparse_like"})
            except Exception as e:
                log.error(f"Sparse query failed: {e}")
        return results

    async def _query_dense(self, query: str) -> list[dict[str, Any]]:
        """Query ChromaDB vector store."""
        results = []
        try:
            if self.vector_store and self.vector_store.is_active:
                matches = self.vector_store.search(query, n_results=10)
                for m in matches:
                    results.append({
                        "id": m["id"],
                        "content": m["content"],
                        "source": "dense",
                        "distance": m["distance"]
                    })
        except Exception as e:
            log.error(f"Dense vector query failed: {e}")
        return results

    async def _query_graph(self, query: str) -> list[dict[str, Any]]:
        """Query local causal knowledge nodes and adjacent claims."""
        results = []
        # Find knowledge nodes matching keywords
        try:
            words = [w for w in query.split() if len(w) > 3]
            if not words:
                return []
            
            conditions = " OR ".join(["content LIKE ?"] * len(words))
            params = [f"%{w}%" for w in words]

            # Fetch matching nodes
            node_rows = await self.db.fetch_all(
                f"SELECT id, content FROM knowledge_nodes WHERE {conditions} LIMIT 5",
                tuple(params)
            )
            for node in node_rows:
                # Add node itself
                results.append({"id": node["id"], "content": node["content"], "source": "graph_node"})
                
                # Fetch causal neighbors (causes, contradicts)
                neighbors = await self.db.fetch_all(
                    """SELECT kn.id, kn.content FROM knowledge_nodes kn
                       INNER JOIN causal_edges e ON e.target_node = kn.id
                       WHERE e.source_node = ? LIMIT 3""",
                    (node["id"],)
                )
                for n in neighbors:
                    results.append({"id": n["id"], "content": n["content"], "source": "graph_neighbor"})
        except Exception as e:
            log.error(f"Graph query failed: {e}")
        return results
