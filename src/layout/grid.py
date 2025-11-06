"""Virtual grid with spans for layout analysis (v2).

Auto-calibrated grid using percentiles for adaptive thresholds.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Tuple

from ..core.models import Block, Grid


def _percentile(data: List[float], p: float) -> float:
    """Compute percentile p (0-100) of data."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100.0)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


def _robust_stats(data: List[float]) -> Tuple[float, float]:
    """Compute robust mean (P50) and std (P84 - P50) from data."""
    if not data:
        return 0.0, 1.0
    sorted_data = sorted(data)
    p50 = _percentile(sorted_data, 50)
    p84 = _percentile(sorted_data, 84)
    std = max(p84 - p50, 1e-6)
    return p50, std


def build_grid(blocks: List[Block]) -> Grid:
    """Build virtual grid from blocks with auto-calibrated thresholds.

    Args:
        blocks: List of Block objects with normalized bboxes [0,1].

    Returns:
        Grid with row_y, col_x, cell_map, spans, and thresholds.
    """
    if not blocks:
        return Grid(
            row_y=[],
            col_x=[],
            cell_map={},
            spans={},
            thresholds={},
        )

    # ========================================================================
    # 1.1 Linhas virtuais (cluster 1D em y)
    # ========================================================================
    # Calcule y_center para cada Block
    y_centers = [(b.id, (b.bbox[1] + b.bbox[3]) / 2.0) for b in blocks]
    # Ordene por y_center
    y_centers.sort(key=lambda x: x[1])

    # Compute gaps sucessivos
    gaps_y = []
    for i in range(len(y_centers) - 1):
        gap = y_centers[i + 1][1] - y_centers[i][1]
        gaps_y.append(gap)

    # Calibre limiar de quebra de linha: δ_line = P40(Δy)
    if gaps_y:
        delta_line = _percentile(gaps_y, 40)
        delta_line = max(delta_line, 0.004)  # floor
    else:
        delta_line = 0.004

    # Varra gerando "runs" onde Δy ≤ δ_line
    row_y: List[float] = []
    current_run: List[float] = []
    for i, (_, y_center) in enumerate(y_centers):
        if i == 0:
            current_run.append(y_center)
        else:
            gap = y_center - y_centers[i - 1][1]
            if gap <= delta_line:
                current_run.append(y_center)
            else:
                # Finaliza run anterior
                if current_run:
                    row_y.append(sum(current_run) / len(current_run))
                current_run = [y_center]
    # Finaliza último run
    if current_run:
        row_y.append(sum(current_run) / len(current_run))

    # ========================================================================
    # 1.2 Colunas (cortes em X)
    # ========================================================================
    # Colete edges X de todos blocos
    x_edges: List[float] = []
    for b in blocks:
        x_edges.append(b.bbox[0])
        x_edges.append(b.bbox[2])
    x_edges = sorted(set(x_edges))

    # Compute gaps
    gaps_x = []
    for i in range(len(x_edges) - 1):
        gap = x_edges[i + 1] - x_edges[i]
        gaps_x.append(gap)

    # Encontre cortes onde Δx_k ≥ τ_cut, com τ_cut = P70(Δx)
    if gaps_x:
        tau_cut = _percentile(gaps_x, 70)
    else:
        tau_cut = 0.05

    # Construa colunas como intervalos entre cortes
    cuts: List[int] = [0]  # sempre começa em 0
    for i in range(len(gaps_x)):
        if gaps_x[i] >= tau_cut:
            cuts.append(i + 1)

    col_x: List[Tuple[float, float]] = []
    for i in range(len(cuts)):
        start_idx = cuts[i]
        end_idx = cuts[i + 1] if i + 1 < len(cuts) else len(x_edges) - 1
        col_x.append((x_edges[start_idx], x_edges[end_idx]))

    # Coalescência: se >6 colunas, unir colunas pequenas
    if len(col_x) > 6:
        widths = [c[1] - c[0] for c in col_x]
        p20_width = _percentile(widths, 20)
        merged_cols: List[Tuple[float, float]] = []
        i = 0
        while i < len(col_x):
            c0, c1 = col_x[i]
            width = c1 - c0
            # Se largura < P20 e há próxima coluna, tenta unir
            if width < p20_width and i + 1 < len(col_x):
                next_c0, next_c1 = col_x[i + 1]
                merged_cols.append((c0, next_c1))
                i += 2
            else:
                merged_cols.append((c0, c1))
                i += 1
        col_x = merged_cols

    # ========================================================================
    # 1.3 Atribuir blocos às células + spans
    # ========================================================================
    cell_map: Dict[int, List[Tuple[int, int]]] = {}
    spans: Dict[int, Tuple[int, int]] = {}

    # Calcule IoU_x para todos blocos vs todas colunas
    all_iou_x: List[float] = []
    block_col_overlaps: Dict[int, List[Tuple[int, float]]] = {}  # block_id -> [(col_idx, iou_x), ...]

    for block in blocks:
        block_x0, _, block_x1, _ = block.bbox
        block_width = block_x1 - block_x0
        overlaps = []

        for col_idx, (col_x0, col_x1) in enumerate(col_x):
            # overlap_x = max(0, min(block_x1, col_x1) - max(block_x0, col_x0))
            overlap_x = max(0.0, min(block_x1, col_x1) - max(block_x0, col_x0))
            # union_x = max(block_x1, col_x1) - min(block_x0, col_x0)
            union_x = max(block_x1, col_x1) - min(block_x0, col_x0)
            if union_x > 0:
                iou_x = overlap_x / union_x
            else:
                iou_x = 0.0

            all_iou_x.append(iou_x)
            overlaps.append((col_idx, iou_x))

        block_col_overlaps[block.id] = overlaps

    # Calibre τ_col_iou = max(0.15, P60(IoU_x_all))
    if all_iou_x:
        tau_col_iou = max(0.15, _percentile(all_iou_x, 60))
    else:
        tau_col_iou = 0.15

    # Para cada bloco, atribua às colunas com IoU_x ≥ τ_col_iou
    for block in blocks:
        block_y_center = (block.bbox[1] + block.bbox[3]) / 2.0
        block_cells: List[Tuple[int, int]] = []

        # Encontre colunas que o bloco intersecta
        cols_for_block: List[int] = []
        for col_idx, iou_x in block_col_overlaps[block.id]:
            if iou_x >= tau_col_iou:
                cols_for_block.append(col_idx)

        # Para cada linha virtual, checa se bloco toca
        for row_idx, row_y_val in enumerate(row_y):
            # Bloco toca linha se |y_center(block) - row_y[i]| ≤ β
            # β = max(P25(|Δy|), 0.003)
            if gaps_y:
                beta = max(_percentile([abs(g) for g in gaps_y], 25), 0.003)
            else:
                beta = 0.003

            if abs(block_y_center - row_y_val) <= beta:
                # Bloco toca esta linha; atribua às colunas que intersecta
                for col_idx in cols_for_block:
                    block_cells.append((row_idx, col_idx))

        if block_cells:
            cell_map[block.id] = block_cells

            # Detecta spans: se bloco cobre múltiplas colunas
            col_indices = sorted(set(c[1] for c in block_cells))
            if len(col_indices) > 1:
                spans[block.id] = (col_indices[0], col_indices[-1])

    # ========================================================================
    # Thresholds
    # ========================================================================
    thresholds: Dict[str, float] = {
        "delta_line": delta_line,
        "tau_cut": tau_cut,
        "tau_col_iou": tau_col_iou,
        "beta": max(_percentile([abs(g) for g in gaps_y], 25), 0.003) if gaps_y else 0.003,
    }

    return Grid(
        row_y=row_y,
        col_x=col_x,
        cell_map=cell_map,
        spans=spans,
        thresholds=thresholds,
    )


