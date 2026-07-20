---
title: "Architecture"
description: "How the Silex memory engine works under the hood."
---

Kinthic runs on a sophisticated dual-store memory layer called the **Silex Engine**. 
Unlike standard AI agents that just append text to a massive prompt or dump everything into a simple vector DB, Kinthic actively *consolidates* its knowledge into an epistemic graph.

## The Silex Engine Workflow

```mermaid
flowchart TB
  subgraph Client[Kinthic Core (Harness)]
    CLI[CLI / TUI]
    TG[Telegram / Discord]
    Loop[Agent Loop & Tools]
  end

  subgraph Engine[Silex Engine (Daemon)]
    API[Memory API]
    AMAC[A-MAC admission]
    SQLite[(SQLite + FTS)]
    Vectors[(Chroma vectors)]
    Graph[(Epistemic graph)]
  end

  CLI --> Loop
  TG --> Loop
  Loop -- HTTP / MCP --> API
  API --> AMAC
  AMAC --> SQLite
  AMAC --> Vectors
  API --> Graph
```

### 1. A-MAC (Admission Control)
Before Kinthic saves a memory, it passes through **A-MAC** (Agent Memory Admission Control). This system actively filters out low-quality or redundant facts. If the agent learns something it already knows, A-MAC updates the confidence score of the existing memory rather than duplicating it.

### 2. Dual-Store Memory
Kinthic uses two databases simultaneously:
- **SQLite (FTS):** This acts as the source of truth. All memories are stored as tamper-evident rows. It provides exact keyword matching.
- **Chroma Vectors:** Memories are also embedded to allow semantic similarity searches.
If the vector database ever corrupts, Kinthic automatically self-heals by re-embedding the rows from SQLite on startup.

### 3. Epistemic Graph
Rather than just keeping flat facts, Kinthic builds an **Epistemic Graph**.
Facts are stored as "nodes", and connections (how one fact influences another) are stored as "edges". Over time, beliefs decay if unreferenced, or strengthen if re-validated.

### 4. Hybrid Recall
When Kinthic searches its memory, it uses Reciprocal Rank Fusion (RRF) to blend:
- Recency (when was it learned?)
- Importance (how critical is this fact?)
- Keyword search (exact text matching)
- Semantic search (vector similarity)

This results in a staggering **92% Hit@12 accuracy** on aged 21-day needle-in-a-haystack benchmarks.
