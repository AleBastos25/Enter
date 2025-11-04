"""Matcher for finding field candidates from label blocks using spatial neighborhood."""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional

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
    """
    candidates = []

    for block in blocks:
        if _contains_any(block.text, synonyms):
            # Compute priority score (higher = better)
            # Prefer shorter blocks (likely labels)
            text_len = len(block.text)
            priority = 1.0 / (1.0 + text_len * 0.01)
            # Boost if larger font
            if block.font_size:
                priority += block.font_size * 0.01
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


def match_fields(
    schema_fields: list[SchemaField],
    layout: LayoutGraph,
    *,
    validate: Optional[Callable[[SchemaField, str], bool]] = None,
    top_k: int = 2,
) -> dict[str, list[FieldCandidate]]:
    """Match fields to value candidates using spatial neighborhood.

    Args:
        schema_fields: List of SchemaField objects with synonyms.
        layout: LayoutGraph with blocks and neighborhood index.
        validate: Optional function to soft-validate field type (returns bool).
        top_k: Maximum number of candidates per field.

    Returns:
        Dictionary mapping field_name -> list[FieldCandidate] (sorted by score desc).
    """
    # Get neighborhood index
    neighborhood = getattr(layout, "neighborhood", {})
    block_by_id = {b.id: b for b in layout.blocks}

    results: dict[str, list[FieldCandidate]] = {}

    for field in schema_fields:
        candidates: list[FieldCandidate] = []

        # 1) Build synonyms
        synonyms = _build_synonyms(field)

        # 2) Find label blocks
        label_block_ids = _find_label_blocks(layout.blocks, synonyms)

        # Load matching config (needed for both table and neighborhood matching)
        matching_cfg = _load_matching_config()

        # 2.5) Check tables first (before neighborhood fallback)
        tables = getattr(layout, "tables", [])
        if tables and label_block_ids:
            # Try to find cell by label in tables
            label_patterns = synonyms + [field.name.lower()]
            table_cell = find_cell_by_label(tables, label_patterns, search_in="any", return_type="cell")

            if table_cell and table_cell.block_ids:
                # Use first block from cell as node_id
                cell_block_id = table_cell.block_ids[0]
                if cell_block_id in block_by_id:
                    cell_block = block_by_id[cell_block_id]
                    raw_line = _first_line(cell_block.text)

                    # High priority for table candidates
                    spatial_score = 0.85  # same_table_row
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

        # Get column/section metadata
        column_by_block = getattr(layout, "column_id_by_block", {})
        section_by_block = getattr(layout, "section_id_by_block", {})

        for label_block_id in label_block_ids:
            nb = neighborhood.get(label_block_id)
            if not nb:
                continue

            label_col = column_by_block.get(label_block_id)
            label_sec = section_by_block.get(label_block_id)

            # Check right_on_same_line (priority)
            if nb.right_on_same_line is not None:
                dst_id = nb.right_on_same_line
                if dst_id not in seen_dst_ids and dst_id in block_by_id:
                    seen_dst_ids.add(dst_id)
                    dst_block = block_by_id[dst_id]
                    raw_line = _first_line(dst_block.text)

                    # Compute scores
                    spatial_score = 1.0  # same_line_right_of
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

                    # Column/section bonuses/penalties
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)

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

                    spatial_score = max(0.0, min(1.0, spatial_score))  # Clamp [0,1]

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=dst_id,
                            source_label_block_id=label_block_id,
                            relation="same_line_right_of",
                            scores={"spatial": spatial_score, "type": type_ok},
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

                    # Compute scores
                    spatial_score = 0.7  # first_below_same_column
                    type_ok = 1.0
                    if validate:
                        type_ok = 1.0 if validate(field, raw_line) else 0.0

                    # Column/section bonuses/penalties
                    dst_col = column_by_block.get(dst_id)
                    dst_sec = section_by_block.get(dst_id)

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

                    spatial_score = max(0.0, min(1.0, spatial_score))  # Clamp [0,1]

                    candidates.append(
                        FieldCandidate(
                            field=field,
                            node_id=dst_id,
                            source_label_block_id=label_block_id,
                            relation="first_below_same_column",
                            scores={"spatial": spatial_score, "type": type_ok},
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

        # Sort by priority: table candidates first, then by score
        def sort_key(c: FieldCandidate) -> tuple[int, float]:
            # Priority: 0 = table, 1 = same_line, 2 = below
            priority = 0 if c.relation == "same_table_row" else (1 if c.relation == "same_line_right_of" else 2)
            score = 0.65 * c.scores.get("type", 0.0) + 0.35 * c.scores.get("spatial", 0.0)
            return (priority, -score)  # Negative for descending

        candidates.sort(key=sort_key)
        # Take top_k
        results[field.name] = candidates[:top_k]

    return results

