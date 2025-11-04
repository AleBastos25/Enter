"""Layout builder for constructing spatial graphs from PDF blocks with line nodes, columns, and sections."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from ..core.models import Block, Document, LayoutGraph, ReadingNode, SpatialEdge
from .heuristics import detect_columns, detect_sections


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


def _load_config() -> dict:
    """Load layout config from YAML, with fallback to defaults."""
    config_path = Path("configs/layout.yaml")
    defaults = {
        "reading": {"make_line_nodes": True, "line_join_y_overlap": 0.60},
        "columns": {
            "enabled": True,
            "max_k": 3,
            "min_gap_x_norm": 0.05,
            "min_col_width_norm": 0.12,
        },
        "sections": {
            "enabled": True,
            "title_font_boost": 1.15,
            "min_above_gap_lines": 1.3,
        },
        "matching": {
            "prefer_same_column_bonus": 0.08,
            "prefer_same_section_bonus": 0.05,
            "cross_column_penalty": 0.06,
            "cross_section_penalty": 0.04,
        },
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                # Merge with defaults
                config = defaults.copy()
                for key in config:
                    if key in loaded:
                        config[key].update(loaded[key])
                return config
        except Exception:
            return defaults
    return defaults


def _make_line_nodes(blocks: list[Block], config: dict) -> tuple[list[ReadingNode], dict[int, list[int]]]:
    """Create explicit line nodes from blocks.

    Splits blocks by newlines to create individual line nodes.

    Returns:
        (line_nodes, line_id_by_block) where line_id_by_block maps block_id -> list of line_ids.
    """
    if not config.get("reading", {}).get("make_line_nodes", True):
        return [], {}

    line_nodes: list[ReadingNode] = []
    line_id_by_block: dict[int, list[int]] = {}
    line_id = 1  # Start at 1 (page is 0)

    for block in blocks:
        lines = block.text.splitlines()
        block_line_ids = []

        for line_text in lines:
            if not line_text.strip():
                continue

            # Estimate line bbox from block bbox (rough - split vertically)
            # For simplicity, assume equal distribution
            block_height = block.bbox[3] - block.bbox[1]
            line_height = block_height / max(len(lines), 1)

            # Find which line this is (approximate y position)
            line_idx = lines.index(line_text)
            y0 = block.bbox[1] + (line_idx * line_height)
            y1 = y0 + line_height

            line_bbox = (block.bbox[0], y0, block.bbox[2], y1)

            line_node = ReadingNode(
                id=line_id,
                type="line",
                parent=0,  # Page node
                children=[],
                ref_block_ids=[block.id],
                meta={"bbox": line_bbox, "text": line_text.strip()},
            )

            line_nodes.append(line_node)
            block_line_ids.append(line_id)
            line_id += 1

        if block_line_ids:
            line_id_by_block[block.id] = block_line_ids

    return line_nodes, line_id_by_block


def _make_page_node(blocks: list[Block], line_nodes: list[ReadingNode]) -> list[ReadingNode]:
    """Create page reading node with line children.

    Returns a list with a single ReadingNode of type "page".
    """
    page_node = ReadingNode(
        id=0,
        type="page",
        parent=None,
        children=[ln.id for ln in line_nodes],
        ref_block_ids=[b.id for b in blocks],
    )
    return [page_node]


# ============================================================================
# Main builder
# ============================================================================


def _assign_column_section_to_blocks(
    line_nodes: list[ReadingNode],
    line_id_by_block: dict[int, list[int]],
    column_by_line: dict[int, int],
    section_by_line: dict[int, int],
) -> tuple[dict[int, int], dict[int, int]]:
    """Assign column_id and section_id to blocks based on their line nodes.

    Uses mode (most common) of line assignments for each block.

    Returns:
        (column_id_by_block, section_id_by_block)
    """
    column_id_by_block: dict[int, int] = {}
    section_id_by_block: dict[int, int] = {}

    for block_id, line_ids in line_id_by_block.items():
        # Get column_ids for lines of this block
        block_columns = [column_by_line.get(ln_id) for ln_id in line_ids if ln_id in column_by_line]
        if block_columns:
            # Use mode (most common)
            column_id_by_block[block_id] = statistics.mode(block_columns)

        # Get section_ids for lines of this block
        block_sections = [section_by_line.get(ln_id) for ln_id in line_ids if ln_id in section_by_line]
        if block_sections:
            # Use mode (most common)
            section_id_by_block[block_id] = statistics.mode(block_sections)

    return column_id_by_block, section_id_by_block


def build_layout(document: Document, blocks: list[Block]) -> LayoutGraph:
    """Build a LayoutGraph from blocks with spatial edges, neighborhood, lines, columns, and sections.

    Args:
        document: Document instance (used for validation).
        blocks: List of Block objects, assumed sorted (top→down, left→right).

    Returns:
        LayoutGraph with blocks, reading nodes (page + lines), spatial edges, neighborhood,
        and column/section metadata.
    """
    # Load config
    config = _load_config()

    # Validate all blocks are from the same page
    pages = set(b.page for b in blocks)
    assert len(pages) == 1, f"All blocks must be from the same page, found: {pages}"

    # Build line nodes
    line_nodes, line_id_by_block = _make_line_nodes(blocks, config)

    # Build reading nodes (page + lines)
    page_nodes = _make_page_node(blocks, line_nodes)
    reading_nodes = page_nodes + line_nodes

    # Detect columns
    column_by_line: dict[int, int] = {}
    if config.get("columns", {}).get("enabled", True):
        column_by_line = detect_columns(
            line_nodes,
            blocks,
            max_k=config["columns"]["max_k"],
            min_gap_x_norm=config["columns"]["min_gap_x_norm"],
            min_col_width_norm=config["columns"]["min_col_width_norm"],
        )

    # Detect sections
    section_by_line: dict[int, int] = {}
    if config.get("sections", {}).get("enabled", True):
        section_by_line = detect_sections(
            line_nodes,
            blocks,
            title_font_boost=config["sections"]["title_font_boost"],
            min_above_gap_lines=config["sections"]["min_above_gap_lines"],
        )

    # Assign to blocks
    column_id_by_block, section_id_by_block = _assign_column_section_to_blocks(
        line_nodes, line_id_by_block, column_by_line, section_by_line
    )

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

    # Attach metadata as extra attributes (temporary hack, not in model yet)
    object.__setattr__(layout_graph, "neighborhood", neighborhood)
    object.__setattr__(layout_graph, "column_id_by_block", column_id_by_block)
    object.__setattr__(layout_graph, "section_id_by_block", section_id_by_block)
    object.__setattr__(layout_graph, "line_id_by_block", line_id_by_block)

    return layout_graph


def dump_layout_debug(layout: LayoutGraph) -> None:
    """Print debug information about layout structure."""
    line_nodes = [rn for rn in layout.reading_nodes if rn.type == "line"]
    column_by_block = getattr(layout, "column_id_by_block", {})
    section_by_block = getattr(layout, "section_id_by_block", {})

    print(f"Layout Debug:")
    print(f"  Blocks: {len(layout.blocks)}")
    print(f"  Line nodes: {len(line_nodes)}")
    print(f"  Columns (distinct): {len(set(column_by_block.values()))}")
    print(f"  Sections (distinct): {len(set(section_by_block.values()))}")
    print(f"\nFirst 8 line nodes:")
    block_by_id = {b.id: b for b in layout.blocks}

    for i, ln in enumerate(line_nodes[:8]):
        block = next((b for b in layout.blocks if b.id in ln.ref_block_ids), None)
        if block:
            col = column_by_block.get(block.id, None)
            sec = section_by_block.get(block.id, None)
            text_preview = block.text.splitlines()[0][:60] if block.text else ""
            print(f"  [line {ln.id}] col={col} sec={sec} text='{text_preview}'")

