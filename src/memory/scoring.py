"""Scoring helpers for applying memory bonuses in matching."""

from __future__ import annotations

from typing import Optional, Tuple

from .pattern_memory import PatternMemory
from .schema import FingerprintObs, OffsetObs


def _normalize_text(s: str) -> str:
    """Normalize text: lowercase, remove accents, collapse spaces."""
    import re
    import unicodedata

    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def memory_bonus_for_label_text(
    mem: Optional[PatternMemory], field_name: str, block_text: str, synonyms_weight: float
) -> float:
    """Compute bonus if block_text contains learned synonym.

    Args:
        mem: PatternMemory instance (None if disabled).
        field_name: Field name.
        block_text: Text of block to check.
        synonyms_weight: Weight for synonym match.

    Returns:
        Bonus score (0.0 or synonyms_weight).
    """
    if not mem:
        return 0.0

    learned_synonyms = mem.get_synonyms(field_name, max_k=20)
    if not learned_synonyms:
        return 0.0

    block_norm = _normalize_text(block_text)
    for syn in learned_synonyms:
        if syn in block_norm:
            return synonyms_weight

    return 0.0


def memory_bonus_for_offset(
    mem: Optional[PatternMemory],
    field_name: str,
    label_bbox: Tuple[float, float, float, float],
    value_bbox: Tuple[float, float, float, float],
    relation: str,
    offset_bonus: float,
) -> float:
    """Compute bonus if offset matches learned pattern.

    Args:
        mem: PatternMemory instance (None if disabled).
        field_name: Field name.
        label_bbox: Normalized bbox of label.
        value_bbox: Normalized bbox of value.
        relation: Spatial relation.
        offset_bonus: Weight for offset match.

    Returns:
        Bonus score (0.0 or offset_bonus).
    """
    if not mem:
        return 0.0

    hints = mem.get_offset_hints(field_name)
    if not hints:
        return 0.0

    # Calculate current offset
    label_center_x = (label_bbox[0] + label_bbox[2]) / 2.0
    label_center_y = (label_bbox[1] + label_bbox[3]) / 2.0
    value_center_x = (value_bbox[0] + value_bbox[2]) / 2.0
    value_center_y = (value_bbox[1] + value_bbox[3]) / 2.0

    dx = value_center_x - label_center_x
    dy = value_center_y - label_center_y

    # Check if matches any learned offset
    for obs in hints:
        if obs.relation == relation:
            if abs(obs.dx - dx) < obs.tol and abs(obs.dy - dy) < obs.tol:
                return offset_bonus

    return 0.0


def memory_bonus_for_fingerprint(
    mem: Optional[PatternMemory],
    field_name: str,
    label_center: Tuple[float, float],
    value_center: Tuple[float, float],
    section_id: Optional[int],
    column_id: Optional[int],
    grid_res: Tuple[int, int],
    fingerprint_bonus: float,
) -> float:
    """Compute bonus if fingerprint matches learned pattern.

    Args:
        mem: PatternMemory instance (None if disabled).
        field_name: Field name.
        label_center: Normalized center of label (x, y).
        value_center: Normalized center of value (x, y).
        section_id: Optional section ID.
        column_id: Optional column ID.
        grid_res: Grid resolution (nx, ny).
        fingerprint_bonus: Weight for fingerprint match.

    Returns:
        Bonus score (0.0 or fingerprint_bonus).
    """
    if not mem:
        return 0.0

    hints = mem.get_fingerprint_hints(field_name)
    if not hints:
        return 0.0

    # Quantize to grid
    from .pattern_memory import _quantize_to_grid

    label_grid = _quantize_to_grid(label_center, grid_res)
    value_grid = _quantize_to_grid(value_center, grid_res)

    # Check if matches any learned fingerprint
    for obs in hints:
        if (
            obs.grid_label == label_grid
            and obs.grid_value == value_grid
            and (obs.section_hint is None or obs.section_hint == section_id)
            and (obs.column_hint is None or obs.column_hint == column_id)
        ):
            return fingerprint_bonus

    return 0.0

