"""Runtime policy for timeouts, early-stop, and resource limits."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class RuntimePolicy:
    """Controls timeouts, early-stop, and resource limits during pipeline execution."""

    # Timeouts
    per_document_seconds: float = 15.0
    per_page_seconds: float = 2.5
    llm_total_seconds: float = 4.0

    # Limits
    max_pages: int = 32
    max_blocks_per_page: int = 3000
    max_blocks_indexed_per_page: int = 1500
    max_candidates_per_field_page: int = 6
    max_total_candidates_per_field: int = 20

    # Early-stop
    min_confidence_per_field: float = 0.80
    page_skip_if_no_signal: bool = True
    page_signal_threshold: float = 0.35
    page_signal_topk: int = 3

    # Memory
    embedding_eviction_pages: int = 3
    block_text_max_chars: int = 400

    # Multi-page flag
    multi_page: bool = False

    # Internal state
    _doc_start_time: Optional[float] = None
    _page_start_time: Optional[float] = None
    _llm_time_used: float = 0.0

    def start_document(self) -> None:
        """Mark start of document processing."""
        self._doc_start_time = time.monotonic()
        self._llm_time_used = 0.0

    def start_page(self) -> None:
        """Mark start of page processing."""
        self._page_start_time = time.monotonic()

    def doc_time_left(self) -> bool:
        """Check if document time budget is still available."""
        if self._doc_start_time is None:
            return True
        elapsed = time.monotonic() - self._doc_start_time
        return elapsed < self.per_document_seconds

    def page_time_left(self) -> bool:
        """Check if page time budget is still available."""
        if self._page_start_time is None:
            return True
        elapsed = time.monotonic() - self._page_start_time
        return elapsed < self.per_page_seconds

    def note_llm_time(self, seconds: float) -> None:
        """Record LLM time usage."""
        self._llm_time_used += seconds

    def llm_time_left(self) -> bool:
        """Check if LLM time budget is still available."""
        return self._llm_time_used < self.llm_total_seconds

    def should_early_stop(self, results: Dict[str, Dict]) -> bool:
        """Check if all fields have reached minimum confidence.

        Args:
            results: Dictionary mapping field_name -> FieldResult dict with 'confidence' key.

        Returns:
            True if all fields have confidence >= min_confidence_per_field.
        """
        if not results:
            return False

        for field_name, field_result in results.items():
            confidence = field_result.get("confidence", 0.0)
            if confidence < self.min_confidence_per_field:
                return False

        return True

    def should_skip_page(self, signals: Dict[str, float]) -> bool:
        """Check if page should be skipped due to lack of signals.

        Args:
            signals: Dictionary mapping field_name -> max_cosine_score.

        Returns:
            True if page_skip_if_no_signal is enabled and no field has signal >= threshold.
        """
        if not self.page_skip_if_no_signal:
            return False

        if not signals:
            return True  # No signals at all, skip

        # Check if any field has signal above threshold
        for field_name, signal_score in signals.items():
            if signal_score >= self.page_signal_threshold:
                return False  # Found at least one signal, don't skip

        return True  # No signals above threshold, skip page


def load_runtime_config() -> RuntimePolicy:
    """Load runtime configuration from YAML file, with safe defaults."""
    config_path = Path("configs/runtime.yaml")

    # Defaults (backward compatible: multi_page=false)
    defaults = {
        "multi_page": False,
        "timeouts": {
            "per_document_seconds": 15.0,
            "per_page_seconds": 2.5,
            "llm_total_seconds": 4.0,
        },
        "limits": {
            "max_pages": 32,
            "max_blocks_per_page": 3000,
            "max_blocks_indexed_per_page": 1500,
            "max_candidates_per_field_page": 6,
            "max_total_candidates_per_field": 20,
        },
        "early_stop": {
            "min_confidence_per_field": 0.80,
            "page_skip_if_no_signal": True,
            "page_signal_threshold": 0.35,
            "page_signal_topk": 3,
        },
        "memory": {
            "embedding_eviction_pages": 3,
            "block_text_max_chars": 400,
        },
    }

    if config_path.exists() and yaml:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                config = defaults.copy()
                # Merge nested dicts
                for key in config:
                    if key in loaded and isinstance(config[key], dict) and isinstance(loaded[key], dict):
                        config[key].update(loaded[key])
                    elif key in loaded:
                        config[key] = loaded[key]
        except Exception:
            config = defaults
    else:
        config = defaults

    return RuntimePolicy(
        multi_page=config.get("multi_page", False),
        per_document_seconds=config.get("timeouts", {}).get("per_document_seconds", 15.0),
        per_page_seconds=config.get("timeouts", {}).get("per_page_seconds", 2.5),
        llm_total_seconds=config.get("timeouts", {}).get("llm_total_seconds", 4.0),
        max_pages=config.get("limits", {}).get("max_pages", 32),
        max_blocks_per_page=config.get("limits", {}).get("max_blocks_per_page", 3000),
        max_blocks_indexed_per_page=config.get("limits", {}).get("max_blocks_indexed_per_page", 1500),
        max_candidates_per_field_page=config.get("limits", {}).get("max_candidates_per_field_page", 6),
        max_total_candidates_per_field=config.get("limits", {}).get("max_total_candidates_per_field", 20),
        min_confidence_per_field=config.get("early_stop", {}).get("min_confidence_per_field", 0.80),
        page_skip_if_no_signal=config.get("early_stop", {}).get("page_skip_if_no_signal", True),
        page_signal_threshold=config.get("early_stop", {}).get("page_signal_threshold", 0.35),
        page_signal_topk=config.get("early_stop", {}).get("page_signal_topk", 3),
        embedding_eviction_pages=config.get("memory", {}).get("embedding_eviction_pages", 3),
        block_text_max_chars=config.get("memory", {}).get("block_text_max_chars", 400),
    )

