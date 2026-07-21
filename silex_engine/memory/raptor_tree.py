"""
silex_engine/memory/raptor_tree.py — Phase 3 Hierarchical Retrieval (RAPTOR)

Implements GMM/K-Means-based soft/hard clustering of local memories and builds
a hierarchical tree of summary nodes stored in SQLite.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, List
from chromadb.utils import embedding_functions
from silex_engine.storage.database import Database

try:
    from sklearn.cluster import KMeans
    import numpy as np
except ImportError:
    KMeans = None
    np = None

log = logging.getLogger("silex.memory.raptor")


class RAPTORNode:
    """A node inside the RAPTOR hierarchical summary tree."""

    def __init__(
        self,
        node_id: str,
        text: str,
        level: int,
        children_ids: list[str],
        embedding: list[float],
    ):
        self.node_id = node_id
        self.text = text
        self.level = level
        self.children_ids = children_ids
        self.embedding = embedding

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "text": self.text,
            "level": self.level,
            "children_ids": self.children_ids,
            "embedding": self.embedding,
        }


class RAPTORTreeBuilder:
    """Clusters memories and builds hierarchical text summarization trees."""

    def __init__(self, db: Database, llm: Any = None):
        self.db = db
        self.llm = llm
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()

    async def build_tree_from_memories(self, max_levels: int = 3, cluster_size: int = 5) -> list[RAPTORNode]:
        """
        1. Fetch active memories and calculate embeddings.
        2. Cluster recursively using K-Means.
        3. Summarize each cluster and build summary nodes.
        4. Save all tree nodes into `raptor_nodes`.
        """
        # Fetch base memories
        try:
            rows = await self.db.fetch_all(
                "SELECT id, content FROM memories WHERE archived_at IS NULL"
            )
        except Exception as e:
            log.error(f"Failed to fetch memories: {e}")
            return []

        if not rows:
            return []

        # Create level 0 base nodes
        current_level_nodes = []
        texts = [r["content"] for r in rows]
        
        try:
            # Generate embeddings
            embeddings = self.emb_fn(texts)
        except Exception as e:
            log.error(f"Failed to generate embeddings: {e}")
            embeddings = [[0.0] * 384 for _ in texts]

        # Convert numpy or raw array objects to float lists
        standardized_embeddings = []
        for emb in embeddings:
            if hasattr(emb, "tolist"):
                standardized_embeddings.append(emb.tolist())
            else:
                standardized_embeddings.append([float(x) for x in emb])

        for i, row in enumerate(rows):
            node = RAPTORNode(
                node_id=row["id"],
                text=row["content"],
                level=0,
                children_ids=[],
                embedding=standardized_embeddings[i],
            )
            current_level_nodes.append(node)

        all_nodes = list(current_level_nodes)

        # Clear old raptor nodes
        await self.db.execute("DELETE FROM raptor_nodes")

        level = 0
        while len(current_level_nodes) > cluster_size and level < max_levels:
            level += 1
            next_level_nodes = []

            # Perform clustering
            clusters = self._cluster_nodes(current_level_nodes, cluster_size)
            
            for cluster_idx, group in clusters.items():
                if not group:
                    continue

                # Generate abstractive summary
                summary_text = await self._summarize_group(group)
                
                # Compute summary embedding
                try:
                    summary_emb = self.emb_fn([summary_text])[0]
                    if hasattr(summary_emb, "tolist"):
                        summary_emb = summary_emb.tolist()
                    else:
                        summary_emb = [float(x) for x in summary_emb]
                except Exception:
                    summary_emb = [0.0] * 384

                summary_node = RAPTORNode(
                    node_id=f"raptor_l{level}_{uuid.uuid4().hex[:8]}",
                    text=summary_text,
                    level=level,
                    children_ids=[g.node_id for g in group],
                    embedding=summary_emb,
                )
                next_level_nodes.append(summary_node)
                all_nodes.append(summary_node)

            current_level_nodes = next_level_nodes

        # Save all nodes to database
        for node in all_nodes:
            await self.db.execute(
                """
                INSERT INTO raptor_nodes (node_id, text, level, children_ids, embedding_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    node.node_id,
                    node.text,
                    node.level,
                    json.dumps(node.children_ids),
                    json.dumps(node.embedding),
                ),
            )

        log.info(f"Built RAPTOR tree with {len(all_nodes)} nodes across {level} levels.")
        return all_nodes

    def _cluster_nodes(self, nodes: list[RAPTORNode], cluster_size: int) -> dict[int, list[RAPTORNode]]:
        """Cluster nodes using K-Means or fallback chunking if sklearn is unavailable."""
        n_samples = len(nodes)
        n_clusters = max(2, n_samples // cluster_size)

        if KMeans is None or np is None:
            # Fallback chunking: partition linearly if sklearn is missing
            clusters = {i: [] for i in range(n_clusters)}
            for idx, node in enumerate(nodes):
                clusters[idx % n_clusters].append(node)
            return clusters

        # Format embeddings as numpy matrix
        matrix = np.array([node.embedding for node in nodes])
        
        # Enforce n_clusters <= n_samples
        n_clusters = min(n_clusters, n_samples)

        # Check if vectors have sufficient variance for clustering
        if np.all(matrix == matrix[0]):
            clusters = {i: [] for i in range(n_clusters)}
            for idx, node in enumerate(nodes):
                clusters[idx % n_clusters].append(node)
            return clusters

        try:
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
            labels = kmeans.fit_predict(matrix)
        except Exception as exc:
            log.warning(f"KMeans clustering failed ({exc}), falling back to linear chunking.")
            clusters = {i: [] for i in range(n_clusters)}
            for idx, node in enumerate(nodes):
                clusters[idx % n_clusters].append(node)
            return clusters

        clusters = {i: [] for i in range(n_clusters)}
        for idx, label in enumerate(labels):
            clusters[label].append(nodes[idx])

        return clusters

    async def _summarize_group(self, group: list[RAPTORNode]) -> str:
        """Query LLM to summarize related nodes, or fallback to simple concatenation."""
        combined_text = "\n".join(f"- {n.text}" for n in group)
        
        if self.llm:
            prompt = (
                "You are a precise developer knowledge consolidator. "
                "Write a single, concise summary statement that captures the core facts "
                "and context from these related memories:\n\n"
                f"{combined_text}\n\n"
                "Summary:"
            )
            try:
                # support complete_text or complete interface
                if hasattr(self.llm, "complete_text"):
                    summary = await self.llm.complete_text(prompt)
                else:
                    summary = await self.llm.complete(prompt)
                return summary.strip()
            except Exception as e:
                log.warning(f"RAPTOR summarization call failed: {e}")

        # Fallback summary: concatenate and shorten
        concatenated = "; ".join(n.text for n in group)
        if len(concatenated) > 180:
            return f"Consolidated Summary: {concatenated[:180]}..."
        return f"Consolidated Summary: {concatenated}"
