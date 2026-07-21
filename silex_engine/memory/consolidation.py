"""
silex_engine/memory/consolidation.py — Phase 2 Memory Consolidation

Implements the background sleep-time consolidation logic, applying
Ebbinghaus forgetting curve decay and access reinforcement to local memories.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("silex.memory.consolidation")


class MemoryConsolidationWorker:
    """Consolidates local memories asynchronously by calculating decay, reinforcement, and deactivation."""

    def __init__(
        self,
        db: Any,
        decay_rate: float = 1e-6,           # Small decay rate per second (~0.086 per day)
        reinforcement_factor: float = 0.05, # Boost for frequently accessed memories
        dormancy_threshold: float = 0.15,   # Confidence level below which memory is archived
    ):
        self.db = db
        self.decay_rate = decay_rate
        self.reinforcement_factor = reinforcement_factor
        self.dormancy_threshold = dormancy_threshold

    async def run_consolidation_pass(self) -> dict[str, int]:
        """
        Scan all active semantic memories.
        Apply Ebbinghaus-style decay based on last_accessed time.
        Reinforce based on access_count.
        Archive memories falling below the dormancy threshold.
        """
        now = datetime.now(timezone.utc)
        stats = {"scanned": 0, "updated": 0, "archived": 0}

        try:
            memories = await self.db.fetch_all(
                "SELECT id, confidence, last_accessed, access_count, created_at, importance FROM memories WHERE archived_at IS NULL"
            )
        except Exception as e:
            log.error(f"Failed to fetch memories for consolidation: {e}")
            return stats

        for mem in memories:
            stats["scanned"] += 1
            mem_id = mem["id"]
            c0 = float(mem["confidence"])
            access_count = int(mem["access_count"])

            # Parse last accessed timestamp
            try:
                last_acc_dt = datetime.fromisoformat(mem["last_accessed"])
            except Exception:
                try:
                    last_acc_dt = datetime.fromisoformat(mem["created_at"])
                except Exception:
                    last_acc_dt = now

            # Time difference in seconds
            delta_t = (now - last_acc_dt).total_seconds()
            if delta_t < 0:
                delta_t = 0.0

            # 1. Calculate decayed confidence: C(t) = C0 * e^(-decay_rate * dt)
            time_decay = math.exp(-self.decay_rate * delta_t)
            decayed = c0 * time_decay

            # 2. Add log-access reinforcement: + alpha * log(1 + N_access) scaled by recency decay
            reinforced = decayed + (self.reinforcement_factor * math.log1p(access_count) * time_decay)
            final_conf = min(max(reinforced, 0.0), 1.0)

            # 3. Archive/deactivate if confidence drops below threshold
            if final_conf < self.dormancy_threshold:
                try:
                    await self.db.execute(
                        "UPDATE memories SET archived_at = ? WHERE id = ?",
                        (now.isoformat(), mem_id),
                    )
                    stats["archived"] += 1
                    log.info(f"Memory {mem_id[:8]}... consolidated to dormant/archived state (confidence {final_conf:.2f})")
                except Exception as e:
                    log.error(f"Failed to archive memory {mem_id}: {e}")
            else:
                try:
                    await self.db.execute(
                        "UPDATE memories SET confidence = ? WHERE id = ?",
                        (final_conf, mem_id),
                    )
                    stats["updated"] += 1
                except Exception as e:
                    log.error(f"Failed to update confidence for memory {mem_id}: {e}")

        log.info(f"Consolidation pass completed: {stats}")
        return stats
