"""Role classification for text units: HEADER / LABEL / VALUE.

Uses deterministic rules to classify TUs by their role in the document.
"""

from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional, Set

from ..core.models import Block, LayoutGraph
from ..validation.patterns import type_gate_generic
from .style_signature import StyleSignature

RoleType = Literal["HEADER", "LABEL", "VALUE"]


# Common label separators
LABEL_SEPARATORS = [":", "—", "–", ".", "•"]


def _is_label_separator(text: str) -> bool:
    """Check if text ends with a label separator.
    
    Args:
        text: Text to check.
        
    Returns:
        True if text ends with label separator.
    """
    text_stripped = text.rstrip()
    return any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)


def _is_short_text(text: str, max_tokens: int = 3) -> bool:
    """Check if text is short (likely a label).
    
    Args:
        text: Text to check.
        max_tokens: Maximum tokens to consider short.
        
    Returns:
        True if text has ≤ max_tokens tokens.
    """
    if not text:
        return False
    tokens = text.split()
    return len(tokens) <= max_tokens


def _has_no_digits(text: str) -> bool:
    """Check if text has no digits.
    
    Args:
        text: Text to check.
        
    Returns:
        True if text has no digits.
    """
    return not bool(re.search(r"\d", text))


def classify_role_initial(
    block: Block,
    layout: LayoutGraph,
    field_type: Optional[str] = None,
    style_signature: Optional[StyleSignature] = None,
) -> Optional[RoleType]:
    """Initial role classification by rules.
    
    Rules (in order of priority):
    1. HEADER if (very large font relative to section) OR (centered and isolated) OR (parent of table/grid)
    2. LABEL if (ends with separator) OR (short ≤3 tokens, no digits) OR (has neighbor that looks like VALUE)
    3. VALUE if (passes type-gate) AND (doesn't end with label separator)
    
    Args:
        block: Block to classify.
        layout: LayoutGraph.
        field_type: Optional field type hint (for type-gate).
        style_signature: Optional style signature for style-based classification.
        
    Returns:
        RoleType or None if unclear.
    """
    text = block.text or ""
    text_stripped = text.strip()
    
    if not text_stripped:
        return None
    
    # Rule 1: HEADER
    # Check if very large font (would need font size comparison with section average)
    # For now, check if bold and large (heuristic)
    if block.bold and block.font_size:
        # Check if font is significantly larger than average
        all_font_sizes = [b.font_size for b in layout.blocks if b.font_size is not None]
        if all_font_sizes:
            avg_font = sum(all_font_sizes) / len(all_font_sizes)
            if block.font_size > avg_font * 1.3:  # 30% larger
                return "HEADER"
    
    # Check if centered and isolated (heuristic: near center of page, few neighbors)
    bbox = block.bbox
    center_x = (bbox[0] + bbox[2]) / 2.0
    center_y = (bbox[1] + bbox[3]) / 2.0
    
    # Check if near center (within 0.3-0.7 range)
    if 0.3 <= center_x <= 0.7 and 0.2 <= center_y <= 0.5:
        # Check if isolated (few blocks nearby)
        nearby_count = 0
        for other in layout.blocks:
            if other.id == block.id:
                continue
            other_bbox = other.bbox
            other_center_x = (other_bbox[0] + other_bbox[2]) / 2.0
            other_center_y = (other_bbox[1] + other_bbox[3]) / 2.0
            
            # Check if within distance
            dist = ((center_x - other_center_x) ** 2 + (center_y - other_center_y) ** 2) ** 0.5
            if dist < 0.2:
                nearby_count += 1
        
        if nearby_count <= 2:  # Isolated
            return "HEADER"
    
    # Rule 2: LABEL
    # Ends with separator
    if _is_label_separator(text_stripped):
        return "LABEL"
    
    # Short (≤3 tokens) and no digits
    if _is_short_text(text_stripped, max_tokens=3) and _has_no_digits(text_stripped):
        return "LABEL"
    
    # Check if has neighbor that looks like VALUE (simplified: check right neighbor)
    neighborhood = getattr(layout, "neighborhood", {})
    nb = neighborhood.get(block.id)
    if nb and nb.right_on_same_line:
        right_block = next((b for b in layout.blocks if b.id == nb.right_on_same_line), None)
        if right_block and field_type:
            # Check if right neighbor passes type-gate
            if type_gate_generic(right_block.text or "", field_type):
                return "LABEL"  # This block is likely a label for the value to the right
    
    # Rule 3: VALUE
    # Passes type-gate and doesn't end with separator
    if field_type:
        if type_gate_generic(text_stripped, field_type) and not _is_label_separator(text_stripped):
            return "VALUE"
    
    # Default: if no clear classification, return None
    return None


