<div align="center">
  <img src="docs/assets/banner.svg" alt="Kinthic" width="100%" />
</div>

> **Kinthic — the local-first agent that remembers. Across sessions, on your machine.**

<div align="center">
  <a href="https://github.com/openyfai/kinthic"><img src="https://img.shields.io/github/stars/openyfai/kinthic?style=for-the-badge&color=312e81" alt="Stars"></a>
  <a href="https://github.com/openyfai/kinthic/blob/main/LICENSE"><img src="https://img.shields.io/github/license/openyfai/kinthic?style=for-the-badge&color=5E6A7A" alt="License AGPL-3.0"></a>
  <a href="https://x.com/openyfai"><img src="https://img.shields.io/badge/BUILT_BY-OpenYF_AI-4338ca?style=for-the-badge" alt="Built By"></a>
</div>

---

Kinthic is a local-first AI agent built on the **Silex memory engine** — not a chat log with vectors bolted on. It persists facts in SQLite, indexes them semantically, and maps relationships in an epistemic graph so it can recall *what* it learned and *how* things connect.

**AGPL-3.0** · data lives in `~/.kinthic/` · loopback gateway by default

## Quickstart

```bash
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
kinthic init          # wizard: provider, skills, optional Telegram/MCP
kinthic               # interactive agent session
```

Windows: use [WSL2](docs/wsl-setup.md). Step-by-step: [docs/quickstart.md](docs/quickstart.md) · [docs.kinthic.com](https://docs.kinthic.com)

**Try memory in 30 seconds** (isolated demo):

```bash
python benchmarks/memory_recall/demo.py
```

## Architecture

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

At the core:

- **A-MAC** — admission control filters low-quality memories before they persist
- **Dual-store** — SQLite commits first; vectors follow with reconciliation on startup
- **Hybrid recall** — blends recency, importance, keyword search, and semantic similarity (RRF)
- **Epistemic graph** — beliefs with confidence that decay and update over time

## CLI essentials

| Command | Purpose |
|---------|---------|
| `kinthic init` | First-run wizard (provider, skills, channels, MCP) |
| `kinthic` | Start interactive agent session |
| `kinthic observe` | Visualize the active Silex memory graph |
| `kinthic daemon start` | Background supervisor (channels, proactive goals) |
| `kinthic web` | Local dashboard (metrics, graph, skills) |
| `kinthic mcp serve --stdio` | Expose Silex memory to Claude Desktop / Cursor |
| `kinthic mcp print-config` | Paste-ready MCP client JSON |
| `kinthic skills install <name>` | Install workflow skills from KinthicHub |
| `kinthic data migrate --from openclaw` | Import legacy agent state |
| `kinthic data backup` / `restore` | Export or restore `~/.kinthic` |
| `kinthic benchmark recall` | Run memory recall benchmark |

Full reference: [docs/cli_reference.md](docs/cli_reference.md)

## Features

- **Persistent memory** — hybrid retrieval, consolidation, tamper-evident rows, self-healing vector sync
- **Skills** — Markdown workflows in `~/.kinthic/skills/`; install from catalog or URL
- **MCP** — use Kinthic as the memory layer for external agents (`silex_recall`, `silex_remember`, …)
- **Channels** — Telegram and Discord adapters
- **Trajectory export** — SFT / GRPO datasets from your agent's own runs
- **Local-first** — your brain is a folder on disk; nothing phones home by default

## Memory recall benchmark

Reproducible needle-in-haystack test: **12 facts**, **500 distractor memories**, facts backdated **21 days** (seed 42):

| Baseline (aged 21d) | Hit@5 | Hit@12 |
|---------------------|------:|-------:|
| No memory | 0% | 0% |
| Keyword only | 42% | 50% |
| Vector only | 92% | 92% |
| **Kinthic hybrid** | **67%** | **92%** |

Hybrid matches vector at Hit@12 and beats keyword-only on paraphrased queries. Reproduce:

```bash
kinthic benchmark recall --seed 42
```

Methodology: [docs/benchmarks/memory-recall.md](docs/benchmarks/memory-recall.md) · raw results: [benchmarks/memory_recall/results/REPORT.md](benchmarks/memory_recall/results/REPORT.md)

## Comparison

Category difference, not a feature checklist:

| Product | Role | Kinthic's angle |
|---------|------|-----------------|
| OpenClaw | Channel gateway | Routes messages; Kinthic **remembers** across sessions |
| Hermes | Task agent | Runs workflows; Kinthic builds a **persistent brain** |
| **Kinthic** | Memory + cognition | Dual-store recall, graph beliefs, skills, MCP memory server |

Migrate: `kinthic data migrate --from openclaw|hermes` — [docs/migration.md](docs/migration.md)

## Documentation

- [docs/quickstart.md](docs/quickstart.md) — golden path install → run
- [docs/cli_reference.md](docs/cli_reference.md) — all commands
- [docs/mcp.md](docs/mcp.md) — MCP setup and Silex memory tools
- [docs/benchmarks/memory-recall.md](docs/benchmarks/memory-recall.md) — benchmark methodology
- [docs.kinthic.com](https://docs.kinthic.com) — hosted docs

## Security

Paranoid by design for an agent with access to your machine:

- **Loopback gateway** — API bound to `127.0.0.1` with local API key
- **Tool approvals** — high-risk tools (writes, shell) require explicit approval
- **Sandboxed execution** — terminal commands run in Docker when enabled
- **Memory guard** — injection filtering on memory writes

Read [SECURITY.md](SECURITY.md) before deployment.

## Contributing & roadmap

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/planning/ROADMAP.md](docs/planning/ROADMAP.md)
- Commercial licensing: contact via GitHub org [openyfai](https://github.com/openyfai)
