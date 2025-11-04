"""Text extraction from field candidates with multi-line/multi-token scoring."""

from __future__ import annotations

import re
from typing import Optional

from ..core.models import Block, FieldCandidate, LayoutGraph, SchemaField
from ..validation.validators import validate_and_normalize

LABEL_SEP_RE = re.compile(r"[:：]\s*")  # ':' variants


def _text_candidates(
    dst_block: Block,
    layout: LayoutGraph,
    field_type: str = "text",
    max_lines_window: int = 3,
    max_tokens: int = 12,
) -> list[str]:
    """Generate text candidates from destination block.

    Returns a ranked list of small text snippets to try:
    1) Individual lines (first N lines)
    2) 2-line and 3-line windows (joined with space)
    3) First K tokens of the first 1-2 lines (sliding windows of up to 3 tokens)

    For text_multiline, limits windows to same section to avoid leaking.

    Args:
        dst_block: Destination block.
        layout: LayoutGraph for section metadata.
        field_type: Field type (text_multiline uses section-aware logic).
        max_lines_window: Maximum lines to consider for windows.
        max_tokens: Maximum tokens to extract per line.

    Returns:
        List of candidate text strings (deduplicated, preserving order).
    """
    lines = [ln.strip() for ln in dst_block.text.splitlines() if ln.strip()]
    if not lines:
        return []

    # Get section of this block (for text_multiline)
    section_by_block = getattr(layout, "section_id_by_block", {})
    dst_section = section_by_block.get(dst_block.id)

    candidates: list[str] = []
    seen = set()

    # 1) Individual lines (first N lines)
    for line in lines[:max_lines_window]:
        if line and line not in seen:
            seen.add(line)
            candidates.append(line)

    # 2) 2-line and 3-line windows
    # For text_multiline, limit to same section (only if we have section info)
    if field_type == "text_multiline" and dst_section is not None:
        # Only create windows within this block (assume same section)
        for window_size in [2, 3]:
            for i in range(len(lines) - window_size + 1):
                window_text = " ".join(lines[i : i + window_size])
                if window_text and window_text not in seen:
                    seen.add(window_text)
                    candidates.append(window_text)
    else:
        # Normal behavior for other types
        for window_size in [2, 3]:
            for i in range(len(lines) - window_size + 1):
                window_text = " ".join(lines[i : i + window_size])
                if window_text and window_text not in seen:
                    seen.add(window_text)
                    candidates.append(window_text)

    # 3) Token windows from first 1-2 lines
    max_lines_for_tokens = min(2, len(lines))
    for i in range(max_lines_for_tokens):
        tokens = re.findall(r"\S+", lines[i])
        tokens = tokens[:max_tokens]

        # Individual tokens
        for token in tokens:
            if token and token not in seen:
                seen.add(token)
                candidates.append(token)

        # Sliding windows of 2-3 tokens
        for n in [2, 3]:
            for j in range(len(tokens) - n + 1):
                window = " ".join(tokens[j : j + n])
                if window and window not in seen:
                    seen.add(window)
                    candidates.append(window)

    return candidates


def _position_bonus(field_meta: dict[str, object] | None, bbox: tuple[float, float, float, float]) -> float:
    """Returns 0.0 or small bonus (e.g., 0.05) if bbox center falls into the hinted quadrant.

    Args:
        field_meta: SchemaField meta dict (may contain position_hint).
        bbox: Normalized bbox (x0, y0, x1, y1) in [0,1].

    Returns:
        Bonus score (0.0 or 0.05).
    """
    if not field_meta:
        return 0.0

    position_hint = field_meta.get("position_hint")
    if not position_hint:
        return 0.0

    x0, y0, x1, y1 = bbox
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0

    # Determine quadrant
    is_left = center_x < 0.5
    is_top = center_y < 0.5

    if position_hint == "top-left" and is_left and is_top:
        return 0.05
    if position_hint == "top-right" and not is_left and is_top:
        return 0.05
    if position_hint == "bottom-left" and is_left and not is_top:
        return 0.05
    if position_hint == "bottom-right" and not is_left and not is_top:
        return 0.05

    return 0.0


def _score_candidate(
    field_type: str, text: str, relation: str, base_ok: bool, position_bonus: float = 0.0
) -> float:
    """Score a candidate text for a field (field-agnostic).

    Args:
        field_type: Field type string.
        text: Candidate text.
        relation: Spatial relation ("same_line_right_of" or "first_below_same_column").
        base_ok: Whether validator returned ok.

    Returns:
        Score between 0.0 and 1.0.
    """
    # Base score: 70% weight on validation
    score = 0.7 * (1.0 if base_ok else 0.0)

    # Spatial bonus: 10% for same_line
    if relation == "same_line_right_of":
        score += 0.1

    # Type-specific bonuses (independent of document)
    field_type = field_type.lower()
    if field_type == "id_simple" and re.search(r"[A-Za-z0-9./-]{3,}", text):
        score += 0.05
    if field_type == "uf" and re.search(r"\b[A-Z]{2}\b", text):
        score += 0.05
    if field_type == "date" and re.search(r"\d", text):
        score += 0.05
    if field_type == "money" and re.search(r"\d", text):
        score += 0.05

    # Position bonus
    score += position_bonus

    return min(score, 1.0)


def extract_from_candidate(
    field: SchemaField, cand: FieldCandidate, layout: LayoutGraph
) -> tuple[Optional[str], float, dict]:
    """Given a FieldCandidate, produce a (value, confidence, trace) tuple.

    Generates multiple candidates (lines, windows, tokens) and scores them,
    returning the best one.

    Args:
        field: SchemaField being extracted.
        cand: FieldCandidate with node_id and relation.
        layout: LayoutGraph with blocks.

    Returns:
        Tuple of (value, confidence, trace_dict).
        If no candidate passes validation, returns (None, 0.0, trace_with_reason).
    """
    # Get destination block
    dst_block = next((b for b in layout.blocks if b.id == cand.node_id), None)
    if not dst_block:
        return None, 0.0, {"node_id": cand.node_id, "relation": cand.relation, "reason": "block_not_found"}

    # Generate candidates (section-aware for text_multiline)
    cands = _text_candidates(dst_block, layout, field.type or "text", max_lines_window=3, max_tokens=12)

    best = (None, 0.0, None)  # (value, score, chosen_text)

    # Get enum_options from field meta if available
    enum_options = field.meta.get("enum_options") if field.meta else None

    # Calculate position bonus once
    position_bonus = _position_bonus(field.meta, dst_block.bbox)

    for txt in cands:
        # Remove "label: " if present
        txt_clean = LABEL_SEP_RE.split(txt, 1)[-1] if ":" in txt else txt

        # Validate and normalize (with enum_options if enum type)
        ok, normalized = validate_and_normalize(
            field.type or "text", txt_clean, enum_options=enum_options
        )

        # Score candidate (with position bonus)
        score = _score_candidate(
            field.type or "text", txt_clean, cand.relation, ok, position_bonus
        )

        if ok and score > best[1]:
            best = (normalized, score, txt_clean)

    if best[0] is None:
        return None, 0.0, {"node_id": cand.node_id, "relation": cand.relation, "reason": "validation_failed"}

    # Confidence final independente de doc
    confidence = 0.90 if cand.relation == "same_line_right_of" else 0.80

    return best[0], confidence, {"node_id": cand.node_id, "relation": cand.relation}
