#!/usr/bin/env python3
"""Thin wrapper — runs the full memory recall benchmark harness."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.memory_recall.harness import main

if __name__ == "__main__":
    raise SystemExit(main())
