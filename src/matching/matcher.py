"""Matcher for finding field candidates from label blocks using spatial neighborhood."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Optional, Tuple

from ..core.models import Block, Candidate, FieldCandidate, GraphV2, Grid, LayoutGraph, SchemaField
from ..tables.extractor import find_cell_by_label, find_table_for_block
from ..validation.patterns import type_gate_generic
from ..validation.shape import damerau_levenshtein_shape, to_shape
from ..validation.validators import validate_soft
from ..extraction.text_extractor import _build_roi_multiline, _decide_keep_label
from .pareto import compute_pareto_criteria, pareto_filter
from .tie_breakers import apply_tie_breakers


def _normalize_text(s: str) -> str:
    """Normalize text: lowercase, remove accents, normalize spaces.

    Args:
        s: Input string.

    Returns:
        Normalized string.
    """
    # Remove accents
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Lowercase
    s = s.lower()
    # Normalize spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein distance between two strings (generic, no language assumptions).

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Edit distance.
    """
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _label_score(a: str, b: str, min_threshold: float = 0.6) -> float:
    """Compute label matching score using Jaccard (token overlap) and Levenshtein similarity (generic).

    Args:
        a: First string (normalized).
        b: Second string (normalized).
        min_threshold: Minimum score to consider a match (default 0.6).

    Returns:
        Score between 0.0 and 1.0. Returns 0.0 if below threshold.
    """
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)
    
    # Jaccard: token overlap
    tok_a = set(a_norm.split())
    tok_b = set(b_norm.split())
    if tok_a or tok_b:
        jaccard = len(tok_a & tok_b) / max(1, len(tok_a | tok_b))
    else:
        jaccard = 0.0
    
    # Levenshtein similarity
    max_len = max(len(a_norm), len(b_norm))
    if max_len == 0:
        lev_sim = 1.0
    else:
        lev_dist = _levenshtein_distance(a_norm, b_norm)
        lev_sim = 1.0 - (lev_dist / max_len)
    
    # Return max of both (best match)
    score = max(jaccard, lev_sim)
    
    # Return 0 if below threshold
    if score < min_threshold:
        return 0.0
    
    return score


def _contains_any(haystack: str, needles: list[str]) -> bool:
    """Check if haystack contains any of the needles (case-insensitive, normalized).

    Args:
        haystack: Text to search in.
        needles: List of strings to search for.

    Returns:
        True if any needle is found in haystack.
    """
    haystack_norm = _normalize_text(haystack)
    for needle in needles:
        if _normalize_text(needle) in haystack_norm:
            return True
    return False


def _first_line(s: str) -> str:
    """Extract first line from text.

    Args:
        s: Multi-line text.

    Returns:
        First line, stripped.
    """
    return s.splitlines()[0].strip() if s else ""


def _extract_text_window(
    relation: str,
    block_id: int,
    label_block_id: Optional[int],
    layout: LayoutGraph,
    grid: Optional[Grid],
    graph_v2: Optional[GraphV2],
    field: Optional[SchemaField] = None,
) -> tuple[str, dict[str, Any]]:
    """Extract text_window for a candidate based on relation (v2).

    Args:
        relation: Relation type (same_block, same_line, south_of, table_row, semantic).
        block_id: Destination block ID.
        label_block_id: Optional label block ID.
        layout: LayoutGraph with blocks.
        grid: Optional Grid structure (v2).
        graph_v2: Optional GraphV2 structure (v2).
        field: Optional SchemaField for keep_label decision.

    Returns:
        Tuple of (text_window, roi_info).
    """
    block = next((b for b in layout.blocks if b.id == block_id), None)
    if not block:
        return ("", {"error": "block_not_found"})

    label_block = None
    if label_block_id:
        label_block = next((b for b in layout.blocks if b.id == label_block_id), None)

    roi_info: dict[str, Any] = {
        "relation": relation,
        "block_id": block_id,
        "label_block_id": label_block_id,
    }

    # same_block: use ROI multiline + keep_label (v2)
    if relation == "same_block" and label_block and grid:
        # Build ROI multiline
        text_window = _build_roi_multiline(label_block, grid, layout.blocks)
        roi_info["roi_method"] = "multiline"
        
        # Decide keep_label if field provided
        if field:
            label_text = label_block.text or ""
            final_value, keep_label = _decide_keep_label(field, label_text, text_window, graph_v2)
            roi_info["keep_label"] = keep_label
            # If final_value is empty (label-only detected), return empty to signal rejection
            if not final_value or not final_value.strip():
                return ("", roi_info)  # Empty text_window signals label-only rejection
            return (final_value, roi_info)
        return (text_window, roi_info)
    
    # same_block (fallback): extract from block text
    elif relation == "same_block":
        block_text = block.text or ""
        roi_info["roi_method"] = "block_text"
        return (block_text, roi_info)
    
    # same_line: extract first line
    elif relation in ("same_line", "same_line_right_of"):
        text_window = _first_line(block.text or "")
        roi_info["roi_method"] = "first_line"
        return (text_window, roi_info)
    
    # south_of / first_below_same_column: extract first line or full block
    elif relation in ("south_of", "first_below_same_column"):
        # For multi-line blocks, try to match with label line
        if label_block and label_block.id != block.id:
            label_lines = [ln.strip() for ln in (label_block.text or "").splitlines() if ln.strip()]
            dst_lines = [ln.strip() for ln in (block.text or "").splitlines() if ln.strip()]
            
            # If both have multiple lines, try to match by position
            if len(label_lines) > 1 and len(dst_lines) > 1:
                # Use first line as default
                text_window = dst_lines[0] if dst_lines else ""
            else:
                text_window = _first_line(block.text or "")
        else:
            text_window = _first_line(block.text or "")
        
        roi_info["roi_method"] = "first_line_or_matched"
        return (text_window, roi_info)
    
    # table_row: extract cell text
    elif relation in ("table_row", "same_table_row"):
        # Extract from block text (cell content)
        text_window = block.text or ""
        roi_info["roi_method"] = "table_cell"
        return (text_window, roi_info)
    
    # semantic: extract first line
    elif relation == "semantic" or relation == "semantic_direct":
        text_window = _first_line(block.text or "")
        roi_info["roi_method"] = "first_line"
        return (text_window, roi_info)
    
    # Default: extract first line
    text_window = _first_line(block.text or "")
    roi_info["roi_method"] = "first_line_default"
    return (text_window, roi_info)


# Removed field-specific validations (_is_valid_name_candidate, _is_valid_inscricao_candidate)
# The system now relies on semantic embeddings and LLM for generic matching
# instead of hardcoded rules for specific field types.


def _split_by_label(text: str, synonyms: list[str]) -> Optional[str]:
    """Split text by label and return the part after the label.

    Args:
        text: Block text.
        synonyms: List of synonyms to search for.

    Returns:
        Text after the first found synonym, or None if not found.
    """
    if not text:
        return None

    t_norm = _normalize_text(text)

    # Sort synonyms by length (longest first) to match more specific ones first
    sorted_syns = sorted(synonyms, key=len, reverse=True)

    for syn in sorted_syns:
        if not syn or not syn.strip():
            continue
        s_norm = _normalize_text(syn.strip())
        idx = t_norm.find(s_norm)
        if idx >= 0:
            syn_original = syn.strip()
            idx_orig = text.lower().find(syn_original.lower())
            if idx_orig >= 0:
                after = text[idx_orig + len(syn_original):].lstrip(" :\u200b\t")
                if after:
                    return after
    return None


