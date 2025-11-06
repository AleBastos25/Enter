"""Deterministic tie-breakers for candidate selection.

Used when Pareto filtering leaves multiple candidates.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..core.models import Block, LayoutGraph


def apply_tie_breakers(
    candidates: List[Dict[str, Any]],
    layout: LayoutGraph,
    field_name: str,
) -> int:
    """Apply tie-breakers to select single candidate from multiple.
    
    Tie-breakers (in order):
    1. Direction preference: → > ↓ > ↑ > ←
    2. Fewer hops
    3. Smaller Manhattan distance
    4. Smaller line_index (reading order)
    5. No inversions (no-crossing)
    
    Args:
        candidates: List of candidate dicts (all non-dominated).
        layout: LayoutGraph.
        field_name: Field name (for debugging).
        
    Returns:
        Index of best candidate.
    """
    if not candidates:
        return -1
    
    if len(candidates) == 1:
        return 0
    
    block_by_id = {b.id: b for b in layout.blocks}
    
    # Map direction to preference score (higher = better)
    direction_pref = {
        "same_line_right_of": 4,  # →
        "same_line": 4,
        "first_below_same_column": 3,  # ↓
        "south_of": 3,
        "above_on_same_column": 2,  # ↑
        "north_of": 2,
        "same_block": 1,  # Special case
        "left_on_same_line": 0,  # ←
        "west_of": 0,
    }
    
    # Evaluate each candidate
    scores: List[float] = []
    
    for cand in candidates:
        score = 0.0
        
        # 1. Direction preference
        relation = cand.get("relation", "")
        score += direction_pref.get(relation, 0) * 1000
        
        # 2. Fewer hops (simplified: 0 for same_block/same_line, 1 for below, etc.)
        if relation in ("same_block", "same_line", "same_line_right_of"):
            hops = 0
        elif relation in ("first_below_same_column", "south_of"):
            hops = 1
        else:
            hops = 2
        score += (10 - hops) * 100  # Fewer hops = higher score
        
        # 3. Manhattan distance (smaller = better)
        block_id = cand.get("block_id")
        label_block_id = cand.get("label_block_id")
        
        if block_id and label_block_id:
            block = block_by_id.get(block_id)
            label_block = block_by_id.get(label_block_id)
            
            if block and label_block:
                # Manhattan distance in normalized coordinates
                block_center_x = (block.bbox[0] + block.bbox[2]) / 2.0
                block_center_y = (block.bbox[1] + block.bbox[3]) / 2.0
                label_center_x = (label_block.bbox[0] + label_block.bbox[2]) / 2.0
                label_center_y = (label_block.bbox[1] + label_block.bbox[3]) / 2.0
                
                manhattan_dist = abs(block_center_x - label_center_x) + abs(block_center_y - label_center_y)
                score += (1.0 - manhattan_dist) * 10  # Smaller distance = higher score
        
        # 4. Line index (reading order: top-left first)
        if block_id:
            block = block_by_id.get(block_id)
            if block:
                # Use y-coordinate as proxy for line index (top = smaller)
                line_index = block.bbox[1]  # y0
                score += (1.0 - line_index) * 1  # Top = higher score
        
        # 5. No inversions (simplified: prefer direct relations)
        # Would need more sophisticated check for actual crossing
        if relation in ("same_block", "same_line", "same_line_right_of", "first_below_same_column"):
            score += 1  # Direct relation (no crossing likely)
        
        scores.append(score)
    
    # Return index of candidate with highest score
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    return best_idx

