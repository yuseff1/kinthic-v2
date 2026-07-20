import json
from typing import List

from silex_core.memory.session import SessionManager
from silex_engine.world.graph import KnowledgeGraph
from silex_engine.memory.memory_store import MemoryStore

class ContextBuilder:
    def __init__(self, session_manager: SessionManager, graph: KnowledgeGraph, memory_store: MemoryStore, skill_loader = None, tool_registry = None):
        self.session_manager = session_manager
        self.graph = graph
        self.memory_store = memory_store
        self.skill_loader = skill_loader
        self.tool_registry = tool_registry

    async def build_context(self, turn_context) -> str:
        """
        Builds the system prompt and context dynamically.
        """
        identity = (
            "You are Kinthic, a persistent and highly capable personal AI agent.\n"
            "You have a causal memory graph and you reason across sessions.\n"
            "When you take actions, explain your reasoning and note any new facts you learned.\n"
        )
        
        # Pull history
        recent_turns = await self.session_manager.get_recent_turns(limit=5)
        history_lines = []
        for t in recent_turns:
            history_lines.append(f"USER: {t.user_input}")
            history_lines.append(f"KINTHIC: {t.response}")
        history = "\n".join(history_lines)
        
        # Pull top-k semantic memories based on user input
        memories = await self.memory_store.retrieve_context(turn_context.user_input)
        memory_str = "\n".join([m.content for m in memories[:5]]) if memories else "None."
        
        # Pull relevant knowledge graph subgraph context
        try:
            await self.graph.load_relevant(turn_context.user_input)
            graph_nodes = await self.graph.retrieve_relevant_context(turn_context.user_input, max_nodes=10)
            if graph_nodes:
                graph_lines = []
                for node in graph_nodes:
                    line = f"- [{node['type']}] {node['content']} (confidence: {node['confidence']:.2f})"
                    relations = []
                    if node["causes"]:
                        relations.append(f"  └── causes: {', '.join(node['causes'])}")
                    if node["caused_by"]:
                        relations.append(f"  └── caused by: {', '.join(node['caused_by'])}")
                    if node["contradicts"]:
                        relations.append(f"  └── contradicts: {', '.join(node['contradicts'])}")
                    if node["related"]:
                        relations.append(f"  └── related: {', '.join(node['related'])}")
                    graph_lines.append(line)
                    for r in relations:
                        graph_lines.append(r)
                graph_context = "\n".join(graph_lines)
            else:
                graph_context = "No direct graph nodes matched."
        except Exception as e:
            from silex_core.utils.logger import setup_logger
            setup_logger("silex.harness.context_builder").warning(f"Failed to query knowledge graph: {e}")
            graph_context = "No direct graph nodes matched."
        
        instructions = (
            "## COGNITIVE INSTRUCTIONS\n"
            "Analyze the current turn and populate the structured output fields with high analytical rigor:\n"
            "1. **new_memories**: Extract facts, preferences, or project-specific decisions stated in this turn. "
            "Only store high-utility, permanent knowledge. Avoid redundancy with SEMANTIC MEMORIES.\n"
            "2. **causal_observations**: Map the causal structure of the discussion. For any causal connections noticed, extract:\n"
            "   - `from_concept` & `to_concept`: Clean, concise events/states.\n"
            "   - `relationship`: 'causes', 'enables', 'requires', 'supports', 'contradicts', 'part_of', 'similar_to', 'temporal'.\n"
            "   - `evidence`: Why this relationship exists based strictly on the current turn.\n"
            "3. **contradictions_detected**: Scan user claims against SEMANTIC MEMORIES. If a conflict exists, "
            "document both claims, analyze which is more likely true, and assign a confidence score.\n"
            "4. **hypotheses**: Formulate testable predictions if the causal graph or context implies something not explicitly stated. Define a test method."
        )

        prompt = (
            f"{identity}\n\n"
            f"{instructions}\n\n"
            f"## SEMANTIC MEMORIES\n{memory_str}\n\n"
            f"## GRAPH CONTEXT\n{graph_context}\n\n"
            f"## CONVERSATION HISTORY\n{history}\n"
        )
        
        if self.tool_registry:
            tools_appendix = self.tool_registry.get_system_prompt_appendix()
            prompt += f"\n{tools_appendix}\n"
        
        if self.skill_loader:
            skills_context = self.skill_loader.format_for_prompt(turn_context.user_input)
            if skills_context:
                prompt += f"\n## AVAILABLE SKILLS\n{skills_context}\n"

        if turn_context.observations:
            obs_str = json.dumps(turn_context.observations, indent=2)
            prompt += f"\n## TOOL OBSERVATIONS\n{obs_str}\n"
            
        return prompt
