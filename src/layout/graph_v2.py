"""Graph V2 with directional edges and connected components (v2).

Builds spatial topology graph from blocks and Grid.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Tuple

from ..core.models import Block, GraphV2, Grid


def _robust_percentile(data: List[float], p: float) -> float:
    """Compute percentile p (0-100) of data."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100.0)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


def build_graph_v2(blocks: List[Block], grid: Grid) -> GraphV2:
    """Build GraphV2 with directional edges and connected components.

    Args:
        blocks: List of Block objects.
        grid: Grid structure from build_grid.

    Returns:
        GraphV2 with adj, component_id, and style.
    """
    if not blocks:
        return GraphV2(
            adj={},
            component_id={},
            style={},
        )

    block_by_id = {b.id: b for b in blocks}
    row_y = grid["row_y"]
    col_x = grid["col_x"]
    cell_map = grid["cell_map"]
    spans = grid["spans"]

    # ========================================================================
    # 2.1 Style z-score
    # ========================================================================
    # Compute font_size statistics (robust: P50 as mean, P84-P50 as std)
    font_sizes = [b.font_size for b in blocks if b.font_size is not None]
    if font_sizes:
        mu_font = _robust_percentile(font_sizes, 50)
        sigma_font = max(_robust_percentile(font_sizes, 84) - mu_font, 1e-6)
    else:
        mu_font = 1.0
        sigma_font = 1.0

    style: Dict[int, Tuple[float, bool]] = {}
    for block in blocks:
        if block.font_size is not None:
            font_z = (block.font_size - mu_font) / sigma_font
        else:
            font_z = 0.0
        style[block.id] = (font_z, block.bold)

    # ========================================================================
    # 2.2 Vizinhanças
    # ========================================================================
    adj: Dict[int, Dict[str, List[int]]] = {}

    for block in blocks:
        block_adj: Dict[str, List[int]] = {
            "same_line": [],
            "same_col": [],
            "north": [],
            "south": [],
            "east": [],
            "west": [],
        }

        block_cells = cell_map.get(block.id, [])
        block_row_indices = set(c[0] for c in block_cells)
        block_col_indices = set(c[1] for c in block_cells)

        # Determine span columns if exists
        if block.id in spans:
            first_col, last_col = spans[block.id]
            block_col_indices.update(range(first_col, last_col + 1))

        # Same_line: blocos que compartilham pelo menos uma linha virtual
        # e cujo centro X esteja à direita
        block_x_center = (block.bbox[0] + block.bbox[2]) / 2.0
        for other in blocks:
            if other.id == block.id:
                continue
            other_cells = cell_map.get(other.id, [])
            other_row_indices = set(c[0] for c in other_cells)
            if block_row_indices & other_row_indices:  # share at least one row
                other_x_center = (other.bbox[0] + other.bbox[2]) / 2.0
                if other_x_center > block_x_center:  # to the right
                    block_adj["same_line"].append(other.id)

        # Same_col: blocos que compartilham pelo menos uma coluna (considerando spans)
        for other in blocks:
            if other.id == block.id:
                continue
            other_cells = cell_map.get(other.id, [])
            other_col_indices = set(c[1] for c in other_cells)
            # Add span columns for other block
            if other.id in spans:
                other_first, other_last = spans[other.id]
                other_col_indices.update(range(other_first, other_last + 1))

            if block_col_indices & other_col_indices:  # share at least one column
                block_adj["same_col"].append(other.id)

        # North/South/East/West: use retângulos
        # Calcule τ_x_line = max(P50(IoU_x_on_same_col), 0.12)
        iou_x_same_col: List[float] = []
        for other in blocks:
            if other.id == block.id:
                continue
            # Check if same column
            if block_col_indices & set(c[1] for c in cell_map.get(other.id, [])):
                # Compute IoU_x
                block_x0, _, block_x1, _ = block.bbox
                other_x0, _, other_x1, _ = other.bbox
                overlap_x = max(0.0, min(block_x1, other_x1) - max(block_x0, other_x0))
                union_x = max(block_x1, other_x1) - min(block_x0, other_x0)
                if union_x > 0:
                    iou_x = overlap_x / union_x
                    iou_x_same_col.append(iou_x)

        if iou_x_same_col:
            tau_x_line = max(_robust_percentile(iou_x_same_col, 50), 0.12)
        else:
            tau_x_line = 0.12

        # South: c.y0 ≥ b.y1 and IoU_x(b,c) ≥ τ_x_line
        block_y0, block_y1 = block.bbox[1], block.bbox[3]
        block_x0, block_x1 = block.bbox[0], block.bbox[2]

        for other in blocks:
            if other.id == block.id:
                continue
            other_y0, other_y1 = other.bbox[1], other.bbox[3]
            other_x0, other_x1 = other.bbox[0], other.bbox[2]

            # Compute IoU_x
            overlap_x = max(0.0, min(block_x1, other_x1) - max(block_x0, other_x0))
            union_x = max(block_x1, other_x1) - min(block_x0, other_x0)
            if union_x > 0:
                iou_x = overlap_x / union_x
            else:
                iou_x = 0.0

            # South
            if other_y0 >= block_y1 and iou_x >= tau_x_line:
                block_adj["south"].append(other.id)

            # North
            if other_y1 <= block_y0 and iou_x >= tau_x_line:
                block_adj["north"].append(other.id)

            # East (right): other.x0 > block.x1 (simplified, IoU_x already computed)
            if other_x0 > block_x1 and iou_x >= tau_x_line:
                block_adj["east"].append(other.id)

            # West (left): other.x1 < block.x0
            if other_x1 < block_x0 and iou_x >= tau_x_line:
                block_adj["west"].append(other.id)

        adj[block.id] = block_adj

    # ========================================================================
    # 2.3 Componentes conexos
    # ========================================================================
    # Monte grafo não-direcionado com arestas {same_line, same_col, north/south/east/west}
    undirected_adj: Dict[int, List[int]] = defaultdict(list)

    for block_id, edges in adj.items():
        # Add edges in both directions
        for relation in ["same_line", "same_col", "north", "south", "east", "west"]:
            for neighbor_id in edges[relation]:
                if neighbor_id not in undirected_adj[block_id]:
                    undirected_adj[block_id].append(neighbor_id)
                if block_id not in undirected_adj[neighbor_id]:
                    undirected_adj[neighbor_id].append(block_id)

    # DFS/BFS para marcar component_id
    component_id: Dict[int, int] = {}
    visited = set()
    current_component = 0

    def dfs(block_id: int, comp_id: int) -> None:
        visited.add(block_id)
        component_id[block_id] = comp_id
        for neighbor_id in undirected_adj[block_id]:
            if neighbor_id not in visited:
                dfs(neighbor_id, comp_id)

    for block in blocks:
        if block.id not in visited:
            dfs(block.id, current_component)
            current_component += 1

    # Ensure all blocks have component_id (even if isolated)
    for block in blocks:
        if block.id not in component_id:
            component_id[block.id] = current_component
            current_component += 1

    return GraphV2(
        adj=adj,
        component_id=component_id,
        style=style,
    )

