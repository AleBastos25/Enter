"""LLM policy: budget tracking and triggering logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMPipelinePolicy:
    """Policy for LLM fallback: budget, triggering, caching."""

    max_calls_per_pdf: int = 2
    min_score: float = 0.50
    max_score: float = 0.80
    calls_used: int = field(default=0, init=False)
    _cache: dict[str, Optional[str]] = field(default_factory=dict, init=False)

    def budget_left(self) -> bool:
        """Check if there are remaining LLM calls in budget."""
        return self.calls_used < self.max_calls_per_pdf

    def should_trigger(self, field_name: str, top_score: Optional[float], have_value: bool) -> bool:
        """Determine if LLM fallback should be triggered.

        Args:
            field_name: Name of the field being extracted.
            top_score: Score of top candidate (None if no candidates).
            have_value: Whether a valid value was already extracted.

        Returns:
            True if LLM should be called.
        """
        # No budget left
        if not self.budget_left():
            return False

        # Already have valid value - don't call LLM
        if have_value:
            return False

        # No candidates at all - trigger
        if top_score is None:
            return True

        # Score in gray zone - trigger
        if self.min_score <= top_score <= self.max_score:
            return True

        return False

    def note_call(self) -> None:
        """Record that an LLM call was made."""
        self.calls_used += 1

    def get_cached(self, cache_key: str) -> Optional[str]:
        """Get cached response for key."""
        return self._cache.get(cache_key)

    def cache_response(self, cache_key: str, value: Optional[str]) -> None:
        """Cache a response."""
        self._cache[cache_key] = value

    def reset(self) -> None:
        """Reset policy for new PDF (reset budget counter and cache)."""
        self.calls_used = 0
        self._cache.clear()

