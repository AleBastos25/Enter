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

    # Timeouts (v2: stricter budgets - máximo 2s por PDF)
    per_document_seconds: float = 2.0  # Requisito: máximo 2s por PDF
    per_document_budget_ms: float = 2000.0  # 2s em ms
    per_page_seconds: float = 1.8  # Budget por página (deixar margem para LLM)
    llm_total_seconds: float = 1.5  # LLM timeout agressivo (configurado em llm.yaml)
    
    # v2: Budgets por etapa (ms)
    grid_graph_budget_ms: float = 60.0
    matching_budget_ms: float = 500.0
    tables_budget_ms: float = 120.0
    # Embeddings removed - embedding_budget_ms no longer used

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

    # Defaults (v2: máximo 2s por PDF)
    defaults = {
        "multi_page": False,
        "timeouts": {
            "per_document_seconds": 2.0,  # Requisito: máximo 2s por PDF
            "per_page_seconds": 1.8,
            "llm_total_seconds": 1.5,
        },
        "limits": {
            "max_pages": 1,  # Single-page only for speed
            "max_blocks_per_page": 2000,  # Reduzido para acelerar
            "max_blocks_indexed_per_page": 0,  # Embeddings desabilitados
            "max_candidates_per_field_page": 5,  # Reduzido para acelerar
            "max_total_candidates_per_field": 15,  # Reduzido para acelerar
        },
        "early_stop": {
            "min_confidence_per_field": 0.75,  # Mais permissivo para early-stop mais rápido
            "page_skip_if_no_signal": False,  # Embeddings desabilitados
            "page_signal_threshold": 0.35,
            "page_signal_topk": 3,
        },
        "memory": {
            # Embeddings removed
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
        per_document_seconds=config.get("timeouts", {}).get("per_document_seconds", 2.0),  # Máximo 2s por PDF
        per_page_seconds=config.get("timeouts", {}).get("per_page_seconds", 1.8),
        llm_total_seconds=config.get("timeouts", {}).get("llm_total_seconds", 1.5),
        max_pages=config.get("limits", {}).get("max_pages", 1),
        max_blocks_per_page=config.get("limits", {}).get("max_blocks_per_page", 1500),
        max_blocks_indexed_per_page=config.get("limits", {}).get("max_blocks_indexed_per_page", 0),
        max_candidates_per_field_page=config.get("limits", {}).get("max_candidates_per_field_page", 3),
        max_total_candidates_per_field=config.get("limits", {}).get("max_total_candidates_per_field", 10),
        min_confidence_per_field=config.get("early_stop", {}).get("min_confidence_per_field", 0.75),
        page_skip_if_no_signal=config.get("early_stop", {}).get("page_skip_if_no_signal", False),
        page_signal_threshold=config.get("early_stop", {}).get("page_signal_threshold", 0.35),
        page_signal_topk=config.get("early_stop", {}).get("page_signal_topk", 3),
        # Embeddings removed - embedding_eviction_pages no longer used
        block_text_max_chars=config.get("memory", {}).get("block_text_max_chars", 400),
    )

