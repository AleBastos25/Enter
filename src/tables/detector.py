"""Table detection: KV-lists and grid tables."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Optional

from ..core.models import Block, LayoutGraph, ReadingNode, TableCell, TableRow, TableStructure


def _load_table_config() -> dict:
    """Load table config from YAML, with fallback to defaults."""
    from pathlib import Path
    import yaml

    config_path = Path("configs/tables.yaml")
    defaults = {
        "kv": {
            "enabled": True,
            "min_row_items": 2,
            "min_rows": 2,
            "max_label_len_chars": 40,
            "label_value_x_gap_max": 0.08,
            "same_row_y_overlap": 0.60,
            "same_column_x_overlap": 0.55,
        },
        "grid": {
            "enabled": True,
            "use_pdf_lines": True,
            "min_cols": 2,
            "min_rows": 2,
            "min_cell_w_norm": 0.06,
            "min_cell_h_norm": 0.012,
            "snap_tol_norm": 0.006,
            "header_font_boost": 1.1,
            "min_row_y_gap": 0.008,
        },
        "rank": {
            "prefer_same_row_bonus": 0.12,
            "prefer_same_col_bonus": 0.06,
            "cross_row_penalty": 0.06,
            "cross_col_penalty": 0.04,
        },
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                config = defaults.copy()
                for key in config:
                    if key in loaded:
                        config[key].update(loaded[key])
                return config
        except Exception:
            pass
    return defaults


def _detect_kv_lists(layout: LayoutGraph, cfg: dict) -> list[TableStructure]:
    """Detect key-value lists (label→value pairs in columns)."""
    if not cfg.get("kv", {}).get("enabled", True):
        return []

    kv_cfg = cfg["kv"]
    line_nodes = [rn for rn in layout.reading_nodes if rn.type == "line"]
    if len(line_nodes) < kv_cfg["min_rows"]:
        return []

    # Group lines by horizontal bands (same row)
    column_by_block = getattr(layout, "column_id_by_block", {})
    block_by_id = {b.id: b for b in layout.blocks}

    # Cluster lines into rows by y-overlap
    rows: list[list[ReadingNode]] = []
    for ln in line_nodes:
        bbox = ln.meta.get("bbox")
        if not bbox:
            continue

        # Find row with y-overlap
        placed = False
        for row in rows:
            if row:
                first_bbox = row[0].meta.get("bbox")
                if first_bbox:
                    # Check y-overlap
                    y_overlap = min(bbox[3], first_bbox[3]) - max(bbox[1], first_bbox[1])
                    y_min = min(bbox[3] - bbox[1], first_bbox[3] - first_bbox[1])
                    if y_min > 0 and (y_overlap / y_min) >= kv_cfg["same_row_y_overlap"]:
                        row.append(ln)
                        placed = True
                        break

        if not placed:
            rows.append([ln])

    # Filter rows with at least min_row_items KV pairs
    kv_tables: list[TableStructure] = []
    table_id = 0

    for row_group in rows:
        if len(row_group) < kv_cfg["min_row_items"]:
            continue

        # Find label→value pairs in each row
        kv_pairs: list[tuple[int, int]] = []  # (label_line_id, value_line_id or block_id)
        cells: list[TableCell] = []
        rows_out: list[TableRow] = []

        row_id = 0
        cell_id = 0

        for ln in row_group:
            # Get blocks for this line
            block_ids = ln.ref_block_ids
            if not block_ids:
                continue

            # Try to split into label (left) and value (right)
            blocks = [block_by_id[bid] for bid in block_ids if bid in block_by_id]
            if len(blocks) < 2:
                continue

            # Sort by x
            blocks.sort(key=lambda b: b.bbox[0])

            # Find gap between potential label and value
            label_blocks: list[Block] = []
            value_blocks: list[Block] = []

            for i in range(len(blocks) - 1):
                gap = blocks[i + 1].bbox[0] - blocks[i].bbox[2]
                if gap > 0 and gap <= kv_cfg["label_value_x_gap_max"]:
                    label_blocks = blocks[: i + 1]
                    value_blocks = blocks[i + 1 :]
                    break

            if not label_blocks or not value_blocks:
                continue

            # Check label length
            label_text = " ".join(b.text for b in label_blocks)
            if len(label_text) > kv_cfg["max_label_len_chars"]:
                continue

            # Create row
            row_bbox = (
                min(b.bbox[0] for b in blocks),
                min(b.bbox[1] for b in blocks),
                max(b.bbox[2] for b in blocks),
                max(b.bbox[3] for b in blocks),
            )

            # Create cells
            label_cell = TableCell(
                id=cell_id,
                row_id=row_id,
                col_id=0,
                bbox=(
                    min(b.bbox[0] for b in label_blocks),
                    min(b.bbox[1] for b in label_blocks),
                    max(b.bbox[2] for b in label_blocks),
                    max(b.bbox[3] for b in label_blocks),
                ),
                block_ids=[b.id for b in label_blocks],
                text=label_text,
                header=False,
            )
            cell_id += 1

            value_text = " ".join(b.text for b in value_blocks)
            value_cell = TableCell(
                id=cell_id,
                row_id=row_id,
                col_id=1,
                bbox=(
                    min(b.bbox[0] for b in value_blocks),
                    min(b.bbox[1] for b in value_blocks),
                    max(b.bbox[2] for b in value_blocks),
                    max(b.bbox[3] for b in value_blocks),
                ),
                block_ids=[b.id for b in value_blocks],
                text=value_text,
                header=False,
            )
            cell_id += 1

            row = TableRow(id=row_id, bbox=row_bbox, cell_ids=[label_cell.id, value_cell.id])
            cells.extend([label_cell, value_cell])
            rows_out.append(row)
            row_id += 1

        if len(rows_out) >= kv_cfg["min_rows"]:
            # Create table bbox
            table_bbox = (
                min(c.bbox[0] for c in cells),
                min(c.bbox[1] for c in cells),
                max(c.bbox[2] for c in cells),
                max(c.bbox[3] for c in cells),
            )

            table = TableStructure(
                id=table_id,
                type="kv",
                bbox=table_bbox,
                row_ids=[r.id for r in rows_out],
                col_count=2,
                cells=cells,
                rows=rows_out,
            )
            kv_tables.append(table)
            table_id += 1

    return kv_tables


def _detect_grid_tables(layout: LayoutGraph, cfg: dict, pdf_lines: Optional[dict] = None) -> list[TableStructure]:
    """Detect grid tables (with or without vector lines)."""
    if not cfg.get("grid", {}).get("enabled", True):
        return []

    grid_cfg = cfg["grid"]
    line_nodes = [rn for rn in layout.reading_nodes if rn.type == "line"]
    if len(line_nodes) < grid_cfg["min_rows"]:
        return []

    block_by_id = {b.id: b for b in layout.blocks}

    # Try to use PDF lines if available
    if grid_cfg.get("use_pdf_lines", True) and pdf_lines:
        # TODO: Implement grid detection using vector lines
        # For now, fall back to alignment-based
        pass

    # Alignment-based detection
    # Cluster lines into rows by y-gap
    rows: list[list[ReadingNode]] = []
    for ln in sorted(line_nodes, key=lambda n: n.meta.get("bbox", [0, 0, 0, 0])[1]):
        bbox = ln.meta.get("bbox")
        if not bbox:
            continue

        placed = False
        for row in rows:
            if row:
                first_bbox = row[0].meta.get("bbox")
                if first_bbox:
                    gap = bbox[1] - first_bbox[3]
                    if gap < grid_cfg["min_row_y_gap"]:
                        row.append(ln)
                        placed = True
                        break

        if not placed:
            rows.append([ln])

    if len(rows) < grid_cfg["min_rows"]:
        return []

    # Cluster columns by x-centroids
    all_x_centers: list[float] = []
    for row in rows:
        for ln in row:
            bbox = ln.meta.get("bbox")
            if bbox:
                all_x_centers.append((bbox[0] + bbox[2]) / 2.0)

    if not all_x_centers:
        return []

    # Simple gap-based column detection
    all_x_centers.sort()
    gaps = [all_x_centers[i + 1] - all_x_centers[i] for i in range(len(all_x_centers) - 1)]
    if not gaps:
        return []

    gap_threshold = grid_cfg.get("min_cell_w_norm", 0.06)
    large_gaps = [i for i, gap in enumerate(gaps) if gap >= gap_threshold]

    # Estimate number of columns
    col_boundaries = sorted(set([all_x_centers[0]] + [all_x_centers[i + 1] for i in large_gaps] + [all_x_centers[-1]]))
    num_cols = len(col_boundaries) - 1

    if num_cols < grid_cfg["min_cols"]:
        return []

    # Build cells
    tables: list[TableStructure] = []
    table_id = 0

    # Group rows that might form a table
    table_rows: list[list[ReadingNode]] = [rows[0]]
    for row in rows[1:]:
        if len(row) >= num_cols:
            table_rows.append(row)
        else:
            # End of table, create structure
            if len(table_rows) >= grid_cfg["min_rows"]:
                cells, rows_out = _build_grid_cells(table_rows, col_boundaries, block_by_id, grid_cfg)
                if cells and rows_out:
                    table_bbox = (
                        min(c.bbox[0] for c in cells),
                        min(c.bbox[1] for c in cells),
                        max(c.bbox[2] for c in cells),
                        max(c.bbox[3] for c in cells),
                    )
                    table = TableStructure(
                        id=table_id,
                        type="grid",
                        bbox=table_bbox,
                        row_ids=[r.id for r in rows_out],
                        col_count=num_cols,
                        cells=cells,
                        rows=rows_out,
                    )
                    tables.append(table)
                    table_id += 1
            table_rows = [row]

    # Handle last table
    if len(table_rows) >= grid_cfg["min_rows"]:
        cells, rows_out = _build_grid_cells(table_rows, col_boundaries, block_by_id, grid_cfg)
        if cells and rows_out:
            table_bbox = (
                min(c.bbox[0] for c in cells),
                min(c.bbox[1] for c in cells),
                max(c.bbox[2] for c in cells),
                max(c.bbox[3] for c in cells),
            )
            table = TableStructure(
                id=table_id,
                type="grid",
                bbox=table_bbox,
                row_ids=[r.id for r in rows_out],
                col_count=num_cols,
                cells=cells,
                rows=rows_out,
            )
            tables.append(table)

    return tables


def _build_grid_cells(
    rows: list[list[ReadingNode]],
    col_boundaries: list[float],
    block_by_id: dict[int, Block],
    grid_cfg: dict,
) -> tuple[list[TableCell], list[TableRow]]:
    """Build cells and rows from line groups."""
    cells: list[TableCell] = []
    rows_out: list[TableRow] = []
    cell_id = 0
    row_id = 0

    # Detect header (first row with larger font)
    font_sizes: list[float] = []
    for row in rows:
        for ln in row:
            for bid in ln.ref_block_ids:
                block = block_by_id.get(bid)
                if block and block.font_size:
                    font_sizes.append(block.font_size)

    median_font = statistics.median(font_sizes) if font_sizes else 0.0
    header_threshold = median_font * grid_cfg.get("header_font_boost", 1.1)

    for row_idx, row_lines in enumerate(rows):
        row_blocks: list[Block] = []
        for ln in row_lines:
            for bid in ln.ref_block_ids:
                if bid in block_by_id:
                    row_blocks.append(block_by_id[bid])

        if not row_blocks:
            continue

        # Determine row bbox
        row_bbox = (
            min(b.bbox[0] for b in row_blocks),
            min(b.bbox[1] for b in row_blocks),
            max(b.bbox[2] for b in row_blocks),
            max(b.bbox[3] for b in row_blocks),
        )

        # Assign blocks to columns
        row_cell_ids: list[int] = []
        for col_idx in range(len(col_boundaries) - 1):
            col_x0 = col_boundaries[col_idx]
            col_x1 = col_boundaries[col_idx + 1]

            # Find blocks in this column
            cell_blocks: list[Block] = []
            for block in row_blocks:
                block_cx = (block.bbox[0] + block.bbox[2]) / 2.0
                if col_x0 <= block_cx < col_x1:
                    cell_blocks.append(block)

            if cell_blocks:
                cell_bbox = (
                    min(b.bbox[0] for b in cell_blocks),
                    min(b.bbox[1] for b in cell_blocks),
                    max(b.bbox[2] for b in cell_blocks),
                    max(b.bbox[3] for b in cell_blocks),
                )
                cell_text = " ".join(b.text for b in cell_blocks)

                # Check if header
                is_header = False
                if row_idx == 0:
                    avg_font = statistics.mean([b.font_size for b in cell_blocks if b.font_size]) if cell_blocks else 0.0
                    is_header = avg_font > header_threshold

                cell = TableCell(
                    id=cell_id,
                    row_id=row_id,
                    col_id=col_idx,
                    bbox=cell_bbox,
                    block_ids=[b.id for b in cell_blocks],
                    text=cell_text,
                    header=is_header,
                )
                cells.append(cell)
                row_cell_ids.append(cell_id)
                cell_id += 1

        if row_cell_ids:
            row = TableRow(id=row_id, bbox=row_bbox, cell_ids=row_cell_ids)
            rows_out.append(row)
            row_id += 1

    return cells, rows_out


def detect_tables(layout: LayoutGraph, cfg: Optional[dict] = None, pdf_lines: Optional[dict] = None) -> list[TableStructure]:
    """Detect KV-lists and grid tables in layout.

    Args:
        layout: LayoutGraph with blocks and line nodes.
        cfg: Optional config dict (if None, loads from YAML).
        pdf_lines: Optional dict with 'h' and 'v' line lists (normalized).

    Returns:
        List of TableStructure objects.
    """
    if cfg is None:
        cfg = _load_table_config()

    tables: list[TableStructure] = []

    # Detect KV-lists
    kv_tables = _detect_kv_lists(layout, cfg)
    tables.extend(kv_tables)

    # Detect grid tables
    grid_tables = _detect_grid_tables(layout, cfg, pdf_lines)
    tables.extend(grid_tables)

    return tables

