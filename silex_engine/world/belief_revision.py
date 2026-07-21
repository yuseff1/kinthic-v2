"""
silex_engine/world/belief_revision.py — Phase 2 Epistemic Integrity

Implements AGM Belief Revision operators (Expansion, Contraction via Levi Identity, Revision)
and the RipplePropagator (bounded BFS confidence propagation along causal dependency edges).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from typing import Any

log = logging.getLogger("silex.world.belief_revision")


class RipplePropagator:
    """Propagates changes in confidence throughout the knowledge graph using bounded BFS."""

    def __init__(self, db: Any, attenuation_factor: float = 0.85):
        self.db = db
        self.attenuation_factor = attenuation_factor

    async def propagate_change(
        self,
        source_node_id: str,
        delta_confidence: float,
        max_depth: int = 4,
    ) -> list[str]:
        """
        Traverse causal_edges in BFS order starting from source_node_id.
        Apply distance-attenuated delta to target nodes' confidence.
        """
        if abs(delta_confidence) < 0.001:
            return []

        visited_depth: dict[str, int] = {source_node_id: 0}
        queue = deque([(source_node_id, delta_confidence, 0)])
        updated_nodes = []

        while queue:
            curr_id, curr_delta, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Find downstream edges where curr_id is the source
            # and retrieve target_node
            try:
                edges = await self.db.fetch_all(
                    "SELECT target_node FROM causal_edges WHERE source_node = ?",
                    (curr_id,),
                )
            except Exception as e:
                log.error(f"Failed to query causal edges for propagation: {e}")
                continue

            for edge in edges:
                target_id = edge["target_node"]
                next_depth = depth + 1
                if target_id in visited_depth and visited_depth[target_id] < next_depth:
                    continue

                visited_depth[target_id] = next_depth
                # Attenuate the delta based on distance
                next_delta = curr_delta * self.attenuation_factor
                if abs(next_delta) < 0.001:
                    continue
                
                # Fetch current node confidence to update
                try:
                    node = await self.db.fetch_one(
                        "SELECT confidence FROM knowledge_nodes WHERE id = ?",
                        (target_id,),
                    )
                    if node:
                        old_conf = float(node["confidence"])
                        new_conf = min(max(old_conf + next_delta, 0.0), 1.0)
                        
                        # Update confidence in database
                        await self.db.execute(
                            "UPDATE knowledge_nodes SET confidence = ?, last_validated = ? WHERE id = ?",
                            (new_conf, datetime_now_iso(), target_id),
                        )
                        if target_id not in updated_nodes:
                            updated_nodes.append(target_id)
                        
                        # Queue for further propagation
                        queue.append((target_id, next_delta, next_depth))
                except Exception as e:
                    log.error(f"Failed to update propagated confidence for node {target_id}: {e}")

        return updated_nodes


class BeliefRevisionEngine:
    """Manages AGM belief revision operators on the proposition_beliefs table."""

    def __init__(self, db: Any):
        self.db = db
        self.propagator = RipplePropagator(db)

    async def revise_belief(self, claim: str, new_stance: str, new_confidence: float) -> None:
        """
        AGM revision operator using the Levi Identity:
        1. If new belief contradicts existing (e.g. stance change), perform contraction (retract negations).
        2. Expand the belief set with the new stance and confidence.
        3. Propagate changes downstream using RipplePropagator.
        """
        now = time.time()
        
        # Check current belief state
        old_belief = await self.db.fetch_one(
            "SELECT proposition_id, stance, confidence, validity_until FROM proposition_beliefs WHERE claim = ?",
            (claim,),
        )

        old_stance = old_belief["stance"] if old_belief else "unknown"
        old_confidence = float(old_belief["confidence"]) if old_belief else 0.5
        prop_id = old_belief["proposition_id"] if old_belief else uuid.uuid4().hex

        # 1. Contraction (Levi Identity check)
        # If the stance is flipping (e.g. true -> false or false -> true), we must invalidate the prior belief first.
        if old_belief and old_stance != new_stance and new_stance in {"true", "false"}:
            log.info(f"AGM Contraction: Invalidating contradictory prior stance '{old_stance}' for: {claim}")
            # Update validity_until to mark it historically deactivated
            await self.db.execute(
                "UPDATE proposition_beliefs SET validity_until = ?, stance = 'retracted' WHERE proposition_id = ?",
                (now, prop_id),
            )
            
            # Record contradiction in contradictions table
            contradiction_id = uuid.uuid4().hex
            analysis = f"AGM stance flip from '{old_stance}' to '{new_stance}' for claim: {claim}"
            
            # Look up corresponding knowledge nodes if any; if missing, create stubs to satisfy FK constraints
            nodes = await self.db.fetch_all(
                "SELECT id FROM knowledge_nodes WHERE content = ? LIMIT 2",
                (claim,),
            )
            if not nodes:
                node_a = uuid.uuid4().hex
                await self.db.execute(
                    """INSERT INTO knowledge_nodes (id, content, node_type, confidence, source, created_at, last_validated)
                       VALUES (?, ?, 'fact', ?, 'system', ?, ?)""",
                    (node_a, claim, new_confidence, datetime_now_iso(), datetime_now_iso()),
                )
                node_b = node_a
            else:
                node_a = nodes[0]["id"]
                node_b = nodes[1]["id"] if len(nodes) > 1 else node_a

            await self.db.execute(
                """INSERT INTO contradictions (id, node_a, node_b, analysis, status, created_at)
                   VALUES (?, ?, ?, ?, 'resolved', ?)""",
                (contradiction_id, node_a, node_b, analysis, datetime_now_iso()),
            )

        # 2. Expansion / Revision write
        delta_confidence = new_confidence - old_confidence
        log_odds = 0.0
        if 0 < new_confidence < 1:
            try:
                log_odds = float(new_confidence / (1.0 - new_confidence))
                log_odds = float(math_log(log_odds))
            except Exception:
                log_odds = 0.0

        if old_belief:
            await self.db.execute(
                """UPDATE proposition_beliefs
                   SET stance = ?, log_odds = ?, confidence = ?, validity_from = ?, validity_until = NULL, updated_at = ?
                   WHERE proposition_id = ?""",
                (new_stance, log_odds, new_confidence, now, now, prop_id),
            )
        else:
            await self.db.execute(
                """INSERT INTO proposition_beliefs 
                   (proposition_id, claim, stance, log_odds, confidence, validity_from, validity_until, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (prop_id, claim, new_stance, log_odds, new_confidence, now, now, now),
            )

        # 3. Propagate changes to the causal world model
        # Find matching knowledge nodes and run the RipplePropagator
        node_rows = await self.db.fetch_all(
            "SELECT id FROM knowledge_nodes WHERE content = ?",
            (claim,),
        )
        for row in node_rows:
            await self.propagator.propagate_change(row["id"], delta_confidence)


# Helper functions to avoid circular imports / missing attributes
def datetime_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def math_log(val: float) -> float:
    import math
    return math.log(val)