def _build_synonyms(field: SchemaField) -> list[str]:
    """Build synonym list for a field (use provided or generate defaults).

    Args:
        field: SchemaField with optional synonyms.

    Returns:
        List of normalized synonym strings.
    """
    if field.synonyms:
        return [s.lower().strip() for s in field.synonyms if s.strip()]

    # Generate defaults
    synonyms = [field.name.lower()]

    # Add variations
    name_norm = _normalize_text(field.name)
    synonyms.append(name_norm)

    # Add common variations for registration/ID fields
    if "inscri" in name_norm or "registro" in name_norm:
        synonyms.extend(["inscricao", "inscrição", "nº oab", "n.oab", "numero oab", "registro"])
    if "seccional" in name_norm:
        synonyms.extend(["seccional", "uf", "conselho"])
    if "nome" in name_norm:
        synonyms.extend(["nome", "name"])

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for syn in synonyms:
        syn_norm = _normalize_text(syn)
        if syn_norm not in seen:
            seen.add(syn_norm)
            unique.append(syn_norm)

    return unique


def _find_label_blocks(blocks: list[Block], synonyms: list[str], min_match: float = 0.6) -> list[int]:
    """Find block IDs that contain any of the synonyms using lightweight label matching (Jaccard/Levenshtein).

    Args:
        blocks: List of blocks to search.
        synonyms: List of normalized synonym strings.
        min_match: Minimum label score threshold (default 0.6).

    Returns:
        List of block IDs that match, prioritized by:
        - Label score (Jaccard/Levenshtein)
        - Shorter text (more likely to be a label)
        - Larger font size (if available)
    """
    candidates = []

    for block in blocks:
        block_text = block.text or ""
        if not block_text:
            continue
        
        best_score = 0.0
        
        # Try each synonym and keep the best match
        for syn in synonyms:
            if not syn or not syn.strip():
                continue
            
            score = _label_score(block_text, syn.strip(), min_threshold=min_match)
            if score > best_score:
                best_score = score
        
        if best_score > 0.0:
            # Compute priority score (higher = better)
            # Start with label matching score
            priority = best_score
            
            # Boost for shorter blocks (likely labels)
            text_len = len(block_text)
            priority *= (1.0 / (1.0 + text_len * 0.01))
            
            # Boost if larger font
            if block.font_size:
                priority += block.font_size * 0.01
            
            # Penalize blocks with many lines (likely not labels)
            line_count = len([l for l in block_text.splitlines() if l.strip()])
            if line_count > 3:
                priority *= 0.5  # Reduce priority for multi-line blocks
            
            candidates.append((block.id, priority))

    # Sort by priority (descending) and return IDs
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [bid for bid, _ in candidates]


def _dedupe_candidates(candidates: list) -> list:
    """Remove duplicate candidates by block_id, keeping the one with highest score_tuple.
    
    DEPRECATED: This function is no longer used in v2 (deduplication handled by score_tuple sorting).
    Kept for backward compatibility with legacy code.

    Args:
        candidates: List of Candidate or FieldCandidate objects.

    Returns:
        Deduplicated list.
    """
    by_node: dict[int, Any] = {}
    for cand in candidates:
        # Get block_id (works for both Candidate and FieldCandidate)
        block_id = cand.get("block_id") if isinstance(cand, dict) else cand.node_id
        
        if block_id not in by_node:
            by_node[block_id] = cand
        else:
            # Keep the one with higher score
            if isinstance(cand, dict) and "score_tuple" in cand:
                # Candidate v2: compare score_tuples lexicographically
                existing = by_node[block_id]
                if isinstance(existing, dict) and "score_tuple" in existing:
                    if cand["score_tuple"] > existing["score_tuple"]:
                        by_node[block_id] = cand
            else:
                # FieldCandidate legacy: compare scores
                existing_score = sum(by_node[block_id].scores.values())
                new_score = sum(cand.scores.values())
                if new_score > existing_score:
                    by_node[block_id] = cand
    return list(by_node.values())


