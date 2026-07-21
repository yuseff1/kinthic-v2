"""
Adaptive Memory Admission Control (A-MAC) Framework.

Implements the S(m) composite scoring function to filter out low-quality,
redundant, or useless memories before they reach the persistent store.

Scores candidates on 5 dimensions:
  1. Utility    (heuristic keyword scoring)
  2. Confidence (ROUGE-L approximation vs context)
  3. Novelty    (semantic distance vs existing memories)
  4. Recency    (exponential decay based on time)
  5. Type Prior (static weighting by information type)
"""

import asyncio
import difflib
from typing import Callable, Coroutine, Dict

from silex_engine.config import AMAC_THRESHOLD, AMAC_WEIGHTS
from silex_engine.logger import setup_logger

log = setup_logger("silex.admission_control")

# Cap the length of strings for LCS to prevent O(n*m) blocking the event loop
MAX_LCS_LENGTH = 2000


class AdmissionController:
    """Evaluates whether a memory candidate is worth storing."""

    def __init__(self, threshold: float = AMAC_THRESHOLD, weights: list[float] = None):
        self.threshold = threshold
        self.weights = weights or AMAC_WEIGHTS
        # weights = [Utility(0.3), Confidence(0.3), Novelty(0.25), Recency(0.05), TypePrior(0.1)]

    async def evaluate(self, content: str) -> bool:
        """Simplified convenience wrapper for evaluation with default arguments."""
        async def dummy_novelty(cand: str) -> float:
            return 1.0
        
        try:
            res = await self.evaluate_admission(
                candidate_content=content,
                content_type="semantic",
                source_context="",
                novelty_checker=dummy_novelty
            )
            return res.get("admitted", False)
        except Exception:
            return False

    async def evaluate_admission(
        self,
        candidate_content: str,
        content_type: str,
        source_context: str,
        novelty_checker: Callable[[str], Coroutine[None, None, float]],
    ) -> Dict[str, float]:
        """
        Evaluate a candidate memory and return its scores.

        Args:
            candidate_content: The memory text.
            content_type: e.g., 'preference', 'fact', 'plan', 'transient', 'semantic'
            source_context: The text context from which the memory was extracted.
            novelty_checker: Async func that takes candidate string and returns
                             a novelty score [0, 1] (1 = completely novel).

        Returns:
            Dict containing individual scores, composite_score, and 'admitted' bool.
        """
        utility = self.evaluate_future_utility(candidate_content)
        confidence = await self.compute_factual_confidence(
            candidate_content, source_context
        )
        novelty = await novelty_checker(candidate_content)
        recency = self.compute_temporal_recency(age_days=0.0)
        type_prior = self.get_content_type_prior(content_type)

        if isinstance(self.weights, dict):
            w_u = self.weights.get("utility", 0.3)
            w_c = self.weights.get("confidence", 0.2)
            w_n = self.weights.get("novelty", 0.3)
            w_r = self.weights.get("recency", 0.1)
            w_t = self.weights.get("type_prior", 0.1)
        else:
            w_u, w_c, w_n, w_r, w_t = self.weights
        import math
        raw_composite = (
            (w_u * utility)
            + (w_c * confidence)
            + (w_n * novelty)
            + (w_r * recency)
            + (w_t * type_prior)
        )
        if math.isnan(raw_composite):
            composite_score = 0.0
        else:
            composite_score = float(max(0.0, min(1.0, raw_composite)))

        # Payload Gating (Context Isolation)
        # If the content exceeds 800 chars, it's likely a bloated payload (e.g., raw tool output).
        # We aggressively truncate it to preserve graph topology while dropping the heavy blob.
        MAX_PAYLOAD_SIZE = 800
        sanitized_content = candidate_content
        if candidate_content and len(candidate_content) > MAX_PAYLOAD_SIZE:
            sanitized_content = (
                candidate_content[:MAX_PAYLOAD_SIZE]
                + "... [PAYLOAD TRUNCATED BY A-MAC]"
            )
            log.warning(
                f"A-MAC payload gating triggered. Truncated {len(candidate_content)} bytes down to {MAX_PAYLOAD_SIZE}."
            )

        return {
            "utility": utility,
            "confidence": confidence,
            "novelty": novelty,
            "recency": recency,
            "type_prior": type_prior,
            "composite_score": composite_score,
            "admitted": composite_score >= self.threshold,
            "sanitized_content": sanitized_content,
        }

    def evaluate_future_utility(self, candidate: str) -> float:
        """Rule-based heuristic for future utility using word boundary matching."""
        import re

        candidate_lower = candidate.lower()
        utility_keywords = [
            "always",
            "never",
            "must",
            "prefer",
            "error",
            "failed",
            "password",
            "key",
            "token",
            "remember",
            "important",
            "api",
            "endpoint",
            "path",
            "directory",
            "config",
        ]
        matches = 0
        for kw in utility_keywords:
            if re.search(rf"\b{re.escape(kw)}\b", candidate_lower):
                matches += 1
        return min(1.0, matches * 0.20)

    async def compute_factual_confidence(self, candidate: str, context: str) -> float:
        """
        Compute ROUGE-L like confidence via Longest Common Subsequence.
        Runs in a background thread to prevent blocking the event loop.
        """
        if not context:
            return 0.5  # Neutral prior if no context provided

        candidate_str = str(candidate) if candidate is not None else ""
        context_str = str(context) if context is not None else ""

        # Cap length to prevent O(n*m) blowup
        cand_trunc = candidate_str[:MAX_LCS_LENGTH]
        ctx_trunc = context_str[:MAX_LCS_LENGTH]

        def _lcs_ratio() -> float:
            if not cand_trunc:
                return 0.0
            matcher = difflib.SequenceMatcher(None, cand_trunc, ctx_trunc)
            matches = sum(triple.size for triple in matcher.get_matching_blocks())
            return min(1.0, matches / len(cand_trunc))

        import anyio.to_thread
        return await anyio.to_thread.run_sync(_lcs_ratio, cancellable=True)

    def compute_temporal_recency(
        self, age_days: float = 0.0, decay_rate: float = 0.01
    ) -> float:
        """
        Exponential decay based on time.
        For admission (where the memory is brand new), age_days is 0.0, returning 1.0.
        """
        import math

        return math.exp(-decay_rate * max(0.0, age_days))

    def get_content_type_prior(self, content_type: str) -> float:
        """Static priority weights based on information type."""
        priors = {
            "preference": 0.9,  # User preferences are highly prized
            "system": 0.9,  # System constraints are critical
            "fact": 0.7,  # Objective truths
            "semantic": 0.7,  # General knowledge
            "plan": 0.5,  # Ephemeral action plans
            "transient": 0.1,  # Scratchpad / short-lived
            "reflection": 0.6,  # Self-reflections
            "inference": 0.5,  # Deduced facts
        }
        return priors.get(content_type, 0.5)

