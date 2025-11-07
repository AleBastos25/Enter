"""Módulo de tiebreakers para desempatar entre múltiplos candidatos."""

from src.graph_extractor.tiebreaker.base import BaseTieBreaker
from src.graph_extractor.tiebreaker.heuristic_tiebreaker import HeuristicTieBreaker
from src.graph_extractor.tiebreaker.llm_tiebreaker import LLMTieBreaker

__all__ = [
    "BaseTieBreaker",
    "HeuristicTieBreaker",
    "LLMTieBreaker",
]

