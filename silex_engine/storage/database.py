"""
SQLite database layer for KINTHIC.

Handles connection management, schema creation, and migrations.
All operations are async via aiosqlite.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
import asyncio
import os

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

import aiosqlite

from silex_engine.config import SILEX_DB
from silex_engine.logger import setup_logger
from silex_engine.utils import safe_create_task

log = setup_logger("silex.storage")

import sys
if not hasattr(sys, "_kinthic_active_transaction_conn_var"):
    sys._kinthic_active_transaction_conn_var = ContextVar("active_transaction_conn_var", default=None)
if not hasattr(sys, "_kinthic_transaction_depth_var"):
    sys._kinthic_transaction_depth_var = ContextVar("transaction_depth_var", default=0)

active_transaction_conn_var: ContextVar[aiosqlite.Connection | None] = sys._kinthic_active_transaction_conn_var
transaction_depth_var: ContextVar[int] = sys._kinthic_transaction_depth_var

# Global registry for active connected databases
_active_databases: dict[str, Database] = {}

# Sentinel marking an executemany() request in the write queue, distinguishing
# it from a regular (sql, params, future) single-statement write and from the
# (None, None, ...) transaction-lease request.
_EXECUTEMANY_MARKER = object()

# ---------------------------------------------------------------------------
# Schema — this IS the database definition
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Memories table
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    memory_type TEXT NOT NULL DEFAULT 'semantic',
    importance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    level INTEGER NOT NULL DEFAULT 1,
    child_memory_ids TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    related_memories TEXT NOT NULL DEFAULT '[]',
    archived_at TEXT,
    content_fingerprint TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(last_accessed DESC);

-- Goals table
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sub_goals TEXT NOT NULL DEFAULT '[]',
    completion_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    turn_count INTEGER NOT NULL DEFAULT 0,
    memories_created INTEGER NOT NULL DEFAULT 0,
    goals_modified INTEGER NOT NULL DEFAULT 0,
    avg_confidence REAL NOT NULL DEFAULT 0.0,
    topics TEXT NOT NULL DEFAULT '[]'
);

-- Turns table (conversation history)
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    user_input TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    response TEXT NOT NULL,
    self_reflection TEXT NOT NULL,
    confidence REAL NOT NULL,
    scratchpad TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, turn_number);

-- =====================================================================
-- Phase 2 — World Model Tables
-- =====================================================================

-- Knowledge nodes (the graph's vertices)
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'fact',
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'inference',
    created_at TEXT NOT NULL,
    last_validated TEXT NOT NULL,
    validation_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON knowledge_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON knowledge_nodes(confidence DESC);

-- Causal edges (the graph's typed relationships)
CREATE TABLE IF NOT EXISTS causal_edges (
    id TEXT PRIMARY KEY,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    strength REAL NOT NULL DEFAULT 0.5,
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_node) REFERENCES knowledge_nodes(id),
    FOREIGN KEY (target_node) REFERENCES knowledge_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON causal_edges(source_node);
CREATE INDEX IF NOT EXISTS idx_edges_target ON causal_edges(target_node);
CREATE INDEX IF NOT EXISTS idx_edges_type ON causal_edges(edge_type);

-- Hypotheses (predictions from the world model)
CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    claim TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);

-- Contradictions (conflicts between knowledge nodes)
CREATE TABLE IF NOT EXISTS contradictions (
    id TEXT PRIMARY KEY,
    node_a TEXT NOT NULL,
    node_b TEXT NOT NULL,
    analysis TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unresolved',
    resolution TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (node_a) REFERENCES knowledge_nodes(id),
    FOREIGN KEY (node_b) REFERENCES knowledge_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_contradictions_status ON contradictions(status);

-- =====================================================================
-- Phase 7 — Semantic Disambiguation
-- =====================================================================

-- Semantic profiles (learned subjective-to-objective mappings)
CREATE TABLE IF NOT EXISTS semantic_profiles (
    term TEXT PRIMARY KEY,
    objective_proxies TEXT NOT NULL, -- JSON list
    context_tags TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    updated_at TEXT NOT NULL
);

-- =====================================================================
-- Phase 3 — Self-Improvement Tables
-- =====================================================================

CREATE TABLE IF NOT EXISTS improvement_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    original_response TEXT NOT NULL,
    feedback TEXT NOT NULL,
    accuracy_score REAL NOT NULL,
    depth_score REAL NOT NULL,
    honesty_score REAL NOT NULL,
    improved_response TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- =====================================================================
-- Phase 4 — Multi-Agent Debate Tables
-- =====================================================================

CREATE TABLE IF NOT EXISTS uncertainties (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    why_uncertain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

-- =====================================================================
-- Phase 5 — Tool Use & Action Logs
-- =====================================================================

CREATE TABLE IF NOT EXISTS action_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    actual_outcome TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'read_only',
    model_update TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_approvals (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool_name TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    expected_outcome TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    execution_result_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_tool_approvals_status ON tool_approvals(status, created_at);

CREATE TABLE IF NOT EXISTS ethical_decisions (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    turn_number INTEGER NOT NULL DEFAULT 0,
    tool_name TEXT NOT NULL,
    principle TEXT NOT NULL,
    action TEXT NOT NULL,
    rationale TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'read_only',
    requires_consent BOOLEAN NOT NULL DEFAULT 0,
    uncertainty REAL NOT NULL DEFAULT 0.0,
    context TEXT NOT NULL DEFAULT 'interactive',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ethical_decisions_session ON ethical_decisions(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ethical_decisions_action ON ethical_decisions(action, created_at);

CREATE TABLE IF NOT EXISTS recent_failures (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    failure_type TEXT NOT NULL, -- 'critic_rejection', 'tool_error', 'consistency_mismatch'
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_recent_failures_session ON recent_failures(session_id, created_at);

-- =====================================================================
-- Phase 6 — Transfer + Generalization
-- =====================================================================

-- =====================================================================
-- Phase 7 — Recursive Self-Improvement
-- =====================================================================

CREATE TABLE IF NOT EXISTS improvement_proposals (
    id TEXT PRIMARY KEY,
    target_system TEXT NOT NULL,
    description TEXT NOT NULL,
    rationale TEXT NOT NULL,
    success_metric TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_history (
    id TEXT PRIMARY KEY,
    total_score REAL NOT NULL,
    accuracy_avg REAL NOT NULL,
    depth_avg REAL NOT NULL,
    honesty_avg REAL NOT NULL,
    domains_tested_json TEXT NOT NULL,
    question_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_kind TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost_usd REAL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    success BOOLEAN NOT NULL DEFAULT 1,
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_model ON llm_usage(provider, model, created_at DESC);

-- =====================================================================
-- Durable Planning
-- =====================================================================

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    title TEXT NOT NULL,
    user_input TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    success_criteria TEXT NOT NULL DEFAULT '',
    tool_budget INTEGER NOT NULL DEFAULT 8,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_plans_session ON plans(session_id, status);

CREATE TABLE IF NOT EXISTS plan_steps (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    required_tools_json TEXT NOT NULL DEFAULT '[]',
    result TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (plan_id) REFERENCES plans(id)
);

CREATE INDEX IF NOT EXISTS idx_plan_steps_plan ON plan_steps(plan_id, step_number);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'system',
    message TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    delivered INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_checkpoints (
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    draft_reasoning TEXT NOT NULL,
    draft_plan TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'executing_tools',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, turn_number)
);

CREATE TABLE IF NOT EXISTS response_cache (
    query_hash TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Saga Telemetry Logs
CREATE TABLE IF NOT EXISTS saga_telemetry_logs (
    saga_id TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saga_telemetry_saga_id ON saga_telemetry_logs(saga_id);

-- =====================================================================
-- Phase 3 — Epistemic Memory Orchestration Tables
-- =====================================================================

-- User profiles: top-level scope anchor for memory isolation
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    global_preferences TEXT NOT NULL DEFAULT '{}'
);

-- Epistemic nodes: typed decision/hypothesis/fact/dead_end vertices
-- Separate from knowledge_nodes (which tracks world-model semantic facts).
-- This table tracks the AGENT'S OWN reasoning trajectory.
CREATE TABLE IF NOT EXISTS epistemic_nodes (
    node_id TEXT PRIMARY KEY,
    run_id TEXT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('decision', 'hypothesis', 'fact', 'dead_end')),
    content TEXT NOT NULL,
    provenance TEXT NOT NULL,
    integrity_hash TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_epistemic_nodes_type_session ON epistemic_nodes(type, session_id);
CREATE INDEX IF NOT EXISTS idx_epistemic_nodes_timestamp ON epistemic_nodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_epistemic_nodes_status ON epistemic_nodes(status, timestamp DESC);

-- Epistemic causal edges: directed semantic links between epistemic nodes
-- NOTE: uses different column names than causal_edges (world-model) to avoid confusion
CREATE TABLE IF NOT EXISTS epistemic_edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL CHECK(relation_type IN (
        'triggered_by', 'contradicts', 'prevented', 'caused_failure_in'
    )),
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_node_id) REFERENCES epistemic_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES epistemic_nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_epistemic_edges_source ON epistemic_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_epistemic_edges_target ON epistemic_edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_epistemic_edges_relation ON epistemic_edges(relation_type);

-- Vault Sync State: Tracks Obsidian Vault exports
CREATE TABLE IF NOT EXISTS vault_sync_state (
    node_id TEXT PRIMARY KEY,
    last_hash TEXT NOT NULL,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES epistemic_nodes(node_id) ON DELETE CASCADE
);

-- Admitted memories: A-MAC gated memory store with composite quality scores
CREATE TABLE IF NOT EXISTS admitted_memories (
    memory_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK(content_type IN ('preference', 'fact', 'plan', 'transient')),
    utility_score REAL NOT NULL,
    confidence_score REAL NOT NULL,
    novelty_score REAL NOT NULL,
    recency_score REAL NOT NULL,
    type_prior REAL NOT NULL,
    composite_score REAL NOT NULL,
    admitted_at REAL NOT NULL,
    integrity_hash TEXT NOT NULL,
    origin_trajectory_id TEXT,
    skill_name TEXT,
    category TEXT
);

CREATE INDEX IF NOT EXISTS idx_admitted_memories_scores ON admitted_memories(user_id, composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_admitted_memories_admitted_at ON admitted_memories(admitted_at DESC);

-- Trust state: persisted Bayesian Beta-Binomial trust model per actor
CREATE TABLE IF NOT EXISTS trust_state (
    actor_id TEXT PRIMARY KEY,
    alpha REAL NOT NULL DEFAULT 10.0,
    beta REAL NOT NULL DEFAULT 1.0,
    last_updated REAL NOT NULL,
    anomaly_count INTEGER NOT NULL DEFAULT 0
);

-- =====================================================================
-- Phase 7 — Self-Evolution Tables
-- =====================================================================
CREATE TABLE IF NOT EXISTS trajectories (
    trajectory_id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    is_success INTEGER NOT NULL CHECK (is_success IN (0, 1)),
    cumulative_latency REAL NOT NULL,
    total_tokens INTEGER NOT NULL,
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trajectory_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trajectory_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    action_name TEXT NOT NULL,
    tool_input TEXT NOT NULL,
    execution_output TEXT NOT NULL,
    epistemic_category TEXT NOT NULL CHECK (epistemic_category IN ('decision', 'hypothesis', 'fact', 'dead_end')),
    latency_ms REAL NOT NULL,
    token_usage INTEGER NOT NULL,
    FOREIGN KEY (trajectory_id) REFERENCES trajectories(trajectory_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trajectory_steps_order ON trajectory_steps(trajectory_id, step_order);
"""

