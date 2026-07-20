---
title: "Agent Orchestration"
description: "How Kinthic spawns parallel workers and isolates tasks."
---

Kinthic features a built-in multi-agent orchestration layer. The primary agent does not need to handle everything sequentially; it can delegate tasks to parallel background workers.

## The `WorkerOrchestrator`

The core of Kinthic's multi-agent system is the `WorkerOrchestrator`. 
When the main agent encounters a task that can be isolated (like running a large test suite or researching documentation), it invokes the `spawn_worker` tool.

### How it Works:
1. **Delegation:** The main agent provides a `task` description, `timeout_seconds`, and an explicit list of tools the worker is allowed to use (`tools_allowed`).
2. **Approval:** Because spawning an agent is a high-risk operation, the `spawn_worker` tool requires your explicit human approval by default.
3. **Leasing:** The system issues an `ActuationLease`. This is a security token that defines exactly what the worker is authorized to do (e.g., whether it has network access or filesystem write access).
4. **Execution:** The orchestrator provisions an isolated environment (either an ephemeral worktree or a Docker sandbox) and hands the job off to the worker.
5. **Return:** Once finished, the worker's output and exit code are returned to the main agent.

### Advanced Harnesses
- **Tool Dispatcher:** Kinthic features a robust dispatcher that catches tool errors, detects infinite loops, and dynamically routes approvals.
- **LATS Orchestrator:** For extremely complex reasoning tasks, Kinthic utilizes a **Language Agent Tree Search (LATS)** orchestrator, allowing the agent to explore multiple reasoning paths in parallel before committing to a final solution.
