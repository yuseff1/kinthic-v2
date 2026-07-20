"""
silex_engine/config.py — Thin compatibility shim.

All canonical values live in silex_core/utils/config.py.
This file re-exports them so legacy imports from silex_engine.config keep working.
"""
import os
from pathlib import Path

# Re-export the canonical constants so any code importing from silex_engine.config
# gets the correct, single source of truth.
from silex_core.utils.config import (  # noqa: F401
    KINTHIC_HOME,
    SILEX_DB,
    SILEX_VECTOR_DB,
    AMAC_THRESHOLD,
    AMAC_WEIGHTS,
    MAX_CONTEXT_MEMORY_CHARS,
    MAX_IMPORTANT_MEMORIES,
    MAX_RECENT_MEMORIES,
    MAX_RELEVANT_MEMORIES,
    MAX_RETRIEVAL_QUERY_CHARS,
    KINTHIC_DAEMON_LOCK,
    gateway_host,
    gateway_port,
)

# Engine-local constants not in silex_core
PORT = int(os.getenv("SILEX_PORT", 8080))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
