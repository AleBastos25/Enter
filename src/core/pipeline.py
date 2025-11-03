from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..extraction.text_extractor import extract_from_candidate
from ..io.pdf_loader import extract_blocks, load_document
from ..layout.builder import build_layout
from ..matching.matcher import match_fields
from ..validation.validators import validate_soft
from .models import SchemaField


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

        # 3) Enrich schema: convert schema_dict -> SchemaField list
        schema_fields = _enrich_schema(schema_dict)

        # 4) Matching
        cands_map = match_fields(
            schema_fields, layout, validate=validate_soft, top_k=self.policy.top_k
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

                                ok_other, _ = validate_and_normalize(used_field_obj.type or "text", value_candidate)
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


# Type inference triggers (case-insensitive, normalized)
TYPE_TRIGGERS = {
    "date": ["data", "date", "emissão", "emissao", "vencimento", "vcto", "venc", "nascimento"],
    "money": ["valor", "preço", "preco", "total", "montante", "amount", "saldo", "value"],
    "id_simple": ["id", "código", "codigo", "registro", "inscrição", "inscricao", "nº", "no", "n."],
    "uf": ["uf", "estado", "seccional", "sigla"],
    "cep": ["cep", "zip"],
}


def _normalize_for_match(text: str) -> str:
    """Normalize text for matching (lowercase, remove accents, etc.)."""
    import unicodedata

    # Remove accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower()


def _generate_synonyms(name: str, description: str) -> list[str]:
    """Generate synonyms from field name and description (generic, not field-specific)."""
    synonyms = [name.lower()]

    name_norm = _normalize_for_match(name)
    desc_norm = _normalize_for_match(description)

    # Generic synonym patterns (never depend on specific PDF)
    # If name contains common patterns, add variants
    if any(word in name_norm for word in ["inscri", "registro", "id", "nº", "no", "numero"]):
        synonyms.extend(["inscrição", "inscricao", "inscri", "nº", "no", "n.", "numero", "registro"])

    if any(word in name_norm for word in ["uf", "estado", "seccional", "sigla"]):
        synonyms.extend(["uf", "estado", "seccional", "sigla"])

    if any(word in name_norm for word in ["nome", "name"]):
        synonyms.extend(["nome", "name"])

    if any(word in name_norm for word in ["cep", "zip"]):
        synonyms.extend(["cep", "zip"])

    # Also use description words if they match common patterns
    desc_words = desc_norm.split()
    for word in desc_words:
        if word in ["inscri", "registro", "id", "nº", "no", "numero"] and word not in synonyms:
            synonyms.append(word)
        if word in ["uf", "estado", "seccional", "sigla"] and word not in synonyms:
            synonyms.append(word)
        if word in ["cep", "zip"] and word not in synonyms:
            synonyms.append(word)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for syn in synonyms:
        syn_norm = syn.lower().strip()
        if syn_norm and syn_norm not in seen:
            seen.add(syn_norm)
            unique.append(syn_norm)

    return unique


def _enrich_schema(schema_dict: Dict[str, str]) -> list[SchemaField]:
    """Convert schema_dict to SchemaField list with heuristic types and synonyms.

    Uses generic triggers and patterns, not hardcoded to specific field names.

    Args:
        schema_dict: Mapping field_name -> description.

    Returns:
        List of SchemaField objects with inferred types and basic synonyms.
    """
    fields = []

    for name, description in schema_dict.items():
        # Heuristic type inference using generic triggers
        name_norm = _normalize_for_match(name)
        desc_norm = _normalize_for_match(description)

        field_type = "text"
        # Check each type in order of specificity
        for ftype, triggers in TYPE_TRIGGERS.items():
            if any(trigger in name_norm or trigger in desc_norm for trigger in triggers):
                field_type = ftype
                break

        # Generate synonyms (generic, not hardcoded)
        synonyms = _generate_synonyms(name, description)

        fields.append(
            SchemaField(
                name=name,
                description=description,
                type=field_type,
                synonyms=synonyms,
            )
        )

    return fields