def _load_matching_config() -> dict:
    """Load matching config from YAML files, with fallback to defaults."""
    from pathlib import Path
    import yaml

    # Load from layout.yaml (column/section bonuses)
    config_path = Path("configs/layout.yaml")
    defaults = {
        "prefer_same_column_bonus": 0.08,
        "prefer_same_section_bonus": 0.05,
        "prefer_same_paragraph_bonus": 0.03,
        "cross_column_penalty": 0.06,
        "cross_section_penalty": 0.04,
        "relation_weight_same_table_row": 0.85,  # From tables.yaml
        "prefer_same_row_bonus": 0.12,
        "prefer_same_col_bonus": 0.06,
        "cross_row_penalty": 0.06,
        "cross_col_penalty": 0.04,
        "use_assignment": False,
        "assignment": {
            "alpha": 0.7,
            "beta": 0.3,
            "topk": 6,
            "null_score": 0.35,
            "use_sinkhorn": True,
            "reg": 0.05,
        },
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                matching_cfg = loaded.get("matching", {})
                if matching_cfg:
                    defaults.update(matching_cfg)
        except Exception:
            pass

    # Also load from tables.yaml (table-specific rankings)
    tables_config_path = Path("configs/tables.yaml")
    if tables_config_path.exists():
        try:
            with open(tables_config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                rank_cfg = loaded.get("rank", {})
                if rank_cfg:
                    defaults.update(rank_cfg)
        except Exception:
            pass

    return defaults


def match_fields(
    schema_fields: list[SchemaField],
    layout: LayoutGraph,
    *,
    validate: Optional[Callable[[SchemaField, str], bool]] = None,
    top_k: int = 2,
    semantic_seeds: Optional[dict[str, list[tuple[int, float]]]] = None,  # Deprecated - embeddings removed
    pattern_memory: Optional[Any] = None,  # PatternMemory (avoid circular import)
    memory_cfg: Optional[dict] = None,
    use_assignment: bool = False,
    llm_client: Optional[Any] = None,  # LLMClient (avoid circular import)
    document_label: str = "unknown",
    temperature: float = 0.0,
) -> dict[str, list[Candidate]]:
    """Match fields to value candidates using spatial neighborhood and semantic seeds (v2).

    Returns Candidate objects with text_window already extracted and score_tuple calculated.

    Args:
        schema_fields: List of SchemaField objects with synonyms.
        layout: LayoutGraph with blocks and neighborhood index.
        validate: Optional function to soft-validate field type (returns bool).
        top_k: Maximum number of candidates per field.
        semantic_seeds: Deprecated - embeddings removed, always empty.
        pattern_memory: Optional PatternMemory instance.
        memory_cfg: Optional memory config dict.
        use_assignment: If True, use global assignment layer (optimal transport).

    Returns:
        Dictionary mapping field_name -> list[Candidate] (sorted by score_tuple lexicographically).
    """
    # Check if assignment layer is enabled via config
    matching_cfg = _load_matching_config()
    use_assignment = use_assignment or matching_cfg.get("use_assignment", False)

    # If assignment layer is enabled, use global assignment
    if use_assignment:
        try:
            from .assignment import global_assignment

            assignment_cfg = matching_cfg.get("assignment", {})
            return global_assignment(
                schema_fields,
                layout.blocks,
                layout,
                semantic_seeds=None,  # Embeddings removed
                matching_cfg=matching_cfg,
                method="sinkhorn" if assignment_cfg.get("use_sinkhorn", True) else "hungarian",
                alpha=assignment_cfg.get("alpha", 0.7),
                beta=assignment_cfg.get("beta", 0.3),
                top_k=assignment_cfg.get("topk", 6),
                null_threshold=assignment_cfg.get("null_score", 0.35),
            )
        except Exception as e:
            # Fallback to traditional matching if assignment fails
            import logging
            logging.warning(f"Assignment layer failed, falling back to traditional matching: {e}")
            pass  # Continue to traditional matching

    # v2: Get Grid and GraphV2 if available
    grid = getattr(layout, "grid", None)
    graph_v2 = getattr(layout, "graph_v2", None)
    
    # Classic matching (original implementation)
    # Get neighborhood index
    neighborhood = getattr(layout, "neighborhood", {})
    block_by_id = {b.id: b for b in layout.blocks}

    results: dict[str, list[Candidate]] = {}
    # Embeddings removed - semantic_seeds no longer used
    semantic_seeds = {}
    
    # v2: Runtime limits (agressivos para garantir ≤2s por PDF)
    MAX_BLOCKS_PER_FIELD = 12  # Reduzido de 15 para garantir ≤2s (máximo 2s por PDF)

    for field in schema_fields:
        candidates: list[Candidate] = []
        blocks_inspected = 0  # v2: limit blocks per field
        early_stopped = False  # v2: early-stop flag

        # 1) Build synonyms (expand with learned synonyms from memory)
        synonyms = _build_synonyms(field)

        # Inject learned synonyms from memory
        if pattern_memory and memory_cfg:
            max_inject = memory_cfg.get("use", {}).get("max_synonyms_injection", 6)
            learned_synonyms = pattern_memory.get_synonyms(field.name, max_k=max_inject)
            for learned in learned_synonyms:
                if learned not in synonyms:
                    synonyms.append(learned)

        # 2) Find label blocks (classic + semantic seeds)
        label_block_ids = _find_label_blocks(layout.blocks, synonyms)
        
        # Removed special handling for "cidade" field - rely on semantic embeddings instead

        # 2.0.5) If no label blocks found and field has position hint, use position-based matching (v2: Candidate)
        # This is a fallback when semantic embeddings don't find matches
        if not label_block_ids and field.meta and field.meta.get("position_hint"):
            if early_stopped:
                pass  # Skip if already early-stopped
            else:
                position_hint = field.meta.get("position_hint")
                # Find blocks in the hinted quadrant
                candidates_by_position = []
                for block in layout.blocks:
                    bbox = block.bbox
                    center_x = (bbox[0] + bbox[2]) / 2.0
                    center_y = (bbox[1] + bbox[3]) / 2.0
                    
                    is_left = center_x < 0.5
                    is_top = center_y < 0.5
                    
                    matches_hint = False
                    if position_hint == "top-left" and is_left and is_top:
                        matches_hint = True
                    elif position_hint == "top-right" and not is_left and is_top:
                        matches_hint = True
                    elif position_hint == "bottom-left" and is_left and not is_top:
                        matches_hint = True
                    elif position_hint == "bottom-right" and not is_left and not is_top:
                        matches_hint = True
                    
                    if matches_hint:
                        # Score by proximity to corner (closer = better)
                        if position_hint == "top-left":
                            dist = center_x + center_y
                        elif position_hint == "top-right":
                            dist = (1.0 - center_x) + center_y
                        elif position_hint == "bottom-left":
                            dist = center_x + (1.0 - center_y)
                        else:  # bottom-right
                            dist = (1.0 - center_x) + (1.0 - center_y)
                        candidates_by_position.append((block.id, dist))
                
                # Sort by distance (closer = better) and take top 5
                candidates_by_position.sort(key=lambda x: x[1])
                position_block_ids = [bid for bid, _ in candidates_by_position[:5]]
                
                # Generate candidates directly from position-based blocks (v2: Candidate)
                for pos_block_id in position_block_ids:
                    if early_stopped or blocks_inspected >= MAX_BLOCKS_PER_FIELD:
                        break
                    if pos_block_id not in block_by_id:
                        continue
                    
                    blocks_inspected += 1
                    
                    # Extract text_window
                    text_window, roi_info = _extract_text_window(
                        "same_block",
                        pos_block_id,
                        pos_block_id,  # label_block_id = pos_block_id for position-based
                        layout,
                        grid,
                        graph_v2,
                        field,
                    )
                    
                    # Type gate HARD DROP: reject candidates that don't match expected type pattern
                    if not type_gate_generic(text_window, field.type or "text"):
                        continue  # Drop candidate before ranking
                    
                    # Position-based score (higher for closer to corner)
                    pos_score = 0.80  # Base score for position-based
                    if candidates_by_position:
                        # Boost for closest blocks
                        closest_dist = candidates_by_position[0][1]
                        this_dist = next((d for bid, d in candidates_by_position if bid == pos_block_id), 1.0)
                        if this_dist < closest_dist * 1.5:  # Within 50% of closest
                            pos_score = 0.85
                    
                    # Create Candidate
                    candidate: Candidate = {
                        "block_id": pos_block_id,
                        "relation": "same_block",  # Treat as same_block for position-based
                        "label_block_id": pos_block_id,
                        "score_tuple": (),  # Will be calculated below
                        "text_window": text_window,
                        "roi_info": {**roi_info, "position_score": pos_score, "position_hint": position_hint},
                    }
                    
                    # Calculate score_tuple
                    memory_hints = None
                    if pattern_memory and memory_cfg:
                        memory_hints = pattern_memory.get_strategy_hints(field.name)
                    
                    candidate["score_tuple"] = _compute_score_tuple(candidate, field, grid, graph_v2, memory_hints)
                    
                    # Check early-stop
                    if candidate["score_tuple"][0] == 1:  # sufficiency_flag=1
                        candidates.append(candidate)
                        early_stopped = True
                        break
                    
                    # Add candidate
                    candidates.append(candidate)

        # 2.1) Semantic seeds removed - using lightweight label matching instead (Jaccard/Levenshtein)

        # Load matching config (needed for both table and neighborhood matching)
        matching_cfg = _load_matching_config()

        # 2.5) Check tables first (before neighborhood fallback)
        tables = getattr(layout, "tables", [])
        if tables and label_block_ids:
            # Try to find cell by label in tables with header-aware matching
            label_patterns = synonyms + [field.name.lower()]
            # For date/money fields, prefer header matching (more accurate column selection)
            search_mode = "header" if field.type in ("date", "money") else "any"
            table_cell = find_cell_by_label(
                tables, 
                label_patterns, 
                search_in=search_mode, 
                return_type="cell",
                field_name=field.name,
                field_synonyms=synonyms
            )

            if table_cell and table_cell.block_ids and not early_stopped:
                # Use first block from cell as node_id
                cell_block_id = table_cell.block_ids[0]
                if cell_block_id in block_by_id:
                    if blocks_inspected >= MAX_BLOCKS_PER_FIELD:
                        pass  # Skip if limit reached
                    else:
                        blocks_inspected += 1
                        
                        # Extract text_window
                        text_window, roi_info = _extract_text_window(
                            "table_row",
                            cell_block_id,
                            label_block_ids[0],
                            layout,
                            grid,
                            graph_v2,
                            field,
                        )
                        
                        # Type gate HARD DROP: reject candidates that don't match expected type pattern
                        if not type_gate_generic(text_window, field.type or "text"):
                            continue  # Drop candidate before ranking
                        
                        # High priority for table candidates (use config value)
                        spatial_score = matching_cfg.get("relation_weight_same_table_row", 0.85)
                        
                        # Add row/col bonuses if available
                        table = find_table_for_block(cell_block_id, tables)
                        if table:
                            label_table = find_table_for_block(label_block_ids[0], tables)
                            if label_table and label_table.id == table.id:
                                # Same table: check if same row/col
                                label_cell = next(
                                    (c for c in label_table.cells if label_block_ids[0] in c.block_ids), None
                                )
                                if label_cell:
                                    if label_cell.row_id == table_cell.row_id:
                                        spatial_score += matching_cfg.get("prefer_same_row_bonus", 0.12)
                                    else:
                                        spatial_score -= matching_cfg.get("cross_row_penalty", 0.06)

                                    if label_cell.col_id == table_cell.col_id:
                                        spatial_score += matching_cfg.get("prefer_same_col_bonus", 0.06)
                                    else:
                                        spatial_score -= matching_cfg.get("cross_col_penalty", 0.04)

                        spatial_score = max(0.0, min(1.0, spatial_score))
                        
                        # Create Candidate (v2)
                        candidate: Candidate = {
                            "block_id": cell_block_id,
                            "relation": "same_table_row",
                            "label_block_id": label_block_ids[0],
                            "score_tuple": (),  # Will be calculated below
                            "text_window": text_window,
                            "roi_info": {**roi_info, "spatial_score": spatial_score, "table_id": table.id if table else None},
                        }
                        
                        # Calculate score_tuple
                        memory_hints = None
                        if pattern_memory and memory_cfg:
                            memory_hints = pattern_memory.get_strategy_hints(field.name)
                        
                        candidate["score_tuple"] = _compute_score_tuple(candidate, field, grid, graph_v2, memory_hints)
                        
                        # Check early-stop
                        if candidate["score_tuple"][0] == 1:  # sufficiency_flag=1
                            candidates.append(candidate)
                            early_stopped = True
                        else:
                            # Add candidate
                            candidates.append(candidate)

        # 3) Generate candidates via neighborhood
        seen_dst_ids = set()  # Avoid duplicates across label blocks

        # Get column/section/paragraph metadata
        column_by_block = getattr(layout, "column_id_by_block", {})
        section_by_block = getattr(layout, "section_id_by_block", {})
        paragraph_by_block = getattr(layout, "paragraph_id_by_block", {})

        for label_block_id in label_block_ids:
            nb = neighborhood.get(label_block_id)
            if not nb:
                continue

            label_col = column_by_block.get(label_block_id)
            label_sec = section_by_block.get(label_block_id)
            label_para = paragraph_by_block.get(label_block_id)

            # Check right_on_same_line (priority) (v2: Candidate)
            if nb.right_on_same_line is not None and not early_stopped:
                dst_id = nb.right_on_same_line
                if dst_id not in seen_dst_ids and dst_id in block_by_id:
                    if blocks_inspected >= MAX_BLOCKS_PER_FIELD:
                        continue
                    
                    # Filter by role: prefer VALUE blocks, avoid LABEL blocks as values
                    block_roles = getattr(layout, "block_roles", {})
                    dst_role = block_roles.get(dst_id)
                    if dst_role == "LABEL":
                        continue  # Skip LABEL blocks as value candidates
                    
                    seen_dst_ids.add(dst_id)
                    blocks_inspected += 1
                    dst_block = block_by_id[dst_id]

                    # Extract text_window
                    text_window, roi_info = _extract_text_window(
                        "same_line_right_of",
                        dst_id,
                        label_block_id,
                        layout,
                        grid,
                        graph_v2,
                        field,
                    )

                    # Type gate HARD DROP: reject candidates that don't match expected type pattern
                    if not type_gate_generic(text_window, field.type or "text"):
                        continue  # Drop candidate before ranking

                    # Column/section/paragraph bonuses/penalties (for roi_info)
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)
                    dst_para = paragraph_by_block.get(dst_id)
                    
                    col_bonus = 0.0
                    if label_col is not None and dst_col is not None:
                        if label_col == dst_col:
                            col_bonus = matching_cfg["prefer_same_column_bonus"]
                        else:
                            col_bonus = -matching_cfg["cross_column_penalty"]
                    
                    sec_bonus = 0.0
                    if label_sec is not None and dst_sec is not None:
                        if label_sec == dst_sec:
                            sec_bonus = matching_cfg["prefer_same_section_bonus"]
                        else:
                            sec_bonus = -matching_cfg["cross_section_penalty"]
                    
                    para_bonus = 0.0
                    if label_para is not None and dst_para is not None:
                        if label_para == dst_para:
                            para_bonus = matching_cfg.get("prefer_same_paragraph_bonus", 0.03)

                    # Memory bonuses (for roi_info)
                    memory_bonus = 0.0
                    if pattern_memory and memory_cfg:
                        from ..memory.scoring import (
                            memory_bonus_for_fingerprint,
                            memory_bonus_for_label_text,
                            memory_bonus_for_offset,
                        )

                        use_cfg = memory_cfg.get("use", {})
                        label_block = block_by_id[label_block_id]

                        # Synonym bonus
                        syn_bonus = memory_bonus_for_label_text(
                            pattern_memory,
                            field.name,
                            label_block.text or "",
                            use_cfg.get("synonyms_weight", 0.06),
                        )

                        # Offset bonus
                        label_bbox = label_block.bbox
                        dst_bbox = dst_block.bbox
                        offset_bonus = memory_bonus_for_offset(
                            pattern_memory,
                            field.name,
                            label_bbox,
                            dst_bbox,
                            "same_line_right_of",
                            use_cfg.get("offset_bonus", 0.07),
                        )

                        # Fingerprint bonus
                        label_center = ((label_bbox[0] + label_bbox[2]) / 2.0, (label_bbox[1] + label_bbox[3]) / 2.0)
                        dst_center = ((dst_bbox[0] + dst_bbox[2]) / 2.0, (dst_bbox[1] + dst_bbox[3]) / 2.0)
                        grid_res = tuple(memory_cfg.get("fingerprint", {}).get("grid_resolution", [4, 4]))
                        fp_bonus = memory_bonus_for_fingerprint(
                            pattern_memory,
                            field.name,
                            label_center,
                            dst_center,
                            label_sec,
                            label_col,
                            grid_res,
                            use_cfg.get("fingerprint_bonus", 0.05),
                        )

                        memory_bonus = syn_bonus + offset_bonus + fp_bonus

                    # Create Candidate (v2)
                    candidate: Candidate = {
                        "block_id": dst_id,
                        "relation": "same_line_right_of",
                        "label_block_id": label_block_id,
                        "score_tuple": (),  # Will be calculated below
                        "text_window": text_window,
                        "roi_info": {
                            **roi_info,
                            "col_bonus": col_bonus,
                            "sec_bonus": sec_bonus,
                            "para_bonus": para_bonus,
                            "memory_bonus": memory_bonus,
                        },
                    }
                    
                    # Calculate score_tuple
                    memory_hints = None
                    if pattern_memory and memory_cfg:
                        memory_hints = pattern_memory.get_strategy_hints(field.name)
                    
                    candidate["score_tuple"] = _compute_score_tuple(candidate, field, grid, graph_v2, memory_hints)
                    
                    # Check early-stop
                    if candidate["score_tuple"][0] == 1:  # sufficiency_flag=1
                        candidates.append(candidate)
                        early_stopped = True
                        break
                    
                    # Add candidate
                    candidates.append(candidate)

            # Check below_on_same_column (fallback) (v2: Candidate)
            # Improved: handle multi-line blocks with multiple labels/values
            if nb.below_on_same_column is not None and not early_stopped:
                dst_id = nb.below_on_same_column
                if dst_id not in seen_dst_ids and dst_id in block_by_id:
                    if blocks_inspected >= MAX_BLOCKS_PER_FIELD:
                        continue
                    
                    seen_dst_ids.add(dst_id)
                    blocks_inspected += 1
                    dst_block = block_by_id[dst_id]
                    label_block = block_by_id[label_block_id]

                    # Improved: For multi-line blocks, try to match label line with value line
                    # If label block has multiple lines (e.g., "Inscrição\nSeccional\nSubseção")
                    # and value block has multiple lines (e.g., "101943\nPR\nCONSELHO SECCIONAL - PARANÁ"),
                    # extract the corresponding line
                    label_lines = [ln.strip() for ln in (label_block.text or "").splitlines() if ln.strip()]
                    dst_lines = [ln.strip() for ln in (dst_block.text or "").splitlines() if ln.strip()]
                    
                    # Find which line of label block contains this field's synonym
                    label_line_idx = None
                    field_name_lower = field.name.lower()
                    field_synonyms_lower = [s.lower().strip() for s in synonyms]
                    
                    for i, label_line in enumerate(label_lines):
                        label_line_norm = _normalize_text(label_line)
                        if field_name_lower in label_line_norm:
                            label_line_idx = i
                            break
                        for syn in field_synonyms_lower:
                            if syn and syn in label_line_norm:
                                label_line_idx = i
                                break
                        if label_line_idx is not None:
                            break
                    
                    # Filter by role: prefer VALUE blocks, avoid LABEL blocks as values
                    # BUT: if role is None or not set, don't filter (allow it)
                    block_roles = getattr(layout, "block_roles", {})
                    dst_role = block_roles.get(dst_id)
                    if dst_role == "LABEL":
                        # Check if this block might still be a value (e.g., same_block relation)
                        # Only skip if it's clearly just a label (short text, ends with separator)
                        dst_block = block_by_id.get(dst_id)
                        if dst_block:
                            dst_block_text = dst_block.text or ""
                            if len(dst_block_text.strip()) <= 10 and dst_block_text.rstrip().endswith((":", "—", "–")):
                                continue  # Skip short labels with separators
                        # Otherwise, allow it (might be label+value in same block)
                    
                    # Extract text_window: use corresponding line if found, else first line
                    # IMPROVEMENT: Also extract specific part from line if field type is short
                    if label_line_idx is not None and label_line_idx < len(dst_lines):
                        # Use corresponding line (better matching for multi-line blocks)
                        text_window = dst_lines[label_line_idx]
                        
                        # For short field types, try to extract just the relevant part
                        if field.type in ["number", "id_simple", "uf", "alphanum_code"]:
                            parts = text_window.split()
                            if len(parts) > 1:
                                # Try to find the part that passes type-gate
                                for part in parts:
                                    if type_gate_generic(part, field.type):
                                        text_window = part
                                        break
                                # If none pass, use first part if short
                                if not any(type_gate_generic(p, field.type) for p in parts):
                                    if len(parts) > 0 and len(parts[0]) <= 10:
                                        text_window = parts[0]
                        
                        roi_info = {
                            "relation": "first_below_same_column",
                            "block_id": dst_id,
                            "label_block_id": label_block_id,
                            "roi_method": "matched_line",
                            "label_line_idx": label_line_idx,
                            "value_line_idx": label_line_idx,
                        }
                    else:
                        # Fallback: use standard extraction
                        text_window, roi_info = _extract_text_window(
                            "first_below_same_column",
                            dst_id,
                            label_block_id,
                            layout,
                            grid,
                            graph_v2,
                            field,
                        )
                        roi_info["roi_method"] = "first_line_fallback"
                        
                        # IMPROVEMENT: For multi-line blocks, try first line if standard extraction didn't work well
                        if not text_window or len(text_window.strip()) < 2:
                            if len(dst_lines) > 0:
                                text_window = dst_lines[0]
                                # For short types, extract part from first line
                                if field.type in ["number", "id_simple", "uf", "alphanum_code"]:
                                    parts = text_window.split()
                                    if len(parts) > 1:
                                        for part in parts:
                                            if type_gate_generic(part, field.type):
                                                text_window = part
                                                break

                    # Type gate HARD DROP: reject candidates that don't match expected type pattern
                    if not type_gate_generic(text_window, field.type or "text"):
                        continue  # Drop candidate before ranking

                    # Column/section/paragraph bonuses/penalties (for roi_info)
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)
                    dst_para = paragraph_by_block.get(dst_id)
                    
                    col_bonus = 0.0
                    if label_col is not None and dst_col is not None:
                        if label_col == dst_col:
                            col_bonus = matching_cfg["prefer_same_column_bonus"]
                        else:
                            col_bonus = -matching_cfg["cross_column_penalty"]
                    
                    sec_bonus = 0.0
                    if label_sec is not None and dst_sec is not None:
                        if label_sec == dst_sec:
                            sec_bonus = matching_cfg["prefer_same_section_bonus"]
                        else:
                            sec_bonus = -matching_cfg["cross_section_penalty"]
                    
                    para_bonus = 0.0
                    if label_para is not None and dst_para is not None:
                        if label_para == dst_para:
                            para_bonus = matching_cfg.get("prefer_same_paragraph_bonus", 0.03)

                    # Memory bonuses (for roi_info)
                    memory_bonus = 0.0
                    if pattern_memory and memory_cfg:
                        from ..memory.scoring import (
                            memory_bonus_for_fingerprint,
                            memory_bonus_for_label_text,
                            memory_bonus_for_offset,
                        )

                        use_cfg = memory_cfg.get("use", {})
                        label_block = block_by_id[label_block_id]

                        # Synonym bonus
                        syn_bonus = memory_bonus_for_label_text(
                            pattern_memory,
                            field.name,
                            label_block.text or "",
                            use_cfg.get("synonyms_weight", 0.06),
                        )

                        # Offset bonus
                        label_bbox = label_block.bbox
                        dst_bbox = dst_block.bbox
                        offset_bonus = memory_bonus_for_offset(
                            pattern_memory,
                            field.name,
                            label_bbox,
                            dst_bbox,
                            "first_below_same_column",
                            use_cfg.get("offset_bonus", 0.07),
                        )

                        # Fingerprint bonus
                        label_center = ((label_bbox[0] + label_bbox[2]) / 2.0, (label_bbox[1] + label_bbox[3]) / 2.0)
                        dst_center = ((dst_bbox[0] + dst_bbox[2]) / 2.0, (dst_bbox[1] + dst_bbox[3]) / 2.0)
                        grid_res = tuple(memory_cfg.get("fingerprint", {}).get("grid_resolution", [4, 4]))
                        fp_bonus = memory_bonus_for_fingerprint(
                            pattern_memory,
                            field.name,
                            label_center,
                            dst_center,
                            label_sec,
                            label_col,
                            grid_res,
                            use_cfg.get("fingerprint_bonus", 0.05),
                        )

                        memory_bonus = syn_bonus + offset_bonus + fp_bonus

                    # Create Candidate (v2)
                    candidate: Candidate = {
                        "block_id": dst_id,
                        "relation": "first_below_same_column",
                        "label_block_id": label_block_id,
                        "score_tuple": (),  # Will be calculated below
                        "text_window": text_window,
                        "roi_info": {
                            **roi_info,
                            "col_bonus": col_bonus,
                            "sec_bonus": sec_bonus,
                            "para_bonus": para_bonus,
                            "memory_bonus": memory_bonus,
                        },
                    }
                    
                    # Calculate score_tuple
                    memory_hints = None
                    if pattern_memory and memory_cfg:
                        memory_hints = pattern_memory.get_strategy_hints(field.name)
                    
                    candidate["score_tuple"] = _compute_score_tuple(candidate, field, grid, graph_v2, memory_hints)
                    
                    # Check early-stop
                    if candidate["score_tuple"][0] == 1:  # sufficiency_flag=1
                        candidates.append(candidate)
                        early_stopped = True
                        break
                    
                    # Add candidate
                    candidates.append(candidate)

        # Helper functions for label detection
        def _split_by_label(text: str, syn_list: list[str]) -> Optional[str]:
            """Split text by label and return the part after the label.
            
            Improved: handles multi-line blocks with multiple labels.
            """
            if not text:
                return None
            
            # Process line by line for better accuracy with multi-line blocks
            lines = text.splitlines()
            t_norm = _normalize_text(text)
            
            # Sort synonyms by length (longest first) to match more specific ones first
            sorted_syns = sorted(syn_list, key=len, reverse=True)
            
            for syn in sorted_syns:
                if not syn or not syn.strip():
                    continue
                s_norm = _normalize_text(syn.strip())
                
                # Check each line for the synonym
                for line in lines:
                    line_norm = _normalize_text(line)
                    # Use word boundary to avoid substring matches
                    import re
                    pattern = r'\b' + re.escape(s_norm) + r'\b'
                    if re.search(pattern, line_norm):
                        # Found synonym in this line, get text after it
                        syn_original = syn.strip()
                        idx_orig = line.lower().find(syn_original.lower())
                        if idx_orig >= 0:
                            # Get text after the synonym, stripping common separators
                            after = line[idx_orig + len(syn_original):].lstrip(" :\u200b\t")
                            if after:
                                return after
                        # Fallback: try normalized position
                        idx = line_norm.find(s_norm)
                        if idx >= 0:
                            after = line[idx:].lstrip(" :\u200b\t")
                            # Remove the synonym itself if it's at the start
                            after_lower = after.lower()
                            if after_lower.startswith(syn_original.lower()):
                                after = after[len(syn_original):].lstrip(" :\u200b\t")
                            if after:
                                return after
                
                # Fallback: whole text search (less accurate)
                idx = t_norm.find(s_norm)
                if idx >= 0:
                    syn_original = syn.strip()
                    idx_orig = text.lower().find(syn_original.lower())
                    if idx_orig >= 0:
                        after = text[idx_orig + len(syn_original):].lstrip(" :\u200b\t")
                        if after:
                            return after
                    after = text[idx:].lstrip(" :\u200b\t")
                    # Remove the synonym itself if it's at the start
                    if after.lower().startswith(syn_original.lower()):
                        after = after[len(syn_original):].lstrip(" :\u200b\t")
                    if after:
                        return after
            return None
        
        def _is_label_only_block(block_text: str, syn_list: list[str]) -> bool:
            """Check if block text is ONLY labels (no meaningful value content).
            
            Improved: better detection for multi-line blocks with multiple labels.
            """
            if not block_text:
                return False
            
            t_norm = _normalize_text(block_text)
            common_labels = [
                "inscrição", "inscricao", "seccional", "subseção", "subsecao",
                "categoria", "endereço", "endereco", "telefone", "situação", "situacao",
                "nome", "data", "valor", "sistema", "produto", "conselho seccional"
            ]
            
            # Process line by line for multi-line blocks
            lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
            
            if len(lines) <= 3:
                # Check if all lines are labels
                label_lines = 0
                for line in lines:
                    line_norm = _normalize_text(line)
                    # Check if line matches common labels or synonyms
                    is_label_line = False
                    for label in common_labels:
                        if label in line_norm:
                            is_label_line = True
                            break
                    if not is_label_line:
                        # Check if line matches any synonym
                        for syn in syn_list:
                            if syn and _normalize_text(syn.strip()) in line_norm:
                                is_label_line = True
                                break
                    if is_label_line:
                        label_lines += 1
                
                # If 70% or more lines are labels, consider it label-only
                if label_lines >= len(lines) * 0.7:
                    return True
            
            # Also check whole block
            words = t_norm.split()
            if len(words) <= 3:
                label_count = sum(1 for w in words if w in common_labels or any(_normalize_text(syn.strip()) in w for syn in syn_list if syn))
                if label_count >= len(words) * 0.7:  # 70% or more are labels
                    return True
            
            return False
        
        # (A) New candidate: value in the SAME BLOCK as label (for each label block found)
        # Only create same_block if the block actually contains a label token
        def _has_label_token(block_text: str, syn_list: list[str]) -> bool:
            """Check if block text contains any synonym (normalized).
            
            Uses word-boundary matching to avoid false positives (e.g., "nome" in "telefone").
            """
            if not block_text:
                return False
            t_norm = _normalize_text(block_text)
            # Split into words for better matching
            words = set(t_norm.split())
            for syn in syn_list:
                if not syn or not syn.strip():
                    continue
                syn_norm = _normalize_text(syn.strip())
                # Check if synonym is a complete word (avoid substring matches)
                if syn_norm in words:
                    return True
                # Also check if it's at word boundary (start/end of text or after/before space)
                if syn_norm == t_norm:  # Exact match
                    return True
                # Word boundary check: syn surrounded by space or start/end
                import re
                pattern = r'\b' + re.escape(syn_norm) + r'\b'
                if re.search(pattern, t_norm):
                    return True
            return False

        for label_block_id in label_block_ids:
            if label_block_id in block_by_id:
                label_block = block_by_id[label_block_id]
                # Check if block contains label token (avoid same_block in random blocks)
                if _has_label_token(label_block.text or "", synonyms + [field.name]):
                    # Check if we already have a same_block candidate for this block
                    if not any(
                        (isinstance(c, dict) and c.get("block_id") == label_block_id and c.get("relation") == "same_block")
                        or (hasattr(c, "node_id") and c.node_id == label_block_id and c.relation == "same_block")
                        for c in candidates
                    ):
                        # For same_block, only create if there's content after the label
                        # Check if split_by_label would find something
                        after_label = _split_by_label(label_block.text or "", synonyms + [field.name])
                        if after_label and len(after_label.strip()) >= 2:
                            if early_stopped or blocks_inspected >= MAX_BLOCKS_PER_FIELD:
                                break
                            
                            blocks_inspected += 1
                            
                            # Extract text_window
                            text_window, roi_info = _extract_text_window(
                                "same_block",
                                label_block_id,
                                label_block_id,
                                layout,
                                grid,
                                graph_v2,
                                field,
                            )
                            
                            # If text_window is empty (label-only detected), skip this candidate
                            if not text_window or not text_window.strip():
                                continue  # Skip label-only candidates
                            
                            # Type gate HARD DROP: reject candidates that don't match expected type pattern
                            if not type_gate_generic(text_window, field.type or "text"):
                                continue  # Drop candidate before ranking
                            
                            # Create Candidate (v2)
                            candidate: Candidate = {
                                "block_id": label_block_id,  # destination = the block itself
                                "relation": "same_block",
                                "label_block_id": label_block_id,
                                "score_tuple": (),  # Will be calculated below
                                "text_window": text_window,
                                "roi_info": roi_info,
                            }
                            
                            # Calculate score_tuple
                            memory_hints = None
                            if pattern_memory and memory_cfg:
                                memory_hints = pattern_memory.get_strategy_hints(field.name)
                            
                            candidate["score_tuple"] = _compute_score_tuple(candidate, field, grid, graph_v2, memory_hints)
                            
                            # Check early-stop
                            if candidate["score_tuple"][0] == 1:  # sufficiency_flag=1
                                candidates.append(candidate)
                                early_stopped = True
                                break
                            
                            # Add candidate
                            candidates.append(candidate)

        # (B) Fallback: if nothing was generated OR nothing seems valid and field is ENUM,
        # do a "global enum scan" - scan all blocks looking for an enum option
        # Also trigger if candidates exist but are likely just labels (not enum values)
        should_do_enum_scan = False
        if field.type == "enum":
            if not candidates:
                should_do_enum_scan = True
            elif not any(
                isinstance(c, dict) and len(c.get("score_tuple", ())) > 2 and c["score_tuple"][2] == 1
                for c in candidates
            ):
                should_do_enum_scan = True
            else:
                # Check if existing candidates are likely just labels (not enum values)
                # This happens when text_window contains only label text, not actual enum values
                from ..validation.validators import validate_and_normalize
                enum_opts_check = (field.meta or {}).get("enum_options") if hasattr(field, "meta") and field.meta else None
                if enum_opts_check:
                    # Check if any candidate's text_window is a valid enum value
                    has_valid_enum_value = False
                    for c in candidates:
                        if isinstance(c, dict):
                            text_win = c.get("text_window", "")
                            if text_win:
                                ok, _ = validate_and_normalize("enum", text_win, enum_options=enum_opts_check)
                                if ok:
                                    has_valid_enum_value = True
                                    break
                    if not has_valid_enum_value:
                        # No valid enum value found, do enum scan
                        should_do_enum_scan = True
        
        if should_do_enum_scan:
            # Get enum_options from meta (should be populated by schema enrichment)
            enum_opts = (field.meta or {}).get("enum_options") if hasattr(field, "meta") and field.meta else None
            
            # Fallback: try to extract from description if not in meta
            if not enum_opts and field.description:
                # Try to extract from description (e.g., "pode ser A, B, C")
                desc_lower = field.description.lower()
                if "pode ser" in desc_lower:
                    # Extract options after "pode ser"
                    parts = field.description.split("pode ser", 1)
                    if len(parts) > 1:
                        options_text = parts[1].split(".")[0]  # Until first period
                        # Try to find uppercase words
                        import re
                        potential_opts = re.findall(r'\b([A-Z][A-Z\sÁÉÍÓÚÂÊÔÃÕÇ]+?)\b', options_text)
                        if potential_opts:
                            enum_opts = [opt.strip().upper() for opt in potential_opts if len(opt.strip()) > 2]
                # Support if meta is embedded in description (workaround)
                if "[meta:" in field.description:
                    try:
                        chunk = field.description.split("[meta:", 1)[1].rsplit("]", 1)[0]
                        meta = eval(chunk) if chunk.startswith("{") else {}
                        enum_opts = meta.get("enum_options") or enum_opts
                    except Exception:
                        pass

            if enum_opts:
                from ..validation.validators import validate_and_normalize

                # Try to find enum value near labels first (if labels found)
                blocks_to_scan = layout.blocks
                if label_block_ids:
                    label_block = block_by_id.get(label_block_ids[0])
                    if label_block:
                        label_col = column_by_block.get(label_block.id)
                        label_sec = section_by_block.get(label_block.id)
                        # Prioritize blocks in same column/section
                        blocks_near = [b for b in layout.blocks if 
                                      (label_col is None or column_by_block.get(b.id) == label_col) and
                                      (label_sec is None or section_by_block.get(b.id) == label_sec)]
                        if blocks_near:
                            blocks_to_scan = blocks_near + [b for b in layout.blocks if b not in blocks_near]

                # Sort blocks by position (top-left first) for better results
                sorted_blocks = sorted(blocks_to_scan, key=lambda b: (b.bbox[1], b.bbox[0]))
                
                for b in sorted_blocks:
                    if early_stopped or blocks_inspected >= MAX_BLOCKS_PER_FIELD:
                        break
                    
                    # Check each line of the block
                    lines = b.text.splitlines() if b.text else []
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        # For enum scan, try multiple strategies:
                        # 1. Check if line itself is an enum value (standalone)
                        # 2. Check if line contains label + enum value
                        # 3. Check each word/token in the line
                        ok = False
                        normalized = None
                        
                        # Strategy 1: Check whole line as enum value (case-insensitive, accent-insensitive)
                        ok, normalized = validate_and_normalize("enum", line, enum_options=enum_opts)
                        
                        # Strategy 2: If not found, check if line contains label and extract value after
                        if not ok:
                            has_label = _has_label_token(line, synonyms + [field.name])
                            if has_label:
                                after_label = _split_by_label(line, synonyms + [field.name])
                                if after_label and len(after_label.strip()) >= 2:
                                    ok, normalized = validate_and_normalize("enum", after_label.strip(), enum_options=enum_opts)
                        
                        # Strategy 3: If still not found, check each word/token (for multi-word enum values)
                        if not ok:
                            # Try each word as potential enum value
                            words = line.split()
                            for word in words:
                                word_clean = word.strip(".,:;!?")
                                if len(word_clean) >= 2:
                                    ok, normalized = validate_and_normalize("enum", word_clean, enum_options=enum_opts)
                                    if ok:
                                        break
                        if ok and normalized:
                            blocks_inspected += 1
                            
                            # Extract text_window (first line of block)
                            text_window, roi_info = _extract_text_window(
                                "global_enum_scan",
                                b.id,
                                label_block_ids[0] if label_block_ids else b.id,
                                layout,
                                grid,
                                graph_v2,
                                field,
                            )
                            
                            # Create Candidate (v2)
                            candidate: Candidate = {
                                "block_id": b.id,
                                "relation": "global_enum_scan",
                                "label_block_id": label_block_ids[0] if label_block_ids else b.id,
                                "score_tuple": (),  # Will be calculated below
                                "text_window": normalized,  # Use normalized value as text_window
                                "roi_info": {**roi_info, "normalized_value": normalized},
                            }
                            
                            # Calculate score_tuple
                            memory_hints = None
                            if pattern_memory and memory_cfg:
                                memory_hints = pattern_memory.get_strategy_hints(field.name)
                            
                            candidate["score_tuple"] = _compute_score_tuple(candidate, field, grid, graph_v2, memory_hints)
                            
                            # Check early-stop
                            if candidate["score_tuple"][0] == 1:  # sufficiency_flag=1
                                candidates.append(candidate)
                                early_stopped = True
                                break
                            
                            # Add candidate
                            candidates.append(candidate)
                            break  # Found a good candidate for this block, check next block
                    if early_stopped or (candidates and isinstance(candidates[-1], dict) and candidates[-1].get("relation") == "global_enum_scan"):
                        break  # Found enum candidate or early-stopped, stop searching

        # v2: Skip dedupe - candidates are already Candidate objects, deduplication handled by score_tuple sorting

        # v2: Cross-column filtering handled by score_tuple (relation_rank and spatial_quality)
        # No need for separate filtering since score_tuple already prioritizes better relations

        # 3.5) Semantic seed neighbors removed - embeddings disabled, using layout-first approach only

        # NEW: Apply Pareto selection and tie-breakers (replacing arbitrary score_tuple sorting)
        proof_data = {
            "pareto_criteria": None,
            "tie_breaker_applied": False,
            "tie_breaker_reason": None,
            "llm_used": False,
            "llm_result": None,
            "memory_invariants": None,
        }
        
        if candidates:
            # Compute Pareto criteria for each candidate (v3.0 requires orthogonal_graph and style_signatures)
            # TODO: Integrate orthogonal_graph and style_signatures from pipeline
            # For now, skip Pareto filtering if required data is not available
            criteria_list = []
            try:
                # Try to get orthogonal_graph and style_signatures if available
                # This is a temporary fix - should be passed from pipeline
                orthogonal_graph = getattr(layout, 'orthogonal_graph', None)
                style_signatures = getattr(layout, 'style_signatures', {})
                
                if orthogonal_graph is None:
                    # Fallback: skip Pareto filtering if orthogonal graph not available
                    criteria_list = []
                    pareto_candidates = candidates
                else:
                    for cand in candidates:
                        criteria = compute_pareto_criteria(
                            cand,
                            field,
                            orthogonal_graph,
                            style_signatures,
                            existing_values=None,
                        )
                        criteria_list.append(criteria)
                    
                    # Filter by Pareto optimality
                    non_dominated_indices = pareto_filter(candidates, criteria_list)
                    pareto_candidates = [candidates[i] for i in non_dominated_indices]
            except Exception as e:
                # Fallback: skip Pareto filtering on error
                criteria_list = []
                pareto_candidates = candidates
            
            proof_data["pareto_criteria"] = criteria_list
            
            if len(pareto_candidates) == 0:
                # No non-dominated candidates, fallback to score_tuple
                candidates.sort(key=lambda c: c["score_tuple"], reverse=True)
                selected = candidates[:top_k]
                results[field.name] = selected
                # Attach proof (minimal)
                for cand in selected:
                    cand["proof"] = {"pareto": {"num_candidates": len(candidates), "num_non_dominated": 0}}
            elif len(pareto_candidates) == 1:
                # Single candidate after Pareto, use it
                selected = pareto_candidates[0]
                results[field.name] = [selected]
                # Build proof
                from ..core.proof import build_proof
                proof = build_proof(
                    field.name,
                    selected,
                    candidates,
                    pareto_criteria=criteria_list,
                    tie_breaker_applied=False,
                    llm_used=False,
                    memory_invariants=proof_data["memory_invariants"],
                )
                selected["proof"] = proof
            else:
                # Multiple candidates after Pareto, apply tie-breakers
                best_idx = apply_tie_breakers(pareto_candidates, layout, field.name)
                proof_data["tie_breaker_applied"] = True
                
                if best_idx >= 0:
                    selected = pareto_candidates[best_idx]
                    proof_data["tie_breaker_reason"] = "direction_preference_and_distance"
                    results[field.name] = [selected]
                    # Build proof
                    from ..core.proof import build_proof
                    proof = build_proof(
                        field.name,
                        selected,
                        candidates,
                        pareto_criteria=criteria_list,
                        tie_breaker_applied=True,
                        tie_breaker_reason=proof_data["tie_breaker_reason"],
                        llm_used=False,
                        memory_invariants=proof_data["memory_invariants"],
                    )
                    selected["proof"] = proof
                else:
                    # Tie-breakers couldn't decide, try LLM chooser if available and temperature allows
                    # Temperature rules: T >= 0.8: 0 calls, 0.4 <= T < 0.8: max 1 call, T < 0.4: max 2-3 calls
                    max_llm_calls = 0
                    if temperature >= 0.8:
                        max_llm_calls = 0
                    elif temperature >= 0.4:
                        max_llm_calls = 1
                    else:
                        max_llm_calls = 3
                    
                    if llm_client and max_llm_calls > 0:
                        try:
                            # Import here to avoid circular dependency
                            from ..llm.chooser import llm_chooser
                            llm_selected = llm_chooser(
                                field,
                                pareto_candidates[:3],  # Max 3 candidates
                                layout,
                                llm_client,
                                document_label=document_label or "unknown",
                            )
                            proof_data["llm_used"] = True
                            
                            if llm_selected:
                                results[field.name] = [llm_selected]
                                # Build proof with LLM info
                                from ..core.proof import build_proof
                                proof = build_proof(
                                    field.name,
                                    llm_selected,
                                    candidates,
                                    pareto_criteria=criteria_list,
                                    tie_breaker_applied=True,
                                    llm_used=True,
                                    llm_result={"pick": pareto_candidates.index(llm_selected) if llm_selected in pareto_candidates else -1, "why": "LLM chooser"},
                                    memory_invariants=proof_data["memory_invariants"],
                                )
                                llm_selected["proof"] = proof
                            else:
                                # LLM chooser returned None, use first pareto candidate
                                selected = pareto_candidates[0]
                                results[field.name] = [selected]
                                from ..core.proof import build_proof
                                proof = build_proof(
                                    field.name,
                                    selected,
                                    candidates,
                                    pareto_criteria=criteria_list,
                                    tie_breaker_applied=True,
                                    llm_used=True,
                                    llm_result={"pick": -1, "why": "LLM chose none"},
                                    memory_invariants=proof_data["memory_invariants"],
                                )
                                selected["proof"] = proof
                        except Exception as e:
                            # LLM chooser failed, use first pareto candidate
                            import logging
                            logging.warning(f"LLM chooser failed for field {field.name}: {e}")
                            selected = pareto_candidates[0]
                            results[field.name] = [selected]
                            from ..core.proof import build_proof
                            proof = build_proof(
                                field.name,
                                selected,
                                candidates,
                                pareto_criteria=criteria_list,
                                tie_breaker_applied=True,
                                llm_used=False,
                                memory_invariants=proof_data["memory_invariants"],
                            )
                            selected["proof"] = proof
                    else:
                        # No LLM available or temperature too high, use first pareto candidate
                        selected = pareto_candidates[0]
                        results[field.name] = [selected]
                        from ..core.proof import build_proof
                        proof = build_proof(
                            field.name,
                            selected,
                            candidates,
                            pareto_criteria=criteria_list,
                            tie_breaker_applied=True,
                            llm_used=False,
                            memory_invariants=proof_data["memory_invariants"],
                        )
                        selected["proof"] = proof
        else:
            # No candidates found, return empty
            results[field.name] = []

    return results


