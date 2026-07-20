import asyncio
import json
from typing import List, Tuple
from silex_engine.models.schemas import KnowledgeNode, CausalEdge, Memory
from silex_engine.storage.database import Database
from silex_engine.logger import setup_logger

log = setup_logger("silex.graph_buffer")


class GraphTransactionBuffer:
    """
    Volatile memory buffer that hoards writes and flushes them to SQLite in a massive atomic transaction.
    Derived from the UNWIND batch-writing physics to prevent disk I/O bottlenecks.
    """

    def __init__(self, db: Database):
        self.db = db
        self._nodes: List[KnowledgeNode] = []
        self._edges: List[CausalEdge] = []
        self._memories: List[Memory] = []
        self._raw_queries: List[Tuple[str, tuple]] = []
        self._lock = asyncio.Lock()

    async def stage_node(self, node: KnowledgeNode) -> None:
        async with self._lock:
            self._nodes.append(node)

    async def stage_edge(self, edge: CausalEdge) -> None:
        async with self._lock:
            self._edges.append(edge)

    async def stage_memory(self, memory: Memory) -> None:
        async with self._lock:
            self._memories.append(memory)

    async def stage_raw_query(self, query: str, params: tuple) -> None:
        async with self._lock:
            self._raw_queries.append((query, params))

    async def commit_flush(self) -> List[Memory]:
        """
        Atomically flush all staged nodes, edges, and memories to SQLite using executemany.

        Routed entirely through `Database.transaction()`/`execute()`/`executemany()`
        (the serialized writer connection) â€” never the plain read connection â€”
        to avoid two connections independently issuing BEGIN against the same
        file (a "database is locked" source under concurrency).

        Staged data is only cleared after a successful commit. On failure it is
        retained so the caller can retry the flush instead of silently losing
        memories/nodes/edges that were staged but never persisted.

        Returns the list of Memory objects that were just committed, so callers
        (MemoryStore.flush/add) can perform vector-store upserts strictly
        *after* the SQLite commit â€” never before â€” which is what prevents
        ChromaDB from ever holding a vector with no backing SQLite row.
        """
        async with self._lock:
            if (
                not self._nodes
                and not self._edges
                and not self._memories
                and not self._raw_queries
            ):
                return []

            memory_count, node_count, edge_count = (
                len(self._memories),
                len(self._nodes),
                len(self._edges),
            )

            try:
                async with self.db.transaction():
                    for query, params in self._raw_queries:
                        await self.db.execute(query, params)

                    if self._memories:
                        memory_data = [
                            (
                                m.id,
                                m.content,
                                m.source.value
                                if hasattr(m.source, "value")
                                else m.source,
                                m.memory_type.value
                                if hasattr(m.memory_type, "value")
                                else m.memory_type,
                                m.importance,
                                m.confidence,
                                m.created_at,
                                m.last_accessed,
                                m.access_count,
                                json.dumps(m.tags),
                                m.level,
                                json.dumps(m.child_memory_ids),
                                json.dumps(m.provenance),
                                json.dumps(m.related_memories),
                                m.archived_at,
                                None,  # content_fingerprint
                            )
                            for m in self._memories
                        ]
                        await self.db.executemany(
                            """
                            INSERT OR REPLACE INTO memories (
                                id, content, source, memory_type, importance, confidence,
                                created_at, last_accessed, access_count, tags, level,
                                child_memory_ids, provenance_json, related_memories, archived_at, content_fingerprint
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            memory_data,
                        )

                    if self._nodes:
                        node_data = [
                            (
                                n.id,
                                n.content,
                                n.node_type.value
                                if hasattr(n.node_type, "value")
                                else n.node_type,
                                n.confidence,
                                n.source,
                                n.created_at,
                                n.last_validated,
                                n.validation_count,
                                n.contradiction_count,
                                n.verification_status.value
                                if hasattr(n.verification_status, "value")
                                else n.verification_status,
                                json.dumps(n.metadata),
                            )
                            for n in self._nodes
                        ]
                        await self.db.executemany(
                            """
                            INSERT OR REPLACE INTO knowledge_nodes (
                                id, content, node_type, confidence, source, created_at,
                                last_validated, validation_count, contradiction_count,
                                verification_status, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            node_data,
                        )

                    if self._edges:
                        edge_data = [
                            (
                                e.id,
                                e.source_node,
                                e.target_node,
                                e.edge_type.value
                                if hasattr(e.edge_type, "value")
                                else e.edge_type,
                                e.strength,
                                e.evidence,
                                e.created_at,
                            )
                            for e in self._edges
                        ]
                        await self.db.executemany(
                            """
                            INSERT OR REPLACE INTO causal_edges (
                                id, source_node, target_node, edge_type, strength, evidence, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            edge_data,
                        )

                # Only clear staged state once the transaction has actually committed.
                committed_memories = list(self._memories)
                self._nodes.clear()
                self._edges.clear()
                self._memories.clear()
                self._raw_queries.clear()

                log.info(
                    f"Batched Flush Complete: {memory_count} memories, {node_count} nodes, {edge_count} edges."
                )
                return committed_memories
            except Exception as e:
                log.error(
                    "Batch flush failed, retaining %d memories/%d nodes/%d edges for retry: %s",
                    memory_count,
                    node_count,
                    edge_count,
                    e,
                )
                raise

