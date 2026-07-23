import asyncio
import uuid
from typing import Any, List

from silex_core.loop import run as cognitive_loop_run
from silex_core.memory.session import SessionManager
from silex_core.tools.registry import ToolRegistry
from silex_engine.storage.database import Database
from silex_engine.world.graph import KnowledgeGraph
from silex_engine.memory.memory_store import MemoryStore
from silex_engine.memory.admission_control import AdmissionController

from silex_core.harness.context_builder import ContextBuilder
from silex_core.harness.tool_dispatcher import ToolDispatcher
from silex_core.harness.memory_writer import MemoryWriter
from silex_core.harness.stop_evaluator import StopEvaluator
from silex_core.llm.factory import build_provider

class TurnContext:
    def __init__(self, session_id: str, user_input: str):
        self.id = session_id
        self.session_id = session_id
        self.user_input = user_input
        self.observations = []
        self.response = None

    def add_observations(self, observations: List[Any]) -> None:
        self.observations.extend(observations)

    def final_response(self) -> Any:
        # Check if response has structured response attribute
        if hasattr(self.response, "response"):
            return self.response.response
        return getattr(self.response, "text", str(self.response))

class LoopWrapper:
    """
    A lightweight wrapper that exposes the expected startup/shutdown/process 
    interface to the legacy CLI, UI, and Server, but internally routes 
    everything to the new V2 architecture.
    """
    def __init__(self, db_path: str | None = None):
        self.db = Database(db_path=db_path)
        self.session_manager = SessionManager(self.db)
        self.graph = KnowledgeGraph(self.db)
        self.memory_store = MemoryStore(self.db)
        self.admission_controller = AdmissionController()

        from silex_core.skills.loader import SkillLoader
        self.skill_loader = SkillLoader(vector_store=self.memory_store.vs)
        self.skill_loader.load_all()

        from silex_core.runtime.settings import RuntimeSettingsStore
        self.llm = build_provider(settings_store=RuntimeSettingsStore())

        from silex_core.memory.file_indexer import FileIndexer
        self.file_indexer = FileIndexer(vector_store=self.memory_store.vs)

        self.tool_registry = ToolRegistry(
            vector_store=self.memory_store.vs,
            db=self.db,
            session_manager=self.session_manager,
            memory_store=self.memory_store,
            llm=self.llm,
            file_indexer=self.file_indexer,
        )
        self.tool_registry.register_skill_tools(self.skill_loader)
        self.context_builder = ContextBuilder(self.session_manager, self.graph, self.memory_store, self.skill_loader, tool_registry=self.tool_registry)
        self.tool_dispatcher = ToolDispatcher(self.tool_registry)
        self.memory_writer = MemoryWriter(self.admission_controller, self.memory_store, self.graph, self.session_manager)
        self.stop_evaluator = StopEvaluator(max_turns=40)
        
        self.session_id = str(uuid.uuid4())
        
        # Expose the actual session manager for server.py compatibility
        self.session = self.session_manager
        
        # Alias memory for get_metrics compatibility
        self.memory = self.memory_store

    async def startup(self, *args, **kwargs):
        await self.db.connect()
        if hasattr(self.llm, "connect"):
            self.llm.connect()
        # Load external MCP tools
        if hasattr(self, "tool_registry"):
            try:
                import logging
                mcp_logger = logging.getLogger("silex.harness.wrapper")
                mcp_count = await self.tool_registry.reload_mcp_tools()
                mcp_logger.info(f"Loaded {mcp_count} MCP tools on startup.")
            except Exception as exc:
                import logging
                mcp_logger = logging.getLogger("silex.harness.wrapper")
                mcp_logger.warning(f"Failed to load MCP tools: {exc}")
        # Ensure we have an active session
        session = await self.session_manager.resume_or_start()
        self.session_id = session.id

    async def shutdown(self):
        if hasattr(self, "tool_registry"):
            try:
                await self.tool_registry.shutdown()
            except Exception:
                pass
        await self.db.close()

    async def process(self, user_input: str, *args, **kwargs):
        # Ensure ContextVar has the active session for the current task/request thread
        if not self.session_manager.current:
            session = await self.session_manager.resume_or_start()
            self.session_id = session.id

        images = kwargs.get("images")
        turn = TurnContext(self.session_id, user_input)
        turn.images = images
        
        # Fire event emitters if passed
        event_emitter = kwargs.get("event_emitter")
        turn.event_emitter = event_emitter
        if event_emitter:
            await event_emitter({"type": "thinking", "data": "Processing with V2 Harness..."})
            
        final_response_text = await cognitive_loop_run(
            turn, 
            self.context_builder, 
            self.tool_dispatcher,
            self.memory_writer,
            self.stop_evaluator,
            self.llm,
            images=images,
        )
        
        if event_emitter:
            await event_emitter({"type": "thinking_done"})
            
        self._turn_count = getattr(turn, "turn_count", 1)
        self._last_usage = []
        try:
            rows = await self.db.fetch_all(
                "SELECT input_tokens, output_tokens FROM llm_usage ORDER BY timestamp DESC LIMIT ?",
                (self._turn_count,)
            )
            self._last_usage = [type("UsageRecord", (), {"input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"]})() for r in (rows or [])]
        except Exception:
            pass

        class WrappedResponse:
            @property
            def response(self):
                return final_response_text
                
        return WrappedResponse()

    async def get_health_status(self) -> dict:
        from silex_core.runtime.settings import RuntimeSettingsStore
        ps = RuntimeSettingsStore().load_settings()
        return {
            "provider": ps.get("provider", "unknown"),
            "model": ps.get("model", "unknown"),
            "router_fast_model": ps.get("fast_model", "none"),
            "current_session": self.session_id,
            "browser_registered": False,
        }

    async def get_usage_summary(self) -> dict:
        try:
            rows = await self.db.fetch_all(
                "SELECT provider, model, "
                "SUM(input_tokens) as input_tokens, "
                "SUM(output_tokens) as output_tokens, "
                "COUNT(*) as requests, "
                "SUM(estimated_cost_usd) as estimated_cost_usd "
                "FROM llm_usage GROUP BY provider, model "
                "ORDER BY requests DESC LIMIT 5"
            )
            totals = await self.db.fetch_one(
                "SELECT SUM(input_tokens) as input_tokens, "
                "SUM(output_tokens) as output_tokens, "
                "COUNT(*) as requests, "
                "SUM(estimated_cost_usd) as estimated_cost_usd "
                "FROM llm_usage"
            )
            return {
                "totals": dict(totals) if totals else {},
                "models": [dict(r) for r in (rows or [])],
            }
        except Exception:
            return {"totals": {}, "models": []}

    async def get_session_info(self) -> dict:
        try:
            mem_count = await self.db.fetch_one("SELECT COUNT(*) as c FROM memories")
            memories = mem_count["c"] if mem_count else 0
        except Exception:
            memories = 0
        try:
            goals_count = await self.db.fetch_one("SELECT COUNT(*) as c FROM goals WHERE status IN ('pending', 'active')")
            goals = goals_count["c"] if goals_count else 0
        except Exception:
            goals = 0
        try:
            turns_count = await self.db.fetch_one("SELECT COUNT(*) as c FROM session_turns")
            turns = turns_count["c"] if turns_count else 0
        except Exception:
            turns = 0
        try:
            nodes_count = await self.db.fetch_one("SELECT COUNT(*) as c FROM epistemic_nodes")
            nodes = nodes_count["c"] if nodes_count else 0
            edges_count = await self.db.fetch_one("SELECT COUNT(*) as c FROM epistemic_edges")
            edges = edges_count["c"] if edges_count else 0
        except Exception:
            nodes, edges = 0, 0
        return {
            "total_memories": memories,
            "active_goals": goals,
            "total_turns": turns,
            "graph_nodes": nodes,
            "graph_edges": edges,
        }

    async def get_all_sessions(self) -> list:
        try:
            rows = await self.db.fetch_all("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 50")
            return [dict(r) for r in (rows or [])]
        except Exception:
            return []
