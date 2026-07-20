# Kinthic TUI Operator Guide

The Ink ledger UI shows one chronological activity stream per session. Each row maps to a **TurnEvent** phase emitted by Python.

## Ledger rows

| Row | Meaning |
|-----|---------|
| **You** | Your submitted prompt |
| **● routing / context / tool** | Live activity (spinner) while the turn runs — collapses when Kinthic replies |
| **● sub-agent** | Worker spawned (e.g. `cognitive_worker`) |
| **● memory** | Items written to long-term memory |
| **● error** | Turn or tool failed — read the detail line |
| **Kinthic** | Assistant reply (streams with typewriter) |
| **── Ns · … ──** | Turn summary: latency, tools, memory, tokens, sub-agents |

## Approvals

When Kinthic needs permission for a risky tool (e.g. `spawn_worker`):

1. An interactive **Tool approval** prompt appears below the ledger.
2. Use **↑↓** to select **Allow once** or **Deny**, then **Enter** (or **y** / **n**).
3. After allow: expect **● allowed**, then **● tool** progress, then **● sub-agent** rows.
4. Long runs emit **tool progress** heartbeats every ~5s so the UI does not look frozen.

File edits use the same **Allow once / Deny** pattern with a diff preview.

## What to expect: spawn_worker

```
You
spawn an agent to find Anthropic's latest blog

● routing   …
● tool      spawn_worker planned
[ApprovalPrompt] Allow once / Deny
● allowed   spawn_worker
● tool      Running spawn_worker...
● sub-agent cognitive_worker  running
● sub-agent cognitive_worker  done
Kinthic
Here is what the agent found: …

── 45.2s · 1 tool · 1 memory · 12,400 tok · 1 sub-agent ──
```

If Docker, network, or the worker fails, you should see **● error** or **● sub-agent failed** with a reason — not silence.

## Demo without LLM

```bash
cd kinthic-ink-ui && npm run demo
```

## Transport

Events use NDJSON at `~/.kinthic/ink_events.ndjson` (50ms poll). Keyboard and approvals go to Python on stderr as JSON packets.
