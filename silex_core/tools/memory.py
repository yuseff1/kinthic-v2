"""
Memory Tools.
Allows the agent to proactively query and update its own memory store mid-turn.
"""

from __future__ import annotations

from silex_core.tools.base import BaseTool
from silex_core.models.schemas import Memory, MemorySource, MemoryType


class SearchMemoryTool(BaseTool):
    """Voluntarily search long-term memory and knowledge graph."""

    name = "search_memory"
    risk_level = "read_only"
    requires_approval = False

    schema = {
        "query": {
            "type": "string",
            "description": "The specific topic, fact, or past conversation to search for.",
        }
    }

    def __init__(self, memory_store):
        super().__init__()
        self.memory_store = memory_store

    def get_prompt_description(self) -> str:
        return (
            "- search_memory: Voluntarily search your long-term memory and "
            "knowledge graph for specific facts, past conversations, or context you might have forgotten. "
            "Args: query (string)"
        )

    async def execute(self, query: str) -> str:
        """Search the memory store and return formatted context."""
        try:
            memories = await self.memory_store.retrieve_context(query)
            if not memories:
                return "No relevant memories found for that query."

            lines = [f"Found {len(memories)} memories related to '{query}':\n"]
            for i, mem in enumerate(memories, 1):
                tags_str = f" [{', '.join(mem.tags)}]" if mem.tags else ""
                lines.append(f"[{i}] {mem.content}")
                lines.append(
                    f"    (Type: {mem.memory_type.value if hasattr(mem.memory_type, 'value') else mem.memory_type}, Source: {mem.source.value if hasattr(mem.source, 'value') else mem.source}, Confidence: {mem.confidence:.1f}){tags_str}"
                )
                lines.append("")

            return "\n".join(lines)
        except Exception as e:
            return f"Error searching memory: {str(e)}"


class AppendObservationTool(BaseTool):
    """Voluntarily append a runtime observation to long-term memory."""

    name = "append_runtime_observation"
    risk_level = "sandbox_write"
    requires_approval = False

    schema = {
        "content": {
            "type": "string",
            "description": "The specific observation, fact, or detail learned during execution to persist.",
        }
    }

    def __init__(self, memory_store):
        super().__init__()
        self.memory_store = memory_store

    def get_prompt_description(self) -> str:
        return (
            "- append_runtime_observation: Voluntarily save a new observation or fact "
            "into your long-term memory so you can recall it in future turns. "
            "Args: content (string)"
        )

    async def execute(self, content: str) -> str:
        """Store observation in memory."""
        try:
            memory = Memory(
                content=content,
                source=MemorySource.REFLECTION,
                memory_type=MemoryType.PROJECT,
                importance=0.6,
                tags=["runtime_observation"],
            )
            await self.memory_store.add(memory)
            return "Observation stored successfully in long-term memory."
        except Exception as e:
            return f"Error storing observation: {str(e)}"
