"""Pareto selection for candidate filtering (non-dominated sorting).

Replaces arbitrary scoring with deterministic Pareto optimality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core.models import Block, GraphV2, Grid, LayoutGraph, SchemaField
from ..validation.patterns import type_gate_generic


@dataclass
class ParetoCriteria:
    """Criteria for Pareto comparison (all equivalent, no weights).
    
    Attributes:
        structural: C1 - Fewer hops, same line/column preference, no crossing.
        style: C2 - Different style from LABEL, consistency with field values.
        lexical: C3 - Enum exact match, text has ≥4 letters and no label separator.
        type: C4 - Passes type-gate for field.
    """
    
    structural: float  # 0.0 (worst) to 1.0 (best)
    style: float  # 0.0 (worst) to 1.0 (best)
    lexical: float  # 0.0 (worst) to 1.0 (best)
    type: float  # 0.0 (rejected) to 1.0 (passed)
    
    def dominates(self, other: "ParetoCriteria") -> bool:
        """Check if this criteria dominates other.
        
        A dominates B if A is not worse in any criterion and better in at least one.
        
        Args:
            other: Other criteria to compare.
            
        Returns:
            True if this dominates other.
        """
        not_worse = (
            self.structural >= other.structural
            and self.style >= other.style
            and self.lexical >= other.lexical
            and self.type >= other.type
        )
        better = (
            self.structural > other.structural
            or self.style > other.style
            or self.lexical > other.lexical
            or self.type > other.type
        )
        return not_worse and better


def compute_pareto_criteria(
    candidate: Dict[str, Any],
    field: SchemaField,
    layout: LayoutGraph,
    grid: Optional[Grid] = None,
    graph_v2: Optional[GraphV2] = None,
    existing_values: Optional[List[str]] = None,
) -> ParetoCriteria:
    """Compute Pareto criteria for a candidate.
    
    Args:
        candidate: Candidate dict with block_id, relation, text_window, etc.
        field: SchemaField being extracted.
        layout: LayoutGraph.
        grid: Optional Grid structure.
        graph_v2: Optional GraphV2 structure.
        existing_values: Optional list of existing values for this field (for consistency).
        
    Returns:
        ParetoCriteria object.
    """
    text_window = candidate.get("text_window", "")
    relation = candidate.get("relation", "")
    block_id = candidate.get("block_id")
    label_block_id = candidate.get("label_block_id")
    
    # C1: Structural (hops, same line/column, no crossing)
    structural_score = 0.0
    
    # Count hops (simplified: 0 for same_block/same_line, 1 for below, etc.)
    if relation in ("same_block", "same_line", "same_line_right_of"):
        hops = 0
    elif relation in ("first_below_same_column", "south_of"):
        hops = 1
    else:
        hops = 2
    
    # Prefer same line/column (higher score for better relations)
    if relation in ("same_line", "same_line_right_of", "same_block"):
        structural_score = 1.0 - (hops * 0.2)  # 1.0 for same line, 0.8 for below, etc.
    elif relation in ("first_below_same_column", "south_of"):
        structural_score = 0.7 - (hops * 0.1)
    else:
        structural_score = 0.5 - (hops * 0.1)
    
    # No crossing penalty (simplified: assume no crossing if relation is direct)
    # Would need more sophisticated check for actual crossing
    structural_score = max(0.0, min(1.0, structural_score))
    
    # C2: Style (different from LABEL, consistency with field values)
    style_score = 0.5  # Default
    
    if graph_v2 and label_block_id and block_id:
        label_style = graph_v2.get("style", {}).get(label_block_id)
        value_style = graph_v2.get("style", {}).get(block_id)
        
        if label_style and value_style:
            # Different style from label (preferred)
            label_font_z, label_bold = label_style
            value_font_z, value_bold = value_style
            
            if abs(label_font_z - value_font_z) > 0.3 or label_bold != value_bold:
                style_score = 1.0  # Different style (good for VALUE)
            else:
                style_score = 0.3  # Similar style (might be label)
        
        # Consistency with existing values (if available)
        if existing_values and text_window:
            # Check if text_window matches pattern of existing values
            # Simplified: check if similar length/pattern
            for existing in existing_values:
                if existing and len(existing) > 0:
                    # Similar length/pattern suggests consistency
                    if abs(len(text_window) - len(existing)) <= 2:
                        style_score = min(1.0, style_score + 0.2)
                        break
    
    # C3: Lexical (enum exact match, text requirements)
    lexical_score = 0.0
    
    if field.type == "enum":
        enum_options = field.meta.get("enum_options") if field.meta else None
        if enum_options:
            text_upper = text_window.upper().strip()
            # Check for exact match (case-insensitive, accent-insensitive)
            from ..validation.validators import validate_and_normalize
            ok, normalized = validate_and_normalize("enum", text_window, enum_options=enum_options)
            if ok and normalized:
                lexical_score = 1.0  # Exact enum match
            else:
                # Partial match (contains enum value)
                for opt in enum_options:
                    if opt.upper() in text_upper or text_upper in opt.upper():
                        lexical_score = 0.5
                        break
    else:
        # Text field: ≥4 letters, no label separator
        text_clean = text_window.strip()
        if len(text_clean) >= 4:
            # Check if ends with label separator (:, —, etc.)
            if not text_clean.rstrip().endswith((":", "—", "–", ".")):
                lexical_score = 1.0
            else:
                lexical_score = 0.3  # Ends with separator (might be label)
        else:
            lexical_score = 0.1  # Too short
    
    # C4: Type (passes type-gate)
    type_score = 1.0 if type_gate_generic(text_window, field.type or "text") else 0.0
    
    return ParetoCriteria(
        structural=structural_score,
        style=style_score,
        lexical=lexical_score,
        type=type_score,
    )


def pareto_filter(candidates: List[Dict[str, Any]], criteria_list: List[ParetoCriteria]) -> List[int]:
    """Filter candidates using Pareto optimality.
    
    Returns indices of non-dominated candidates.
    
    Args:
        candidates: List of candidate dicts.
        criteria_list: List of ParetoCriteria (one per candidate).
        
    Returns:
        List of indices of non-dominated candidates.
    """
    if not candidates or not criteria_list:
        return []
    
    if len(candidates) != len(criteria_list):
        raise ValueError("candidates and criteria_list must have same length")
    
    # Find non-dominated candidates
    non_dominated = []
    
    for i, criteria_i in enumerate(criteria_list):
        is_dominated = False
        
        for j, criteria_j in enumerate(criteria_list):
            if i != j and criteria_j.dominates(criteria_i):
                is_dominated = True
                break
        
        if not is_dominated:
            non_dominated.append(i)
    
    return non_dominated

