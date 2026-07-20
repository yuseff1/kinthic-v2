"""
Memory Store - KINTHIC's persistent knowledge.

Handles storing, retrieving, searching, and managing memories in SQLite.
The retrieval strategy uses three pools: recency, importance, and relevance.

Polish additions:
  - Duplicate detection before storing
  - Memory deletion (forget)
  - Memory search command
  - Manual memory injection
  - Importance decay over time
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from math import exp
from typing import Any

from silex_engine.memory.admission_control import AdmissionController
from silex_engine.memory.guard import MemoryGuardMiddleware
from silex_engine.models.schemas import Memory, MemorySource, MemoryType
from silex_engine.storage.database import Database
from silex_engine.config import (
    MAX_CONTEXT_MEMORY_CHARS,
    MAX_IMPORTANT_MEMORIES,
    MAX_RECENT_MEMORIES,
    MAX_RELEVANT_MEMORIES,
    MAX_RETRIEVAL_QUERY_CHARS,
)
from silex_engine.memory.vector_store import VectorStore
import hashlib


async def _run_sync(fn, /, *args, **kwargs):
    """Run blocking work in a worker thread (anyio-safe for MCP HTTP transport)."""
    import anyio.to_thread

    if kwargs:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
    return await anyio.to_thread.run_sync(fn, *args)


from silex_engine.logger import setup_logger
from silex_engine.storage.graph_buffer import GraphTransactionBuffer

log = setup_logger("silex.memory")


class MemoryStore:
    """SQLite-backed persistent memory for KINTHIC."""

    def __init__(self, db: Database):
        self.db = db
        self.vs = VectorStore(collection_name="kinthic_memories")
        self.amac = AdmissionController()
        self.guard = MemoryGuardMiddleware()
        self.buffer = GraphTransactionBuffer(db)
        self._fts5_available: bool | None = None  # lazily probed on first search

    async def flush(self) -> None:
        """Atomically flush all pending SQLite writes, then upsert their vectors.

        Vector writes only happen for memories that `commit_flush()` confirms
        were actually committed to SQLite — never before, and never for
        memories that end up not being committed (e.g. an outer transaction
        that rolls back before this runs). This is what closes the "orphan
        vector" split-brain for memories added while nested inside a
        caller-managed transaction (see `add()` below): those calls only
        stage; the vector write is deferred all the way to this point.
        """
        flushed_memories = await self.buffer.commit_flush()
        for memory in flushed_memories:
            await self._upsert_vector(memory)

    async def _upsert_vector(self, memory: Memory) -> None:
        """Best-effort vector upsert for an already SQLite-durable memory.

        Must only ever be called after the corresponding SQLite row is
        committed. Failure here is logged, not raised — `reconcile_vector_index`
        (startup + periodic) backfills any memory missing a vector, so a
        failure here delays semantic recall rather than losing the memory.
        """
        if not self.vs.is_active:
            return
        content_type = (
            memory.memory_type.value
            if isinstance(memory.memory_type, MemoryType)
            else memory.memory_type
        )
        try:
            await _run_sync(
                self.vs.add_chunks,
                [memory.content],
                [
                    {
                        "type": content_type,
                        "timestamp": datetime.now(timezone.utc).timestamp(),
                    }
                ],
                ids=[memory.id],
            )
        except Exception as e:
            log.error(
                "Vector store write failed for %s after SQLite commit; "
                "will be backfilled by the next reconciliation pass: %s",
                memory.id,
                e,
            )

    async def _check_fts5(self) -> bool:
        """Return True if the memories_fts FTS5 virtual table is available."""
        if self._fts5_available is None:
            try:
                await self.db.fetch_one("SELECT count(*) FROM memories_fts LIMIT 0")
                self._fts5_available = True
            except Exception:
                self._fts5_available = False
        return self._fts5_available

    async def fts5_available(self) -> bool:
        """Public wrapper for FTS5 availability checks."""
        return await self._check_fts5()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add_with_result(self, memory: Memory) -> dict:
        """Store a memory and return structured admission outcome (MCP/API transparency)."""
        if await self._is_duplicate(memory.content):
            log.debug(f"Skipped duplicate memory: {memory.content[:40]}...")
            return {
                "accepted": False,
                "memory": None,
                "reason": "duplicate",
                "amac_score": None,
            }

        async def novelty_checker(cand: str) -> float:
            if self.vs.is_active:
                try:
                    results = await _run_sync(self.vs.search, cand, 1)
                    if results and "distance" in results[0]:
                        return min(1.0, results[0]["distance"] / 2.0)
                except Exception as e:
                    log.warning(
                        "Vector search rejected novelty candidate, defaulting to 1.0 novelty: %s",
                        e,
                    )
            return 1.0

        content_type = (
            memory.memory_type.value
            if isinstance(memory.memory_type, MemoryType)
            else memory.memory_type
        )
        prov_dict = memory.provenance if isinstance(memory.provenance, dict) else {}
        source_context = prov_dict.get("context", "")
        session_id = prov_dict.get("session_id", None)
        user_id = prov_dict.get("user_id", "default")

        guard_result = self.guard.validate_write_attempt(memory.id, memory.content)
        if not guard_result["allowed"]:
            log.warning(f"MemoryGuard rejected memory write for {memory.id}")
            return {
                "accepted": False,
                "memory": None,
                "reason": "guard_blocked",
                "amac_score": None,
            }

        if guard_result["flagged"]:
            memory.confidence *= 0.5
            memory.importance *= 0.5

        prov_dict["hmac_signature"] = guard_result.get("signature")
        memory.provenance = prov_dict

        amac_result = await self.amac.evaluate_admission(
            memory.content,
            content_type,
            source_context,
            novelty_checker,
        )

        if not amac_result["admitted"]:
            score = amac_result.get("composite_score")
            log.info(
                f"Memory rejected by A-MAC (Score: {score:.2f}): {memory.content[:40]}..."
            )
            return {
                "accepted": False,
                "memory": None,
                "reason": "amac_rejected",
                "amac_score": float(score) if score is not None else None,
            }

        stored = await self._commit_admitted_memory(
            memory, amac_result, content_type, user_id, session_id
        )
        return {
            "accepted": True,
            "memory": stored,
            "reason": "accepted",
            "amac_score": float(amac_result.get("composite_score", 0.0)),
        }

    async def add(self, memory: Memory) -> Memory | None:
        """Store a new memory (with duplicate detection and A-MAC gating)."""
        result = await self.add_with_result(memory)
        return result.get("memory") if result.get("accepted") else None

    async def _commit_admitted_memory(
        self,
        memory: Memory,
        amac_result: dict,
        content_type: str,
        user_id: str,
        session_id,
    ) -> Memory:
        """Persist a memory that passed guard + A-MAC checks."""
        memory.content = amac_result.get("sanitized_content", memory.content)

        import math

        composite_score = amac_result.get("composite_score", 0.0)
        if math.isnan(composite_score):
            composite_score = 0.0

        integrity_hash = hashlib.sha256(
            f"{memory.id}|{memory.content}|{composite_score}".encode(
                "utf-8", errors="replace"
            )
        ).hexdigest()

        mapped_type = "fact"
        if content_type in ("preference", "normative", "character"):
            mapped_type = "preference"
        elif content_type in ("plan", "project"):
            mapped_type = "plan"
        elif content_type == "transient":
            mapped_type = "transient"

        content_fingerprint = hashlib.sha256(
            memory.content.strip().lower().encode()
        ).hexdigest()

        async def _write_sqlite_rows() -> None:
            await self.buffer.stage_memory(memory)

            await self.buffer.stage_raw_query(
                """
                INSERT OR REPLACE INTO admitted_memories (
                    memory_id, user_id, session_id, content, content_type,
                    utility_score, confidence_score, novelty_score, recency_score, type_prior,
                    composite_score, admitted_at, integrity_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    user_id,
                    session_id,
                    memory.content,
                    mapped_type,
                    amac_result["utility"],
                    amac_result["confidence"],
                    amac_result["novelty"],
                    amac_result["recency"],
                    amac_result["type_prior"],
                    amac_result["composite_score"],
                    datetime.now(timezone.utc).timestamp(),
                    integrity_hash,
                ),
            )

            try:
                if await self._check_fts5():
                    await self.buffer.stage_raw_query(
                        "INSERT OR IGNORE INTO memories_fts(content, id) VALUES (?, ?)",
                        (memory.content, memory.id),
                    )
            except Exception:
                self._fts5_available = None

        from silex_engine.storage.database import transaction_depth_var

        await _write_sqlite_rows()

        if transaction_depth_var.get() == 0:
            # Commit SQLite FIRST, then upsert the vector. This ordering (and
            # only vector-writing memories that `commit_flush()` confirms were
            # actually committed) is the fix for the historical "orphan
            # vector" split-brain: previously the vector was written
            # before/independently of the SQLite commit, so a crash or later
            # rollback left a vector with no backing row — and since
            # duplicate/novelty checks only query ChromaDB, that orphan would
            # permanently block the same content from ever being re-added.
            flushed_memories = await self.buffer.commit_flush()
            for flushed in flushed_memories:
                await self._upsert_vector(flushed)
        else:
            # Nested inside a caller-managed outer transaction: only stage.
            # Committing (and therefore vector-writing) here would be unsafe —
            # the outer transaction might still roll back this row. The
            # eventual top-level `flush()` call performs both the commit and
            # the vector upsert together once this data is actually durable.
            pass

        log.debug(
            f"Stored memory (A-MAC {composite_score:.2f}): {memory.content[:60]}..."
        )
        return memory

    async def get(self, memory_id: str) -> Memory | None:
        """Retrieve a single memory by ID."""
        row = await self.db.fetch_one(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        )
        if row is None:
            return None
        return self._row_to_memory(row)

    async def get_by_index(self, index: int) -> Memory | None:
        """Retrieve a memory by its display index (1-based, sorted by importance)."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories ORDER BY importance DESC"
        )
        if 1 <= index <= len(rows):
            return self._row_to_memory(rows[index - 1])
        return None

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        row = await self.db.fetch_one(
            "SELECT content FROM memories WHERE id = ?", (memory_id,)
        )
        if row is None:
            return False
        async with self.db.transaction():
            await self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            await self.db.execute(
                "DELETE FROM admitted_memories WHERE memory_id = ?", (memory_id,)
            )
            try:
                if await self._check_fts5():
                    await self.db.execute(
                        "DELETE FROM memories_fts WHERE id = ?", (memory_id,)
                    )
            except Exception:
                pass

        if self.vs.is_active:
            try:
                await _run_sync(self.vs.delete_by_ids, [memory_id])
            except Exception as e:
                # SQLite has already committed the delete — the vector is now an
                # orphan. Don't log-and-forget: durably queue it for retry so it
                # gets cleaned up even across a process restart, instead of
                # silently lingering in ChromaDB (and in search results) until
                # the next full reconciliation pass happens to notice it.
                log.error(
                    "Vector store delete failed for %s (SQLite already committed); queuing for retry: %s",
                    memory_id,
                    e,
                )
                try:
                    await self.db.execute(
                        "INSERT OR REPLACE INTO pending_vector_deletes (memory_id, queued_at, attempts) VALUES (?, ?, 0)",
                        (memory_id, datetime.now(timezone.utc).timestamp()),
                    )
                except Exception as queue_exc:
                    log.error(
                        "Failed to queue vector-delete retry for %s: %s",
                        memory_id,
                        queue_exc,
                    )

        log.info(f"Deleted memory: {row['content'][:40]}...")
        return True

    async def retry_pending_vector_deletes(self, max_attempts: int = 10) -> int:
        """Retry vector-store deletes that failed at delete()-time.

        Call on startup and periodically (see cron worker). Idempotent.
        Returns the count of successfully retried deletes.
        """
        if not self.vs.is_active:
            return 0

        rows = await self.db.fetch_all(
            "SELECT memory_id, attempts FROM pending_vector_deletes WHERE attempts < ?",
            (max_attempts,),
        )
        if not rows:
            return 0

        succeeded = 0
        for row in rows:
            memory_id = row["memory_id"]
            try:
                await _run_sync(self.vs.delete_by_ids, [memory_id])
                await self.db.execute(
                    "DELETE FROM pending_vector_deletes WHERE memory_id = ?",
                    (memory_id,),
                )
                succeeded += 1
            except Exception as e:
                log.warning(
                    "Retry of pending vector delete for %s failed (attempt %d): %s",
                    memory_id,
                    row["attempts"] + 1,
                    e,
                )
                try:
                    await self.db.execute(
                        "UPDATE pending_vector_deletes SET attempts = attempts + 1 WHERE memory_id = ?",
                        (memory_id,),
                    )
                except Exception:
                    pass

        if succeeded:
            log.info("Retried %d pending vector delete(s) successfully.", succeeded)
        return succeeded

    async def delete_by_index(self, index: int) -> bool:
        """Delete a memory by its display index (1-based)."""
        memory = await self.get_by_index(index)
        if memory:
            return await self.delete(memory.id)
        return False

    async def update_access(self, memory_id: str) -> None:
        """Mark a memory as accessed (updates timestamp and counter)."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            UPDATE memories
            SET last_accessed = ?, access_count = access_count + 1
            WHERE id = ?
            """,
            (now, memory_id),
        )

    async def update_access_bulk(self, memory_ids: list[str]) -> None:
        """Mark multiple memories as accessed in a single batched write.

        Used by retrieve_context, which previously issued one UPDATE per
        retrieved memory (each a separate round-trip through the serialized
        writer queue) on every single turn.
        """
        if not memory_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        await self.db.executemany(
            """
            UPDATE memories
            SET last_accessed = ?, access_count = access_count + 1
            WHERE id = ?
            """,
            [(now, memory_id) for memory_id in memory_ids],
        )

    async def count(self) -> int:
        """Get total memory count."""
        row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM memories")
        return row["cnt"] if row else 0

    async def all_memories(self) -> list[Memory]:
        """Retrieve all memories (use sparingly)."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories ORDER BY importance DESC"
        )
        return [m for r in rows if (m := self._row_to_memory(r)) is not None]

    async def list_page(
        self, offset: int = 0, limit: int = 20, tag: str | None = None
    ) -> tuple[list[Memory], int]:
        """Paginated memory listing with optional tag filter."""
        if tag:
            count_row = await self.db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM memories m, json_each(m.tags) je
                WHERE je.value = ?
                """,
                (tag,),
            )
            rows = await self.db.fetch_all(
                """
                SELECT m.* FROM memories m, json_each(m.tags) je
                WHERE je.value = ?
                ORDER BY m.importance DESC
                LIMIT ? OFFSET ?
                """,
                (tag, limit, offset),
            )
        else:
            count_row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM memories")
            rows = await self.db.fetch_all(
                "SELECT * FROM memories ORDER BY importance DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        total = int(count_row["cnt"]) if count_row else 0
        memories = [m for r in rows if (m := self._row_to_memory(r)) is not None]
        return memories, total

    async def search(self, query: str) -> list[Memory]:
        """Search memories by keyword (for the :search command)."""
        return await self._search_relevant(query, limit=50)

    async def add_manual(
        self,
        content: str,
        importance: float = 0.5,
        level: int = 1,
        child_memory_ids: list[str] = None,
        tags: list[str] | None = None,
    ) -> Memory | None:
        """Add a memory manually from user command or pruner flush.

        Bypasses A-MAC threshold and duplicate check (intentional), but still
        runs the injection guard to prevent prompt-injection via memory content.

        Returns None if the guard blocks the write — callers (e.g. the weekly
        consolidator) must treat that identically to "nothing was persisted"
        and must NOT archive/discard other memories on the assumption that
        this one landed. Previously this returned a Memory object even when
        blocked, so callers had no way to distinguish "persisted" from
        "guard-blocked", which caused consolidation to archive children whose
        synthesis was silently never written.
        """
        # Apply injection guard even on manual/system memories
        guard_result = self.guard.validate_write_attempt(
            f"manual-{content[:32]}", content
        )
        if not guard_result["allowed"]:
            log.warning("MemoryGuard blocked add_manual content: %s...", content[:40])
            return None
        if guard_result["flagged"]:
            importance = importance * 0.7

        memory = Memory(
            content=content,
            source=MemorySource.USER,
            importance=importance,
            tags=list(tags) if tags else ["manual"],
            level=level,
            child_memory_ids=child_memory_ids or [],
        )
        if guard_result.get("signature"):
            memory.provenance["hmac_signature"] = guard_result["signature"]

        # Bypass duplicate check for manual memories - user explicitly wants it
        await self.db.execute(
            """
            INSERT INTO memories (id, content, source, memory_type, importance,
                                  confidence, created_at, last_accessed,
                                  access_count, tags, level, child_memory_ids, provenance_json,
                                  related_memories, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                memory.source.value,
                memory.memory_type.value,
                memory.importance,
                memory.confidence,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
                json.dumps(memory.tags),
                memory.level,
                json.dumps(memory.child_memory_ids),
                json.dumps(memory.provenance),
                json.dumps(memory.related_memories),
                memory.archived_at,
            ),
        )
        # SQLite is already durable above; route the vector write through the
        # same best-effort helper `add()` uses so a Chroma failure here can't
        # raise past a committed write and crash the caller (e.g. the weekly
        # consolidator) — reconcile_vector_index backfills it instead.
        await self._upsert_vector(memory)

        try:
            if await self._check_fts5():
                await self.db.execute(
                    "INSERT INTO memories_fts(content, id) VALUES (?, ?)",
                    (memory.content, memory.id),
                )
        except Exception:
            self._fts5_available = None

        log.info(f"Manual memory stored: {content[:40]}...")
        return memory

    # ------------------------------------------------------------------
    # Retrieval Strategy
    # ------------------------------------------------------------------

    async def retrieve_context(self, query: str) -> list[Memory]:
        """
        Retrieve memory context using hybrid search (RRF) blending keyword and semantic pools.
        """
        # A pathologically long query (e.g. a pasted document used as turn
        # input) would otherwise be tokenized into thousands of FTS terms and
        # embedded in full for no retrieval-quality benefit.
        query = query[:MAX_RETRIEVAL_QUERY_CHARS]
        candidates: dict[str, Memory] = {}

        # Pool 1: Recent
        recent = await self._get_recent(MAX_RECENT_MEMORIES)
        for m in recent:
            candidates[m.id] = m

        # Pool 2: Important
        important = await self._get_important(MAX_IMPORTANT_MEMORIES)
        for m in important:
            candidates[m.id] = m

        # Pool 3: Relevant (keyword search)
        keyword_results = []
        if query.strip():
            keyword_results = await self._search_relevant(
                query, MAX_RELEVANT_MEMORIES * 2
            )
            for m in keyword_results:
                candidates[m.id] = m

        # Pool 4: Semantic (vector search)
        semantic_results = []
        semantic_memories = []
        if query.strip() and self.vs.is_active:
            semantic_results = await _run_sync(
                self.vs.search, query, MAX_RELEVANT_MEMORIES * 2
            )
            semantic_ids = [res["id"] for res in semantic_results if res.get("id")]
            if semantic_ids:
                placeholders = ",".join("?" * len(semantic_ids))
                rows = await self.db.fetch_all(
                    f"SELECT * FROM memories WHERE id IN ({placeholders}) AND archived_at IS NULL",
                    tuple(semantic_ids),
                )
                import math

                now_ts = datetime.now(timezone.utc).timestamp()
                for row in rows:
                    res = next(
                        (r for r in semantic_results if r["id"] == row["id"]), None
                    )
                    if not res:
                        continue
                    try:
                        created_at = datetime.fromisoformat(row["created_at"])
                        age_days = (now_ts - created_at.timestamp()) / 86400.0
                        distance = res.get("distance", 1.0)
                        similarity = max(0.0, 1.0 - (distance / 2.0))
                        adjusted_score = similarity * math.exp(
                            -age_days / 180.0
                        )
                        if adjusted_score > 0.1:
                            m = self._row_to_memory(row)
                            if m is not None:
                                semantic_memories.append(m)
                                candidates[m.id] = m
                    except Exception as exc:
                        # A single malformed timestamp/row must not abort retrieval
                        # for the whole turn — skip just this candidate.
                        log.warning(
                            "Skipping malformed memory row %s during semantic scoring: %s",
                            row.get("id"),
                            exc,
                        )

        # Reciprocal Rank Fusion (RRF) for hybrid search relevance blending
        rrf_scores = {}
        if query.strip():
            # Rank keyword results by TF-IDF keyword relevance
            def get_keyword_relevance(m):
                query_words = {w.lower() for w in query.split() if len(w) > 2}
                content_words_list = [
                    w.lower() for w in m.content.split() if len(w) > 2
                ]
                if not query_words:
                    return 0.0
                matching_terms = query_words & set(content_words_list)
                matching_term_count = len(matching_terms)
                matching_term_freq = sum(
                    content_words_list.count(w) for w in matching_terms
                )
                import math

                return (matching_term_count / len(query_words)) * math.log(
                    1 + matching_term_freq
                )

            keyword_sorted = sorted(
                keyword_results, key=get_keyword_relevance, reverse=True
            )
            keyword_ranks = {m.id: idx + 1 for idx, m in enumerate(keyword_sorted)}

            # Rank semantic results by vector similarity distance
            semantic_ranks = {}
            if self.vs.is_active and semantic_results:

                def get_semantic_distance(m):
                    res = next((r for r in semantic_results if r["id"] == m.id), None)
                    return res["distance"] if res and "distance" in res else 1.0

                semantic_sorted = sorted(semantic_memories, key=get_semantic_distance)
                semantic_ranks = {
                    m.id: idx + 1 for idx, m in enumerate(semantic_sorted)
                }

            # Compute RRF score (k = 60)
            all_relevant_ids = set(keyword_ranks.keys()) | set(semantic_ranks.keys())
            raw_rrf_scores = {}
            for m_id in all_relevant_ids:
                rank_k = keyword_ranks.get(m_id, 1e9)
                rank_s = semantic_ranks.get(m_id, 1e9)
                raw_rrf_scores[m_id] = 1.0 / (60.0 + rank_k) + 1.0 / (60.0 + rank_s)

            # Normalize RRF score to range [0.0, 1.0]
            if raw_rrf_scores:
                max_rrf = 2.0 / 61.0
                for m_id, raw_score in raw_rrf_scores.items():
                    rrf_scores[m_id] = min(raw_score / max_rrf, 1.0)

        # Fetch A-MAC composite scores to reward high-quality admitted memories
        amac_scores: dict[str, float] = {}
        if candidates:
            ids = list(candidates.keys())
            placeholders = ",".join("?" * len(ids))
            try:
                amac_rows = await self.db.fetch_all(
                    f"SELECT memory_id, composite_score FROM admitted_memories"
                    f" WHERE memory_id IN ({placeholders})",
                    tuple(ids),
                )
                amac_scores = {
                    r["memory_id"]: float(r["composite_score"]) for r in amac_rows
                }
            except Exception:
                pass

        result = sorted(
            candidates.values(),
            key=lambda m: self._retrieval_score(
                m, query, rrf_scores, amac_scores.get(m.id, 0.5)
            ),
            reverse=True,
        )

        # Enforce a total content-size budget: keep highest-scoring memories
        # (already sorted above) until the budget is exhausted, rather than
        # handing the full candidate pool to the prompt assembler unbounded.
        budgeted_result: list[Memory] = []
        total_chars = 0
        for m in result:
            content_len = len(m.content)
            if budgeted_result and total_chars + content_len > MAX_CONTEXT_MEMORY_CHARS:
                break
            budgeted_result.append(m)
            total_chars += content_len
        result = budgeted_result

        # Update access timestamps for retrieved memories in one batched write
        # instead of N sequential round-trips through the writer queue.
        await self.update_access_bulk([m.id for m in result])

        log.debug(f"Retrieved {len(result)} memories for context")
        return result

    async def _get_recent(self, limit: int) -> list[Memory]:
        """Get most recently accessed memories."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories WHERE archived_at IS NULL ORDER BY last_accessed DESC LIMIT ?",
            (limit,),
        )
        return [m for r in rows if (m := self._row_to_memory(r)) is not None]

    async def _get_important(self, limit: int) -> list[Memory]:
        """Get highest importance memories."""
        rows = await self.db.fetch_all(
            "SELECT * FROM memories WHERE archived_at IS NULL ORDER BY importance DESC LIMIT ?",
            (limit,),
        )
        return [m for r in rows if (m := self._row_to_memory(r)) is not None]

    # Hard cap on distinct FTS MATCH terms per query — even a query within the
    # char budget could pathologically consist of thousands of short unique
    # tokens (e.g. "a1 a2 a3 ...").
    _MAX_FTS_KEYWORDS = 40

    async def _search_relevant(self, query: str, limit: int) -> list[Memory]:
        """
        Keyword relevance search: FTS5 (BM25) when available, LIKE fallback.
        """
        query = query[:MAX_RETRIEVAL_QUERY_CHARS]
        keywords = [kw.strip().lower() for kw in query.split() if len(kw.strip()) > 2][
            : self._MAX_FTS_KEYWORDS
        ]
        if not keywords:
            return []

        # Try FTS5 first — returns BM25-ranked results
        if await self._check_fts5():
            try:
                # Wrap each token in double-quotes to handle punctuation safely
                fts_query = " ".join(f'"{kw}"' for kw in keywords)
                fts_rows = await self.db.fetch_all(
                    "SELECT id FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_query, limit),
                )
                if fts_rows:
                    ids = [r["id"] for r in fts_rows]
                    placeholders = ",".join("?" * len(ids))
                    rows = await self.db.fetch_all(
                        f"SELECT * FROM memories WHERE id IN ({placeholders}) AND archived_at IS NULL"
                        f" ORDER BY importance DESC",
                        tuple(ids),
                    )
                    return [
                        m for r in rows if (m := self._row_to_memory(r)) is not None
                    ]
            except Exception as exc:
                log.debug("FTS5 search failed, falling back to LIKE: %s", exc)
                self._fts5_available = None  # reset so next call retries

        # Fallback: LIKE search (original behaviour)
        conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in keywords])
        params = tuple(f"%{kw}%" for kw in keywords)
        rows = await self.db.fetch_all(
            f"SELECT * FROM memories WHERE archived_at IS NULL AND ({conditions}) ORDER BY importance DESC LIMIT ?",
            (*params, limit),
        )
        return [m for r in rows if (m := self._row_to_memory(r)) is not None]

    @staticmethod
    def _retrieval_score(
        memory: Memory,
        query: str,
        rrf_scores: dict[str, float] | None = None,
        amac_boost: float = 0.5,
    ) -> float:
        """
        Fuse importance, reliability, recency, relevance, source trust, and A-MAC quality.

        amac_boost is the composite A-MAC score from admitted_memories (0.0–1.0).
        Centered around 0.5 so memories without an A-MAC record are neutral.
        """
        import math

        query_words = {w.lower() for w in query.split() if len(w) > 2}
        content_words_list = [w.lower() for w in memory.content.split() if len(w) > 2]
        relevance = 0.0
        if rrf_scores and memory.id in rrf_scores:
            relevance = rrf_scores[memory.id]
        elif query_words:
            matching_terms = query_words & set(content_words_list)
            matching_term_count = len(matching_terms)
            matching_term_freq = sum(
                content_words_list.count(w) for w in matching_terms
            )
            relevance = (matching_term_count / len(query_words)) * math.log(
                1 + matching_term_freq
            )

        age_days = 20.7944  # fallback to achieve exp(-age_days/30) = 0.5
        try:
            last_accessed = datetime.fromisoformat(memory.last_accessed)
            age_days = max((datetime.now(timezone.utc) - last_accessed).days, 0)
        except Exception:
            pass

        source_trust = {
            MemorySource.USER: 0.9,
            MemorySource.SYSTEM: 0.85,
            MemorySource.REFLECTION: 0.65,
            MemorySource.INFERENCE: 0.55,
        }.get(memory.source, 0.5)

        type_bonus = {
            MemoryType.PREFERENCE: 0.08,
            MemoryType.PROCEDURAL: 0.06,
            MemoryType.PROJECT: 0.06,
            MemoryType.NORMATIVE: 0.10,
            MemoryType.CHARACTER: 0.09,
        }.get(memory.memory_type, 0.0)

        # A-MAC quality signal: centered at 0.5 so score ∈ [-0.03, +0.03]
        amac_signal = (amac_boost - 0.5) * 0.06

        return (
            memory.importance * exp(-age_days / 30) * 0.43
            + memory.confidence * 0.20
            + relevance * 0.25
            + source_trust * 0.09
            + type_bonus
            + amac_signal
        )

    # ------------------------------------------------------------------
    # Duplicate Detection
    # ------------------------------------------------------------------

    async def _is_duplicate(self, content: str) -> bool:
        """
        Check if a very similar memory already exists.

        Uses vector semantic similarity to catch rephrased facts.
        Falls back to word overlap if VectorStore is offline.
        """
        if self.vs.is_active:
            results = await _run_sync(self.vs.search, content, 1)
            # Distance < 0.2 typically indicates semantic equivalence with MiniLM
            if results and results[0].get("distance", 1.0) < 0.2:
                return True

        content_lower = content.lower().strip()
        content_words = set(content_lower.split())

        if not content_words:
            return False

        # Fallback: Check against recent memories
        recent = await self._get_recent(50)
        for mem in recent:
            existing_words = set(mem.content.lower().strip().split())
            if not existing_words:
                continue

            # Calculate word overlap
            overlap = content_words & existing_words
            smaller = min(len(content_words), len(existing_words))

            if smaller > 0 and len(overlap) / smaller >= 0.8:
                return True

        return False

    async def archive(self, memory_id: str) -> bool:
        """Soft-archive a memory without destroying provenance."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE memories SET archived_at = ? WHERE id = ?",
            (now, memory_id),
        )
        return True

    async def update_confidence(self, memory_id: str, confidence: float) -> bool:
        """Adjust memory confidence for correction workflows."""
        confidence = max(0.0, min(1.0, confidence))
        await self.db.execute(
            "UPDATE memories SET confidence = ? WHERE id = ?",
            (confidence, memory_id),
        )
        return True

    async def merge(self, keep_id: str, merge_id: str) -> bool:
        """Merge two memories by archiving the duplicate and linking provenance."""
        keep = await self.get(keep_id)
        duplicate = await self.get(merge_id)
        if not keep or not duplicate:
            return False
        related = set(keep.related_memories)
        related.add(merge_id)
        provenance = dict(keep.provenance)
        provenance.setdefault("merged_memory_ids", [])
        provenance["merged_memory_ids"].append(merge_id)
        await self.db.execute(
            "UPDATE memories SET related_memories = ?, provenance_json = ? WHERE id = ?",
            (json.dumps(sorted(related)), json.dumps(provenance), keep_id),
        )
        await self.archive(merge_id)
        return True

    async def decay_importance(self, days: int = 7, decay_factor: float = 0.95):
        """Multiplies importance by decay_factor for memories not accessed in the last `days`."""
        await self.db.execute(
            """
            UPDATE memories
            SET importance = importance * ?
            WHERE (julianday('now') - julianday(last_accessed)) > ?
              AND archived_at IS NULL
            """,
            (decay_factor, days),
        )
        log.info(
            f"Decayed importance of memories untouched in {days} days by factor {decay_factor}."
        )

    async def decay_graph_entropy(
        self, days: int = 14, decay_factor: float = 0.8, absolute_threshold: float = 0.1
    ):
        """Phase 2 Patch: Decays confidence of unaccessed graph nodes. Hard-deletes obsolete nodes to prevent vector saturation."""
        await self.db.execute(
            """
            UPDATE knowledge_nodes
            SET confidence = confidence * ?
            WHERE (julianday('now') - julianday(last_validated)) > ?
            """,
            (decay_factor, days),
        )

        await self.db.execute(
            """
            DELETE FROM knowledge_nodes
            WHERE confidence < ?
            """,
            (absolute_threshold,),
        )
        log.warning(
            f"Graph Entropy Decay executed. Penalized {days}-day old nodes. Hard-purged nodes below {absolute_threshold} confidence."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_json_loads(raw: Any, default: Any) -> Any:
        """Parse JSON, tolerating corrupt/legacy rows instead of raising."""
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    def _row_to_memory(self, row: dict) -> Memory | None:
        """Convert a database row to a Memory model; verify HMAC integrity.

        A single corrupt column (bad JSON, unparseable timestamp) must not
        crash the whole retrieval batch — such rows are skipped (logged) so
        the rest of the turn's context can still be assembled.
        """
        try:
            provenance = self._safe_json_loads(row.get("provenance_json"), {})
            signature = (
                provenance.get("hmac_signature")
                if isinstance(provenance, dict)
                else None
            )
            if not self.guard.validate_read_attempt(
                row["id"], row["content"], signature
            ):
                log.warning(
                    "MemoryGuard rejected tampered memory on read: %s", row["id"]
                )
                return None

            return Memory(
                id=row["id"],
                content=row["content"],
                source=row["source"],
                memory_type=row.get("memory_type", "semantic"),
                importance=row["importance"],
                confidence=row.get("confidence", 0.5),
                created_at=row["created_at"],
                last_accessed=row["last_accessed"],
                access_count=row["access_count"],
                tags=self._safe_json_loads(row.get("tags"), []),
                level=row.get("level", 1),
                child_memory_ids=self._safe_json_loads(row.get("child_memory_ids"), []),
                provenance=provenance if isinstance(provenance, dict) else {},
                related_memories=self._safe_json_loads(row.get("related_memories"), []),
                archived_at=row.get("archived_at"),
            )
        except Exception as exc:
            log.error(
                "Skipping corrupt memory row %s: %s", row.get("id", "<unknown>"), exc
            )
            return None

    # ------------------------------------------------------------------
    # Semantic Profiles (Phase 7)
    # ------------------------------------------------------------------

    async def get_semantic_profile(self, term: str) -> dict | None:
        """Retrieve the objective mapping for a subjective term."""
        row = await self.db.fetch_one(
            "SELECT * FROM semantic_profiles WHERE term = ?", (term.lower(),)
        )
        if row:
            return {
                "term": row["term"],
                "objective_proxies": json.loads(row["objective_proxies"]),
                "context_tags": json.loads(row["context_tags"]),
                "confidence": row["confidence"],
                "updated_at": row["updated_at"],
            }
        return None

    async def save_semantic_profile(
        self, term: str, objective_proxies: list[str], confidence: float = 0.5
    ):
        """Save or update a semantic profile."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO semantic_profiles (term, objective_proxies, confidence, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                objective_proxies = excluded.objective_proxies,
                confidence = excluded.confidence,
                updated_at = excluded.updated_at
            """,
            (term.lower(), json.dumps(objective_proxies), confidence, now),
        )

    async def get_all_semantic_profiles(self) -> dict[str, list[str]]:
        """Retrieve all learned semantic mappings."""
        rows = await self.db.fetch_all(
            "SELECT term, objective_proxies FROM semantic_profiles"
        )
        return {row["term"]: json.loads(row["objective_proxies"]) for row in rows}

    async def get_vector_drift_count(self) -> int:
        """Cheap, read-only check of SQLite<->ChromaDB id-set drift.

        Unlike `reconcile_vector_index`, this performs no repair and no
        embedding calls — just an id-set diff — so it's safe to call from a
        hot path like `/api/metrics`.
        """
        if not self.vs.is_active:
            return 0
        try:
            rows = await self.db.fetch_all(
                "SELECT id FROM memories WHERE archived_at IS NULL"
            )
            valid_ids = {row["id"] for row in rows}
            existing = self.vs.collection.get(include=[])
            existing_ids = set(existing.get("ids", []))
        except Exception as e:
            log.warning("Vector drift check failed: %s", e)
            return -1
        return len(valid_ids ^ existing_ids)

    async def reconcile_vector_index(self) -> int:
        """Re-sync SQLite <-> ChromaDB in both directions. Idempotent.

        Forward: ensure every non-archived SQLite memory has a vector entry
        (heals a memory whose vector write failed or was never attempted).

        Reverse: purge vectors with no backing non-archived SQLite row. These
        are orphans left by a crash/rollback between a vector write and the
        SQLite commit; left alone, dedup/novelty checks (which only query
        ChromaDB) would treat that content as a permanent duplicate and block
        the same memory from ever being re-added.

        Call on startup (see CognitiveLoop.startup) or after a vector store
        crash. Returns the count of re-indexed (forward-healed) memories.
        """
        if not self.vs.is_active:
            return 0

        rows = await self.db.fetch_all(
            "SELECT id, content, memory_type FROM memories WHERE archived_at IS NULL"
        )
        valid_ids = {row["id"] for row in rows}

        existing_ids: set[str] = set()
        try:
            existing = self.vs.collection.get(include=[])
            existing_ids = set(existing.get("ids", []))
        except Exception:
            pass

        count = 0
        for row in rows:
            if row["id"] not in existing_ids:
                try:
                    await _run_sync(
                        self.vs.add_chunks,
                        [row["content"]],
                        [{"type": row["memory_type"], "timestamp": 0.0}],
                        ids=[row["id"]],
                    )
                    count += 1
                except Exception as e:
                    log.error("Reconcile failed for memory %s: %s", row["id"], e)

        orphan_ids = existing_ids - valid_ids
        if orphan_ids:
            try:
                await _run_sync(self.vs.delete_by_ids, list(orphan_ids))
                log.warning(
                    "Vector index reconciliation: purged %d orphaned vector(s) with no backing memory row",
                    len(orphan_ids),
                )
            except Exception as e:
                log.error("Failed to purge orphaned vectors: %s", e)

        if count:
            log.info("Vector index reconciliation: re-indexed %d memories", count)
        return count

    async def auto_sign_legacy_memories(self) -> int:
        """Scan SQLite database for unsigned/legacy memories and sign them on startup.

        This prevents security validation errors and amnesia issues when upgrading
        the database to strict signature checking mode.
        """
        rows = await self.db.fetch_all(
            "SELECT id, content, provenance_json FROM memories"
        )

        signed_count = 0
        for row in rows:
            memory_id = row["id"]
            content = row["content"]
            prov_raw = row["provenance_json"]

            try:
                provenance = json.loads(prov_raw)
            except Exception:
                provenance = {}

            if not isinstance(provenance, dict):
                provenance = {}

            signature = provenance.get("hmac_signature")

            # Check signature validity
            is_valid = False
            if signature:
                is_valid = self.guard.validate_read_attempt(memory_id, content, signature)

            if not is_valid:
                # Re-sign the legacy or untrusted memory with the local HMAC key
                result = self.guard.validate_write_attempt(memory_id, content)
                if result.get("allowed") and result.get("signature"):
                    provenance["hmac_signature"] = result["signature"]
                    updated_prov = json.dumps(provenance)
                    await self.db.execute(
                        "UPDATE memories SET provenance_json = ? WHERE id = ?",
                        (updated_prov, memory_id)
                    )
                    signed_count += 1

        if signed_count:
            log.info("Auto-signed %d legacy memories in the database", signed_count)
        return signed_count


