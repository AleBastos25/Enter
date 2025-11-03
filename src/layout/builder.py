"""Layout builder for constructing spatial graphs from PDF blocks.

TODO: introduce explicit `line` nodes in next iteration (page→line), leveraging span/line geometry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..core.models import Block, Document, LayoutGraph, ReadingNode, SpatialEdge


@dataclass
class LayoutThresholds:
    """Thresholds for spatial edge detection (defaults for MVP0)."""

    same_line_y_overlap: float = 0.60
    right_of_dx_chars: float = 8.0
    first_below_dy_lineheights: float = 1.5
    same_column_x_overlap: float = 0.50


@dataclass
class SpatialNeighborhood:
    """Spatial neighborhood index for a block (O(1) access to neighbors)."""

    right_on_same_line: Optional[int] = None
    left_on_same_line: Optional[int] = None
    below_on_same_column: Optional[int] = None
    above_on_same_column: Optional[int] = None


# ============================================================================
# Geometry helpers (working with normalized bboxes [0,1])
# ============================================================================


def _height(b: Block) -> float:
    """Get block height (normalized)."""
    return b.bbox[3] - b.bbox[1]


def _width(b: Block) -> float:
    """Get block width (normalized)."""
    return b.bbox[2] - b.bbox[0]


def _vertical_overlap_ratio(a: Block, b: Block) -> float:
    """Compute vertical overlap ratio: overlap_y / min(height(a), height(b)).

    Returns a value in [0, 1].
    """
    y0_a, y1_a = a.bbox[1], a.bbox[3]
    y0_b, y1_b = b.bbox[1], b.bbox[3]
    overlap_y = max(0.0, min(y1_a, y1_b) - max(y0_a, y0_b))
    min_height = min(_height(a), _height(b))
    if min_height <= 0:
        return 0.0
    return min(1.0, overlap_y / min_height)


def _horizontal_overlap_ratio(a: Block, b: Block) -> float:
    """Compute horizontal overlap ratio: overlap_x / min(width(a), width(b)).

    Returns a value in [0, 1].
    """
    x0_a, x1_a = a.bbox[0], a.bbox[2]
    x0_b, x1_b = b.bbox[0], b.bbox[2]
    overlap_x = max(0.0, min(x1_a, x1_b) - max(x0_a, x0_b))
    min_width = min(_width(a), _width(b))
    if min_width <= 0:
        return 0.0
    return min(1.0, overlap_x / min_width)


def _mean_char_width_norm(b: Block) -> float:
    """Compute mean character width (normalized) for a block.

    Returns: (x1 - x0) / len(non_whitespace_chars), with floor 1e-6.
    """
    text_no_ws = re.sub(r"\s+", "", b.text)
    len_text = len(text_no_ws) or 1
    bbox_width = _width(b)
    if bbox_width <= 0:
        return 1e-6
    return max(1e-6, bbox_width / len_text)


def _dx_norm(src: Block, dst: Block) -> float:
    """Horizontal distance (normalized): dst.x0 - src.x1.

    Positive = dst is to the right of src.
    Returns min(0, actual) to clip negative values (overlap -> 0 gap).
    """
    return max(0.0, dst.bbox[0] - src.bbox[2])


def _dy_norm(src: Block, dst: Block) -> float:
    """Vertical distance (normalized): dst.y0 - src.y1.

    Positive = dst is below src.
    Returns min(0, actual) to clip negative values (overlap -> 0 gap).
    """
    return max(0.0, dst.bbox[1] - src.bbox[3])


def _dx_chars(src: Block, dst: Block) -> float:
    """Horizontal distance in character units.

    Returns: max(0, dx_norm) / max(_mean_char_width_norm(src), 1e-6).
    """
    dx = _dx_norm(src, dst)
    char_width = max(_mean_char_width_norm(src), 1e-6)
    return dx / char_width


def _line_height_units(src: Block, dst: Block) -> float:
    """Vertical distance in line height units.

    Returns: max(0, dy_norm) / max(_height(src), 1e-6).
    """
    dy = _dy_norm(src, dst)
    src_height = max(_height(src), 1e-6)
    return dy / src_height


# ============================================================================
# Spatial edge computation
# ============================================================================


def _find_same_line_right_candidate(
    src: Block, candidates: list[Block], thresholds: LayoutThresholds
) -> Optional[tuple[Block, float]]:
    """Find best candidate to the right on the same line.

    Returns (best_block, dx_chars) or None if no valid candidate.
    """
    best = None
    best_dx = float("inf")

    for dst in candidates:
        if dst.id == src.id:
            continue

        # Must be strictly to the right
        if dst.bbox[0] <= src.bbox[2]:
            continue

        # Must have sufficient vertical overlap
        if _vertical_overlap_ratio(src, dst) < thresholds.same_line_y_overlap:
            continue

        dx = _dx_chars(src, dst)
        if dx < best_dx:
            best_dx = dx
            best = dst

    if best and best_dx <= thresholds.right_of_dx_chars:
        return (best, best_dx)
    return None


def _find_first_below_candidate(
    src: Block, candidates: list[Block], thresholds: LayoutThresholds
) -> Optional[tuple[Block, float]]:
    """Find best candidate below in the same column.

    Returns (best_block, dy_lines) or None if no valid candidate.
    """
    best = None
    best_dy = float("inf")

    for dst in candidates:
        if dst.id == src.id:
            continue

        # Must be strictly below
        if dst.bbox[1] <= src.bbox[3]:
            continue

        # Must have sufficient horizontal overlap
        if _horizontal_overlap_ratio(src, dst) < thresholds.same_column_x_overlap:
            continue

        dy = _line_height_units(src, dst)
        if dy < best_dy:
            best_dy = dy
            best = dst

    if best and best_dy <= thresholds.first_below_dy_lineheights:
        return (best, best_dy)
    return None


def _make_spatial_edges_and_neighborhood(
    blocks: list[Block], thresholds: LayoutThresholds
) -> tuple[list[SpatialEdge], dict[int, SpatialNeighborhood]]:
    """Build spatial edges (max 1 per src) and neighborhood index.

    Returns:
        (edges, neighborhood_dict)
    """
    edges: list[SpatialEdge] = []
    neighborhood: dict[int, SpatialNeighborhood] = {}

    # Build lookup by id
    block_by_id = {b.id: b for b in blocks}

    for src in blocks:
        nbh = SpatialNeighborhood()

        # A) same_line_right_of (priority)
        right_candidate = _find_same_line_right_candidate(src, blocks, thresholds)
        if right_candidate:
            dst, dx_chars = right_candidate
            edges.append(
                SpatialEdge(
                    src_id=src.id,
                    dst_id=dst.id,
                    type="same_line_right_of",
                    weights={"dx_chars": dx_chars},
                )
            )
            nbh.right_on_same_line = dst.id

        # B) first_below_same_column (fallback if no same-line edge)
        if not right_candidate:
            below_candidate = _find_first_below_candidate(src, blocks, thresholds)
            if below_candidate:
                dst, dy_lines = below_candidate
                edges.append(
                    SpatialEdge(
                        src_id=src.id,
                        dst_id=dst.id,
                        type="first_below_same_column",
                        weights={"dy_lines": dy_lines},
                    )
                )
                nbh.below_on_same_column = dst.id

        # Neighborhood: fill all directions (independent of edge emission)
        # Right on same line
        if not nbh.right_on_same_line:
            right_cand = _find_same_line_right_candidate(src, blocks, thresholds)
            if right_cand:
                nbh.right_on_same_line = right_cand[0].id

        # Left on same line (reverse search)
        left_best = None
        left_dx = float("inf")
        for dst in blocks:
            if dst.id == src.id:
                continue
            # Must be strictly to the left
            if dst.bbox[2] >= src.bbox[0]:
                continue
            if _vertical_overlap_ratio(src, dst) < thresholds.same_line_y_overlap:
                continue
            # dx in reverse direction
            dx = _dx_chars(dst, src)  # reverse src/dst
            if dx < left_dx:
                left_dx = dx
                left_best = dst
        if left_best and left_dx <= thresholds.right_of_dx_chars:
            nbh.left_on_same_line = left_best.id

        # Below on same column (already computed if edge exists, but fill if missing)
        if not nbh.below_on_same_column:
            below_cand = _find_first_below_candidate(src, blocks, thresholds)
            if below_cand:
                nbh.below_on_same_column = below_cand[0].id

        # Above on same column (reverse search)
        above_best = None
        above_dy = float("inf")
        for dst in blocks:
            if dst.id == src.id:
                continue
            # Must be strictly above
            if dst.bbox[3] >= src.bbox[1]:
                continue
            if _horizontal_overlap_ratio(src, dst) < thresholds.same_column_x_overlap:
                continue
            # dy in reverse direction
            dy = _line_height_units(dst, src)  # reverse src/dst
            if dy < above_dy:
                above_dy = dy
                above_best = dst
        if above_best and above_dy <= thresholds.first_below_dy_lineheights:
            nbh.above_on_same_column = above_best.id

        neighborhood[src.id] = nbh

    return edges, neighborhood


# ============================================================================
# Reading node construction
# ============================================================================


def _make_page_node(blocks: list[Block]) -> list[ReadingNode]:
    """Create a minimal page reading node (MVP0: no line nodes yet).

    Returns a list with a single ReadingNode of type "page".
    """
    return [
        ReadingNode(
            id=0,
            type="page",
            parent=None,
            children=[],
            ref_block_ids=[b.id for b in blocks],
        )
    ]


# ============================================================================
# Main builder
# ============================================================================


def build_layout(document: Document, blocks: list[Block]) -> LayoutGraph:
    """Build a LayoutGraph from blocks with spatial edges and neighborhood.

    Args:
        document: Document instance (used for validation).
        blocks: List of Block objects, assumed sorted (top→down, left→right).

    Returns:
        LayoutGraph with blocks, reading nodes, spatial edges, and neighborhood index.
    """
    # Validate all blocks are from the same page
    pages = set(b.page for b in blocks)
    assert len(pages) == 1, f"All blocks must be from the same page, found: {pages}"

    # Build reading nodes (minimal: just page)
    reading_nodes = _make_page_node(blocks)

    # Build spatial edges and neighborhood
    thresholds = LayoutThresholds()
    edges, neighborhood = _make_spatial_edges_and_neighborhood(blocks, thresholds)

    # Create LayoutGraph
    layout_graph = LayoutGraph(
        blocks=blocks,
        reading_nodes=reading_nodes,
        spatial_edges=edges,
        tables=[],
    )

    # Attach neighborhood as extra attribute (temporary hack, not in model yet)
    # Use object.__setattr__ to bypass frozen dataclass restriction
    object.__setattr__(layout_graph, "neighborhood", neighborhood)

    return layout_graph

