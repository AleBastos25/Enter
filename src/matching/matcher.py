"""Matcher for finding field candidates from label blocks using spatial neighborhood."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Optional

from ..core.models import Block, FieldCandidate, LayoutGraph, SchemaField
from ..tables.extractor import find_cell_by_label, find_table_for_block


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


def _find_label_blocks(blocks: list[Block], synonyms: list[str]) -> list[int]:
    """Find block IDs that contain any of the synonyms.

    Args:
        blocks: List of blocks to search.
        synonyms: List of normalized synonym strings.

    Returns:
        List of block IDs that match, prioritized by:
        - Shorter text (more likely to be a label)
        - Larger font size (if available)
        - Word-boundary matches (more specific)
    """
    candidates = []

    for block in blocks:
        block_text = block.text or ""
        if not block_text:
            continue
            
        # Use word-boundary matching for better accuracy
        t_norm = _normalize_text(block_text)
        words = set(t_norm.split())
        
        matched = False
        match_score = 0.0
        
        for syn in synonyms:
            if not syn or not syn.strip():
                continue
            syn_norm = _normalize_text(syn.strip())
            
            # Check if synonym is a complete word (best match)
            if syn_norm in words:
                matched = True
                match_score = 2.0  # Best score for word match
                break
            # Check word boundary
            import re
            pattern = r'\b' + re.escape(syn_norm) + r'\b'
            if re.search(pattern, t_norm):
                matched = True
                match_score = 1.5  # Good score for boundary match
                break
            # Fallback: substring (lowest score)
            if syn_norm in t_norm:
                matched = True
                match_score = 1.0
                # Don't break, continue to find better matches
        
        if matched:
            # Compute priority score (higher = better)
            # Prefer shorter blocks (likely labels)
            text_len = len(block_text)
            priority = match_score * (1.0 / (1.0 + text_len * 0.01))
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


def _dedupe_candidates(candidates: list[FieldCandidate]) -> list[FieldCandidate]:
    """Remove duplicate candidates by node_id, keeping the one with highest score.

    Args:
        candidates: List of FieldCandidate objects.

    Returns:
        Deduplicated list.
    """
    by_node: dict[int, FieldCandidate] = {}
    for cand in candidates:
        node_id = cand.node_id
        if node_id not in by_node:
            by_node[node_id] = cand
        else:
            # Keep the one with higher total score
            existing_score = sum(by_node[node_id].scores.values())
            new_score = sum(cand.scores.values())
            if new_score > existing_score:
                by_node[node_id] = cand
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
    semantic_seeds: Optional[dict[str, list[tuple[int, float]]]] = None,
    pattern_memory: Optional[Any] = None,  # PatternMemory (avoid circular import)
    memory_cfg: Optional[dict] = None,
    use_assignment: bool = False,
) -> dict[str, list[FieldCandidate]]:
    """Match fields to value candidates using spatial neighborhood and semantic seeds.

    Args:
        schema_fields: List of SchemaField objects with synonyms.
        layout: LayoutGraph with blocks and neighborhood index.
        validate: Optional function to soft-validate field type (returns bool).
        top_k: Maximum number of candidates per field.
        semantic_seeds: Optional dict mapping field_name -> list of (block_id, cosine_score) tuples.
        pattern_memory: Optional PatternMemory instance.
        memory_cfg: Optional memory config dict.
        use_assignment: If True, use global assignment layer (optimal transport).

    Returns:
        Dictionary mapping field_name -> list[FieldCandidate] (sorted by score desc).
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
                semantic_seeds=semantic_seeds,
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

    # Classic matching (original implementation)
    # Get neighborhood index
    neighborhood = getattr(layout, "neighborhood", {})
    block_by_id = {b.id: b for b in layout.blocks}

    results: dict[str, list[FieldCandidate]] = {}
    semantic_seeds = semantic_seeds or {}

    for field in schema_fields:
        candidates: list[FieldCandidate] = []

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

        # 2.0.5) If no label blocks found and field has position hint, use position-based matching
        # This is a fallback when semantic embeddings don't find matches
        if not label_block_ids and field.meta and field.meta.get("position_hint"):
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
            
            # Generate candidates directly from position-based blocks
            for pos_block_id in position_block_ids:
                if pos_block_id in block_by_id:
                    pos_block = block_by_id[pos_block_id]
                    raw_line = _first_line(pos_block.text)
                    
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0
                    
                    # Position-based score (higher for closer to corner)
                    pos_score = 0.80  # Base score for position-based
                    if candidates_by_position:
                        # Boost for closest blocks
                        closest_dist = candidates_by_position[0][1]
                        this_dist = next((d for bid, d in candidates_by_position if bid == pos_block_id), 1.0)
                        if this_dist < closest_dist * 1.5:  # Within 50% of closest
                            pos_score = 0.85
                    
                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=pos_block_id,
                            source_label_block_id=pos_block_id,  # Use same block as label
                            relation="same_block",  # Treat as same_block for position-based
                            scores={"spatial": pos_score, "type": type_ok},
                            local_context=raw_line[:120],
                        )
                    )

        # 2.1) Add semantic seeds as potential label blocks AND as direct candidates
        field_seeds = semantic_seeds.get(field.name, [])
        for seed_block_id, cosine_score in field_seeds:
            if seed_block_id not in label_block_ids and seed_block_id in block_by_id:
                label_block_ids.append(seed_block_id)
            
            # 2.1.1) If semantic similarity is high (cosine > 0.70), add as direct candidate
            # This allows embeddings to find values directly without needing a label match
            if cosine_score > 0.70 and seed_block_id in block_by_id:
                seed_block = block_by_id[seed_block_id]
                raw_line = _first_line(seed_block.text)
                
                # Type validation
                type_ok = 1.0
                if validate:
                    type_ok = 1.0 if validate(field, raw_line) else 0.0
                
                # Only add if type validation passes (or validate is None)
                if type_ok > 0.0:
                    candidates.append(FieldCandidate(
                        field=field,
                        node_id=seed_block_id,
                        source_label_block_id=seed_block_id,
                        relation="semantic_direct",
                        scores={
                            "semantic": cosine_score,
                            "type": type_ok,
                            "spatial": 0.0,  # No spatial score for direct semantic matches
                        },
                        local_context=raw_line[:120],
                    ))

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

            if table_cell and table_cell.block_ids:
                # Use first block from cell as node_id
                cell_block_id = table_cell.block_ids[0]
                if cell_block_id in block_by_id:
                    cell_block = block_by_id[cell_block_id]
                    raw_line = _first_line(cell_block.text)

                    # High priority for table candidates (use config value)
                    spatial_score = matching_cfg.get("relation_weight_same_table_row", 0.85)
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

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

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=cell_block_id,
                            source_label_block_id=label_block_ids[0],
                            relation="same_table_row",
                            scores={"spatial": spatial_score, "type": type_ok},
                            local_context=raw_line[:120],
                        )
                    )

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

            # Check right_on_same_line (priority)
            if nb.right_on_same_line is not None:
                dst_id = nb.right_on_same_line
                if dst_id not in seen_dst_ids and dst_id in block_by_id:
                    seen_dst_ids.add(dst_id)
                    dst_block = block_by_id[dst_id]
                    raw_line = _first_line(dst_block.text)

                    # Compute scores (rely on semantic embeddings and type validation, not field-specific filters)
                    spatial_score = 1.0  # same_line_right_of
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

                    # Column/section/paragraph bonuses/penalties
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)
                    dst_para = paragraph_by_block.get(dst_id)

                    if label_col is not None and dst_col is not None:
                        if label_col == dst_col:
                            spatial_score += matching_cfg["prefer_same_column_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_column_penalty"]

                    if label_sec is not None and dst_sec is not None:
                        if label_sec == dst_sec:
                            spatial_score += matching_cfg["prefer_same_section_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_section_penalty"]

                    if label_para is not None and dst_para is not None:
                        if label_para == dst_para:
                            spatial_score += matching_cfg.get("prefer_same_paragraph_bonus", 0.03)
                        # No penalty for cross-paragraph (too fine-grained)

                    spatial_score = max(0.0, min(1.0, spatial_score))  # Clamp [0,1]

                    # Memory bonuses
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

                    spatial_score = min(1.0, spatial_score + memory_bonus)  # Add memory bonus (cap at 1.0)

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=dst_id,
                            source_label_block_id=label_block_id,
                            relation="same_line_right_of",
                            scores={
                                "spatial": spatial_score,
                                "type": type_ok,
                                "memory": memory_bonus,
                            },
                            local_context=raw_line[:120],
                        )
                    )

            # Check below_on_same_column (fallback)
            if nb.below_on_same_column is not None:
                dst_id = nb.below_on_same_column
                if dst_id not in seen_dst_ids and dst_id in block_by_id:
                    seen_dst_ids.add(dst_id)
                    dst_block = block_by_id[dst_id]
                    raw_line = _first_line(dst_block.text)

                    # Compute scores (rely on semantic embeddings and type validation, not field-specific filters)
                    spatial_score = 0.7  # first_below_same_column
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

                    # Column/section/paragraph bonuses/penalties
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)
                    dst_para = paragraph_by_block.get(dst_id)

                    if label_col is not None and dst_col is not None:
                        if label_col == dst_col:
                            spatial_score += matching_cfg["prefer_same_column_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_column_penalty"]

                    if label_sec is not None and dst_sec is not None:
                        if label_sec == dst_sec:
                            spatial_score += matching_cfg["prefer_same_section_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_section_penalty"]

                    if label_para is not None and dst_para is not None:
                        if label_para == dst_para:
                            spatial_score += matching_cfg.get("prefer_same_paragraph_bonus", 0.03)
                        # No penalty for cross-paragraph (too fine-grained)

                    spatial_score = max(0.0, min(1.0, spatial_score))  # Clamp [0,1]

                    # Memory bonuses
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

                    spatial_score = min(1.0, spatial_score + memory_bonus)  # Add memory bonus (cap at 1.0)

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=dst_id,
                            source_label_block_id=label_block_id,
                            relation="first_below_same_column",
                            scores={
                                "spatial": spatial_score,
                                "type": type_ok,
                                "memory": memory_bonus,
                            },
                            local_context=raw_line[:120],
                        )
                    )

        # Helper functions for label detection
        def _split_by_label(text: str, syn_list: list[str]) -> Optional[str]:
            """Split text by label and return the part after the label."""
            if not text:
                return None
            t_norm = _normalize_text(text)
            sorted_syns = sorted(syn_list, key=len, reverse=True)
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
        
        def _is_label_only_block(block_text: str, syn_list: list[str]) -> bool:
            """Check if block text is ONLY labels (no meaningful value content)."""
            if not block_text:
                return False
            t_norm = _normalize_text(block_text)
            common_labels = [
                "inscrição", "inscricao", "seccional", "subseção", "subsecao",
                "categoria", "endereço", "endereco", "telefone", "situação", "situacao",
                "nome", "data", "valor", "sistema", "produto"
            ]
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
                    if not any(c.node_id == label_block_id and c.relation == "same_block" for c in candidates):
                        # For same_block, only create if there's content after the label
                        # Check if split_by_label would find something
                        after_label = _split_by_label(label_block.text or "", synonyms + [field.name])
                        if after_label and len(after_label.strip()) >= 2:
                            raw_line = _first_line(label_block.text)
                            
                            # Type validation only (rely on semantic embeddings for field-specific matching)
                            type_ok = 1.0
                            if validate:
                                type_ok = 1.0 if validate(field, raw_line) else 0.0

                            candidates.append(
                                FieldCandidate(
                                    field=field,
                                    node_id=label_block_id,  # destination = the block itself
                                    source_label_block_id=label_block_id,
                                    relation="same_block",
                                    scores={"spatial": 0.85, "type": type_ok},  # slightly below same_line_right_of
                                    local_context=raw_line[:120],
                                )
                            )

        # (B) Fallback: if nothing was generated OR nothing seems valid and field is ENUM,
        # do a "global enum scan" - scan all blocks looking for an enum option
        if field.type == "enum" and (
            not candidates or not any(c.scores.get("type", 0.0) > 0.0 for c in candidates)
        ):  # No candidates or no valid candidates found
            enum_opts = (field.meta or {}).get("enum_options") if hasattr(field, "meta") else None
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
                    # Check each line of the block
                    lines = b.text.splitlines() if b.text else []
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        # Skip if line is just a label (no meaningful content after potential label)
                        if _has_label_token(line, synonyms + [field.name]):
                            # Check if there's content after the label
                            after_label = _split_by_label(line, synonyms + [field.name])
                            if not after_label or len(after_label.strip()) < 2:
                                continue  # Skip lines that are just labels
                        ok, normalized = validate_and_normalize("enum", line, enum_options=enum_opts)
                        if ok and normalized:
                            # Store the normalized value in local_context for easy extraction
                            candidates.append(
                                FieldCandidate(
                                    field=field,
                                    node_id=b.id,
                                    source_label_block_id=label_block_ids[0] if label_block_ids else b.id,
                                    relation="global_enum_scan",
                                    scores={"spatial": 0.75, "type": 1.0},  # lower priority than same_block
                                    local_context=normalized,  # Store normalized value directly
                                )
                            )
                            break  # Found a good candidate for this block, check next block
                    if candidates and candidates[-1].relation == "global_enum_scan":
                        break  # Found enum candidate, stop searching

        # 4) Dedupe and sort by score
        candidates = _dedupe_candidates(candidates)

        # 4.5) Avoid cross-column jumps if same-column candidate exists
        # Get column of label (if any)
        if label_block_ids:
            label_col = column_by_block.get(label_block_ids[0])
            if label_col is not None:
                # Filter: prefer same-column candidates
                same_col = [c for c in candidates if column_by_block.get(c.node_id) == label_col]
                cross_col = [c for c in candidates if column_by_block.get(c.node_id) != label_col]
                # If we have same-column candidates, don't include cross-column unless no valid same-column
                if same_col:
                    # Keep same-column candidates, but allow cross-column if they're very high score
                    valid_same_col = [c for c in same_col if c.scores.get("type", 0.0) > 0.0]
                    if valid_same_col:
                        candidates = same_col + [c for c in cross_col if c.scores.get("type", 0.0) > 0.8]

        # 3.5) Process semantic seed blocks (if any) - moved before dedupe
        # For each semantic seed, look for neighbors and add candidates with semantic boost
        field_seeds = semantic_seeds.get(field.name, [])
        seed_block_to_score = {bid: score for bid, score in field_seeds}

        # Type-aware gate: require higher cosine for digit-requiring types
        REQUIRES_DIGITS = {"id_simple", "cep", "money", "date", "int", "float", "percent"}
        min_semantic_threshold = 0.60 if field.type in REQUIRES_DIGITS else 0.35

        for seed_block_id, cosine_score in field_seeds:
            # Filter: require higher threshold for digit-requiring types
            if cosine_score < min_semantic_threshold:
                continue
            if seed_block_id not in block_by_id:
                continue

            nb = neighborhood.get(seed_block_id)
            if not nb:
                continue

            # Check right_on_same_line from seed
            if nb.right_on_same_line is not None:
                dst_id = nb.right_on_same_line
                if dst_id in block_by_id and dst_id not in seen_dst_ids:
                    dst_block = block_by_id[dst_id]
                    # Type-aware filter: digit-requiring types need digits in destination
                    if field.type in REQUIRES_DIGITS:
                        if not re.search(r"\d", dst_block.text or ""):
                            continue  # Skip if no digits for numeric types
                    seen_dst_ids.add(dst_id)
                    raw_line = _first_line(dst_block.text)

                    spatial_score = 1.0  # same_line_right_of
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

                    # Semantic boost
                    semantic_boost = min(1.0, cosine_score / 0.85) if cosine_score > 0 else 0.0

                    # Column/section bonuses
                    seed_col = column_by_block.get(seed_block_id)
                    seed_sec = section_by_block.get(seed_block_id)
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)

                    if seed_col is not None and dst_col is not None:
                        if seed_col == dst_col:
                            spatial_score += matching_cfg["prefer_same_column_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_column_penalty"]

                    if seed_sec is not None and dst_sec is not None:
                        if seed_sec == dst_sec:
                            spatial_score += matching_cfg["prefer_same_section_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_section_penalty"]

                    spatial_score = max(0.0, min(1.0, spatial_score))

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=dst_id,
                            source_label_block_id=seed_block_id,
                            relation="same_line_right_of",
                            scores={
                                "spatial": spatial_score,
                                "type": type_ok,
                                "semantic": cosine_score,
                            },
                            local_context=raw_line[:120],
                        )
                    )

            # Check below_on_same_column from seed
            if nb.below_on_same_column is not None:
                dst_id = nb.below_on_same_column
                if dst_id in block_by_id and dst_id not in seen_dst_ids:
                    dst_block = block_by_id[dst_id]
                    # Type-aware filter: digit-requiring types need digits in destination
                    if field.type in REQUIRES_DIGITS:
                        if not re.search(r"\d", dst_block.text or ""):
                            continue  # Skip if no digits for numeric types
                    seen_dst_ids.add(dst_id)
                    raw_line = _first_line(dst_block.text)

                    spatial_score = 0.7  # first_below_same_column
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

                    # Semantic boost
                    semantic_boost = min(1.0, cosine_score / 0.85) if cosine_score > 0 else 0.0

                    # Column/section bonuses
                    seed_col = column_by_block.get(seed_block_id)
                    seed_sec = section_by_block.get(seed_block_id)
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)

                    if seed_col is not None and dst_col is not None:
                        if seed_col == dst_col:
                            spatial_score += matching_cfg["prefer_same_column_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_column_penalty"]

                    if seed_sec is not None and dst_sec is not None:
                        if seed_sec == dst_sec:
                            spatial_score += matching_cfg["prefer_same_section_bonus"]
                        else:
                            spatial_score -= matching_cfg["cross_section_penalty"]

                    spatial_score = max(0.0, min(1.0, spatial_score))

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=dst_id,
                            source_label_block_id=seed_block_id,
                            relation="first_below_same_column",
                            scores={
                                "spatial": spatial_score,
                                "type": type_ok,
                                "semantic": cosine_score,
                            },
                            local_context=raw_line[:120],
                        )
                    )

        # 4) Dedupe and sort by score
        candidates = _dedupe_candidates(candidates)

        # 4.5) Avoid cross-column jumps if same-column candidate exists
        # Get column of label (if any)
        if label_block_ids:
            label_col = column_by_block.get(label_block_ids[0])
            if label_col is not None:
                # Filter: prefer same-column candidates
                same_col = [c for c in candidates if column_by_block.get(c.node_id) == label_col]
                cross_col = [c for c in candidates if column_by_block.get(c.node_id) != label_col]
                # If we have same-column candidates, don't include cross-column unless no valid same-column
                if same_col:
                    # Keep same-column candidates, but allow cross-column if they're very high score
                    valid_same_col = [c for c in same_col if c.scores.get("type", 0.0) > 0.0]
                    if valid_same_col:
                        candidates = same_col + [c for c in cross_col if c.scores.get("type", 0.0) > 0.8]

        # Sort by priority: table candidates first, then by score (with semantic boost and memory)
        def sort_key(c: FieldCandidate) -> tuple[int, float, float]:
            # Priority: 0 = table, 1 = same_line, 2 = same_block/semantic_direct, 3 = global_enum_scan (for enum fields), 4 = below, 5 = global_enum_scan (others)
            if c.relation == "same_table_row":
                priority = 0
            elif c.relation == "same_line_right_of":
                priority = 1
            elif c.relation == "same_block" or c.relation == "semantic_direct":
                priority = 2
            elif c.relation == "global_enum_scan" and field.type == "enum":
                # Boost global_enum_scan for enum fields (they're very reliable)
                priority = 3
            elif c.relation == "first_below_same_column":
                priority = 4
            else:  # global_enum_scan (non-enum) or others
                priority = 5

            # Memory bonus flag (prefer candidates with memory bonus)
            has_memory = 1.0 if c.scores.get("memory", 0.0) > 0.0 else 0.0

            # Updated score: type (50%) + spatial (25%) + semantic (25%)
            # Increased semantic weight from 10% to 25% for better embedding-based matching
            # Note: spatial_score already includes memory bonus
            type_score = c.scores.get("type", 0.0)
            spatial_score = c.scores.get("spatial", 0.0)
            semantic_score = c.scores.get("semantic", 0.0)
            semantic_boost = min(1.0, semantic_score / 0.85) if semantic_score > 0 else 0.0
            score = 0.50 * type_score + 0.25 * spatial_score + 0.25 * semantic_boost
            return (priority, -has_memory, -score)  # Negative for descending (prefer memory, then score)

        candidates.sort(key=sort_key)
        # Take top_k
        results[field.name] = candidates[:top_k]

    return results

