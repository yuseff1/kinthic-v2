import numpy as np
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SILEX.Observability")


class LocalAlignmentVerifier:
    def __init__(
        self,
        baseline_prompt: str,
        stability_threshold: float = -0.015,
        variance_budget: float = 0.15,
    ):
        self.baseline_prompt = baseline_prompt
        self.stability_threshold = (
            stability_threshold  # Minimum allowable slope for beta regression
        )
        self.variance_budget = variance_budget  # Absolute limit of cosine drift

        # Telemetry storage
        self.composite_scores: List[float] = []
        self.cosine_drifts: List[float] = []

        # Simulated local embedding generation (e.g., via nomic-embed-text/llama.cpp)
        self.embedding_dimension = 384
        self.baseline_embedding = self._generate_local_embedding(baseline_prompt)

    def _generate_local_embedding(self, text: str) -> np.ndarray:
        """Simulates generation of a dense embedding vector using on-device modules."""
        # Replace this stub with actual local model integration:
        # np.array(local_embed_engine.embed(text))
        np.random.seed(hash(text) % (2**32 - 1))
        raw_vector = np.random.randn(self.embedding_dimension)
        return raw_vector / np.linalg.norm(raw_vector)

    def verify_mutation(
        self, mutated_prompt: str, locked_constraints: List[str]
    ) -> Tuple[float, float]:
        """
        Evaluates a mutated prompt candidate against the system's baseline.
        Computes cosine drift and structural constraint preservation.
        """
        mutated_embedding = self._generate_local_embedding(mutated_prompt)

        # 1. Compute cosine distance as a measure of semantic drift
        dot_product = np.dot(self.baseline_embedding, mutated_embedding)
        norm_product = np.linalg.norm(self.baseline_embedding) * np.linalg.norm(
            mutated_embedding
        )
        cosine_similarity = (
            float(dot_product / norm_product) if norm_product != 0 else 0.0
        )
        cosine_drift = 1.0 - cosine_similarity

        # 2. Compute the preservation ratio of locked constraints
        matched_constraints = sum(
            1 for c in locked_constraints if c.lower() in mutated_prompt.lower()
        )
        preservation_score = (
            matched_constraints / len(locked_constraints) if locked_constraints else 1.0
        )

        # 3. Calculate the composite mutation score
        # Weighted metric: 50% preservation, 50% semantic similarity
        composite_score = (preservation_score * 0.5) + (cosine_similarity * 0.5)

        self.cosine_drifts.append(cosine_drift)
        self.composite_scores.append(composite_score)

        logger.info(
            f"Mutation evaluated. Cosine Drift: {cosine_drift:.4f}, Composite Score: {composite_score:.4f}"
        )
        return cosine_drift, composite_score

    def analyze_drift_trend(self) -> bool:
        """
        Runs ordinary least squares (OLS) linear regression over historical mutations.
        Returns False if the trend indicates systematic performance degradation.
        """
        n = len(self.composite_scores)

        # Terminate immediately if the latest mutation violates the absolute variance budget
        if self.cosine_drifts and self.cosine_drifts[-1] > self.variance_budget:
            logger.critical(
                f"Instant alignment halt: current drift {self.cosine_drifts[-1]:.4f} exceeds variance budget {self.variance_budget:.4f}."
            )
            return False

        if n < 5:
            logger.info("Insufficient mutation history to compute regression slopes.")
            return True

        # OLS Regression: Y = alpha + beta * X
        y = np.array(self.composite_scores)
        x = np.arange(n)

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        covariance = np.sum((x - x_mean) * (y - y_mean))
        variance = np.sum((x - x_mean) ** 2)

        beta = float(covariance / variance) if variance != 0 else 0.0
        logger.info(
            f"OLS analysis complete over {n} iterations. Trend slope (beta): {beta:.6f}"
        )

        # A negative beta slope indicates progressive decay of constraint preservation
        if beta < self.stability_threshold:
            logger.critical(
                f"Systematic degradation detected: prompt slope of {beta:.6f} breaches stability thresholds."
            )
            return False

        return True