def propagate_role_by_style(
    blocks: List[Block],
    initial_roles: Dict[int, Optional[RoleType]],
    style_signatures: Dict[int, StyleSignature],
    graph_v2: Optional[Dict] = None,
) -> Dict[int, RoleType]:
    """Propagate roles by style components.
    
    Connect TUs with identical style signatures that are orthogonally adjacent,
    and assign a single role to the component by priority: HEADER > LABEL > VALUE.
    
    If any TU in component is HEADER, entire component is HEADER.
    Else if any TU is LABEL, entire component is LABEL.
    Else VALUE.
    
    Special rule: If a VALUE ends with label separator, component becomes LABEL.
    
    Args:
        blocks: List of blocks.
        initial_roles: Dictionary mapping block_id -> initial role (or None).
        style_signatures: Dictionary mapping block_id -> StyleSignature.
        graph_v2: Optional GraphV2 structure with adjacency.
        
    Returns:
        Dictionary mapping block_id -> final role.
    """
    if not blocks:
        return {}
    
    # Build style components (TUs with same signature that are orthogonally connected)
    component_by_block: Dict[int, int] = {}
    component_id = 0
    
    # Use graph_v2 component_id if available, else build from style
    if graph_v2 and "component_id" in graph_v2:
        component_by_block = graph_v2["component_id"]
    else:
        # Build components from style signatures
        # Group blocks with same signature
        signature_to_blocks: Dict[StyleSignature, List[int]] = {}
        for block in blocks:
            sig = style_signatures.get(block.id)
            if sig:
                if sig not in signature_to_blocks:
                    signature_to_blocks[sig] = []
                signature_to_blocks[sig].append(block.id)
        
        # Assign component IDs
        for sig, block_ids in signature_to_blocks.items():
            for block_id in block_ids:
                component_by_block[block_id] = component_id
            component_id += 1
    
    # Assign roles to components (priority: HEADER > LABEL > VALUE)
    component_role: Dict[int, RoleType] = {}
    
    for comp_id in set(component_by_block.values()):
        component_blocks = [b for b in blocks if component_by_block.get(b.id) == comp_id]
        
        # Check initial roles
        has_header = False
        has_label = False
        has_value = False
        
        for block in component_blocks:
            role = initial_roles.get(block.id)
            if role == "HEADER":
                has_header = True
            elif role == "LABEL":
                has_label = True
            elif role == "VALUE":
                has_value = True
        
        # Priority: HEADER > LABEL > VALUE
        if has_header:
            component_role[comp_id] = "HEADER"
        elif has_label:
            component_role[comp_id] = "LABEL"
        elif has_value:
            component_role[comp_id] = "VALUE"
        else:
            # Default: VALUE if unclear
            component_role[comp_id] = "VALUE"
        
        # Special rule: If VALUE ends with separator, convert to LABEL
        for block in component_blocks:
            if component_role[comp_id] == "VALUE":
                text = block.text or ""
                if _is_label_separator(text):
                    component_role[comp_id] = "LABEL"
                    break
    
    # Assign final roles to blocks
    final_roles: Dict[int, RoleType] = {}
    for block in blocks:
        comp_id = component_by_block.get(block.id)
        if comp_id is not None:
            final_roles[block.id] = component_role.get(comp_id, "VALUE")
        else:
            # Fallback: use initial role or default to VALUE
            final_roles[block.id] = initial_roles.get(block.id) or "VALUE"
    
    return final_roles

