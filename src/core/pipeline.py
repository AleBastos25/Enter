from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..extraction.text_extractor import extract_from_candidate
from ..io.pdf_loader import extract_blocks, load_document
from ..layout.builder import build_layout
from ..matching.matcher import match_fields
from .models import SchemaField
from .schema import enrich_schema


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
          - Confidence is heuristic (0.9 for same-line-right-of, 0.8 for first-below); 0.0 for null.
          - Time budgets and LLM parts are TODO for future iterations.
        """
        # 1) Load & blocks
        doc = load_document(pdf_path, label=label)
        blocks = extract_blocks(doc)

        # 2) Layout
        layout = build_layout(doc, blocks)

        # 3) Enrich schema: convert schema_dict -> ExtractionSchema
        enriched = enrich_schema(label, schema_dict)
        schema_fields = enriched.fields

        # 4) Matching (no soft validation needed; hard validators in extraction)
        cands_map = match_fields(
            schema_fields, layout, validate=None, top_k=self.policy.top_k
        )

        # 5) Extraction loop with reuse prevention
        results: Dict[str, Dict[str, Any]] = {}
        used_blocks: Dict[int, tuple[str, Optional[str]]] = {}  # node_id -> (field_name, normalized_value)

        for field in schema_fields:
            candidates = cands_map.get(field.name, [])

            value = None
            confidence = 0.0
            source = "none"
            trace: Dict[str, Any] = {"reason": "no_evidence"}

            # Try top-1, then top-2
            for cand in candidates[:2]:
                # Check if this block was already used by another field
                if cand.node_id in used_blocks:
                    used_field, used_value = used_blocks[cand.node_id]
                    # Apply penalty: if value is incompatible with this field's type, skip
                    # (Still allow if no other candidate works)
                    if used_field != field.name:
                        # Check if the normalized value is incompatible with this field's type
                        # For now, we'll still try it but with lower priority (already sorted by score)
                        pass

                value_candidate, conf_candidate, trace_candidate = extract_from_candidate(
                    field, cand, layout
                )

                if value_candidate is not None:
                    # Check compatibility: if this block was used before, verify type compatibility
                    if cand.node_id in used_blocks:
                        used_field, used_value = used_blocks[cand.node_id]
                        if used_field != field.name:
                            # If normalized values are identical, likely same entity - skip
                            if used_value == value_candidate:
                                continue
                            # If types are incompatible, skip
                            used_field_obj = next((f for f in schema_fields if f.name == used_field), None)
                            if used_field_obj:
                                # Check if value would validate for the other field's type
                                # If not, it's incompatible and we should skip
                                from ..validation.validators import validate_and_normalize

                                ok_other, _ = validate_and_normalize(
                                    used_field_obj.type or "text",
                                    value_candidate,
                                    enum_options=used_field_obj.meta.get("enum_options")
                                    if used_field_obj.meta
                                    else None,
                                )
                                if not ok_other:
                                    # This value doesn't work for the other field's type,
                                    # so it might be okay for this field
                                    pass
                                else:
                                    # Value works for both - likely ambiguous, skip to avoid reuse
                                    continue

                    value = value_candidate
                    confidence = conf_candidate
                    source = "heuristic"
                    trace = trace_candidate
                    # Mark this block as used
                    used_blocks[cand.node_id] = (field.name, value_candidate)
                    break

            results[field.name] = {
                "value": value,  # None will be serialized as null
                "confidence": confidence,
                "source": source,
                "trace": trace,
            }

        # 6) Assemble JSON
        return {
            "label": label,
            "results": results,
        }




