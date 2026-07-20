"""
Spawn Worker Tool.
Allows the agent to delegate tasks to an isolated worker.
"""

from __future__ import annotations

import uuid

from silex_core.tools.base import BaseTool


class SpawnWorkerTool(BaseTool):
    """Spawns an isolated worker container to run a typed task."""

    name = "spawn_worker"
    risk_level = "sandbox_write"
    requires_approval = True
    description = (
        "Spawns a new isolated Docker container worker to run a specified task/command. "
        "Returns the output of the task execution."
    )
    schema = {
        "task": "string (The command/task to execute inside the worker)",
        "objective": "string (Human-readable objective for telemetry, optional)",
        "tools_allowed": "array of strings (List of tools the worker is authorized to use, default: ['run_terminal_command'])",
        "timeout_seconds": "integer (The maximum time in seconds the worker is allowed to run, default: 600)",
        "network_allowed": "boolean (Whether worker may use egress proxy, default: false)",
        "workspace_mode": "string (ephemeral or worktree for coding tasks, default: ephemeral)",
    }

    async def execute(
        self,
        task: str,
        tools_allowed: list[str] | None = None,
        timeout_seconds: int = 600,
        objective: str = "",
        network_allowed: bool = False,
        workspace_mode: str = "ephemeral",
    ) -> str:
        from agent.jobs import WorkerJob
        from agent.security.lease import ActuationLease
        from agent.orchestrator import WorkerOrchestrator

        tools = tools_allowed or ["run_terminal_command"]
        task_id = f"spawn_{uuid.uuid4().hex[:8]}"

        job = WorkerJob(
            objective=objective or task[:120],
            command=task,
            allowed_tools=tools,
            timeout_seconds=float(timeout_seconds),
            network_allowed=network_allowed,
            workspace_mode=workspace_mode,
            job_id=task_id,
        )

        lease = ActuationLease.issue(
            task_id=task_id,
            agent_id="kinthic_main",
            ttl_seconds=float(timeout_seconds),
            allowed_tools=tools,
            network_allowed=network_allowed,
        )

        orchestrator = WorkerOrchestrator.instance()
        handle = await orchestrator.spawn_job(job, lease)
        result = await handle.structured_result()
        return (
            result.output
            if result.success
            else f"{result.output}\n[Worker failed exit_code={result.exit_code}]"
        )