def debug_render_grid(grid: Grid, blocks: List[Block], svg_path: str) -> None:
    """Render grid visualization to SVG file.

    Args:
        grid: Grid structure.
        blocks: List of blocks.
        svg_path: Path to output SVG file.
    """
    try:
        from xml.etree import ElementTree as ET

        # Create SVG
        svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width="1000", height="1400")
        svg.set("viewBox", "0 0 1 1")

        # Draw rows
        for row_y in grid["row_y"]:
            line = ET.SubElement(svg, "line", x1="0", y1=str(row_y), x2="1", y2=str(row_y))
            line.set("stroke", "#00ff00")
            line.set("stroke-width", "0.002")
            line.set("stroke-opacity", "0.5")

        # Draw columns
        for col_x0, col_x1 in grid["col_x"]:
            # Vertical line at x0
            line = ET.SubElement(svg, "line", x1=str(col_x0), y1="0", x2=str(col_x0), y2="1")
            line.set("stroke", "#0000ff")
            line.set("stroke-width", "0.002")
            line.set("stroke-opacity", "0.5")
            # Vertical line at x1
            line = ET.SubElement(svg, "line", x1=str(col_x1), y1="0", x2=str(col_x1), y2="1")
            line.set("stroke", "#0000ff")
            line.set("stroke-width", "0.002")
            line.set("stroke-opacity", "0.5")

        # Draw blocks
        for block in blocks:
            x0, y0, x1, y1 = block.bbox
            rect = ET.SubElement(svg, "rect", x=str(x0), y=str(y0), width=str(x1 - x0), height=str(y1 - y0))
            rect.set("fill", "none")
            rect.set("stroke", "#ff0000")
            rect.set("stroke-width", "0.003")

            # Draw spans if exists
            if block.id in grid["spans"]:
                first_col, last_col = grid["spans"][block.id]
                if first_col < len(grid["col_x"]) and last_col < len(grid["col_x"]):
                    col_x0 = grid["col_x"][first_col][0]
                    col_x1 = grid["col_x"][last_col][1]
                    span_rect = ET.SubElement(
                        svg, "rect", x=str(col_x0), y=str(y0), width=str(col_x1 - col_x0), height=str(y1 - y0)
                    )
                    span_rect.set("fill", "#ffff00")
                    span_rect.set("fill-opacity", "0.2")

        # Write to file
        tree = ET.ElementTree(svg)
        ET.indent(tree, space="  ")
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)

    except Exception as e:
        print(f"Error rendering grid to SVG: {e}")

