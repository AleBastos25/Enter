from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

# Embeddings removed - no longer used
from ..extraction.text_extractor import extract_from_candidate
from ..io.pdf_loader import extract_blocks, iter_page_blocks, load_document
from ..layout.builder import build_layout
from .policy import RuntimePolicy, load_runtime_config
from .doc_profile import build_doc_profile, DocProfile
from ..llm.client import create_client
from ..llm.policy import LLMPipelinePolicy
from ..llm.scorer import score_matrix
from ..llm.prompts import build_prompt, build_batch_prompt, parse_llm_response, parse_batch_response, build_retry_prompt, parse_retry_response
from ..matching.matcher import match_fields
from ..matching.candidates import build_candidate_sets, Candidate as CandidateV3
from ..matching.assign import solve_assignment
from ..tables.detector import detect_tables
from ..validation.validators import validate_and_normalize
from .models import Block, Document, LayoutGraph, SchemaField
from .schema import enrich_schema
from ..memory.pattern_registry import PatternRegistry


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
        
        # Limit blocks early for speed (máximo 2s por PDF)
        if len(blocks) > runtime_policy.max_blocks_per_page:
            blocks = blocks[:runtime_policy.max_blocks_per_page]

        # 2) Layout (blocks já limitados acima para garantir ≤2s)
        layout = build_layout(doc, blocks)
        
        # Check timeout after layout
        if not runtime_policy.doc_time_left():
            results = {}
            for field in schema_fields:
                results[field.name] = {
                    "value": None,
                    "confidence": 0.0,
                    "source": "timeout",
                    "trace": {"reason": "timeout", "page_index": 0, "notes": "Timeout after layout"},
                }
            return {"label": label, "results": results}

        # 2.5) Detect tables (limitado para garantir ≤2s)
        pdf_lines = getattr(layout, "pdf_lines", None)
        tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
        # Limitar número de tabelas para acelerar (máximo 10 tabelas por página)
        if len(tables) > 10:
            tables = tables[:10]
        # Attach tables to layout (via setattr since it's a frozen dataclass)
        object.__setattr__(layout, "tables", tables)
        
        # Check timeout after table detection
        if not runtime_policy.doc_time_left():
            results = {}
            for field in schema_fields:
                results[field.name] = {
                    "value": None,
                    "confidence": 0.0,
                    "source": "timeout",
                    "trace": {"reason": "timeout", "page_index": 0, "notes": "Timeout after table detection"},
                }
            return {"label": label, "results": results}

        # 2.6) Build DocProfile (v3)
        grid = getattr(layout, "grid", None)
        graph_v2 = getattr(layout, "graph_v2", None)
        profile = build_doc_profile(blocks, pdf_lines, graph_v2, grid)
        
        # Load runtime config for assignment constraints (early, before candidate sets)
        runtime_cfg_data = None
        try:
            runtime_cfg_path = Path("configs/runtime.yaml")
            if runtime_cfg_path.exists():
                with open(runtime_cfg_path, "r", encoding="utf-8") as f:
                    runtime_cfg_data = yaml.safe_load(f) or {}
        except Exception:
            runtime_cfg_data = {}

        # 3) Enrich schema: convert schema_dict -> ExtractionSchema
        enriched = enrich_schema(label, schema_dict)
        schema_fields = enriched.fields
        
        # Check timeout after schema enrichment
        if not runtime_policy.doc_time_left():
            results = {}
            for field in schema_fields:
                results[field.name] = {
                    "value": None,
                    "confidence": 0.0,
                    "source": "timeout",
                    "trace": {"reason": "timeout", "page_index": 0, "notes": "Timeout after schema enrichment"},
                }
            return {"label": label, "results": results}

        # 3.5) Load pattern memory and pattern registry (v3)
        memory_cfg = _load_memory_config()
        pattern_memory = None
        pattern_registry = None
        if memory_cfg.get("enabled", False):
            from ..memory.pattern_memory import PatternMemory
            from ..memory.store import MemoryStore

            store = MemoryStore(memory_cfg.get("store_dir", "data/artifacts/pattern_memory"))
            pattern_memory = PatternMemory(label, memory_cfg, store)
        
        # 2.7) Compute document temperature (for LLM budget control) - after pattern_memory is loaded
        from ..memory.temperature import compute_global_temperature
        document_temperature = compute_global_temperature(
            pattern_memory if memory_cfg.get("enabled", False) else None,
            label,
            schema_fields,
        )
        # LLM budget based on temperature: T >= 0.8: 0 calls, 0.4 <= T < 0.8: max 1, T < 0.4: max 3
        if document_temperature >= 0.8:
            llm_budget = 0
        elif document_temperature >= 0.4:
            llm_budget = 1
        else:
            llm_budget = 3
        
        # Load pattern registry (v3)
        if memory_cfg.get("patterns", {}).get("enabled", True):
            pattern_store_dir = Path(memory_cfg.get("patterns", {}).get("store_dir", "data/artifacts/pattern_registry"))
            pattern_registry = PatternRegistry(pattern_store_dir)

        # 4) Build candidate sets (v3: type-first)
        candidate_sets = build_candidate_sets(
            blocks,
            layout,
            schema_fields,
            profile,
            tables,
        )
        
        # Check timeout after candidate generation
        if not runtime_policy.doc_time_left():
            results = {}
            for field in schema_fields:
                results[field.name] = {
                    "value": None,
                    "confidence": 0.0,
                    "source": "timeout",
                    "trace": {"reason": "timeout", "page_index": 0, "notes": "Timeout after candidate generation"},
                }
            return {"label": label, "results": results}

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
                max_calls_per_pdf=llm_config.get("budget", {}).get("max_calls_per_pdf", 3),  # v3: 3 calls (scorer + retry)
                min_score=llm_config.get("trigger", {}).get("min_score", 0.50),
                max_score=llm_config.get("trigger", {}).get("max_score", 0.80),
            )
        
        # 4.6) LLM Scorer (v3) - if multiple candidates or conflicts
        use_scorer = False
        has_any_candidates = False
        for field_name, candidates in candidate_sets.items():
            if len(candidates) > 0:
                has_any_candidates = True
            if len(candidates) > 1:
                use_scorer = True
                break
        
        score_matrix_result = {}
        assignment_result = None
        
        # If we have candidates, try assignment (even with single candidates)
        if has_any_candidates:
            # Build default score matrix if no LLM scorer
            if not (use_scorer and llm_client):
                # Build dummy score matrix (all 0.7 for first candidate, 0.5 for others)
                score_matrix_result = {}
                for field_name, candidates in candidate_sets.items():
                    score_matrix_result[field_name] = {}
                    for i, cand in enumerate(candidates):
                        score = 0.7 if i == 0 else 0.5
                        score_matrix_result[field_name][cand.candidate_id] = score
            elif use_scorer and llm_client:
                scorer_config = llm_config.get("scorer", {})
                if scorer_config.get("enabled", True):
                    score_matrix_result = score_matrix(
                        schema_fields,
                        candidate_sets,
                        profile,
                        llm_client,
                        timeout_seconds=scorer_config.get("timeout_seconds", 2.0),
                    )
            
            # Solve assignment with score matrix
            if score_matrix_result:
                assignment_config = runtime_cfg_data.get("assignment", {}) if runtime_cfg_data else {}
                assignment_result = solve_assignment(
                    score_matrix_result,
                    candidate_sets,
                    schema_fields,
                    profile,
                    constraints=assignment_config,
                )
        
        # Compute document temperature (for LLM call limits)
        from ..memory.temperature import compute_global_temperature
        doc_temperature = compute_global_temperature(
            pattern_memory if memory_cfg.get("enabled", False) else None,
            label,
            schema_fields,
        )
        
        # Fallback to legacy matching if no candidates or assignment failed
        if not assignment_result or not has_any_candidates:
            # Use legacy matching as fallback (with new Pareto + tie-breakers + LLM chooser)
            cands_map = match_fields(
                schema_fields,
                layout,
                validate=None,
                top_k=runtime_policy.max_candidates_per_field_page,
                semantic_seeds={},
                pattern_memory=pattern_memory,
                memory_cfg=memory_cfg if memory_cfg.get("enabled", False) else None,
                temperature=doc_temperature,
                document_label=label,
                llm_client=llm_client if llm_budget > 0 else None,
            )
            # Convert to assignment format - handle both Candidate and dict types
            picks_dict = {}
            # Also need to convert dict candidates to CandidateV3 format and add to candidate_sets
            for field in schema_fields:
                field_cands = cands_map.get(field.name, [])
                if field_cands and len(field_cands) > 0:
                    first_cand = field_cands[0]
                    if isinstance(first_cand, CandidateV3):
                        picks_dict[field.name] = first_cand.candidate_id
                    elif isinstance(first_cand, dict):
                        # Convert dict candidate to CandidateV3 and add to candidate_sets
                        block_id = first_cand.get("block_id")
                        relation = first_cand.get("relation", "unknown")
                        text_window = first_cand.get("text_window", "")
                        label_block_id = first_cand.get("label_block_id")
                        
                        # Create candidate_id from relation and block_id
                        cand_id = f"fallback_{field.name}_{block_id}_{relation}"
                        
                        # Create CandidateV3
                        from ..core.models import Block
                        block = next((b for b in layout.blocks if b.id == block_id), None)
                        if block:
                            cand_v3 = CandidateV3(
                                candidate_id=cand_id,
                                block_id=block_id,
                                relation=relation,
                                snippet=text_window[:100],
                                region_text=text_window,
                                label_block_id=label_block_id,
                                features=type('Features', (), {
                                    'in_table': False,
                                    'in_repeated_footer': False,
                                    'font_size': block.font_size or 0,
                                    'is_bold': False,
                                })(),
                            )
                            # Add to candidate_sets and candidate_by_id
                            if field.name not in candidate_sets:
                                candidate_sets[field.name] = []
                            candidate_sets[field.name].append(cand_v3)
                            candidate_by_id[cand_id] = cand_v3
                            picks_dict[field.name] = cand_id
                        else:
                            picks_dict[field.name] = None
                    else:
                        picks_dict[field.name] = None
                else:
                    picks_dict[field.name] = None
            
            assignment_result = type('AssignmentResult', (), {
                'picks': picks_dict,
                'scores': {field.name: 0.7 for field in schema_fields},
                'dropped_conflicts': [],
            })()

        # 5) Extract values from assignment picks (v3)
        results: Dict[str, Dict[str, Any]] = {}
        
        # Build candidate lookup by ID
        candidate_by_id: Dict[str, CandidateV3] = {}
        for field_name, candidates in candidate_sets.items():
            for cand in candidates:
                candidate_by_id[cand.candidate_id] = cand
        
        assignment_config = runtime_cfg_data.get("assignment", {}) if runtime_cfg_data else {}
        
        for field in schema_fields:
            # Check timeout before processing each field
            if not runtime_policy.doc_time_left():
                results[field.name] = {
                    "value": None,
                    "confidence": 0.0,
                    "source": "timeout",
                    "trace": {"reason": "timeout", "page_index": 0, "notes": "Processing timeout reached"},
                }
                continue

            # Get picked candidate from assignment (v3)
            picked_cand_id = assignment_result.picks.get(field.name) if assignment_result else None
            
            value = None
            confidence = 0.0
            source = "none"
            trace: Dict[str, Any] = {
                "reason": "no_evidence",
                "page_index": 0,
                "notes": "No evidence found for this field",
            }

            # Extract from picked candidate (v3)
            if picked_cand_id and picked_cand_id in candidate_by_id:
                cand = candidate_by_id[picked_cand_id]
                
                # Get block for text extraction
                block = next((b for b in blocks if b.id == cand.block_id), None)
                if not block:
                    continue
                
                # For same_block relations, use ROI extraction; otherwise use block text
                if cand.relation == "same_block" and cand.label_block_id:
                    # Extract ROI properly for same_block
                    from ..extraction.text_extractor import _extract_text_window
                    grid = getattr(layout, "grid", None)
                    graph_v2 = getattr(layout, "graph_v2", None)
                    text_window, roi_info = _extract_text_window(
                        "same_block",
                        cand.label_block_id,
                        cand.block_id,
                        layout,
                        grid,
                        graph_v2,
                        field,
                    )
                    # If ROI extraction failed or returned empty, fallback to block text
                    if not text_window or not text_window.strip():
                        text_window = block.text or ""
                else:
                    # For other relations, use block text directly (more reliable than snippet/region_text)
                    text_window = block.text or ""
                
                # Convert Candidate to dict format for extract_from_candidate
                cand_dict = {
                    "block_id": cand.block_id,
                    "relation": cand.relation,
                    "label_block_id": cand.label_block_id,
                    "text_window": text_window,
                    "score_tuple": (1, 0, 1, 0.8, 0.8, 0, 0, 1),  # Dummy score_tuple
                }
                
                value_candidate, conf_candidate, trace_candidate = extract_from_candidate(
                    field, cand_dict, layout
                )
                
                if value_candidate is not None:
                    value = value_candidate
                    confidence = assignment_result.scores.get(field.name, conf_candidate) if assignment_result else conf_candidate
                    source = "table" if cand.features.in_table else "heuristic"
                    trace = {**trace_candidate, "page_index": 0, "candidate_id": picked_cand_id, "assignment_score": confidence}
                    
                    # Attach proof from candidate if available
                    if hasattr(cand, "proof") or (isinstance(cand, dict) and "proof" in cand):
                        proof = cand.proof if hasattr(cand, "proof") else cand.get("proof")
                        if proof:
                            trace["proof"] = proof
                    
                    # Learn pattern (v3)
                    if pattern_registry and confidence >= 0.85:
                        pattern_registry.learn_patterns(label, field.name, value)
                    
                    # Try second best if normalization fails (v3)
                    if not value_candidate or value_candidate == "":
                        candidates_list = candidate_sets.get(field.name, [])
                        if len(candidates_list) > 1:
                            second_cand = candidates_list[1]
                            second_cand_dict = {
                                "block_id": second_cand.block_id,
                                "relation": second_cand.relation,
                                "label_block_id": second_cand.label_block_id,
                                "text_window": second_cand.block.text if second_cand.block else "",
                                "score_tuple": (1, 0, 1, 0.8, 0.8, 0, 0, 1),
                            }
                            value_second, conf_second, trace_second = extract_from_candidate(
                                field, second_cand_dict, layout
                            )
                            if value_second and value_second != "":
                                value = value_second
                                confidence = conf_second
                                trace = {**trace_second, "page_index": 0, "candidate_id": candidates_list[1].candidate_id, "source": "second_best"}
            elif not picked_cand_id or (picked_cand_id and picked_cand_id not in candidate_by_id):
                # Assignment didn't pick a candidate, try fallback to match_fields
                if not hasattr(self, '_fallback_cands_map'):
                    # Build fallback candidates using match_fields only once
                    from ..matching.matcher import match_fields
                    self._fallback_cands_map = match_fields(
                        schema_fields,
                        layout,
                        validate=None,
                        top_k=runtime_policy.max_candidates_per_field_page,
                        semantic_seeds={},
                        pattern_memory=pattern_memory,
                        memory_cfg=memory_cfg if memory_cfg.get("enabled", False) else None,
                        temperature=doc_temperature,
                        document_label=label,
                        llm_client=llm_client if llm_budget > 0 else None,
                    )
                
                # Try to extract from fallback candidates
                fallback_candidates = self._fallback_cands_map.get(field.name, [])
                if fallback_candidates:
                    # Use first candidate from fallback
                    fallback_cand = fallback_candidates[0]
                    if isinstance(fallback_cand, dict):
                        value_candidate, conf_candidate, trace_candidate = extract_from_candidate(
                            field, fallback_cand, layout
                        )
                        if value_candidate is not None:
                            value = value_candidate
                            confidence = conf_candidate
                            source = "heuristic"
                            trace = {**trace_candidate, "page_index": 0, "source": "fallback_match_fields"}
            
            # Store result
            results[field.name] = {
                "value": value,
                "confidence": confidence,
                "source": source,
                "trace": trace,
            }
            
            # LLM Retry (v3) - if value is None or confidence low
            if (value is None or confidence < 0.60) and llm_client and llm_policy:
                retry_config = llm_config.get("retry", {})
                if retry_config.get("enabled", True):
                    retry_fields = retry_config.get("only_for_fields", ["date", "money", "enum", "alphanum_code", "text"])
                    if field.type in retry_fields or not retry_fields:
                        candidates_list = candidate_sets.get(field.name, [])
                        if candidates_list:
                            retry_prompt = build_retry_prompt(
                                {"name": field.name, "type": field.type, "description": field.description},
                                candidates_list[:5],
                            )
                            try:
                                retry_timeout = retry_config.get("timeout_seconds", 2.0)
                                if runtime_policy.llm_time_left():
                                    retry_response = llm_client.generate(retry_prompt, max_tokens=256, timeout=retry_timeout)
                                    retry_result = parse_retry_response(retry_response)
                                    if retry_result.get("chosen_id") and retry_result.get("value_raw"):
                                        # Validate retry value
                                        ok, normalized = validate_and_normalize(
                                            field.type or "text",
                                            retry_result["value_raw"],
                                            enum_options=field.meta.get("enum_options") if field.meta else None,
                                        )
                                        if ok and normalized:
                                            value = normalized
                                            confidence = 0.75
                                            source = "llm"
                                            trace = {"reason": "llm_retry", "page_index": 0, "chosen_id": retry_result["chosen_id"]}
                            except Exception:
                                pass  # LLM retry failed, keep original value
            
            # Fallback: try legacy matching if no assignment result
            if value is None and not assignment_result:
                candidates_legacy = match_fields(
                    [field],
                    layout,
                    validate=None,
                    top_k=1,
                    semantic_seeds={},
                    pattern_memory=pattern_memory,
                    memory_cfg=memory_cfg if memory_cfg.get("enabled", False) else None,
                ).get(field.name, [])
                
                if candidates_legacy:
                    cand_legacy = candidates_legacy[0]
                    value_legacy, conf_legacy, trace_legacy = extract_from_candidate(
                        field, cand_legacy, layout
                    )
                    if value_legacy:
                        value = value_legacy
                        confidence = conf_legacy
                        source = "heuristic"
                        trace = {**trace_legacy, "page_index": 0}

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
                            "candidate_id": cand.candidate_id,
                            "block_id": cand.block_id,
                            "relation": cand.relation,
                            "pattern_type": cand.pattern_type,
                        }
                        for cand in candidate_sets.get(field.name, [])[:5]  # Top 5
                    ]
                    for field in schema_fields
                },
                "assignment": {
                    field.name: {
                        "picked_id": assignment_result.picks.get(field.name) if assignment_result else None,
                        "score": assignment_result.scores.get(field.name, 0.0) if assignment_result else 0.0,
                    }
                    for field in schema_fields
                } if assignment_result else {},
                # Embeddings removed - semantic_seeds no longer used
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

        # Embeddings removed - no longer used

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

            # Embeddings removed - semantic_seeds no longer used
            semantic_seeds: Dict[str, List[Tuple[int, float]]] = {}
            
            # Page signals removed - embeddings no longer used
            page_signals: Dict[str, float] = {}
            if debug:
                page_signals_by_page[page_index] = page_signals

            # Skip page logic removed - embeddings no longer used

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
                    # v2: Get block_id and relation (works for both Candidate and FieldCandidate)
                    block_id = cand.get("block_id") if isinstance(cand, dict) else cand.node_id
                    relation = cand.get("relation") if isinstance(cand, dict) else cand.relation
                    
                    if block_id in used_blocks:
                        used_field, used_value = used_blocks[block_id]
                        if used_field != field.name and used_value == value:
                            continue

                    value_candidate, conf_candidate, trace_candidate = extract_from_candidate(
                        field, cand, layout
                    )
                    if value_candidate is not None:
                        value = value_candidate
                        confidence = conf_candidate
                        source = "table" if relation in ("same_table_row", "table_row") else "heuristic"
                        # trace_candidate already has page_index from extract_from_candidate, but ensure it matches this page
                        trace = {**trace_candidate, "page_index": page_index}
                        trace["relation"] = relation  # Ensure relation is in trace
                        used_blocks[block_id] = (field.name, value_candidate)

                        # Learn (pattern memory)
                        if pattern_memory and memory_cfg.get("enabled", False):
                            learn_cfg = memory_cfg.get("learn", {})
                            min_confidence = learn_cfg.get("min_confidence", 0.85)
                            accept_relations = learn_cfg.get("accept_relations", [])
                            if confidence >= min_confidence and relation in accept_relations:
                                label_block_id = cand.get("label_block_id") if isinstance(cand, dict) else cand.source_label_block_id
                                label_block = next(
                                    (b for b in layout.blocks if b.id == label_block_id), None
                                ) if label_block_id else None
                                value_block = next((b for b in layout.blocks if b.id == block_id), None)
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
                                        relation,
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
            # Embeddings removed
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
    """Preprocess block text (legacy function, embeddings removed).

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


# Embeddings removed - _build_semantic_seeds no longer used


# Embeddings removed - _build_semantic_seeds_per_page no longer used


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