# ============================================================================
# v2 Matcher: Tournament system with score_tuple
# ============================================================================


def _compute_score_tuple(
    candidate: Candidate,
    field: SchemaField,
    grid: Optional[Grid],
    graph: Optional[GraphV2],
    memory_hints: Optional[dict] = None,
) -> tuple:
    """Compute score_tuple for candidate (lexicographic ordering).

    Returns:
        Tuple of (sufficiency_flag, relation_rank, type_gate, style_coherence,
        same_component, shape_goodness, spatial_quality, memory_bonus, semantic_boost_bucket)
    """
    # type_gate: use generic pattern-based gate (v2)
    type_gate = 1 if type_gate_generic(candidate["text_window"], field.type or "text") else 0
    
    relation = candidate["relation"]
    relation_rank_map = {
        "table_row": 4,
        "same_line": 3,
        "same_block": 2,
        "south_of": 1,
        "semantic": 0,
    }
    relation_rank = relation_rank_map.get(relation, 0)
    
    # Suficiência: table_row + type ok, same_line + type ok, same_block keep_label + (enum_ok ou length≥4)
    sufficiency_flag = 0
    if relation == "table_row" and type_gate == 1:
        sufficiency_flag = 1
    elif relation == "same_line" and type_gate == 1:
        sufficiency_flag = 1
    elif relation == "same_block" and type_gate == 1:
        # Check if enum_ok or length≥4
        text = candidate["text_window"]
        if field.type == "enum":
            enum_options = field.meta.get("enum_options") if field.meta else None
            if enum_options:
                for opt in enum_options:
                    if opt.lower() in text.lower():
                        sufficiency_flag = 1
                        break
        elif len(text.strip()) >= 4:
            sufficiency_flag = 1
    
    # style_coherence: 1 se |font_z(label) - font_z(value)| ≤ 0.5
    style_coherence = 0
    if graph and candidate.get("label_block_id"):
        label_block_id = candidate["label_block_id"]
        value_block_id = candidate["block_id"]
        label_style = graph.get("style", {}).get(label_block_id)
        value_style = graph.get("style", {}).get(value_block_id)
        if label_style and value_style:
            label_font_z = label_style[0]
            value_font_z = value_style[0]
            if abs(label_font_z - value_font_z) <= 0.5:
                style_coherence = 1
    
    # same_component: 1 se label e candidato no mesmo component_id
    same_component = 0
    if graph and candidate.get("label_block_id"):
        label_comp = graph.get("component_id", {}).get(candidate["label_block_id"])
        value_comp = graph.get("component_id", {}).get(candidate["block_id"])
        if label_comp is not None and value_comp is not None and label_comp == value_comp:
            same_component = 1
    
    # shape_goodness: 1 - min(1, DL_shape/len(shape_ref))
    # Use pattern-based expected shape (v2)
    shape_goodness = 0
    text_shape = to_shape(candidate["text_window"])
    if text_shape:
        from ..validation.patterns import detect_pattern
        
        # Detect pattern in candidate text
        pattern = detect_pattern(candidate["text_window"])
        field_type = (field.type or "text").lower()
        
        # Expected shape based on pattern (generic, not hardcoded by type)
        if pattern == "digits_only":
            expected_shape = "D" * len(candidate["text_window"].replace(" ", ""))
        elif pattern == "digits_with_separators":
            # Expected: mostly digits with some separators
            digits = len([c for c in candidate["text_window"] if c.isdigit()])
            expected_shape = "D" * digits + "P" * max(1, len(candidate["text_window"]) - digits)
        elif pattern == "isolated_letters":
            expected_shape = "U2"  # Default for isolated letters
        elif pattern == "date_like":
            expected_shape = "D2-P-D2-P-D4"  # Common date pattern
        elif pattern == "money_like":
            # Money: digits with separators
            digits = len([c for c in candidate["text_window"] if c.isdigit()])
            expected_shape = "D" * digits + "P" * max(1, len(candidate["text_window"]) - digits)
        else:
            expected_shape = text_shape  # No shape comparison for text/alphanumeric
        
        if expected_shape != text_shape:
            dl_dist = damerau_levenshtein_shape(text_shape, expected_shape)
            shape_goodness = max(0.0, 1.0 - min(1.0, dl_dist / max(len(expected_shape), 1)))
        else:
            shape_goodness = 1.0
        shape_goodness = int(shape_goodness > 0.5)  # Convert to 0/1
    
    # spatial_quality: valores fixos por relação
    spatial_quality_map = {
        "same_line": 1.0,
        "table_row": 0.9,
        "same_block": 0.85,
        "south_of": 0.7,
        "semantic": 0.5,
    }
    spatial_quality = spatial_quality_map.get(relation, 0.5)
    
    # memory_bonus: 2 se auto_apply, 1 se memory hints, 0 se nada
    memory_bonus = 0
    if memory_hints:
        if memory_hints.get("auto_apply", False):
            memory_bonus = 2
        elif memory_hints.get("hints", False):
            memory_bonus = 1
    
    # semantic_boost_bucket: floor(cosine*10), só se semantic
    semantic_boost_bucket = 0
    if relation == "semantic" and "semantic_score" in candidate:
        cosine = candidate.get("semantic_score", 0.0)
        semantic_boost_bucket = int(cosine * 10)
    
    return (
        sufficiency_flag,
        relation_rank,
        type_gate,
        style_coherence,
        same_component,
        shape_goodness,
        spatial_quality,
        memory_bonus,
        semantic_boost_bucket,
    )

