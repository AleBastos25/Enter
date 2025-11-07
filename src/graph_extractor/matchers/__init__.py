"""Módulo de matchers para encontrar nós correspondentes a campos do schema."""

from src.graph_extractor.matchers.base import BaseMatcher, MatchResult
from src.graph_extractor.matchers.pattern_matcher import PatternMatcher
from src.graph_extractor.matchers.regex_matcher import RegexMatcher
from src.graph_extractor.matchers.embedding_matcher import EmbeddingMatcher

__all__ = [
    "BaseMatcher",
    "MatchResult",
    "PatternMatcher",
    "RegexMatcher",
    "EmbeddingMatcher",
]

