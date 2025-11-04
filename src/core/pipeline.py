from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from ..embedding.client import create_embedding_client
from ..embedding.index import CosineIndex
from ..embedding.policy import EmbeddingPolicy
from ..extraction.text_extractor import extract_from_candidate
from ..io.cache import key_for_block, key_for_query, load_vec, save_vec
from ..io.pdf_loader import extract_blocks, iter_page_blocks, load_document
from ..layout.builder import build_layout
from .policy import RuntimePolicy, load_runtime_config
from ..llm.client import create_client
from ..llm.policy import LLMPipelinePolicy
from ..llm.prompts import build_prompt, parse_llm_response
from ..matching.matcher import match_fields
from ..tables.detector import detect_tables
from ..validation.validators import validate_and_normalize
from .models import Block, Document, LayoutGraph, SchemaField
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

    def run(self, label: str, schema_dict: Dict[str, str], pdf_path: str, debug: bool = False) -> Dict[str, Any]:
        """Executes the v1.0 pipeline (multi-page or single-page) and returns a JSON-serializable dict.

        Input:
          - label: document type (string).
          - schema_dict: mapping field_name -> description (no types yet).
          - pdf_path: path to a PDF file (supports multi-page).
          - debug: if True, include diagnostic information in output.

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
              },
              "debug": { ... }  # Only if debug=True
            }

        Contract:
          - For every key passed in `schema_dict`, an entry must exist in "results".
          - If no valid evidence is found for a field, return null with source="none" and confidence=0.0.
          - Do not invent values; only use PDF text evidence (no external knowledge).
        """
        # Load runtime policy
        runtime_policy = load_runtime_config()
        runtime_policy.start_document()

        # Load document
        doc = load_document(pdf_path, label=label)

        # Check if multi-page mode
        if runtime_policy.multi_page:
            return self._run_multi_page(doc, label, schema_dict, runtime_policy, debug=debug)
        else:
            return self._run_single_page(doc, label, schema_dict, runtime_policy, debug=debug)

    def _run_single_page(
        self, doc: Document, label: str, schema_dict: Dict[str, str], runtime_policy: RuntimePolicy, debug: bool = False
    ) -> Dict[str, Any]:
        """Single-page processing (backward compatible)."""
        # 1) Load & blocks (first page only)
        blocks = extract_blocks(doc)

        # 2) Layout
        layout = build_layout(doc, blocks)

        # 2.5) Detect tables
        pdf_lines = getattr(layout, "pdf_lines", None)
        tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
        # Attach tables to layout (via setattr since it's a frozen dataclass)
        object.__setattr__(layout, "tables", tables)

        # 3) Enrich schema: convert schema_dict -> ExtractionSchema
        enriched = enrich_schema(label, schema_dict)
        schema_fields = enriched.fields

        # 3.5) Load pattern memory (if enabled)
        memory_cfg = _load_memory_config()
        pattern_memory = None
        if memory_cfg.get("enabled", False):
            from ..memory.pattern_memory import PatternMemory
            from ..memory.store import MemoryStore

            store = MemoryStore(memory_cfg.get("store_dir", "data/artifacts/pattern_memory"))
            pattern_memory = PatternMemory(label, memory_cfg, store)

        # 3.6) Semantic seeding (if enabled)
        semantic_seeds: Dict[str, List[Tuple[int, float]]] = {}
        embedding_config = _load_embedding_config()
        if embedding_config.get("enabled", False):
            semantic_seeds = _build_semantic_seeds(
                doc, blocks, schema_fields, layout, embedding_config
            )

        # 4) Matching (includes table lookup, semantic seeds, and memory; no soft validation needed; hard validators in extraction)
        cands_map = match_fields(
            schema_fields,
            layout,
            validate=None,
            top_k=self.policy.top_k,
            semantic_seeds=semantic_seeds,
            pattern_memory=pattern_memory,
            memory_cfg=memory_cfg if memory_cfg.get("enabled", False) else None,
        )

        # 4.5) Load LLM config and create client/policy (if enabled)
        llm_config = _load_llm_config()
        llm_client = None
        llm_policy = None

        if llm_config.get("enabled", True):
            provider = llm_config.get("provider", "none")
            model = llm_config.get("model", "gpt-4o-mini")
            temperature = llm_config.get("temperature", 0.0)
            llm_client = create_client(provider, model, temperature)
            llm_policy = LLMPipelinePolicy(
                max_calls_per_pdf=llm_config.get("budget", {}).get("max_calls_per_pdf", 2),
                min_score=llm_config.get("trigger", {}).get("min_score", 0.50),
                max_score=llm_config.get("trigger", {}).get("max_score", 0.80),
            )

        # 5) Extraction loop with reuse prevention and LLM fallback
        results: Dict[str, Dict[str, Any]] = {}
        used_blocks: Dict[int, tuple[str, Optional[str]]] = {}  # node_id -> (field_name, normalized_value)
        used_values_by_type: Dict[str, set[str]] = {}  # type -> set of used values (to avoid duplicates)

        for field in schema_fields:
            candidates = cands_map.get(field.name, [])
            field_type = field.type or "text"

            value = None
            confidence = 0.0
            source = "none"
            trace: Dict[str, Any] = {
                "reason": "no_evidence",
                "page_index": 0,
                "notes": "No evidence found for this field",
            }
            trace_candidate: Dict[str, Any] = trace  # Initialize for LLM fallback

            # Try top candidates (increase to 5 to catch global_enum_scan and other relations)
            for cand in candidates[:5]:
                # Check if this block was already used by another field
                # Special handling: global_enum_scan and enum fields can reuse blocks if value validates
                is_enum_scan = cand.relation == "global_enum_scan"
                is_enum_field = field.type == "enum"
                
                # Get embed_client if available (for semantic similarity boost)
                embed_client_for_extraction = None
                if embedding_config.get("enabled", False):
                    try:
                        provider = embedding_config.get("provider", "local")
                        model_name = embedding_config.get("model", "all-MiniLM-L6-v2")
                        dim = embedding_config.get("dim", 384)
                        from ..embedding.client import create_embedding_client
                        embed_client_for_extraction = create_embedding_client(provider, model_name, dim)
                    except Exception:
                        embed_client_for_extraction = None
                
                value_candidate, conf_candidate, trace_candidate = extract_from_candidate(
                    field, cand, layout, embed_client=embed_client_for_extraction
                )
                
                if value_candidate is not None:
                    # Check if this value was already used by another field of the same type
                    if field_type not in used_values_by_type:
                        used_values_by_type[field_type] = set()
                    
                    if value_candidate in used_values_by_type[field_type]:
                        # Same value already extracted by another field of the same type - skip
                        # This prevents fields like inscricao and subsecao from getting the same value
                        continue
                    
                    # Check if this block was already used by another field
                    if cand.node_id in used_blocks:
                        used_field, used_value = used_blocks[cand.node_id]
                        if used_field != field.name:
                            # If the same exact value is extracted, skip (avoid duplicates)
                            if value_candidate == used_value:
                                # Same value already extracted by another field - skip
                                continue
                        
                if value_candidate is not None:
                    # Check compatibility: if this block was used before, verify type compatibility
                    if cand.node_id in used_blocks:
                        used_field, used_value = used_blocks[cand.node_id]
                        if used_field != field.name:
                            # If normalized values are identical, likely same entity - skip
                            if used_value == value_candidate:
                                continue
                            
                            # For fields of the same type (e.g., both id_simple), avoid reusing same block
                            # even if values are different (they might be different lines from same block)
                            used_field_obj = next((f for f in schema_fields if f.name == used_field), None)
                            if used_field_obj and field.type == used_field_obj.type:
                                # Same type extracting from same block - prefer different blocks to avoid ambiguity
                                # Only skip if this is not the best candidate (lower confidence)
                                if conf_candidate < 0.90:  # Not very high confidence, try other candidates first
                                    continue
                            
                            # Special case: enum fields with global_enum_scan can reuse if value validates
                            if is_enum_scan and is_enum_field:
                                # Check if the value validates for this enum field
                                from ..validation.validators import validate_and_normalize
                                ok_current, _ = validate_and_normalize(
                                    field.type or "text",
                                    value_candidate,
                                    enum_options=field.meta.get("enum_options") if field.meta else None,
                                )
                                if ok_current:
                                    # Value validates for this enum, allow reuse
                                    pass
                                else:
                                    continue
                            
                            # If types are incompatible, skip
                            used_field_obj = next((f for f in schema_fields if f.name == used_field), None)
                            if used_field_obj:
                                # Check if value would validate for the other field's type
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
                                    # UNLESS this is an enum field with global_enum_scan
                                    if not (is_enum_scan and is_enum_field):
                                        continue

                    value = value_candidate
                    confidence = conf_candidate
                    # Determine source: "table" if from table, else "heuristic"
                    source = "table" if cand.relation == "same_table_row" else "heuristic"
                    trace = trace_candidate
                    # Mark this block as used
                    used_blocks[cand.node_id] = (field.name, value_candidate)
                    # Mark this value as used for this type
                    used_values_by_type[field_type].add(value_candidate)

                    # Learn from high-confidence extraction (pattern memory)
                    if pattern_memory and memory_cfg.get("enabled", False):
                        learn_cfg = memory_cfg.get("learn", {})
                        min_confidence = learn_cfg.get("min_confidence", 0.85)
                        accept_relations = learn_cfg.get("accept_relations", [])
                        if confidence >= min_confidence and cand.relation in accept_relations:
                            # Get label and value blocks
                            label_block = next(
                                (b for b in layout.blocks if b.id == cand.source_label_block_id), None
                            )
                            value_block = next((b for b in layout.blocks if b.id == cand.node_id), None)

                            if label_block and value_block:
                                # Build context
                                context = {
                                    "section_id": getattr(layout, "section_id_by_block", {}).get(
                                        label_block.id
                                    ),
                                    "column_id": getattr(layout, "column_id_by_block", {}).get(label_block.id),
                                    "page_index": layout.page_index,
                                    "enum_options": field.meta.get("enum_options") if field.meta else None,
                                }

                                # Learn
                                pattern_memory.learn(
                                    field.name,
                                    label_block.text or "",
                                    value_candidate,
                                    cand.relation,
                                    label_block.bbox,
                                    value_block.bbox,
                                    confidence,
                                    context,
                                )

                    break

            # 5.5) LLM fallback (if enabled and budget allows)
            # Trigger if no value found OR confidence is low OR score is in gray zone
            should_use_llm = False
            if llm_client and llm_policy:
                # Calculate top score from candidates
                top_score = None
                if candidates:
                    top_cand = candidates[0]
                    top_score = (
                        0.60 * top_cand.scores.get("type", 0.0)
                        + 0.30 * top_cand.scores.get("spatial", 0.0)
                        + 0.10 * min(1.0, top_cand.scores.get("semantic", 0.0) / 0.85)
                    )

                # Check if should trigger LLM
                # Trigger if:
                # 1. No value found
                # 2. Confidence is low (< 0.75) - value might be incorrect
                # 3. Score is in gray zone (ambiguous) - even with value, LLM might help
                # 4. Value is implausible (doesn't make semantic sense for the field)
                plausibility = 1.0
                if value is not None:
                    from ..extraction.text_extractor import _validate_plausibility
                    plausibility = _validate_plausibility(field, value)
                
                if value is None:
                    should_use_llm = llm_policy.should_trigger(field.name, top_score, have_value=False)
                elif confidence < 0.75:
                    # Low confidence - value might be incorrect, try LLM
                    should_use_llm = llm_policy.budget_left()
                elif plausibility < 0.5:
                    # Value is implausible - likely wrong, try LLM to correct
                    should_use_llm = llm_policy.budget_left()
                elif confidence < 0.80 and plausibility < 0.7:
                    # Medium confidence with low plausibility - try LLM
                    should_use_llm = llm_policy.budget_left()
                elif top_score is not None and llm_policy.min_score <= top_score <= llm_policy.max_score:
                    # Score in gray zone - ambiguous, LLM might help clarify
                    should_use_llm = llm_policy.budget_left()

            if should_use_llm:
                # Build context from evidence (use top candidate if available)
                # Improved: include multiple lines, field description, and richer context
                context_text = ""
                if candidates and "evidence" in trace_candidate:
                    evidence = trace_candidate.get("evidence", {})
                    candidate_text = evidence.get("candidate_text", "")
                    neighbors = evidence.get("neighbors", "")
                    
                    # Build richer context
                    context_parts = []
                    
                    # Add field description for better context
                    if field.description:
                        context_parts.append(f"Field: {field.name}\nDescription: {field.description}")
                    
                    # Use full block text (up to 500 chars) instead of just first line
                    if candidates:
                        top_cand = candidates[0]
                        dst_block = next((b for b in layout.blocks if b.id == top_cand.node_id), None)
                        if dst_block and dst_block.text:
                            # Use first 500 chars of block (may include multiple lines)
                            block_text = dst_block.text[:500]
                            context_parts.append(f"Block text: {block_text}")
                        elif candidate_text:
                            context_parts.append(f"Candidate text: {candidate_text}")
                    
                    if neighbors:
                        context_parts.append(f"Neighbors: {neighbors}")
                    
                    context_text = "\n".join(context_parts)
                elif candidates:
                    # Fallback: use candidate text with field description
                    top_cand = candidates[0]
                    dst_block = next((b for b in layout.blocks if b.id == top_cand.node_id), None)
                    context_parts = []
                    if field.description:
                        context_parts.append(f"Field: {field.name}\nDescription: {field.description}")
                    if dst_block and dst_block.text:
                        block_text = dst_block.text[:500]
                        context_parts.append(f"Block text: {block_text}")
                    context_text = "\n".join(context_parts)

                if context_text:
                    # Build prompt
                    enum_options = field.meta.get("enum_options") if field.meta else None
                    prompt = build_prompt(
                        field.name,
                        field.type or "text",
                        context_text,
                        enum_options=enum_options,
                        regex_hint=field.regex,
                    )

                    # Call LLM
                    max_tokens = llm_config.get("budget", {}).get("max_tokens_per_call", 256)
                    timeout = llm_config.get("timeout_seconds", 2.0)
                    llm_response = llm_client.generate(prompt, max_tokens=max_tokens, timeout=timeout)
                    llm_policy.note_call()

                    # Parse response
                    llm_value = parse_llm_response(llm_response)

                    if llm_value:
                        # Hard validation: must pass validator
                        ok, normalized = validate_and_normalize(
                            field.type or "text",
                            llm_value,
                            enum_options=enum_options,
                        )

                        if ok and normalized:
                            value = normalized
                            # Lower confidence for LLM (below heuristic)
                            confidence = 0.75 if candidates and candidates[0].relation == "same_table_row" else 0.70
                            source = "llm"
                            trace = {
                                **trace_candidate,
                                "page_index": trace_candidate.get("page_index", 0),
                                "notes": trace_candidate.get("notes", "Value extracted via LLM fallback") + " (LLM fallback)",
                                "llm": {
                                    "used": True,
                                    "chars_context": len(context_text),
                                },
                            }
                            # Use top candidate node_id for tracking
                            if candidates:
                                used_blocks[candidates[0].node_id] = (field.name, normalized)

            # Ensure page_index and notes are in trace (for single-page, default to 0)
            if "page_index" not in trace:
                trace["page_index"] = 0
            if "notes" not in trace:
                trace["notes"] = trace.get("reason", "No evidence found")
            
            results[field.name] = {
                "value": value,  # None will be serialized as null
                "confidence": confidence,
                "source": source,
                "trace": trace,
            }

        # 6) Commit pattern memory if enabled
        if pattern_memory and memory_cfg.get("enabled", False):
            pattern_memory.commit()

        # 7) Assemble JSON
        output = {
            "label": label,
            "results": results,
        }
        
        # Add debug info if requested
        if debug:
            debug_info = {
                "pages_processed": [0],  # Single page mode
                "blocks_count": len(blocks),
                "tables_count": len(tables),
                "candidates_by_field": {
                    field.name: [
                        {
                            "node_id": cand.node_id,
                            "relation": cand.relation,
                            "scores": cand.scores,
                        }
                        for cand in cands_map.get(field.name, [])[:5]  # Top 5
                    ]
                    for field in schema_fields
                },
                "semantic_seeds": {
                    field.name: seeds[:3]  # Top 3
                    for field in schema_fields
                    if field.name in semantic_seeds and (seeds := semantic_seeds[field.name])
                },
            }
            output["debug"] = debug_info
        
        return output

    def _run_multi_page(
        self, doc: Document, label: str, schema_dict: Dict[str, str], runtime_policy: RuntimePolicy, debug: bool = False
    ) -> Dict[str, Any]:
        """Multi-page processing with fusion, early-stop, and page skipping."""
        # Initialize schema
        enriched = enrich_schema(label, schema_dict)
        schema_fields = enriched.fields

        # Load configs
        memory_cfg = _load_memory_config()
        embedding_config = _load_embedding_config()
        llm_config = _load_llm_config()

        # Initialize pattern memory
        pattern_memory = None
        if memory_cfg.get("enabled", False):
            from ..memory.pattern_memory import PatternMemory
            from ..memory.store import MemoryStore

            store = MemoryStore(memory_cfg.get("store_dir", "data/artifacts/pattern_memory"))
            pattern_memory = PatternMemory(label, memory_cfg, store)

        # Initialize LLM client/policy
        llm_client = None
        llm_policy = None
        if llm_config.get("enabled", True):
            provider = llm_config.get("provider", "none")
            model = llm_config.get("model", "gpt-4o-mini")
            temperature = llm_config.get("temperature", 0.0)
            llm_client = create_client(provider, model, temperature)
            llm_policy = LLMPipelinePolicy(
                max_calls_per_pdf=llm_config.get("budget", {}).get("max_calls_per_pdf", 2),
                min_score=llm_config.get("trigger", {}).get("min_score", 0.50),
                max_score=llm_config.get("trigger", {}).get("max_score", 0.80),
            )

        # Initialize embedding client (if enabled)
        embed_client = None
        embedding_indexes: Dict[int, CosineIndex] = {}  # page_index -> index
        if embedding_config.get("enabled", False):
            provider = embedding_config.get("provider", "hash")
            model_name = embedding_config.get("model", "all-MiniLM-L6-v2")
            dim = embedding_config.get("dim", 384)
            try:
                embed_client = create_embedding_client(provider, model_name, dim)
            except Exception:
                embed_client = None

        # Results per page (for fusion)
        page_results: Dict[int, Dict[str, Dict[str, Any]]] = {}  # page_index -> field_name -> result
        page_signals_by_page: Dict[int, Dict[str, float]] = {}  # For debug: page_index -> field_name -> signal

        # Process each page
        pages_processed = 0
        for page_index, blocks in iter_page_blocks(doc):
            # Check limits
            if pages_processed >= runtime_policy.max_pages:
                break
            if not runtime_policy.doc_time_left():
                break

            runtime_policy.start_page()

            # Limit blocks per page
            if len(blocks) > runtime_policy.max_blocks_per_page:
                blocks = blocks[: runtime_policy.max_blocks_per_page]

            # Build layout for this page
            layout = build_layout(doc, blocks)
            object.__setattr__(layout, "page_index", page_index)

            # Detect tables
            pdf_lines = getattr(layout, "pdf_lines", None)
            tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
            object.__setattr__(layout, "tables", tables)

            # Build embedding index for this page (if enabled)
            semantic_seeds: Dict[str, List[Tuple[int, float]]] = {}
            if embed_client and embedding_config.get("enabled", False):
                semantic_seeds, page_index_obj = _build_semantic_seeds_per_page(
                    doc, blocks, schema_fields, layout, embedding_config, embed_client, runtime_policy
                )
                embedding_indexes[page_index] = page_index_obj

                # Evict old indexes (LRU)
                if len(embedding_indexes) > runtime_policy.embedding_eviction_pages:
                    oldest_page = min(embedding_indexes.keys())
                    del embedding_indexes[oldest_page]

            # Get page signals (max cosine per field)
            page_signals: Dict[str, float] = {}
            for field in schema_fields:
                field_seeds = semantic_seeds.get(field.name, [])
                if field_seeds:
                    page_signals[field.name] = max(score for _, score in field_seeds)
            
            # Store signals for debug
            if debug:
                page_signals_by_page[page_index] = page_signals

            # Skip page if no signals (only when embeddings are enabled)
            # When embeddings are disabled, we rely on heuristics only, so don't skip pages
            if embedding_config.get("enabled", False) and runtime_policy.should_skip_page(page_signals):
                continue

            # Match fields
            cands_map = match_fields(
                schema_fields,
                layout,
                validate=None,
                top_k=runtime_policy.max_candidates_per_field_page,
                semantic_seeds=semantic_seeds,
                pattern_memory=pattern_memory,
                memory_cfg=memory_cfg if memory_cfg.get("enabled", False) else None,
            )

            # Extract and validate for this page
            page_results[page_index] = {}
            used_blocks: Dict[int, tuple[str, Optional[str]]] = {}

            for field in schema_fields:
                candidates = cands_map.get(field.name, [])

                value = None
                confidence = 0.0
                source = "none"
                trace: Dict[str, Any] = {
                    "reason": "no_evidence",
                    "page_index": page_index,
                    "notes": "No evidence found for this field on this page",
                }

                for cand in candidates[:3]:
                    if cand.node_id in used_blocks:
                        used_field, used_value = used_blocks[cand.node_id]
                        if used_field != field.name and used_value == value:
                            continue

                    value_candidate, conf_candidate, trace_candidate = extract_from_candidate(
                        field, cand, layout, embed_client=embed_client if embedding_config.get("enabled", False) else None
                    )
                    if value_candidate is not None:
                        value = value_candidate
                        confidence = conf_candidate
                        source = "table" if cand.relation == "same_table_row" else "heuristic"
                        # trace_candidate already has page_index from extract_from_candidate, but ensure it matches this page
                        trace = {**trace_candidate, "page_index": page_index}
                        used_blocks[cand.node_id] = (field.name, value_candidate)

                        # Learn (pattern memory)
                        if pattern_memory and memory_cfg.get("enabled", False):
                            learn_cfg = memory_cfg.get("learn", {})
                            min_confidence = learn_cfg.get("min_confidence", 0.85)
                            accept_relations = learn_cfg.get("accept_relations", [])
                            if confidence >= min_confidence and cand.relation in accept_relations:
                                label_block = next(
                                    (b for b in layout.blocks if b.id == cand.source_label_block_id), None
                                )
                                value_block = next((b for b in layout.blocks if b.id == cand.node_id), None)
                                if label_block and value_block:
                                    context = {
                                        "section_id": getattr(layout, "section_id_by_block", {}).get(label_block.id),
                                        "column_id": getattr(layout, "column_id_by_block", {}).get(label_block.id),
                                        "paragraph_id": getattr(layout, "paragraph_id_by_block", {}).get(label_block.id),
                                        "page_index": page_index,
                                        "enum_options": field.meta.get("enum_options") if field.meta else None,
                                    }
                                    pattern_memory.learn(
                                        field.name,
                                        label_block.text or "",
                                        value_candidate,
                                        cand.relation,
                                        label_block.bbox,
                                        value_block.bbox,
                                        confidence,
                                        context,
                                    )
                        break

                page_results[page_index][field.name] = {
                    "value": value,
                    "confidence": confidence,
                    "source": source,
                    "trace": trace,
                }

            pages_processed += 1

            # Early-stop check
            fused = _fuse_page_results(page_results, schema_fields)
            if runtime_policy.should_early_stop(fused):
                break

        # Final fusion across all pages
        final_results = _fuse_page_results(page_results, schema_fields)

        # LLM fallback (if enabled and budget allows)
        if llm_client and llm_policy:
            for field in schema_fields:
                result = final_results.get(field.name, {})
                if result.get("value") is None or result.get("confidence", 0.0) < runtime_policy.min_confidence_per_field:
                    # Try LLM fallback
                    # (Reuse logic from single-page, but simplified for multi-page)
                    # For now, skip LLM in multi-page to keep it simple
                    pass

        # Commit pattern memory
        if pattern_memory and memory_cfg.get("enabled", False):
            pattern_memory.commit()

        output = {
            "label": label,
            "results": final_results,
        }
        
        # Add debug info if requested
        if debug:
            # Collect debug info from all pages
            debug_info = {
                "pages_processed": sorted(page_results.keys()),
                "pages_skipped": pages_processed - len(page_results),
                "page_signals": page_signals_by_page,  # Signals per page per field
                "candidates_by_field_page": {},  # Will collect below
            }
            
            # Collect page signals and candidates (from last processed pages)
            for page_idx, page_field_results in page_results.items():
                for field_name, result in page_field_results.items():
                    if field_name not in debug_info["candidates_by_field_page"]:
                        debug_info["candidates_by_field_page"][field_name] = {}
                    
                    trace = result.get("trace", {})
                    relation = trace.get("relation", "unknown")
                    node_id = trace.get("node_id")
                    
                    if page_idx not in debug_info["candidates_by_field_page"][field_name]:
                        debug_info["candidates_by_field_page"][field_name][page_idx] = []
                    
                    if node_id is not None:
                        debug_info["candidates_by_field_page"][field_name][page_idx].append({
                            "node_id": node_id,
                            "relation": relation,
                            "confidence": result.get("confidence", 0.0),
                        })
            
            output["debug"] = debug_info
        
        return output


