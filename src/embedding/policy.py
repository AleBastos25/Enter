"""Policy for embedding usage: budget, thresholds, top-K."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmbeddingPolicy:
    """Policy for semantic matching with embeddings."""

    top_k_per_field: int = 6
    min_sim_threshold: float = 0.35
    max_blocks_considered: int = 2000
    max_calls_per_pdf: int = 100
    batch_size: int = 64
    calls_used: int = 0

    def budget_left(self) -> bool:
        """Check if there are remaining embedding calls in budget."""
        return self.calls_used < self.max_calls_per_pdf

    def note_call(self, batch_size: int = 1) -> None:
        """Record that embedding calls were made.

        Args:
            batch_size: Number of texts in the batch (counts as 1 call if batched).
        """
        self.calls_used += 1

    def reset(self) -> None:
        """Reset policy for new PDF."""
        self.calls_used = 0

