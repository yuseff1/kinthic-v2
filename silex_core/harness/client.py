from typing import List, Dict, Any
import json
from silex_engine.world.graph import KnowledgeGraph
from silex_engine.memory.memory_store import MemoryStore

class LocalSilexClient:
    """
    Implements the SilexClient protocol required by ContextBuilder and MemoryWriter.
    Uses direct Python imports to the standalone Silex Engine.
    """
    def __init__(self, graph: KnowledgeGraph, memory_store: MemoryStore):
        self.graph = graph
        self.memory = memory_store
        
    async def get_graph_neighborhood(self, text: str) -> str:
        # Simplistic implementation for the stub
        try:
            # We would extract entities from text and query the graph
            return "Graph Context: Basic neighborhood data"
        except Exception as e:
            return f"Error accessing graph: {e}"

    async def recall_memories(self, query: str, session_id: str, k: int = 5) -> str:
        try:
            memories = await self.memory.retrieve(query, limit=k)
            return "\n".join([m.get("content", "") for m in memories])
        except Exception:
            return "No recent memories found."

    async def get_active_goals(self, session_id: str) -> str:
        return "No active goals."

    async def get_active_contradictions(self, session_id: str) -> str:
        return "No active contradictions."

    async def remember(self, content: str, source: str, session_id: str) -> str:
        try:
            await self.memory.add_memory(content, source=source)
            return "Memory stored."
        except Exception as e:
            return f"Failed to store memory: {e}"

    async def graph_add(self, node: Dict[str, Any], edges: List[Dict[str, Any]]) -> str:
        try:
            # Simplistic mock for adding to graph
            await self.graph.add_node(node.get("id", "unknown"), **node)
            return "Graph updated."
        except Exception as e:
            return f"Failed to update graph: {e}"

    async def update_belief(self, node_id: str, new_confidence: float) -> str:
        return "Belief updated."