def _load_memory_config() -> dict:
    """Load memory config from YAML, with fallback to defaults."""
    config_path = Path("configs/memory.yaml")
    defaults = {
        "enabled": False,
        "store_dir": "data/artifacts/pattern_memory",
        "learn": {
            "min_confidence": 0.85,
            "accept_relations": ["same_line_right_of", "same_table_row", "same_block"],
            "max_synonyms_per_field": 12,
            "max_offsets_per_field": 24,
            "max_layout_fingerprints": 24,
            "decay_factor": 0.98,
            "min_weight_to_keep": 0.15,
        },
        "use": {
            "synonyms_weight": 0.06,
            "offset_bonus": 0.07,
            "fingerprint_bonus": 0.05,
            "prefer_memory_over_embedding": True,
            "max_synonyms_injection": 6,
        },
        "fingerprint": {
            "grid_resolution": [4, 4],
            "label_context_chars": 40,
        },
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                config = defaults.copy()
                # Merge nested dicts
                for key in config:
                    if key in loaded:
                        if isinstance(config[key], dict) and isinstance(loaded[key], dict):
                            config[key].update(loaded[key])
                        else:
                            config[key] = loaded[key]
                return config
        except Exception:
            pass
    return defaults


def _load_embedding_config() -> dict:
    """Load embedding config from YAML, with fallback to defaults."""
    config_path = Path("configs/embedding.yaml")
    defaults = {
        "enabled": False,  # Default disabled to avoid regressions
        "provider": "hash",
        "model": "all-MiniLM-L6-v2",
        "dim": 384,
        "index": {
            "top_k_per_field": 4,
            "min_sim_threshold": 0.45,
            "max_blocks_considered": 2000,
        },
        "budget": {"max_calls_per_pdf": 100, "batch_size": 64},
        "cache": {"dir": ".cache/embeddings", "persist": True},
        "preproc": {
            "lowercase": True,
            "strip_accents": True,
            "collapse_spaces": True,
            "max_chars_per_block": 300,
            "drop_short_tokens_under": 2,
        },
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                config = defaults.copy()
                # Merge nested dicts
                for key in config:
                    if key in loaded:
                        if isinstance(config[key], dict) and isinstance(loaded[key], dict):
                            config[key].update(loaded[key])
                        else:
                            config[key] = loaded[key]
                return config
        except Exception:
            pass
    return defaults


def _load_llm_config() -> dict:
    """Load LLM config from YAML, with fallback to defaults."""
    config_path = Path("configs/llm.yaml")
    defaults = {
        "enabled": True,
        "budget": {"max_calls_per_pdf": 2, "max_tokens_per_call": 256},
        "timeout_seconds": 2.0,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "trigger": {"min_score": 0.50, "max_score": 0.80},
        "context": {
            "max_chars_candidate_text": 300,
            "neighbor_window": {"lines_above": 1, "lines_below": 1, "include_left_right": True},
        },
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                config = defaults.copy()
                # Merge nested dicts
                for key in config:
                    if key in loaded:
                        if isinstance(config[key], dict) and isinstance(loaded[key], dict):
                            config[key].update(loaded[key])
                        else:
                            config[key] = loaded[key]
                return config
        except Exception:
            pass
    return defaults


def _preprocess_block_text(text: str, config: dict) -> str:
    """Preprocess block text for embedding.

    Args:
        text: Block text.
        config: Preprocessing config.

    Returns:
        Preprocessed text.
    """
    # Normalize
    s = text
    if config.get("lowercase", True):
        s = s.lower()
    if config.get("strip_accents", True):
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    if config.get("collapse_spaces", True):
        s = re.sub(r"\s+", " ", s).strip()

    # Truncate
    max_chars = config.get("max_chars_per_block", 300)
    s = s[:max_chars]

    # Drop if too short
    min_tokens = config.get("drop_short_tokens_under", 2)
    tokens = s.split()
    if len(tokens) < min_tokens:
        return ""

    return s


def _build_semantic_seeds(
    doc: Document,
    blocks: List[Block],
    schema_fields: List[SchemaField],
    layout: LayoutGraph,
    config: dict,
) -> Dict[str, List[Tuple[int, float]]]:
    """Build semantic seeds for each field using embeddings.

    Args:
        doc: Document.
        blocks: List of blocks.
        schema_fields: List of schema fields.
        layout: Layout graph.
        config: Embedding config.

    Returns:
        Dictionary mapping field_name -> list of (block_id, cosine_score) tuples.
    """
    # Load embedding client
    provider = config.get("provider", "hash")
    model = config.get("model", "all-MiniLM-L6-v2")
    dim = config.get("dim", 384)

    try:
        embed_client = create_embedding_client(provider, model, dim)
    except Exception:
        # If embedding fails, return empty seeds (no regressions)
        return {}

    # Load policy
    policy = EmbeddingPolicy(
        top_k_per_field=config.get("index", {}).get("top_k_per_field", 4),
        min_sim_threshold=config.get("index", {}).get("min_sim_threshold", 0.45),
        max_blocks_considered=config.get("index", {}).get("max_blocks_considered", 2000),
        max_calls_per_pdf=config.get("budget", {}).get("max_calls_per_pdf", 100),
        batch_size=config.get("budget", {}).get("batch_size", 64),
    )

    # Cache setup
    cache_dir = config.get("cache", {}).get("dir", ".cache/embeddings")
    cache_enabled = config.get("cache", {}).get("persist", True)

    # Preprocess blocks
    preproc_config = config.get("preproc", {})
    block_texts: List[str] = []
    block_ids: List[int] = []
    for block in blocks:
        text = _preprocess_block_text(block.text, preproc_config)
        if text:  # Skip empty blocks
            block_texts.append(text)
            block_ids.append(block.id)

    # Limit blocks if too many
    if len(block_texts) > policy.max_blocks_considered:
        # Sample by keeping blocks with more text (prioritize informative blocks)
        block_with_text = [(len(t), bid) for t, bid in zip(block_texts, block_ids)]
        block_with_text.sort(reverse=True)
        selected = block_with_text[: policy.max_blocks_considered]
        block_ids = [bid for _, bid in selected]
        # Rebuild block_texts for selected IDs
        selected_block_ids_set = set(block_ids)
        block_texts = [t for t, bid in zip(block_texts, block_ids) if bid in selected_block_ids_set]
        block_ids = [bid for bid in block_ids if bid in selected_block_ids_set]

    if not block_texts:
        return {}

    # Index blocks (with cache)
    svd_cfg = config.get("index", {}).get("svd", {})
    index = CosineIndex(
        dim=embed_client.dim,
        svd_enabled=svd_cfg.get("enabled", False),
        svd_n_components=svd_cfg.get("n_components"),
        svd_min_size=svd_cfg.get("min_size", 100),
        svd_variance_threshold=svd_cfg.get("variance_threshold", 0.95),
    )
    block_embeddings = []

    # Process blocks in batches
    for batch_start in range(0, len(block_texts), policy.batch_size):
        batch_end = min(batch_start + policy.batch_size, len(block_texts))
        batch_texts = block_texts[batch_start:batch_end]
        batch_ids = block_ids[batch_start:batch_end]

        # Check cache for each block
        batch_embs = []
        needs_embed = []
        needs_embed_indices = []

        for i, (text, bid) in enumerate(zip(batch_texts, batch_ids)):
            cache_key = key_for_block(doc.id, bid, model)
            cached_vec = None
            if cache_enabled:
                cached_vec = load_vec(cache_dir, cache_key)

            if cached_vec is not None:
                vec = cached_vec
                batch_embs.append(vec)
            else:
                needs_embed.append(text)
                needs_embed_indices.append(i)
                batch_embs.append(None)

        # Embed missing ones
        if needs_embed:
            try:
                new_embs = embed_client.embed(needs_embed)
                policy.note_call(len(needs_embed))
                # Fill in batch_embs
                for idx, emb in zip(needs_embed_indices, new_embs):
                    vec = np.array(emb)
                    batch_embs[idx] = vec
                    # Save to cache
                    if cache_enabled:
                        bid = batch_ids[idx]
                        cache_key = key_for_block(doc.id, bid, model)
                        save_vec(cache_dir, cache_key, vec)
            except Exception:
                # If embedding fails, skip this batch
                continue

        # Add to index
        valid_embs = []
        valid_ids = []
        for bid, emb in zip(batch_ids, batch_embs):
            if emb is not None:
                valid_embs.append(emb)
                valid_ids.append(bid)

        if valid_embs:
            emb_matrix = np.vstack(valid_embs)
            index.add(valid_ids, emb_matrix)

    # Query per field
    semantic_seeds: Dict[str, List[Tuple[int, float]]] = {}

    # Get pattern memory if available (for value examples)
    pattern_memory = None
    memory_cfg = _load_memory_config()
    if memory_cfg.get("enabled", False):
        try:
            from ..memory.pattern_memory import PatternMemory
            from ..memory.store import MemoryStore
            # Get label from first field or use default
            label = schema_fields[0].name if schema_fields else "default"
            store = MemoryStore(memory_cfg.get("store_dir", "data/artifacts/pattern_memory"))
            pattern_memory = PatternMemory(label, memory_cfg, store)
        except Exception:
            pattern_memory = None
    
    for field in schema_fields:
        # Build query text
        query_parts = [field.name, field.description[:100]]  # Truncate description
        if field.synonyms:
            query_parts.extend(field.synonyms[:3])  # Top 3 synonyms
        
        # Add value examples from pattern memory if available
        if pattern_memory:
            value_examples = pattern_memory.get_value_examples(field.name, max_k=2)
            if value_examples:
                query_parts.extend([f"example: {ex}" for ex in value_examples])
        
        query_text = " ".join(query_parts)
        query_text = _preprocess_block_text(query_text, preproc_config)

        if not query_text:
            continue

        # Embed query (with cache)
        cache_key = key_for_query(field.name, query_text, model)
        query_vec = None
        if cache_enabled:
            cached_query = load_vec(cache_dir, cache_key)
            if cached_query is not None:
                query_vec = cached_query

        if query_vec is None:
            try:
                query_embs = embed_client.embed([query_text])
                query_vec = np.array(query_embs[0])
                policy.note_call(1)
                if cache_enabled:
                    save_vec(cache_dir, cache_key, query_vec)
            except Exception:
                continue
        else:
            query_vec = cached_query

        # Search
        top_ids, top_scores = index.search(query_vec.reshape(1, -1), top_k=policy.top_k_per_field)

        # Filter by threshold and build seeds
        seeds: List[Tuple[int, float]] = []
        for bid, score in zip(top_ids[0], top_scores[0]):
            if score >= policy.min_sim_threshold:
                seeds.append((int(bid), float(score)))

        if seeds:
            semantic_seeds[field.name] = seeds

    return semantic_seeds


def _build_semantic_seeds_per_page(
    doc: Document,
    blocks: List[Block],
    schema_fields: List[SchemaField],
    layout: LayoutGraph,
    config: dict,
    embed_client: Any,
    runtime_policy: RuntimePolicy,
) -> Tuple[Dict[str, List[Tuple[int, float]]], CosineIndex]:
    """Build semantic seeds for a single page and return index.

    Similar to _build_semantic_seeds but for per-page processing with eviction.
    """
    # Load policy
    policy = EmbeddingPolicy(
        top_k_per_field=config.get("index", {}).get("top_k_per_field", 4),
        min_sim_threshold=config.get("index", {}).get("min_sim_threshold", 0.45),
        max_blocks_considered=runtime_policy.max_blocks_indexed_per_page,
        max_calls_per_pdf=config.get("budget", {}).get("max_calls_per_pdf", 100),
        batch_size=config.get("budget", {}).get("batch_size", 64),
    )

    # Cache setup
    cache_dir = config.get("cache", {}).get("dir", ".cache/embeddings")
    cache_enabled = config.get("cache", {}).get("persist", True)
    model_name = config.get("model", "all-MiniLM-L6-v2")

    # Preprocess blocks
    preproc_config = config.get("preproc", {})
    block_texts: List[str] = []
    block_ids: List[int] = []
    for block in blocks:
        text = _preprocess_block_text(block.text, preproc_config)
        if text:
            block_texts.append(text)
            block_ids.append(block.id)

    if not block_texts:
        svd_cfg = config.get("index", {}).get("svd", {})
        return {}, CosineIndex(
            dim=embed_client.dim,
            svd_enabled=svd_cfg.get("enabled", False),
            svd_n_components=svd_cfg.get("n_components"),
            svd_min_size=svd_cfg.get("min_size", 100),
            svd_variance_threshold=svd_cfg.get("variance_threshold", 0.95),
        )

    # Index blocks (with cache)
    svd_cfg = config.get("index", {}).get("svd", {})
    index = CosineIndex(
        dim=embed_client.dim,
        svd_enabled=svd_cfg.get("enabled", False),
        svd_n_components=svd_cfg.get("n_components"),
        svd_min_size=svd_cfg.get("min_size", 100),
        svd_variance_threshold=svd_cfg.get("variance_threshold", 0.95),
    )

    # Process blocks in batches
    for batch_start in range(0, len(block_texts), policy.batch_size):
        batch_end = min(batch_start + policy.batch_size, len(block_texts))
        batch_texts = block_texts[batch_start:batch_end]
        batch_ids = block_ids[batch_start:batch_end]

        # Check cache
        batch_embs = []
        needs_embed = []
        needs_embed_indices = []

        for i, (text, bid) in enumerate(zip(batch_texts, batch_ids)):
            cache_key = key_for_block(doc.id, bid, model_name)
            cached_vec = None
            if cache_enabled:
                cached_vec = load_vec(cache_dir, cache_key)

            if cached_vec is not None:
                vec = cached_vec
                batch_embs.append(vec)
            else:
                needs_embed.append(text)
                needs_embed_indices.append(i)
                batch_embs.append(None)

        # Embed missing ones
        if needs_embed:
            try:
                new_embs = embed_client.embed(needs_embed)
                policy.note_call(len(needs_embed))
                for idx, emb in zip(needs_embed_indices, new_embs):
                    vec = np.array(emb)
                    batch_embs[idx] = vec
                    if cache_enabled:
                        bid = batch_ids[idx]
                        cache_key = key_for_block(doc.id, bid, model_name)
                        save_vec(cache_dir, cache_key, vec)
            except Exception:
                continue

        # Add to index
        valid_embs = []
        valid_ids = []
        for bid, emb in zip(batch_ids, batch_embs):
            if emb is not None:
                valid_embs.append(emb)
                valid_ids.append(bid)

        if valid_embs:
            emb_matrix = np.vstack(valid_embs)
            index.add(valid_ids, emb_matrix)

    # Query per field
    semantic_seeds: Dict[str, List[Tuple[int, float]]] = {}

    # Get pattern memory if available (for value examples)
    # Note: label is not available in this function, so we skip pattern memory here
    # Pattern memory requires label, which is only available at the Pipeline level
    
    for field in schema_fields:
        query_parts = [field.name, field.description[:100]]
        if field.synonyms:
            query_parts.extend(field.synonyms[:3])
        query_text = " ".join(query_parts)
        query_text = _preprocess_block_text(query_text, preproc_config)

        if not query_text:
            continue

        # Embed query
        cache_key = key_for_query(field.name, query_text, model_name)
        query_vec = None
        if cache_enabled:
            cached_query = load_vec(cache_dir, cache_key)
            if cached_query is not None:
                query_vec = cached_query

        if query_vec is None:
            try:
                query_embs = embed_client.embed([query_text])
                query_vec = np.array(query_embs[0])
                policy.note_call(1)
                if cache_enabled:
                    save_vec(cache_dir, cache_key, query_vec)
            except Exception:
                continue
        else:
            query_vec = cached_query

        # Search
        top_ids, top_scores = index.search(query_vec.reshape(1, -1), top_k=policy.top_k_per_field)

        # Filter by threshold
        seeds: List[Tuple[int, float]] = []
        for bid, score in zip(top_ids[0], top_scores[0]):
            if score >= policy.min_sim_threshold:
                seeds.append((int(bid), float(score)))

        if seeds:
            semantic_seeds[field.name] = seeds

    return semantic_seeds, index


def _fuse_page_results(
    page_results: Dict[int, Dict[str, Dict[str, Any]]], schema_fields: List[SchemaField]
) -> Dict[str, Dict[str, Any]]:
    """Fuse results across pages: prefer strong relations, then higher confidence.

    Args:
        page_results: Dictionary mapping page_index -> field_name -> result dict.
        schema_fields: List of schema fields.

    Returns:
        Fused results dictionary mapping field_name -> result dict.
    """
    # Relation priority: same_line_right_of > same_table_row > same_block > first_below > global_enum_scan
    relation_priority = {
        "same_line_right_of": 0,
        "same_table_row": 1,
        "same_block": 2,
        "first_below_same_column": 3,
        "global_enum_scan": 4,
    }

    final_results: Dict[str, Dict[str, Any]] = {}

    for field in schema_fields:
        candidates: List[tuple[int, Dict[str, Any]]] = []  # (priority, result)

        # Collect all page results for this field
        for page_index, page_field_results in page_results.items():
            result = page_field_results.get(field.name)
            if not result or result.get("value") is None:
                continue

            # Get relation from trace
            relation = result.get("trace", {}).get("relation", "unknown")
            priority = relation_priority.get(relation, 99)
            confidence = result.get("confidence", 0.0)

            candidates.append((priority, result))

        if not candidates:
            final_results[field.name] = {
                "value": None,
                "confidence": 0.0,
                "source": "none",
                "trace": {"reason": "no_evidence"},
            }
            continue

        # Sort by priority (lower = better), then confidence (higher = better)
        candidates.sort(key=lambda x: (x[0], -x[1].get("confidence", 0.0)))

        # Best result
        best_result = candidates[0][1]
        final_results[field.name] = best_result

    return final_results

