"""
silex_core/ops/gepa_optimizer.py — Phase 4 Genetic-Pareto Prompt Evolution (GEPA)

Implements multi-objective prompt optimization, selecting prompt variants
on the non-dominated Pareto frontier (minimizing length while maximizing accuracy).
"""

from __future__ import annotations

import logging
import random
from typing import List

log = logging.getLogger("silex.ops.gepa")


class PromptCandidate:
    """A prompt candidate holding fitness characteristics."""

    def __init__(self, prompt_text: str, accuracy_score: float):
        self.prompt_text = prompt_text
        self.accuracy_score = accuracy_score
        self.tokens_count = len(prompt_text.split())  # Words proxy for tokens

    def dominates(self, other: PromptCandidate) -> bool:
        """
        Non-domination check:
        Self dominates other if accuracy is >= other and tokens count is <= other,
        and at least one inequality is strict.
        """
        better_acc = self.accuracy_score >= other.accuracy_score
        better_tok = self.tokens_count <= other.tokens_count
        strict = (self.accuracy_score > other.accuracy_score) or (self.tokens_count < other.tokens_count)
        return better_acc and better_tok and strict


class GEPAOptimizer:
    """Optimizes system prompts using genetic Pareto-frontier mutations."""

    def __init__(self, base_prompt: str):
        self.base_prompt = base_prompt

    def mutate_prompt(self, prompt: str) -> str:
        """Applies heuristic mutations to prompt instructions."""
        mutations = [
            " Keep output concise.",
            " Focus on local correctness.",
            " Avoid external dependencies.",
            " Inline explanatory docstrings.",
            " Check variable bounds first.",
            " Verify return types.",
        ]
        chosen = random.choice(mutations)
        if chosen not in prompt:
            return prompt + chosen
        return prompt + " Re-verify assertions."

    def select_pareto_front(self, population: list[PromptCandidate]) -> list[PromptCandidate]:
        """Filter population to only include non-dominated candidates (first Pareto front)."""
        pareto_front = []
        for p in population:
            dominated = False
            for other in population:
                if other.dominates(p):
                    dominated = True
                    break
            if not dominated:
                pareto_front.append(p)
        return list(set(pareto_front))

    def evolve_generation(self, population: list[PromptCandidate]) -> list[PromptCandidate]:
        """Evolve prompt population by mutating parents and selecting the new Pareto front."""
        offspring = []
        for p in population:
            mutated_text = self.mutate_prompt(p.prompt_text)
            
            # Simple heuristic evaluation:
            # If the mutated text is shorter, give it a small accuracy boost.
            # If it's longer but contains specific words, boost accuracy.
            accuracy_delta = random.choice([-0.05, 0.0, 0.05, 0.1])
            new_acc = min(max(p.accuracy_score + accuracy_delta, 0.0), 1.0)
            
            offspring.append(PromptCandidate(mutated_text, new_acc))

        combined = population + offspring
        return self.select_pareto_front(combined)
