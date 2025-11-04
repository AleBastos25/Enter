"""Heuristics for column detection and section identification."""

from __future__ import annotations

import statistics
from typing import List, Tuple

from ..core.models import Block, ReadingNode


def detect_columns(
    line_nodes: List[ReadingNode],
    blocks: List[Block],
    max_k: int = 3,
    min_gap_x_norm: float = 0.05,
    min_col_width_norm: float = 0.12,
) -> dict[int, int]:
    """Detect columns by clustering line centroids.

    Args:
        line_nodes: List of ReadingNode(type="line") with meta["bbox"].
        blocks: List of blocks for reference.
        max_k: Maximum number of columns to try (1..max_k).
        min_gap_x_norm: Minimum gap between columns (normalized).
        min_col_width_norm: Minimum column width to consider valid.

    Returns:
        Dictionary mapping line_node.id -> column_id (0-based).
    """
    if not line_nodes:
        return {}

    # Get centroids X for each line
    centroids: List[Tuple[int, float]] = []
    for ln in line_nodes:
        bbox = ln.meta.get("bbox")
        if bbox:
            cx = (bbox[0] + bbox[2]) / 2.0
            centroids.append((ln.id, cx))

    if not centroids:
        return {}

    # Sort by centroid X
    centroids.sort(key=lambda x: x[1])
    cx_values = [cx for _, cx in centroids]

    # Try k=1..max_k and choose best partition
    best_k = 1
    best_assignment: dict[int, int] = {}
    best_score = float("inf")

    for k in range(1, max_k + 1):
        if len(centroids) < k:
            break

        # Simple gap-based clustering
        if k == 1:
            # Single column: assign all to 0
            assignment = {ln_id: 0 for ln_id, _ in centroids}
            # Score: variance of centroids
            if len(cx_values) > 1:
                score = statistics.variance(cx_values) if len(cx_values) > 1 else 0.0
            else:
                score = 0.0
        else:
            # Find gaps
            gaps = [cx_values[i + 1] - cx_values[i] for i in range(len(cx_values) - 1)]
            if not gaps:
                continue

            # Find large gaps (potential column boundaries)
            gap_threshold = min_gap_x_norm
            large_gaps = [i for i, gap in enumerate(gaps) if gap >= gap_threshold]

            if len(large_gaps) < k - 1:
                # Not enough gaps, try k-1
                continue

            # Choose k-1 largest gaps as boundaries
            gap_with_idx = [(i, gaps[i]) for i in large_gaps]
            gap_with_idx.sort(key=lambda x: -x[1])  # Sort by gap size descending
            boundaries = sorted([gap_with_idx[i][0] for i in range(k - 1)])

            # Assign columns
            assignment: dict[int, int] = {}
            col_idx = 0
            for i, (ln_id, _) in enumerate(centroids):
                if col_idx < len(boundaries) and i > boundaries[col_idx]:
                    col_idx += 1
                assignment[ln_id] = col_idx

            # Validate column widths
            col_ranges: List[Tuple[float, float]] = []
            for col in range(k):
                col_centroids = [cx for ln_id, cx in centroids if assignment[ln_id] == col]
                if col_centroids:
                    col_ranges.append((min(col_centroids), max(col_centroids)))

            # Check minimum width
            valid = all(
                (max_cx - min_cx) >= min_col_width_norm for min_cx, max_cx in col_ranges
            )
            if not valid:
                continue

            # Score: sum of variances within each column
            score = 0.0
            for col in range(k):
                col_cx = [cx for ln_id, cx in centroids if assignment[ln_id] == col]
                if len(col_cx) > 1:
                    score += statistics.variance(col_cx)
                elif len(col_cx) == 1:
                    score += 0.0

        if score < best_score:
            best_score = score
            best_k = k
            best_assignment = assignment

    # If no valid partition found, default to single column
    if not best_assignment:
        best_assignment = {ln_id: 0 for ln_id, _ in centroids}

    return best_assignment


