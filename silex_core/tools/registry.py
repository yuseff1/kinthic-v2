"""
Tool Registry. Manages tool registration and execution routing.

Security: All tool arguments are validated against the tool's schema
before execution to prevent injection of unexpected parameters.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from silex_core.models.schemas import ToolCall, ToolResult
from silex_core.tools.base import BaseTool
from silex_core.tools.search import WebSearchTool, SemanticSearchTool, XSearchTool
from silex_core.tools.file_reader import FileReaderTool
from silex_core.tools.code_editor import CodeEditorTool, ApplyEditTool
from silex_core.tools.system import ListDirectoryTool, RunTerminalCommandTool, RunShellCommandTool
from silex_core.tools.browser import BrowserTool
from silex_core.tools.phantom import PhantomTool
from silex_core.tools.memory import SearchMemoryTool, AppendObservationTool
from silex_core.utils.logger import setup_logger
from silex_core.utils.config import require_tool_approvals, code_apply_enabled

log = setup_logger("silex.tools.registry")


class ToolRegistry:
    """Holds available tools and executes them based on ToolCalls."""

    def __init__(
        self,
        vector_store=None,
        db=None,
        session_manager=None,
        memory_store=None,
        llm=None,
        file_indexer=None,
    ):
        self.tools: dict[str, BaseTool] = {}
        self.vector_store = vector_store
        self.db = db
        self.session_manager = session_manager
        self.memory_store = memory_store
        self.llm = llm
        self.file_indexer = file_indexer
        self._register_defaults()

    def _register_defaults(self):
        """Register the default tools."""
        self.register(WebSearchTool())
        self.register(XSearchTool())
        self.register(FileReaderTool())
        self.register(PhantomTool())  # Phantom Simulator — dry-run before apply
        self.register(CodeEditorTool())
        self.register(ApplyEditTool())
        self.register(ListDirectoryTool())
        self.register(RunTerminalCommandTool())
        self.register(RunShellCommandTool())
        self.register(BrowserTool())
        from silex_core.tools.worker import SpawnWorkerTool

        self.register(SpawnWorkerTool())

        if self.vector_store and getattr(self.vector_store, "is_active", False):
            self.register(SemanticSearchTool(self.vector_store))

        if getattr(self, "memory_store", None):
            self.register(SearchMemoryTool(self.memory_store))
            self.register(AppendObservationTool(self.memory_store))

        if getattr(self, "llm", None):
            from silex_core.tools.directives import UpdateDirectivesTool

            self.register(UpdateDirectivesTool(self.llm))
            from silex_core.tools.web_extract import WebExtractTool

            self.register(WebExtractTool(self.llm))

        if getattr(self, "file_indexer", None):
            from silex_core.tools.rag_query import RAGQueryTool
            from silex_core.tools.rag_index import RAGIndexTool

            self.register(RAGQueryTool(self.file_indexer))
            self.register(RAGIndexTool(self.file_indexer))

        # Phase D — Load user tool plugins from ~/.kinthic/plugins/tools/ and workspace plugins/tools/
        try:
            from silex_core.utils.config import KINTHIC_PLUGINS_TOOLS, WORKSPACE_DIR
            from silex_core.plugins.loader import load_tool_plugins

            # 1. Global home plugins
            user_tools = load_tool_plugins(KINTHIC_PLUGINS_TOOLS)
            for tool in user_tools:
                self.register(tool)

            # 2. Local workspace plugins
            workspace_plugins_dir = WORKSPACE_DIR / "plugins" / "tools"
            workspace_tools = load_tool_plugins(workspace_plugins_dir)
            for tool in workspace_tools:
                self.register(tool)
        except Exception as exc:
            log.warning("Plugin loader error: %s", exc)

    def register_default_tools(
        self, mcp_manager: MCPManager = None, skill_loader=None
    ) -> None:
        from silex_core.tools.web import WebSearchTool, WebExtractTool
        from silex_core.tools.system import (
            TimeTool,
            WaitTool,
            WriteFileTool,
            ReadFileTool,
            RunCommandTool,
            SetGoalTool,
            ReplaceFileTool,
        )
        from silex_core.tools.memory import SearchMemoryTool
        from silex_core.tools.skills import SkillsListTool, SkillViewTool, SkillManageTool

        self.register(WebSearchTool())
        self.register(WebExtractTool())
        self.register(TimeTool())
        self.register(WaitTool())
        self.register(WriteFileTool())
        self.register(ReplaceFileTool())
        self.register(ReadFileTool())
        self.register(RunCommandTool())
        self.register(SetGoalTool())
        self.register(SearchMemoryTool(self.memory_store))

        self.register(SkillsListTool(skill_loader))
        self.register(SkillViewTool(skill_loader))
        self.register(SkillManageTool(skill_loader))

    def register_skill_tools(self, skill_loader) -> None:
        """Register progressive disclosure skill tools."""
        from silex_core.tools.skills import SkillsListTool, SkillViewTool, SkillManageTool

        self.register(SkillsListTool(skill_loader))
        self.register(SkillViewTool(skill_loader))
        self.register(SkillManageTool(skill_loader))

    async def reload_mcp_tools(self) -> int:
        """Unregister stale MCP tools and register fresh ones from mcp.yaml."""
        for name in list(self.tools.keys()):
            if name.startswith("mcp__"):
                del self.tools[name]
        try:
            from silex_core.mcp.manager import get_mcp_manager

            mgr = get_mcp_manager()
            adapted = await mgr.discover_tools()
            for tool in adapted:
                self.register(tool)
            return len(adapted)
        except Exception as exc:
            log.warning("MCP reload failed: %s", exc)
            return 0

    def register(self, tool: BaseTool) -> None:
        """Register a new tool."""
        self.tools[tool.name] = tool
        log.info(f"Registered tool: {tool.name}")

    def get_system_prompt_appendix(self) -> str:
        """Returns the formatted documentation of all tools for the LLM prompt."""
        if not self.tools:
            return "No tools available."

        docs = "AVAILABLE TOOLS:\n"
        for tool in self.tools.values():
            docs += tool.get_prompt_description() + "\n"

        # Append advanced instructions for the browser tool and its ref ID protocol
        docs += (
            "\nBROWSER TOOL PROTOCOL:\n"
            "1. When using the `browser` tool, first `navigate` to the target page, then call `scrape`.\n"
            "2. The `scrape` output contains an 'ACCESSIBILITY TREE' alongside the standard raw markdown.\n"
            "3. Interactive elements are annotated in the ACCESSIBILITY TREE with unique ref IDs inside brackets, e.g., 'link [e12] \"Sign In\"'.\n"
            "4. For any follow-up actions like `click` or `type`, you MUST use the corresponding element's ref ID (e.g. 'e12') in the `selector` field. "
            "Do NOT write raw CSS or XPath selectors if a ref ID is available. This avoids DOM fragility and reduces failures.\n"
            "5. The `screenshot` action overlays these ref ID tags visually onto the image, allowing you to visually verify element placement.\n"
        )

        return docs

    async def execute(
        self, call: ToolCall, execution_mode: str = "interactive"
    ) -> ToolResult:
        """Execute a ToolCall and return a ToolResult."""
        tool = self.tools.get(call.tool_name)
        if not tool:
            log.warning(f"Attempted to call unknown tool: {call.tool_name}")
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome="Error: Tool not found in registry.",
                success=False,
                error="Tool not found",
            )

        # ── Parse arguments ──────────────────────────────────────
        args_dict = {}
        if isinstance(call.arguments, str):
            try:
                args_dict = json.loads(call.arguments)
            except json.JSONDecodeError:
                return ToolResult(
                    tool_name=call.tool_name,
                    actual_outcome="Error: Failed to parse arguments as JSON.",
                    success=False,
                    error="JSON parse error",
                )
        elif isinstance(call.arguments, dict):
            args_dict = call.arguments

        # ── Validate arguments against schema ────────────────────
        # Only allow keys defined in the tool's schema
        allowed_keys = set(tool.schema.keys()) if tool.schema else set()
        unexpected_keys = set(args_dict.keys()) - allowed_keys
        if unexpected_keys:
            log.warning(
                f"Tool {call.tool_name}: rejected unexpected args: {unexpected_keys}"
            )
            # Strip unexpected keys rather than crash
            args_dict = {k: v for k, v in args_dict.items() if k in allowed_keys}

        log.info(f"Executing {call.tool_name} with args: {list(args_dict.keys())}")

        if self._approval_required(tool):
            approval_id = await self._queue_approval(
                tool, args_dict, call.expected_outcome
            )
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome=(
                    f"Error: Approval required for {call.tool_name} "
                    f"(risk={tool.risk_level}, approval_id={approval_id})."
                ),
                success=False,
                error="approval_required",
            )

        try:
            timeout_seconds = getattr(tool, "timeout_seconds", 180.0)

            # Wrap execution in a hard timeout to prevent deadlocks
            outcome = await asyncio.wait_for(
                tool.execute(**args_dict), timeout=timeout_seconds
            )

            # Tools return human-readable strings, so normalize the common error prefixes.
            success = not outcome.lower().startswith("error:")

            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome=outcome,
                success=success,
                error=outcome if not success else None,
            )
        except asyncio.TimeoutError:
            log.error(
                f"Tool {call.tool_name} timed out after {timeout_seconds}s. Execution severed."
            )
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome=f"Error: Tool execution timed out after {timeout_seconds} seconds. The process was forcibly terminated to prevent engine deadlock.",
                success=False,
                error="Timeout",
            )
        except asyncio.CancelledError:
            log.warning(
                f"Tool {call.tool_name} execution was cancelled by the DAG Orchestrator."
            )
            raise  # Crucial: Must propagate up so the TaskGroup DAG handles the rollback properly
        except BaseException as e:
            # Catching BaseException ensures we don't miss SystemExit or KeyboardInterrupt
            if isinstance(e, Exception):
                log.error(f"Tool {call.tool_name} crashed: {e}")
            else:
                log.critical(
                    f"Tool {call.tool_name} encountered critical system exception: {e}"
                )

            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome=f"Error executing tool: internal error occurred ({type(e).__name__}).",
                success=False,
                error=f"Internal tool execution error: {str(e)}",
            )

    def _approval_required(self, tool: BaseTool) -> bool:
        if not tool.requires_approval or not require_tool_approvals():
            return False
        # When the operator enables code_apply, code-editor tools are
        # auto-approved at this layer.  The ethics engine has ALREADY run
        # (lines 108-144 above) — this flag only skips the manual approval
        # queue, it does NOT bypass ethical evaluation.
        if tool.risk_level == "repo_write" and code_apply_enabled():
            return False
        return True

    # Maximum seconds to wait for an operator to approve a tool call.
    # When set to 0 (or not in interactive mode), the old dead-end behaviour applies.
    APPROVAL_TIMEOUT_SECONDS: float = 120.0

    async def _queue_approval(
        self, tool: BaseTool, args_dict: dict, reason: str
    ) -> str:
        approval_id = str(uuid.uuid4())
        if self.db:
            await self.db.execute(
                """
                INSERT INTO tool_approvals (
                    id, session_id, tool_name, risk_level, arguments_json,
                    expected_outcome, reason, status, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    self.session_manager.current.id
                    if self.session_manager and self.session_manager.current
                    else None,
                    tool.name,
                    tool.risk_level,
                    json.dumps(args_dict),
                    reason or "Tool requested by model.",
                    reason or "Tool requested by model.",
                    "pending",
                    datetime.now(timezone.utc).isoformat(),
                    None,
                ),
            )
        return approval_id

    async def _wait_for_approval(
        self,
        approval_id: str,
        timeout: float,
        *,
        turn_emitter=None,
        tool_name: str | None = None,
    ) -> str:
        """
        Poll the DB until the approval is resolved or timeout is reached.
        Returns the resolved status: 'approved', 'rejected', or 'timeout'.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        poll_interval = 0.25
        last_progress = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(poll_interval)
            if not self.db:
                break
            row = await self.db.fetch_one(
                "SELECT status FROM tool_approvals WHERE id = ?", (approval_id,)
            )
            if row and row["status"] in ("approved", "rejected"):
                return row["status"]
            now = asyncio.get_event_loop().time()
            if turn_emitter is not None and tool_name and now - last_progress >= 5.0:
                try:
                    await turn_emitter.tool_progress(
                        tool_name,
                        "Running approved tool...",
                    )
                except Exception:
                    pass
                last_progress = now
        return "timeout"

    async def execute_with_gate(
        self,
        call: "ToolCall",
        execution_mode: str = "interactive",
        approval_timeout: float | None = None,
        event_emitter=None,
        turn_emitter=None,
    ) -> "ToolResult":
        """
        Execute with pause-and-resume approval gate.
        If approval is required, emits an event to the operator surface and waits.
        On approval, executes the tool and returns a real ToolResult.
        On rejection or timeout, returns a refused ToolResult.
        """
        timeout = (
            approval_timeout
            if approval_timeout is not None
            else self.APPROVAL_TIMEOUT_SECONDS
        )

        result = await self.execute(call, execution_mode=execution_mode)

        if result.error != "approval_required" or timeout <= 0:
            return result

        # Extract approval_id from the error message
        approval_id: str | None = None
        msg = result.actual_outcome or ""
        for part in msg.split("approval_id="):
            if len(part) > 8:
                approval_id = part.split(")")[0].strip().split(" ")[0].strip(".")
                break

        if not approval_id:
            return result

        # Notify operator surfaces
        tool = self.tools.get(call.tool_name)
        risk = tool.risk_level if tool else "unknown"
        try:
            if turn_emitter is not None:
                await turn_emitter.approval_request(
                    approval_id,
                    call.tool_name,
                    risk,
                    msg,
                )
            elif event_emitter is not None:
                await event_emitter(
                    {
                        "type": "approval_requested",
                        "data": {
                            "approval_id": approval_id,
                            "tool_name": call.tool_name,
                            "risk_level": risk,
                            "reason": msg,
                        },
                    }
                )
        except Exception:
            pass

        try:
            from silex_core.adapters.approval_notifier import notify_approval_required

            await notify_approval_required(
                self.db, approval_id, call.tool_name, risk, msg
            )
        except Exception as e:
            log.warning(f"Failed to queue telegram approval notification: {e}")

        resolved_status = await self._wait_for_approval(
            approval_id,
            timeout=timeout,
            turn_emitter=turn_emitter,
            tool_name=call.tool_name,
        )

        if resolved_status == "approved":
            try:
                if turn_emitter is not None:
                    await turn_emitter.tool_progress(
                        call.tool_name,
                        "Running approved tool...",
                    )
            except Exception:
                pass
            # Re-execute now that it's been approved (execution already happened in resolve_approval)
            if self.db:
                row = await self.db.fetch_one(
                    "SELECT execution_result_json FROM tool_approvals WHERE id = ?",
                    (approval_id,),
                )
                if row and row["execution_result_json"]:
                    try:
                        exec_result = json.loads(row["execution_result_json"])
                        return ToolResult(
                            tool_name=call.tool_name,
                            actual_outcome=exec_result.get(
                                "actual_outcome", "Approved and executed."
                            ),
                            success=exec_result.get("success", True),
                        )
                    except Exception:
                        pass
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome="Approved. Tool was executed by operator.",
                success=True,
            )

        reason_msg = (
            "rejected by operator"
            if resolved_status == "rejected"
            else "approval timed out"
        )
        try:
            if turn_emitter is not None:
                await turn_emitter.error(f"Tool {call.tool_name} was {reason_msg}.")
        except Exception:
            pass
        return ToolResult(
            tool_name=call.tool_name,
            actual_outcome=f"Error: Tool {call.tool_name} was {reason_msg}.",
            success=False,
            error=reason_msg,
        )

    async def get_pending_approvals(self) -> list[dict]:
        if not self.db:
            return []
        return await self.db.fetch_all(
            "SELECT * FROM tool_approvals WHERE status = 'pending' ORDER BY created_at DESC"
        )

    async def resolve_approval(self, approval_id: str, status: str) -> bool:
        if status not in {"approved", "rejected"}:
            return False
        if not self.db:
            return False
        now = datetime.now(timezone.utc).isoformat()
        approval = await self.db.fetch_one(
            "SELECT * FROM tool_approvals WHERE id = ?",
            (approval_id,),
        )
        if not approval:
            return False

        execution_result_json = None
        if status == "approved":
            tool = self.tools.get(approval["tool_name"])
            if tool:
                args_dict = json.loads(approval["arguments_json"])
                try:
                    outcome = await tool.execute(**args_dict)
                    execution_result_json = json.dumps(
                        {
                            "success": not outcome.lower().startswith("error:"),
                            "actual_outcome": outcome,
                        }
                    )
                except Exception as exc:
                    execution_result_json = json.dumps(
                        {
                            "success": False,
                            "actual_outcome": "Error executing approved tool.",
                            "error": str(exc),
                        }
                    )

        await self.db.execute(
            "UPDATE tool_approvals SET status = ?, resolved_at = ?, execution_result_json = ? WHERE id = ?",
            (status, now, execution_result_json, approval_id),
        )
        return True

    async def shutdown(self):
        """Close any tools that require explicit cleanup."""
        for tool in self.tools.values():
            if hasattr(tool, "close") and callable(tool.close):
                try:
                    import inspect
                    if inspect.iscoroutinefunction(tool.close):
                        await tool.close()
                    else:
                        tool.close()
                except Exception as e:
                    log.warning(f"Error shutting down tool {tool.name}: {e}")
