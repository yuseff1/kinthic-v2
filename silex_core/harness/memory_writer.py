from silex_engine.memory.admission_control import AdmissionController
from silex_engine.memory.memory_store import MemoryStore
from silex_engine.world.graph import KnowledgeGraph

from silex_core.memory.session import SessionManager

class MemoryWriter:
    def __init__(self, admission_controller: AdmissionController, memory_store: MemoryStore, graph: KnowledgeGraph, session_manager: SessionManager):
        self.admission_controller = admission_controller
        self.memory_store = memory_store
        self.graph = graph
        self.session_manager = session_manager

    async def write(self, response, turn_context) -> None:
        """
        Persists information from the LLM's final response into the Silex Engine.
        Does not write during tool-call turns to prevent memory corruption.
        """
        # If there are tool calls, we defer memory writing until the final turn.
        tool_calls = getattr(response, "tool_calls", [])
        if isinstance(tool_calls, list) and len(tool_calls) > 0:
            return

        new_memories = getattr(response, "new_memories", [])
        causal_obs = getattr(response, "causal_observations", [])

        # Process Semantic Memories through Admission Control (A-MAC)
        if new_memories:
            from silex_engine.models.schemas import Memory, MemorySource, MemoryType
            for memory in new_memories:
                content = getattr(memory, "content", str(memory))
                if not content:
                    continue
                
                # Construct proper Memory schema with provenance context
                memory_obj = Memory(
                    content=content,
                    source=MemorySource.INFERENCE,
                    memory_type=MemoryType.SEMANTIC,
                    importance=0.6,
                    provenance={
                        "context": getattr(turn_context, "user_input", ""),
                        "session_id": getattr(turn_context, "id", None)
                    }
                )
                await self.memory_store.add(memory_obj)

                # Revise propositions under the AGM belief framework
                try:
                    from silex_engine.world.belief_revision import BeliefRevisionEngine
                    engine = BeliefRevisionEngine(self.graph.db)
                    await engine.revise_belief(content, "true", 0.7)
                except Exception as e:
                    from silex_core.utils.logger import setup_logger
                    setup_logger("silex.harness.memory_writer").warning(f"AGM belief revision skip: {e}")

        # Process Causal Graph Updates
        if causal_obs:
            from silex_engine.models.schemas import KnowledgeNode, CausalEdge, NodeType
            from silex_core.utils.logger import setup_logger
            log = setup_logger("silex.harness.memory_writer")
            
            for obs in causal_obs:
                from_c = getattr(obs, "from_concept", None)
                to_c = getattr(obs, "to_concept", None)
                rel = getattr(obs, "relationship", None)
                strength = getattr(obs, "strength", 0.5)
                evidence = getattr(obs, "evidence", "")
                
                if from_c and to_c and rel:
                    try:
                        node_a = KnowledgeNode(content=from_c, node_type=NodeType.FACT)
                        node_b = KnowledgeNode(content=to_c, node_type=NodeType.FACT)
                        
                        node_a = await self.graph.add_node(node_a)
                        node_b = await self.graph.add_node(node_b)
                        
                        edge = CausalEdge(
                            source_node=node_a.id,
                            target_node=node_b.id,
                            edge_type=rel,
                            strength=strength,
                            evidence=evidence
                        )
                        await self.graph.add_edge(edge)
                    except Exception as e:
                        log.error(f"Failed to write causal observation edge to graph: {e}")

        res_text = getattr(response, "response", None) or getattr(response, "text", None) or str(response)
        reflection = getattr(response, "self_reflection", "")
        conf = getattr(response, "confidence", 0.5)

        await self.session_manager.record_turn(
            user_input=getattr(turn_context, "user_input", ""),
            reasoning=getattr(response, "reasoning", ""),
            response=res_text,
            self_reflection=reflection,
            confidence=conf
        )