def detect_sections(
    line_nodes: List[ReadingNode],
    blocks: List[Block],
    title_font_boost: float = 1.15,
    min_above_gap_lines: float = 1.3,
) -> dict[int, int]:
    """Detect sections by identifying title lines.

    Args:
        line_nodes: List of ReadingNode(type="line") ordered by reading order.
        blocks: List of blocks for font size lookup.
        title_font_boost: Multiplier for median font size to identify titles.
        min_above_gap_lines: Minimum gap (in line heights) above to consider a title.

    Returns:
        Dictionary mapping line_node.id -> section_id (0-based).
    """
    if not line_nodes:
        return {}

    # Get font sizes for all lines
    font_sizes: List[float] = []
    block_by_id = {b.id: b for b in blocks}

    for ln in line_nodes:
        # Get font size from first block referenced
        if ln.ref_block_ids:
            block = block_by_id.get(ln.ref_block_ids[0])
            if block and block.font_size:
                font_sizes.append(block.font_size)

    if not font_sizes:
        return {}

    median_font_size = statistics.median(font_sizes)
    title_threshold = median_font_size * title_font_boost

    # Identify title lines
    title_lines: List[int] = []
    for i, ln in enumerate(line_nodes):
        if ln.ref_block_ids:
            block = block_by_id.get(ln.ref_block_ids[0])
            if block:
                is_title = False
                # Check font size
                if block.font_size and block.font_size > title_threshold:
                    is_title = True
                # Check bold + gap above
                elif block.bold and i > 0:
                    # Calculate gap above
                    prev_ln = line_nodes[i - 1]
                    prev_bbox = prev_ln.meta.get("bbox")
                    curr_bbox = ln.meta.get("bbox")
                    if prev_bbox and curr_bbox:
                        gap = curr_bbox[1] - prev_bbox[3]  # y0 - y1_prev
                        # Estimate line height from previous block
                        if prev_ln.ref_block_ids:
                            prev_block = block_by_id.get(prev_ln.ref_block_ids[0])
                            if prev_block and prev_block.font_size:
                                line_height = prev_block.font_size * 1.2  # Rough estimate
                                gap_lines = gap / line_height if line_height > 0 else 0
                                if gap_lines >= min_above_gap_lines:
                                    is_title = True

                if is_title:
                    title_lines.append(ln.id)

    # Assign sections: each title starts a new section
    assignment: dict[int, int] = {}
    section_id = 0

    for ln in line_nodes:
        if ln.id in title_lines:
            section_id += 1
        assignment[ln.id] = section_id

    return assignment


def detect_paragraphs(
    line_nodes: List[ReadingNode],
    blocks: List[Block],
    column_by_line: dict[int, int],
    section_by_line: dict[int, int],
    min_gap_lines: float = 0.8,
    margin_alignment_tol: float = 0.02,
) -> dict[int, int]:
    """Detect paragraphs by grouping consecutive lines in same column/section.

    Groups consecutive lines that:
    - Are in the same column and section
    - Have small vertical gap (less than min_gap_lines)
    - Have similar left margin alignment (within tolerance)

    Args:
        line_nodes: List of ReadingNode(type="line") ordered by reading order.
        blocks: List of blocks for bbox lookup.
        column_by_line: Dictionary mapping line_id -> column_id.
        section_by_line: Dictionary mapping line_id -> section_id.
        min_gap_lines: Minimum gap (in line heights) to start a new paragraph.
        margin_alignment_tol: Tolerance for left margin alignment (normalized).

    Returns:
        Dictionary mapping line_node.id -> paragraph_id (0-based).
    """
    if not line_nodes:
        return {}

    block_by_id = {b.id: b for b in blocks}
    assignment: dict[int, int] = {}
    paragraph_id = 0

    # Group lines by column and section first
    groups: dict[tuple[int, int], list[ReadingNode]] = {}
    for ln in line_nodes:
        col_id = column_by_line.get(ln.id, 0)
        sec_id = section_by_line.get(ln.id, 0)
        key = (col_id, sec_id)
        if key not in groups:
            groups[key] = []
        groups[key].append(ln)

    # Within each group, detect paragraphs
    for (col_id, sec_id), group_lines in groups.items():
        if not group_lines:
            continue

        # Sort by y position
        group_lines.sort(key=lambda ln: ln.meta.get("bbox", [0, 0, 0, 0])[1] if ln.meta.get("bbox") else 0)

        current_paragraph_id = paragraph_id
        paragraph_id += 1

        # First line always starts a paragraph
        if group_lines:
            assignment[group_lines[0].id] = current_paragraph_id

        # For subsequent lines, check gap and alignment
        for i in range(1, len(group_lines)):
            prev_ln = group_lines[i - 1]
            curr_ln = group_lines[i]

            prev_bbox = prev_ln.meta.get("bbox")
            curr_bbox = curr_ln.meta.get("bbox")

            if not prev_bbox or not curr_bbox:
                # Missing bbox, start new paragraph
                current_paragraph_id = paragraph_id
                paragraph_id += 1
                assignment[curr_ln.id] = current_paragraph_id
                continue

            # Calculate vertical gap
            gap = curr_bbox[1] - prev_bbox[3]  # y0_curr - y1_prev

            # Estimate line height from previous line
            prev_block_id = prev_ln.ref_block_ids[0] if prev_ln.ref_block_ids else None
            prev_block = block_by_id.get(prev_block_id) if prev_block_id else None
            line_height = prev_block.font_size * 1.2 if prev_block and prev_block.font_size else 0.01
            if line_height <= 0:
                line_height = 0.01

            gap_lines = gap / line_height if line_height > 0 else float("inf")

            # Check margin alignment (left margin)
            prev_left = prev_bbox[0]
            curr_left = curr_bbox[0]
            margin_diff = abs(curr_left - prev_left)

            # Start new paragraph if:
            # - Gap is large (>= min_gap_lines)
            # - Margin difference is significant (>= margin_alignment_tol)
            if gap_lines >= min_gap_lines or margin_diff >= margin_alignment_tol:
                current_paragraph_id = paragraph_id
                paragraph_id += 1

            assignment[curr_ln.id] = current_paragraph_id

    return assignment
