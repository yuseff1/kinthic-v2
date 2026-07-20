"""
Language Agent Tree Search (LATS) — MCTS-based planning for Kinthic v2.
Replaces git checkpoints with in-memory LATSState snapshots.
Wires critic evaluation directly to StopEvaluator criteria.
"""

from __future__ import annotations
import math
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol

class ToolCall(Protocol):
    name: str
    arguments: dict

@dataclass
class LATSState:
    """In-memory snapshot replacing the old git-based checkpoints."""
    observations: List[str] = field(default_factory=list)
    system_prompt: str = ""
    # Add any other ephemeral state needed per branch
    
class StopEvaluator(Protocol):
    async def is_done(self, session_id: str, response: Any) -> bool: ...

class LLMResponse(Protocol):
    reasoning: str
    response: str
    tool_calls: List[ToolCall]
    has_tool_calls: bool

class LLM(Protocol):
    async def complete(self, context: str) -> LLMResponse: ...

class ToolDispatcher(Protocol):
    async def dispatch(self, session_id: str, tool_calls: List[dict]) -> List[dict]: ...

class LATSNode:
    """A node in the Language Agent Tree Search representing state & action."""
    def __init__(
        self,
        node_id: str,
        parent: Optional[LATSNode] = None,
        reasoning: str = "",
        response: str = "",
        tool_calls: Optional[List[dict]] = None,
        observation: str = "",
        critic_score: float = 0.0,
        is_acceptable: bool = False,
        feedback: str = "",
        depth: int = 0,
        state: Optional[LATSState] = None,
    ) -> None:
        self.node_id = node_id
        self.parent = parent
        self.children: List[LATSNode] = []
        self.reasoning = reasoning
        self.response = response
        self.tool_calls = tool_calls or []
        self.observation = observation
        self.critic_score = critic_score
        self.is_acceptable = is_acceptable
        self.feedback = feedback
        self.depth = depth
        self.state = state or LATSState()

        self.visit_count = 0
        self.value_sum = 0.0

    @property
    def value(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.value_sum / self.visit_count

    def ucb1(self, exploration_constant: float = 1.0) -> float:
        if self.visit_count == 0:
            return float("inf")
        if not self.parent:
            return self.value
        return self.value + exploration_constant * math.sqrt(
            math.log(self.parent.visit_count) / self.visit_count
        )

class LATSOrchestrator:
    """Orchestrates Monte Carlo Tree Search with LLMs and tool execution."""

    def __init__(
        self,
        llm: LLM,
        dispatcher: ToolDispatcher,
        stop_evaluator: StopEvaluator,
        max_iterations: int = 3,
        exploration_constant: float = 1.0,
        critic_threshold: float = 0.7,
    ) -> None:
        self.llm = llm
        self.dispatcher = dispatcher
        self.stop_evaluator = stop_evaluator
        self.max_iterations = max_iterations
        self.exploration_constant = exploration_constant
        self.critic_threshold = critic_threshold

    async def search(
        self,
        session_id: str,
        context: str,
    ) -> LLMResponse:
        """
        Execute LATS to find the best response by exploring decision branches.
        """
        root_id = str(uuid.uuid4())
        
        # Pass 1
        llm_response = await self.llm.complete(context)
        
        # Convert LLMResponse tool_calls to dict for dispatcher if needed
        # Assuming llm_response.tool_calls is a list of dicts or has dict-like access
        tool_calls = getattr(llm_response, "tool_calls", [])
        
        root_state = LATSState(system_prompt=context)
        root = LATSNode(
            node_id=root_id,
            parent=None,
            reasoning=getattr(llm_response, "reasoning", ""),
            response=getattr(llm_response, "response", getattr(llm_response, "text", "")),
            tool_calls=tool_calls,
            depth=0,
            state=root_state,
        )

        # Execute root tools if planned
        if root.tool_calls:
            results = await self.dispatcher.dispatch(session_id, root.tool_calls)
            obs_text = "\n".join(str(r) for r in results)
            root.observation = obs_text
            root.state.observations.append(obs_text)
            
            # Redraft
            redraft_prompt = context + f"\n\nTOOL RESULTS:\n{obs_text}"
            llm_response = await self.llm.complete(redraft_prompt)
            root.response = getattr(llm_response, "response", getattr(llm_response, "text", ""))
            root.reasoning = getattr(llm_response, "reasoning", "")
            
        # Stop Evaluator as Critic
        is_done = await self.stop_evaluator.is_done(session_id, llm_response)
        
        # Mocking score since stop_eval is binary, we can simulate a threshold score
        # In a real implementation we'd read model confidence, but we map is_done to a high score
        root.is_acceptable = is_done
        root.critic_score = 1.0 if is_done else 0.5
        root.feedback = "Acceptable" if is_done else "Requires more iterations."
        
        root.visit_count = 1
        root.value_sum = root.critic_score

        if root.is_acceptable or root.critic_score >= self.critic_threshold:
            return llm_response

        # Search iterations
        best_node = root
        for iteration in range(1, self.max_iterations + 1):
            selected = root
            while selected.children:
                selected = max(
                    selected.children,
                    key=lambda node: node.ucb1(self.exploration_constant),
                )

            # Expansion
            candidates = await self._generate_candidates(selected, context, num_candidates=2)
            
            for candidate_resp in candidates:
                child_id = str(uuid.uuid4())
                child_state = LATSState(
                    observations=list(selected.state.observations),
                    system_prompt=context
                )
                child = LATSNode(
                    node_id=child_id,
                    parent=selected,
                    reasoning=getattr(candidate_resp, "reasoning", ""),
                    response=getattr(candidate_resp, "response", getattr(candidate_resp, "text", "")),
                    tool_calls=getattr(candidate_resp, "tool_calls", []),
                    depth=selected.depth + 1,
                    state=child_state,
                )

                if child.tool_calls:
                    results = await self.dispatcher.dispatch(session_id, child.tool_calls)
                    obs_text = "\n".join(str(r) for r in results)
                    child.observation = obs_text
                    child.state.observations.append(obs_text)
                    
                    redraft_prompt = context + f"\n\nTOOL RESULTS:\n{obs_text}"
                    candidate_resp = await self.llm.complete(redraft_prompt)
                    child.response = getattr(candidate_resp, "response", getattr(candidate_resp, "text", ""))
                    child.reasoning = getattr(candidate_resp, "reasoning", "")
                    
                is_done = await self.stop_evaluator.is_done(session_id, candidate_resp)
                child.is_acceptable = is_done
                child.critic_score = 1.0 if is_done else 0.5
                child.feedback = "Acceptable" if is_done else "Requires more iterations."
                
                child.visit_count = 1
                child.value_sum = child.critic_score
                selected.children.append(child)
                
                if child.critic_score > best_node.critic_score:
                    best_node = child
                    
                if child.is_acceptable:
                    break
                    
            # Backprop
            curr = selected
            while curr:
                curr.visit_count += 1
                curr.value_sum += best_node.critic_score
                curr = curr.parent
                
            if best_node.is_acceptable:
                break
                
        # We need to construct the final LLMResponse to return
        class FinalResponse:
            text = best_node.response
            reasoning = best_node.reasoning
            has_tool_calls = len(best_node.tool_calls) > 0
            tool_calls = best_node.tool_calls
            
        return FinalResponse()

    async def _generate_candidates(self, node: LATSNode, context: str, num_candidates: int = 2) -> List[Any]:
        # Generate varied responses using the llm
        prompt = context + f"\n\nPREVIOUS ATTEMPT FAILED.\nREASONING: {node.reasoning}\nOBSERVATION: {node.observation}\nProvide a corrected approach."
        
        # Mock concurrency by just awaiting serially for this implementation
        candidates = []
        for i in range(num_candidates):
            # In real system, we'd alter temperature per call if supported
            resp = await self.llm.complete(prompt)
            candidates.append(resp)
        return candidates
