from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any


__all__ = ["PipelinePolicy", "Pipeline"]


@dataclass(frozen=True)
class PipelinePolicy:
    """Global knobs for the extraction pipeline (policy values).

    Notes:
    - MVP0 may not use all fields yet; they live here to avoid changing
      function signatures later as capabilities are added.
    - Thresholds mirror the high-level design but are not enforced here.
    """

    accept_threshold: float = 0.80
    fallback_threshold: float = 0.50
    top_k: int = 2
    time_budget_ms: int = 9000


class Pipeline:
    def __init__(self, policy: Optional[PipelinePolicy] = None) -> None:
        self.policy = policy or PipelinePolicy()

    def run(self, label: str, schema_dict: Dict[str, str], pdf_path: str) -> Dict[str, Any]:
        """Executes the MVP0 pipeline and returns a JSON-serializable dict.

        Input:
          - label: document type (string).
          - schema_dict: mapping field_name -> description (no types yet).
          - pdf_path: path to a one-page, already OCR'd PDF file.

        Output:
          - A dict with shape:
            {
              "label": <label>,
              "results": {
                "<field_name>": {
                  "value": <str or null>,
                  "confidence": <float 0..1>,
                  "source": "heuristic" | "table" | "llm" | "none",
                  "trace": { ... }
                },
                ...
              }
            }

        Contract:
          - For every key passed in `schema_dict`, an entry must exist in "results".
          - If no valid evidence is found for a field, return null with source="none" and confidence=0.0.
          - Do not invent values; only use PDF text evidence (no external knowledge).
          - MVP0 must not call any LLM.

        Notes on MVP0 scope:
          - No columns/sections, no tables, no embeddings, no LLM.
          - Confidence is heuristic in future steps (e.g., 0.9 for same-line-right-of,
            0.8 for first-below); 0.0 for null. Not implemented yet.
        """
        # TODO: 1) ingestion: create `Document`, load blocks from pdf_path
        # TODO: 2) layout: build a `LayoutGraph` with ReadingNode(page/line) and SpatialEdge (two relations only)
        # TODO: 3) schema enrichment: convert schema_dict -> ExtractionSchema with basic type/regex/synonyms
        # TODO: 4) matching: for each field, find label blocks (by synonyms) and propose candidates using SpatialEdges
        # TODO: 5) extraction: clean candidate text, validate by regex/type; pick the first valid; else null
        # TODO: 6) assemble: build final JSON dict (label + results), including trace & simple confidence
        raise NotImplementedError("MVP0 pipeline body to be implemented in later tasks")