MIGRATIONS_SQL = [
    "ALTER TABLE memories ADD COLUMN memory_type TEXT NOT NULL DEFAULT 'semantic'",
    "ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5",
    "ALTER TABLE memories ADD COLUMN level INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE memories ADD COLUMN child_memory_ids TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE memories ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE memories ADD COLUMN archived_at TEXT",
    "ALTER TABLE memories ADD COLUMN content_fingerprint TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_fingerprint ON memories(content_fingerprint) WHERE content_fingerprint IS NOT NULL",
    "ALTER TABLE action_logs ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'read_only'",
    "ALTER TABLE turns ADD COLUMN scratchpad TEXT",
    "ALTER TABLE knowledge_nodes ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unverified'",
    "CREATE TABLE IF NOT EXISTS ethical_decisions (id TEXT PRIMARY KEY, session_id TEXT, turn_number INTEGER NOT NULL DEFAULT 0, tool_name TEXT NOT NULL, principle TEXT NOT NULL, action TEXT NOT NULL, rationale TEXT NOT NULL, risk_level TEXT NOT NULL DEFAULT 'read_only', requires_consent BOOLEAN NOT NULL DEFAULT 0, uncertainty REAL NOT NULL DEFAULT 0.0, context TEXT NOT NULL DEFAULT 'interactive', created_at TEXT NOT NULL, FOREIGN KEY (session_id) REFERENCES sessions(id))",
    # Indexes on columns added by migrations must run after ALTERs (older DBs skip CREATE TABLE).
    "CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)",
    "CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived_at)",
    "CREATE INDEX IF NOT EXISTS idx_ethical_decisions_session ON ethical_decisions(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_ethical_decisions_action ON ethical_decisions(action, created_at)",
    "ALTER TABLE tool_approvals ADD COLUMN expected_outcome TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tool_approvals ADD COLUMN execution_result_json TEXT",
    "CREATE TABLE IF NOT EXISTS llm_usage (id TEXT PRIMARY KEY, session_id TEXT, provider TEXT NOT NULL, model TEXT NOT NULL, request_kind TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL, duration_ms INTEGER NOT NULL DEFAULT 0, success BOOLEAN NOT NULL DEFAULT 1, error TEXT, created_at TEXT NOT NULL, FOREIGN KEY (session_id) REFERENCES sessions(id))",
    "CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_model ON llm_usage(provider, model, created_at DESC)",
    "CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, type TEXT NOT NULL DEFAULT 'system', message TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'info', delivered INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS turn_checkpoints (session_id TEXT NOT NULL, turn_number INTEGER NOT NULL, draft_reasoning TEXT NOT NULL, draft_plan TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'executing_tools', updated_at TEXT NOT NULL, PRIMARY KEY (session_id, turn_number))",
    "CREATE TABLE IF NOT EXISTS response_cache (query_hash TEXT PRIMARY KEY, response TEXT NOT NULL, created_at TEXT NOT NULL)",
    "ALTER TABLE turns ADD COLUMN priority_tags TEXT NOT NULL DEFAULT '[]'",
    "CREATE TABLE IF NOT EXISTS saga_telemetry_logs (saga_id TEXT NOT NULL, status TEXT NOT NULL, current_step TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_saga_telemetry_saga_id ON saga_telemetry_logs(saga_id)",
    # ----------------------------------------------------------------
    # Phase 1 — Epistemic Memory Orchestration migrations
    # These use CREATE TABLE IF NOT EXISTS so they are safe to re-run
    # on fresh databases that already have the tables from SCHEMA_SQL.
    # ----------------------------------------------------------------
    "CREATE TABLE IF NOT EXISTS user_profiles (user_id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, global_preferences TEXT NOT NULL DEFAULT '{}')",
    "CREATE TABLE IF NOT EXISTS epistemic_nodes (node_id TEXT PRIMARY KEY, run_id TEXT, session_id TEXT NOT NULL, timestamp REAL NOT NULL, type TEXT NOT NULL CHECK(type IN ('decision', 'hypothesis', 'fact', 'dead_end')), content TEXT NOT NULL, provenance TEXT NOT NULL, integrity_hash TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')), FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE)",
    "CREATE INDEX IF NOT EXISTS idx_epistemic_nodes_type_session ON epistemic_nodes(type, session_id)",
    "CREATE INDEX IF NOT EXISTS idx_epistemic_nodes_timestamp ON epistemic_nodes(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_epistemic_nodes_status ON epistemic_nodes(status, timestamp DESC)",
    "CREATE TABLE IF NOT EXISTS epistemic_edges (edge_id TEXT PRIMARY KEY, source_node_id TEXT NOT NULL, target_node_id TEXT NOT NULL, relation_type TEXT NOT NULL CHECK(relation_type IN ('triggered_by', 'contradicts', 'prevented', 'caused_failure_in')), weight REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (source_node_id) REFERENCES epistemic_nodes(node_id) ON DELETE CASCADE, FOREIGN KEY (target_node_id) REFERENCES epistemic_nodes(node_id) ON DELETE CASCADE)",
    "CREATE INDEX IF NOT EXISTS idx_epistemic_edges_source ON epistemic_edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_epistemic_edges_target ON epistemic_edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_epistemic_edges_relation ON epistemic_edges(relation_type)",
    "CREATE TABLE IF NOT EXISTS admitted_memories (memory_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT, content TEXT NOT NULL, content_type TEXT NOT NULL CHECK(content_type IN ('preference', 'fact', 'plan', 'transient')), utility_score REAL NOT NULL, confidence_score REAL NOT NULL, novelty_score REAL NOT NULL, recency_score REAL NOT NULL, type_prior REAL NOT NULL, composite_score REAL NOT NULL, admitted_at REAL NOT NULL, integrity_hash TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_admitted_memories_scores ON admitted_memories(user_id, composite_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_admitted_memories_admitted_at ON admitted_memories(admitted_at DESC)",
    "CREATE TABLE IF NOT EXISTS trust_state (actor_id TEXT PRIMARY KEY, alpha REAL NOT NULL DEFAULT 10.0, beta REAL NOT NULL DEFAULT 1.0, last_updated REAL NOT NULL, anomaly_count INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS vault_sync_state (node_id TEXT PRIMARY KEY, last_hash TEXT NOT NULL, synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (node_id) REFERENCES epistemic_nodes(node_id) ON DELETE CASCADE)",
    # ----------------------------------------------------------------
    # Phase 7 — Self-Evolution migrations
    # ----------------------------------------------------------------
    "CREATE TABLE IF NOT EXISTS trajectories (trajectory_id TEXT PRIMARY KEY, task_description TEXT NOT NULL, is_success INTEGER NOT NULL CHECK (is_success IN (0, 1)), cumulative_latency REAL NOT NULL, total_tokens INTEGER NOT NULL, timestamp REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS trajectory_steps (step_id INTEGER PRIMARY KEY AUTOINCREMENT, trajectory_id TEXT NOT NULL, step_order INTEGER NOT NULL, action_name TEXT NOT NULL, tool_input TEXT NOT NULL, execution_output TEXT NOT NULL, epistemic_category TEXT NOT NULL CHECK (epistemic_category IN ('decision', 'hypothesis', 'fact', 'dead_end')), latency_ms REAL NOT NULL, token_usage INTEGER NOT NULL, FOREIGN KEY (trajectory_id) REFERENCES trajectories(trajectory_id) ON DELETE CASCADE)",
    "CREATE INDEX IF NOT EXISTS idx_trajectory_steps_order ON trajectory_steps(trajectory_id, step_order)",
    "CREATE TABLE IF NOT EXISTS synthesized_trajectories (trajectory_id TEXT PRIMARY KEY, skill_name TEXT NOT NULL, synthesized_at REAL NOT NULL, FOREIGN KEY (trajectory_id) REFERENCES trajectories(trajectory_id) ON DELETE CASCADE)",
    "ALTER TABLE admitted_memories ADD COLUMN origin_trajectory_id TEXT",
    "ALTER TABLE notifications ADD COLUMN type TEXT NOT NULL DEFAULT 'system'",
    "ALTER TABLE admitted_memories ADD COLUMN skill_name TEXT",
    "ALTER TABLE admitted_memories ADD COLUMN category TEXT",
    # ----------------------------------------------------------------
    # Durable Autonomy Kernel — durable goal execution tables
    # ----------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS autonomous_jobs (
        goal_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','claimed','running','step_saved','paused','completed','failed','cancelled')),
        idempotency_key TEXT NOT NULL DEFAULT '',
        retry_count INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        timeout_seconds REAL NOT NULL DEFAULT 3600.0,
        created_at REAL NOT NULL,
        started_at REAL,
        completed_at REAL,
        last_heartbeat REAL,
        output_summary TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (goal_id, run_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_autonomous_jobs_status ON autonomous_jobs(status, created_at)",
    """CREATE TABLE IF NOT EXISTS job_events (
        event_id TEXT PRIMARY KEY,
        goal_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        payload_hash TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_job_events_goal_run ON job_events(goal_id, run_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_kind ON job_events(kind, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS job_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        goal_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        superstep INTEGER NOT NULL DEFAULT 0,
        state_json TEXT NOT NULL DEFAULT '{}',
        summary TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_job_checkpoints_goal ON job_checkpoints(goal_id, run_id, superstep DESC)",
    """CREATE TABLE IF NOT EXISTS agent_heartbeats (
        process_id TEXT PRIMARY KEY,
        goal_id TEXT,
        run_id TEXT,
        last_seen REAL NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )""",
    # ----------------------------------------------------------------
    # Epistemic Integrity — evidence ledger and proposition beliefs
    # ----------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS evidence_ledger (
        evidence_id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL
            CHECK(source_type IN ('memory','tool_result','web_search','user_statement','agent_observation','world_graph','contradiction','inference')),
        source_id TEXT,
        claim TEXT NOT NULL,
        supports_positive INTEGER NOT NULL DEFAULT 1,
        confidence REAL NOT NULL DEFAULT 0.5,
        session_id TEXT,
        goal_id TEXT,
        created_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_evidence_ledger_claim ON evidence_ledger(claim)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_ledger_source ON evidence_ledger(source_type, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS proposition_beliefs (
        proposition_id TEXT PRIMARY KEY,
        claim TEXT NOT NULL UNIQUE,
        stance TEXT NOT NULL DEFAULT 'unknown'
            CHECK(stance IN ('true','false','uncertain','unknown','retracted')),
        log_odds REAL NOT NULL DEFAULT 0.0,
        confidence REAL NOT NULL DEFAULT 0.5,
        validity_from REAL,
        validity_until REAL,
        last_verified_at REAL,
        verification_source TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_proposition_beliefs_stance ON proposition_beliefs(stance, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_proposition_beliefs_claim ON proposition_beliefs(claim)",
    # ----------------------------------------------------------------
    # Phase 1 — Memory Engine Hardening
    # ----------------------------------------------------------------
    # Cache-stable memory prefix: frozen per-session digest
    "ALTER TABLE sessions ADD COLUMN memory_summary TEXT",
    # FTS5 full-text search over memories (porter stemmer + unicode)
    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content, id UNINDEXED, tokenize='porter unicode61')",
    # FTS5 full-text search over conversation turns
    "CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(user_input, response, id UNINDEXED, tokenize='porter unicode61')",
    # Index last maintenance pass timestamps in user_profiles.global_preferences (JSON)
    # No schema change needed — stored as JSON key inside existing global_preferences column.
    # Durable retry queue for vector-store deletes that failed after the SQLite
    # row was already removed — see MemoryStore.delete()/retry_pending_vector_deletes().
    """CREATE TABLE IF NOT EXISTS pending_vector_deletes (
        memory_id TEXT PRIMARY KEY,
        queued_at REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0
    )""",
]


# ---------------------------------------------------------------------------
# Database connection management
# ---------------------------------------------------------------------------


class _WriteCompleteCursor:
    """Placeholder cursor returned after a threaded MCP write."""

    async def fetchone(self):
        return None

    async def fetchall(self):
        return []


class TransactionContext:
    """Async context manager for transaction isolation to avoid contextvar generator loss."""
    def __init__(self, db: Database):
        self.db = db
        self.depth = 0
        self.start_event = None
        self.done_event = None
        self.finish_event = None
        self.tx_state = None
        self.token = None

    async def __aenter__(self):
        self.depth = transaction_depth_var.get()
        transaction_depth_var.set(self.depth + 1)

        if self.depth == 0:
            if self.db._writer_dead:
                transaction_depth_var.set(0)
                raise RuntimeError(
                    "Database writer loop is dead; refusing to open another transaction."
                )

            self.start_event = asyncio.Event()
            self.done_event = asyncio.Event()
            self.finish_event = asyncio.Event()
            self.tx_state = {"action": "rollback"}

            # Put transaction request in queue
            try:
                await self.db._enqueue_write(
                    (None, None, self.start_event, self.done_event, (self.tx_state, self.finish_event))
                )
            except RuntimeError:
                transaction_depth_var.set(0)
                raise

            try:
                await self.start_event.wait()
            except asyncio.CancelledError:
                self.tx_state["error"] = asyncio.CancelledError(
                    "Transaction lease cancelled before acquisition."
                )
                self.tx_state["action"] = "rollback"
                self.done_event.set()
                self.finish_event.set()
                raise

            # Check if BEGIN IMMEDIATE failed in the writer loop
            if "error" in self.tx_state:
                transaction_depth_var.set(0)
                raise RuntimeError(
                    f"Database transaction could not begin: {self.tx_state['error']}"
                ) from self.tx_state["error"]

            # Store connection in ContextVar and keep token to reset it
            self.token = active_transaction_conn_var.set(self.db._write_conn)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.depth == 0:
            body_raised = exc_type is not None
            if not body_raised:
                self.tx_state["action"] = "commit"
            else:
                self.tx_state["action"] = "rollback"

            try:
                self.done_event.set()
                writer_ack = True
                try:
                    await asyncio.wait_for(self.finish_event.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    writer_ack = False
                    self.db._writer_dead = True
                    if self.token:
                        active_transaction_conn_var.reset(self.token)
                    else:
                        active_transaction_conn_var.set(None)
                    transaction_depth_var.set(0)
                    log.critical(
                        "Transaction finish_event timed out after 30s — writer loop may be dead"
                    )
                    raise SystemError("Database writer loop permanently deadlocked")

                if self.token:
                    active_transaction_conn_var.reset(self.token)
                else:
                    active_transaction_conn_var.set(None)
                transaction_depth_var.set(0)

                if not body_raised and (
                    self.tx_state.get("forced_rollback") or not writer_ack
                ):
                    raise RuntimeError(
                        "Transaction did not commit: the writer's 30s watchdog forcibly "
                        "rolled it back (or the writer never acknowledged completion). "
                        "None of this transaction's writes were persisted."
                    )
            finally:
                pass
        else:
            transaction_depth_var.set(self.depth)


class Database:
    """Async SQLite database wrapper for KINTHIC with serialized background write queue."""

    @property
    def _write_conn(self) -> aiosqlite.Connection | None:
        normalized_path = os.path.abspath(self.db_path)
        existing = _active_databases.get(normalized_path)
        if existing and existing is not self:
            return existing._write_conn
        return self._write_conn_internal

    @_write_conn.setter
    def _write_conn(self, val: aiosqlite.Connection | None):
        normalized_path = os.path.abspath(self.db_path)
        existing = _active_databases.get(normalized_path)
        if existing and existing is not self:
            existing._write_conn = val
        else:
            self._write_conn_internal = val

    # Consecutive writer-loop crashes tolerated before we stop respawning and
    # start failing writes fast instead of risking another silent hang.
    MAX_CONSECUTIVE_WRITER_FAILURES = 5

    # How long a caller will wait for room in the (bounded, maxsize=10000)
    # write queue before the write is shed (rejected) instead of blocking
    # indefinitely. If the queue stays saturated this long the writer is
    # structurally stuck (alive but not keeping up) and callers deserve a
    # fast, clear failure rather than an unbounded hang.
    WRITE_QUEUE_ENQUEUE_TIMEOUT = float(
        os.getenv("KINTHIC_WRITE_QUEUE_ENQUEUE_TIMEOUT", "60.0")
    )

    # How often to attempt a WAL checkpoint(TRUNCATE) so the -wal file doesn't
    # grow unbounded under sustained write load between SQLite's own passive
    # auto-checkpoints.
    WAL_CHECKPOINT_INTERVAL_SECONDS = float(
        os.getenv("KINTHIC_WAL_CHECKPOINT_INTERVAL_SECONDS", str(30 * 60))
    )

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(SILEX_DB)
        self._lockfile_path = f"{self.db_path}.lock"
        self._conn: aiosqlite.Connection | None = None
        self.write_queue = asyncio.Queue(maxsize=10000)
        self.worker_task = None
        self.is_running = False
        self._write_conn_internal = None
        # Set once the writer loop has crashed too many times in a row to
        # keep respawning. While True, all writes fail immediately instead of
        # being silently queued forever with nothing left to consume them.
        self._writer_dead = False
        self._checkpoint_task = None
        self._is_shared = False
        self._force_single_connection = False

    def _cleanup_orphaned_locks(self) -> None:
        """Scan for lockfile. Check if PID is alive. If not, clean it."""
        try:
            import psutil
        except ImportError:
            log.warning("psutil not available; skipping orphaned process detection.")
            return

        if not os.path.exists(self._lockfile_path):
            return

        try:
            with open(self._lockfile_path, "r") as f:
                content = f.read().strip()
                if not content:
                    return
                lock_pid = int(content)
            
            if lock_pid == os.getpid():
                return
                
            if psutil.pid_exists(lock_pid):
                log.warning(f"Database lock is held by alive Kinthic process (PID {lock_pid}). Cannot safely claim lock.")
            else:
                log.info(f"Database lock held by dead process {lock_pid}. Clearing orphaned lockfile.")
                os.remove(self._lockfile_path)
        except Exception as e:
            log.debug(f"Error checking lockfile: {e}")
            try:
                os.remove(self._lockfile_path)
            except OSError:
                pass

    async def connect(self) -> None:
        """Open the database connection and ensure schema exists."""
        normalized_path = os.path.abspath(self.db_path)
        if normalized_path in _active_databases:
            existing = _active_databases[normalized_path]
            self._conn = existing._conn
            self.write_queue = existing.write_queue
            self.worker_task = existing.worker_task
            self._checkpoint_task = existing._checkpoint_task
            self._is_shared = True
            self._force_single_connection = getattr(existing, "_force_single_connection", False)
            log.info(f"Reusing active database connection for path: {self.db_path}")
            return

        self._is_shared = False
        log.info(f"Connecting to database: {self.db_path}")
        self._cleanup_orphaned_locks()
        self._conn = await aiosqlite.connect(self.db_path, timeout=15.0)
        self._conn.row_factory = aiosqlite.Row

        # Enable WAL mode + settings for robust multi-process concurrency
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA busy_timeout=15000")
        await self._conn.execute("PRAGMA foreign_keys=ON")

        # Verify if WAL mode was successfully enabled
        try:
            cursor = await self._conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            current_mode = row[0].lower() if row else "delete"
            if current_mode != "wal":
                log.warning(
                    f"SQLite WAL mode could not be enabled (current mode: {current_mode}). "
                    "Falling back to single-connection serialization to prevent database deadlocks."
                )
                self._force_single_connection = True
            else:
                self._force_single_connection = False
        except Exception as e:
            log.warning(f"Failed to query current journal mode: {e}")
            self._force_single_connection = False

        # Create tables if they don't exist
        await self._conn.executescript(SCHEMA_SQL)
        await self._run_migrations()
        # Seed the default user profile to satisfy the foreign key constraint
        await self._conn.execute(
            "INSERT OR IGNORE INTO user_profiles (user_id) VALUES ('default')"
        )
        await self._conn.commit()

        # Write our PID to the lockfile
        try:
            with open(self._lockfile_path, "w") as f:
                f.write(str(os.getpid()))
        except Exception as e:
            log.warning(f"Could not write PID lockfile: {e}")

        # Start background writer task
        self.is_running = True
        self.worker_task = safe_create_task(self._writer_loop_supervisor(), "db_writer_supervisor")
        self._checkpoint_task = safe_create_task(self._periodic_checkpoint_loop(), "db_checkpoint")

        log.info("Database schema initialized and background writer queue started")
        _active_databases[normalized_path] = self

    async def _run_migrations(self) -> None:
        """Apply additive migrations for existing local SQLite brains."""
        for sql in MIGRATIONS_SQL:
            try:
                await self._conn.execute(sql)
            except aiosqlite.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise

    async def close(self) -> None:
        """Close the database connection and shut down the writer loop."""
        if getattr(self, "_is_shared", False):
            log.debug(f"Skipping close for shared database connection: {self.db_path}")
            return

        normalized_path = os.path.abspath(self.db_path)
        _active_databases.pop(normalized_path, None)

        self.is_running = False
        if self._checkpoint_task:
            self._checkpoint_task.cancel()
            try:
                await self._checkpoint_task
            except (asyncio.CancelledError, Exception):
                pass
            self._checkpoint_task = None
        # Stop background writer worker task
        await self.write_queue.put(None)
        if self.worker_task:
            try:
                await self.worker_task
            except Exception:
                pass
            self.worker_task = None
            
        # Remove lockfile
        try:
            if not getattr(self, "_is_shared", False) and os.path.exists(self._lockfile_path):
                with open(self._lockfile_path, "r") as f:
                    if int(f.read().strip()) == os.getpid():
                        os.remove(self._lockfile_path)
        except Exception:
            pass

        if self._conn:
            await self._conn.close()
            self._conn = None
            log.info("Database connection closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the active connection or fail."""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def _enqueue_write(self, item) -> None:
        """Put a write/transaction-lease request on the queue, shedding
        (raising) instead of blocking forever if it stays saturated."""
        try:
            await asyncio.wait_for(
                self.write_queue.put(item), timeout=self.WRITE_QUEUE_ENQUEUE_TIMEOUT
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Database write queue has been saturated for over "
                f"{self.WRITE_QUEUE_ENQUEUE_TIMEOUT:.0f}s — shedding this write instead of "
                f"blocking indefinitely (writer alive but not keeping up)."
            )

    def _is_write_query(self, sql: str) -> bool:
        sql_stripped = sql.strip().upper()
        # Any query modifying data is enqueued
        write_keywords = (
            "INSERT",
            "UPDATE",
            "DELETE",
            "REPLACE",
            "CREATE",
            "DROP",
            "ALTER",
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
        )
        return sql_stripped.startswith(write_keywords)

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a single SQL statement. Auto-commits or routes writes to the background queue."""
        from silex_engine.utils import mcp_http_write_ctx

        tx_conn = active_transaction_conn_var.get()
        if tx_conn is not None:
            # We are inside a transaction: run directly on the transaction writer connection
            log.info(f"DB_EXECUTE [TX]: {sql.strip()[:100]} | params: {params}")
            return await tx_conn.execute(sql, params)

        if self._is_write_query(sql):
            if mcp_http_write_ctx.get():
                await self.execute_write_in_thread(sql, params)
                return _WriteCompleteCursor()

            if self._writer_dead:
                raise RuntimeError(
                    "Database writer loop is dead; refusing to queue another write."
                )
            # Write query outside transaction: execute through background writer queue
            log.info(f"DB_EXECUTE [WRITE QUEUE]: {sql.strip()[:100]} | params: {params}")
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            await self._enqueue_write((sql, params, future))
            return await future
        else:
            # Read query: run on main read-only connection
            log.info(f"DB_EXECUTE [READ]: {sql.strip()[:100]} | params: {params}")
            return await self.conn.execute(sql, params)

    async def execute_write_in_thread(self, sql: str, params: tuple = ()) -> None:
        """Run a single write on a sync SQLite connection (MCP HTTP / anyio-safe)."""
        import anyio.to_thread

        def _run() -> None:
            import sqlite3

            conn = sqlite3.connect(self.db_path, timeout=30.0)
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_run)

    async def executemany(self, sql: str, seq_of_params: list[tuple]) -> None:
        """Batch INSERT/UPDATE via executemany, routed through the same
        single-writer path as execute() (writer connection only — never the
        read connection). No-op on an empty sequence.
        """
        if not seq_of_params:
            return

        tx_conn = active_transaction_conn_var.get()
        if tx_conn is not None:
            await tx_conn.executemany(sql, seq_of_params)
            return

        if self._writer_dead:
            raise RuntimeError(
                "Database writer loop is dead; refusing to queue another write."
            )

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self._enqueue_write((_EXECUTEMANY_MARKER, (sql, seq_of_params), future))
        await future

    def transaction(self) -> TransactionContext:
        """Async context manager for transaction isolation."""
        return TransactionContext(self)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict."""
        cursor = await self.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as dicts."""
        cursor = await self.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    def _drain_queue_with_error(self, error: Exception) -> None:
        """Fail every still-queued write/transaction request immediately.

        Used when the writer loop is declared dead so callers currently
        blocked on a future/event don't hang forever waiting for a consumer
        that will never come back.
        """
        while True:
            try:
                item = self.write_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if item is None:
                    continue
                if item[0] is None:
                    _, _, start_event, done_event, payload = item
                    tx_state, finish_event = payload
                    tx_state["error"] = error
                    tx_state["action"] = "rollback"
                    tx_state["forced_rollback"] = True
                    start_event.set()
                    done_event.set()
                    finish_event.set()
                else:
                    _, _, future = item
                    if not future.done():
                        future.set_exception(error)
            finally:
                self.write_queue.task_done()

    async def _periodic_checkpoint_loop(self):
        """Periodically runs PRAGMA wal_checkpoint(TRUNCATE) so the -wal file
        is folded back into the main DB file and truncated, instead of
        growing unbounded under sustained write load between SQLite's own
        passive auto-checkpoints (which can be starved by long-lived readers).

        Issued directly on the writer connection rather than through the
        write queue: wrapping it in the queue's implicit BEGIN IMMEDIATE would
        make the checkpoint always report busy/no-op. aiosqlite serializes all
        calls on a connection through one background thread, so sharing the
        connection with the writer loop task is safe — worst case the
        checkpoint lands mid another statement and reports busy=1, which is
        harmless and simply retried next interval.
        """
        while self.is_running:
            try:
                await asyncio.sleep(self.WAL_CHECKPOINT_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                return
            if not self.is_running or self._writer_dead:
                continue
            conn = self._write_conn
            if conn is None:
                continue
            try:
                cursor = await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                row = await cursor.fetchone()
                if row is not None:
                    busy, wal_pages, checkpointed_pages = row[0], row[1], row[2]
                    if busy:
                        log.debug(
                            "WAL checkpoint(TRUNCATE) partial: busy=%s wal_pages=%s checkpointed=%s",
                            busy,
                            wal_pages,
                            checkpointed_pages,
                        )
                    else:
                        log.debug(
                            "WAL checkpoint(TRUNCATE) complete: wal_pages=%s checkpointed=%s",
                            wal_pages,
                            checkpointed_pages,
                        )
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning(
                    f"Periodic WAL checkpoint failed (will retry next interval): {e}"
                )

    async def _writer_loop_supervisor(self):
        """Supervises the background database writer loop, automatically re-spawning it if it fails/cancels."""
        log.info("Database writer loop supervisor started")
        consecutive_failures = 0
        while self.is_running:
            try:
                # Run the actual writer queue loop
                await self._process_write_queue_loop()
                consecutive_failures = 0
            except asyncio.CancelledError:
                log.info("Database writer loop supervisor cancelled")
                break
            except Exception as e:
                consecutive_failures += 1
                log.critical(
                    f"CRITICAL TELEMETRY: Database writer loop failed with exception: {e} "
                    f"(consecutive failure {consecutive_failures}/{self.MAX_CONSECUTIVE_WRITER_FAILURES}). "
                    f"Re-spawning consumer task connection cleanly...",
                    exc_info=True,
                )
                if self._write_conn:
                    try:
                        await self._write_conn.close()
                    except Exception:
                        pass
                    self._write_conn = None

                if consecutive_failures >= self.MAX_CONSECUTIVE_WRITER_FAILURES:
                    log.critical(
                        "Database writer loop crashed %d times in a row — giving up on "
                        "respawning. All writes will now fail fast (instead of hanging "
                        "indefinitely queued with no consumer) until the process is restarted.",
                        consecutive_failures,
                    )
                    self._writer_dead = True
                    self._drain_queue_with_error(
                        RuntimeError(
                            "Database writer loop is dead after repeated crashes"
                        )
                    )
                    break

                await asyncio.sleep(0.5)

    async def _process_write_queue_loop(self):
        """Dedicated writer loop consuming writes sequentially over a single connection."""
        if getattr(self, "_force_single_connection", False):
            self._write_conn = self._conn
            log.info("Writer thread reusing main connection (Single-Connection Safety Mode)")
        else:
            self._write_conn = await aiosqlite.connect(self.db_path, timeout=15.0)
            self._write_conn.row_factory = aiosqlite.Row

            await self._write_conn.execute("PRAGMA journal_mode=WAL")
            await self._write_conn.execute("PRAGMA synchronous=NORMAL")
            await self._write_conn.execute("PRAGMA busy_timeout=15000")
            await self._write_conn.execute("PRAGMA foreign_keys=ON")
            await self._write_conn.commit()

        while self.is_running:
            try:
                item = await self.write_queue.get()
                if item is None:
                    self.write_queue.task_done()
                    break

                # Check if it is a transaction request
                if item[0] is None:
                    _, _, start_event, done_event, payload = item
                    tx_state, finish_event = payload

                    try:
                        await self._write_conn.execute("BEGIN IMMEDIATE;")
                        start_event.set()

                        # Phase 2 Fix: Apply timeout to prevent deadlocks from starving the background writer
                        try:
                            await asyncio.wait_for(done_event.wait(), timeout=30.0)
                        except asyncio.TimeoutError:
                            proc_info = []
                            try:
                                import psutil
                                current_pid = os.getpid()
                                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                                    if proc.info['pid'] != current_pid:
                                        cmd_str = " ".join(proc.info['cmdline'] or []).lower()
                                        if "kinthic" in cmd_str or "daemon" in cmd_str or "dashboard" in cmd_str:
                                            proc_info.append(f"PID {proc.info['pid']}: {proc.info['cmdline']}")
                            except Exception:
                                pass
                            proc_msg = f" Concurrent processes holding lock: {', '.join(proc_info)}" if proc_info else ""
                            log.critical(
                                f"Transaction blocked the writer thread for 30s! Forcing rollback.{proc_msg}"
                            )
                            tx_state["error"] = RuntimeError(
                                "Transaction blocked too long"
                            )
                            tx_state["action"] = "rollback"
                            tx_state["forced_rollback"] = True

                        action = tx_state.get("action", "rollback")
                        if action == "commit":
                            await self._write_conn.commit()
                        else:
                            await self._write_conn.rollback()
                    except Exception as e:
                        log.error(f"Transaction in background writer failed: {e}")
                        tx_state["error"] = e
                        tx_state["forced_rollback"] = True
                        start_event.set()  # Unblock caller — they will read tx_state["error"]
                        try:
                            await self._write_conn.rollback()
                        except Exception:
                            pass
                    finally:
                        finish_event.set()
                        self.write_queue.task_done()
                    continue

                if item[0] is _EXECUTEMANY_MARKER:
                    _, (sql, seq_of_params), future = item
                    try:
                        await self._write_conn.execute("BEGIN IMMEDIATE;")
                        await self._write_conn.executemany(sql, seq_of_params)
                        await self._write_conn.commit()
                        future.set_result(None)
                    except Exception as ex:
                        try:
                            await self._write_conn.rollback()
                        except Exception:
                            pass
                        future.set_exception(ex)
                    finally:
                        self.write_queue.task_done()
                    continue

                # Regular single query write
                query, params, future = item
                try:
                    await self._write_conn.execute("BEGIN IMMEDIATE;")
                    cursor = await self._write_conn.execute(query, params)
                    await self._write_conn.commit()
                    future.set_result(cursor)
                except Exception as ex:
                    try:
                        await self._write_conn.rollback()
                    except Exception:
                        pass
                    future.set_exception(ex)
                finally:
                    self.write_queue.task_done()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Error in background writer loop: {e}")
                raise

        if self._write_conn and not getattr(self, "_force_single_connection", False):
            await self._write_conn.close()
        self._write_conn = None

