"""
Causal Knowledge Graph Generator â€” Epistemic Trajectory Tracing.

Tracks the agent's OWN decision history as a directed, time-indexed graph.

Four epistemic node types represent logical validity of information:
  - decision:   Active tool executions, shell commands, or file edits.
  - hypothesis: Untested code changes or proposed structural modifications.
  - fact:       Green test passes, verified env vars, confirmed system state.
  - dead_end:   Subprocess crashes, compiler exceptions, unhandled exceptions.

Four edge types define semantic dependencies:
  - triggered_by:      An execution route was initiated by a parent decision.
  - contradicts:       A verified fact invalidates a hypothesis.
  - prevented:         An action successfully bypassed a dead_end.
  - caused_failure_in: A decision is the root cause of a dead_end.

Design decisions vs. the research PDF:
  - Uses the existing Database / asyncio.Queue write path instead of a
    separate BackgroundWriteQueue + threading.Thread. This avoids contention
    on the same SQLite WAL file.
  - Recursive traceback CTE includes a JSON-accumulated visited-set to
    detect and break cycles before hitting max_depth.
  - Nodes are soft-deleted (status='archived') rather than hard-deleted so
    causal chains remain navigable.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from silex_engine.storage.database import Database
from silex_engine.logger import setup_logger

log = setup_logger("silex.causal_graph")

NodeType = Literal["decision", "hypothesis", "fact", "dead_end"]
EdgeType = Literal["triggered_by", "contradicts", "prevented", "caused_failure_in"]

# How many days before an unlinked active node is eligible for archiving
_ARCHIVE_AFTER_DAYS = 30

# Default max depth for recursive traceback queries
_DEFAULT_MAX_DEPTH = 12


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EpistemicNode:
    """A single typed vertex in the epistemic graph."""

    node_id: str
    session_id: str
    type: NodeType
    content: str
    provenance: str
    run_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    integrity_hash: str = ""

    def __post_init__(self) -> None:
        if not self.integrity_hash:
            self.integrity_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """SHA-256 of content + provenance + type + timestamp for tamper detection."""
        payload = f"{self.type}|{self.content}|{self.provenance}|{self.timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Return True if the stored hash still matches the content."""
        return self.integrity_hash == self._compute_hash()

    @staticmethod
    def new(
        session_id: str,
        type: NodeType,
        content: str,
        provenance: str,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "EpistemicNode":
        """Convenience constructor â€” auto-generates a UUID node_id."""
        return EpistemicNode(
            node_id=str(uuid.uuid4()),
            session_id=session_id,
            type=type,
            content=content,
            provenance=provenance,
            run_id=run_id,
            metadata=metadata or {},
        )


@dataclass
class CausalEdge:
    """A directed typed relationship between two epistemic nodes."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: EdgeType
    weight: float = 1.0

    @staticmethod
    def new(
        source_node_id: str,
        target_node_id: str,
        relation_type: EdgeType,
        weight: float = 1.0,
    ) -> "CausalEdge":
        """Convenience constructor â€” auto-generates a UUID edge_id."""
        return CausalEdge(
            edge_id=str(uuid.uuid4()),
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type=relation_type,
            weight=weight,
        )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class CausalKnowledgeGraphGenerator:
    """
    Manages the epistemic memory graph for the SILEX microkernel.

    All writes are routed through the existing Database write queue
    (asyncio-based, BEGIN IMMEDIATE, FileLock) to avoid contention.
    All reads use the read connection (WAL mode allows concurrent reads).
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def _enforce_node_integrity(self, row: dict) -> dict | None:
        """Verify the integrity_hash of a fetched epistemic node row."""
        try:
            ntype = row.get("type") or row.get("node_type", "fact")
            expected_hash = hashlib.sha256(
                f"{ntype}|{row.get('content', '')}|{row.get('provenance', '')}|{row.get('timestamp', 0)}".encode("utf-8")
            ).hexdigest()
            if row.get("integrity_hash") != expected_hash:
                log.warning("Integrity check failed for epistemic node %s! Dropping.", row.get("node_id"))
                return None
            return row
        except Exception as exc:
            log.warning("Failed to verify integrity for epistemic node %s: %s", row.get("node_id"), exc)
            return None

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    async def register_node(self, node: EpistemicNode) -> bool:
        """
        Persist an epistemic node to the database.

        Returns True on success, False on failure (non-raising so callers
        don't need to wrap every observation in try/except).
        """
        dml = """
            INSERT INTO epistemic_nodes
                (node_id, run_id, session_id, timestamp, type, content,
                 provenance, integrity_hash, metadata, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """
        params = (
            node.node_id,
            node.run_id,
            node.session_id,
            node.timestamp,
            node.type,
            node.content,
            node.provenance,
            node.integrity_hash,
            json.dumps(node.metadata),
        )
        try:
            await self.db.execute(dml, params)
            return True
        except Exception as exc:
            if "UNIQUE constraint" in str(exc).upper() or "unique" in str(exc).lower():
                log.warning(
                    "Epistemic node %s already exists (idempotent skip)", node.node_id
                )
                return True  # Idempotent: treat existing node as success
            log.error("Failed to register epistemic node %s: %s", node.node_id, exc)
            return False

    async def register_edge(self, edge: CausalEdge) -> bool:
        """
        Persist a causal edge to the database.

        Returns True on success, False on failure.
        """
        dml = """
            INSERT INTO epistemic_edges
                (edge_id, source_node_id, target_node_id, relation_type, weight)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            edge.edge_id,
            edge.source_node_id,
            edge.target_node_id,
            edge.relation_type,
            edge.weight,
        )
        try:
            await self.db.execute(dml, params)
            return True
        except Exception as exc:
            if "UNIQUE constraint" in str(exc).upper() or "unique" in str(exc).lower():
                log.warning(
                    "Causal edge %s already exists (idempotent skip)", edge.edge_id
                )
                return True
            log.error("Failed to register causal edge %s: %s", edge.edge_id, exc)
            return False

    async def register_observation(
        self,
        session_id: str,
        type: NodeType,
        content: str,
        provenance: str,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        parent_node_id: Optional[str] = None,
        edge_type: Optional[EdgeType] = None,
        edge_weight: float = 1.0,
    ) -> Optional[str]:
        """
        Convenience method: register a node and optionally link it to a parent.

        Returns the new node_id on success, None on failure.
        This is the primary method cognitive_loop.py should call â€”
        one call creates the node and the causal link atomically.
        """
        # Validate: both or neither must be set
        if bool(parent_node_id) != bool(edge_type):
            raise ValueError(
                f"parent_node_id and edge_type must both be set or both be None. "
                f"Got parent_node_id={parent_node_id!r}, edge_type={edge_type!r}"
            )

        node = EpistemicNode.new(
            session_id=session_id,
            type=type,
            content=content,
            provenance=provenance,
            run_id=run_id,
            metadata=metadata,
        )

        async def _write_observation() -> Optional[str]:
            success = await self.register_node(node)
            if not success:
                return None

            if parent_node_id and edge_type:
                edge = CausalEdge.new(
                    source_node_id=parent_node_id,
                    target_node_id=node.node_id,
                    relation_type=edge_type,
                    weight=edge_weight,
                )
                edge_ok = await self.register_edge(edge)
                if not edge_ok:
                    raise RuntimeError(
                        f"Failed to register causal edge for observation {node.node_id}"
                    )
            return node.node_id

        from silex_engine.storage.database import transaction_depth_var

        if transaction_depth_var.get() == 0:
            async with self.db.transaction():
                return await _write_observation()
        return await _write_observation()

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    async def query_traceback_tree(
        self,
        terminal_node_id: str,
        max_depth: int = _DEFAULT_MAX_DEPTH,
    ) -> List[Dict[str, Any]]:
        """
        Recursive CTE traceback: walk *backwards* from a terminal node
        (typically a dead_end) to find its ancestor decisions/hypotheses.

        Cycle detection: the CTE accumulates a JSON list of visited node IDs.
        A node is only expanded if it hasn't already appeared on the current
        path â€” this prevents infinite loops even if the graph has cycles.

        Returns a list of dicts ordered from terminal (depth=0) to root.
        Returns [] on any error (non-raising).
        """
        cte_query = """
            WITH RECURSIVE CausalTrace(
                node_id, parent_id, link_type, depth, visited_path
            ) AS (
                -- Anchor: start at the terminal node
                SELECT
                    ?,
                    NULL,
                    'terminal_sink',
                    0,
                    json_array(?)

                UNION ALL

                -- Recursive step: walk backwards along edges
                SELECT
                    ee.source_node_id,
                    ct.node_id,
                    ee.relation_type,
                    ct.depth + 1,
                    json_insert(ct.visited_path, '$[#]', ee.source_node_id)
                FROM epistemic_edges ee
                INNER JOIN CausalTrace ct ON ee.target_node_id = ct.node_id
                WHERE
                    ct.depth < ?
                    -- Cycle guard: only follow a node we haven't visited
                    AND ee.source_node_id NOT IN (
                        SELECT value FROM json_each(ct.visited_path)
                    )
            )
            SELECT
                ct.node_id,
                ct.parent_id,
                ct.link_type,
                ct.depth,
                en.type       AS node_type,
                en.content,
                en.provenance,
                en.integrity_hash,
                en.metadata,
                en.timestamp,
                en.status
            FROM CausalTrace ct
            INNER JOIN epistemic_nodes en ON ct.node_id = en.node_id
            ORDER BY ct.depth ASC
        """
        try:
            rows = await self.db.fetch_all(
                cte_query,
                (terminal_node_id, terminal_node_id, max_depth),
            )
            return [valid for row in rows if (valid := self._enforce_node_integrity(dict(row)))]
        except Exception as exc:
            log.error(
                "Recursive traceback query failed for node %s: %s",
                terminal_node_id,
                exc,
            )
            return []

    async def get_recent_trajectory(
        self,
        session_id: str,
        limit: int = 20,
        include_types: Optional[List[NodeType]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the most recent active epistemic nodes for a session.

        Used by ContextBuilder to inject a short "what the agent recently
        decided / discovered" section into the system prompt.

        Args:
            session_id:    Current session ID.
            limit:         Max nodes to return (default 20).
            include_types: If set, only return nodes of these types.
                           Defaults to all types.

        Returns a list of dicts ordered newest-first.
        """
        if include_types:
            placeholders = ",".join("?" * len(include_types))
            query = f"""
                SELECT node_id, type, content, provenance, timestamp, metadata, status, integrity_hash
                FROM epistemic_nodes
                WHERE session_id = ?
                  AND status = 'active'
                  AND type IN ({placeholders})
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params: Tuple = (session_id, *include_types, limit)
        else:
            query = """
                SELECT node_id, type, content, provenance, timestamp, metadata, status, integrity_hash
                FROM epistemic_nodes
                WHERE session_id = ?
                  AND status = 'active'
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (session_id, limit)

        try:
            rows = await self.db.fetch_all(query, params)
            return [valid for row in rows if (valid := self._enforce_node_integrity(dict(row)))]
        except Exception as exc:
            log.error(
                "get_recent_trajectory failed for session %s: %s", session_id, exc
            )
            return []

    async def get_dead_ends_for_session(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return active dead_end nodes for a session, newest first.

        Used by the cognitive loop to surface recent failures before retrying.
        """
        try:
            rows = await self.db.fetch_all(
                """
                SELECT node_id, type, content, provenance, timestamp, metadata, integrity_hash
                FROM epistemic_nodes
                WHERE session_id = ? AND type = 'dead_end' AND status = 'active'
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            return [valid for row in rows if (valid := self._enforce_node_integrity(dict(row)))]
        except Exception as exc:
            log.error("get_dead_ends_for_session failed: %s", exc)
            return []

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single epistemic node by ID."""
        try:
            row = await self.db.fetch_one(
                "SELECT * FROM epistemic_nodes WHERE node_id = ?", (node_id,)
            )
            if not row:
                return None
            return self._enforce_node_integrity(dict(row))
        except Exception as exc:
            log.error("get_node failed for %s: %s", node_id, exc)
            return None

    # ------------------------------------------------------------------
    # Archiving (30-day soft-delete, called by CronWorker)
    # ------------------------------------------------------------------

    async def archive_old_nodes(self, days: int = _ARCHIVE_AFTER_DAYS) -> int:
        """
        Soft-archive active epistemic nodes older than `days` days that are
        not referenced by any active session (i.e., the session has ended).

        This keeps causal chains intact while preventing unbounded DB growth.
        Linked nodes (source or target of any edge) are preserved regardless
        of age to avoid orphaning causal chains.

        Returns the count of archived nodes.
        """
        cutoff_ts = time.time() - (days * 86400)
        dml = """
            UPDATE epistemic_nodes
            SET status = 'archived'
            WHERE status = 'active'
              AND timestamp < ?
              AND session_id NOT IN (
                  SELECT id FROM sessions WHERE ended_at IS NULL
              )
              AND node_id NOT IN (
                  SELECT source_node_id FROM epistemic_edges
                  UNION
                  SELECT target_node_id FROM epistemic_edges
              )
            RETURNING node_id
        """
        try:
            cursor = await self.db.execute(dml, (cutoff_ts,))
            rows = await cursor.fetchall() if cursor else []
            count = len(rows)
            if count:
                log.info("Archived %d epistemic nodes older than %d days.", count, days)
            return count
        except Exception as exc:
            log.error("archive_old_nodes failed: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """
        Clean teardown. The Database instance manages its own connection;
        we just log that the graph is being closed.
        """
        log.info("CausalKnowledgeGraphGenerator: shutdown complete.")

