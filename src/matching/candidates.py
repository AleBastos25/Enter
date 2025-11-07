"""Type-first candidate generation (v3).

Generates candidates by pattern type and structure before matching to schema fields.
This reduces label bias and improves recall in "unusual" layouts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from ..core.models import Block, LayoutGraph, SchemaField
from ..core.doc_profile import DocProfile
from ..validation.patterns import PatternType, detect_pattern
from ..tables.detector import TableStructure


@dataclass
class CandidateFeatures:
    """Geometric and structural features of a candidate.
    
    Attributes:
        relation: Spatial relation (same_line_right_of, same_block, etc.)
        dist_xy: Normalized distance (dx, dy) from label (if available).
        same_col: Whether candidate is in same column as label.
        row_consistency: Consistency score for table rows (0-1).
        in_repeated_footer: Whether candidate is in repeated footer/header.
        font_z: Font z-score (normalized font size).
        bold: Whether text is bold.
        header_proximity: Distance to nearest header (0-1, 1=very close).
        in_table: Optional (table_id, row_idx, col_idx) if in table.
        section_id: Optional section ID.
        component_id: Optional connected component ID.
    """
    
    relation: str
    dist_xy: Tuple[float, float] = (0.0, 0.0)
    same_col: bool = False
    row_consistency: float = 0.0
    in_repeated_footer: bool = False
    font_z: float = 0.0
    bold: bool = False
    header_proximity: float = 0.0
    in_table: Optional[Tuple[str, int, int]] = None  # (table_id, row, col)
    section_id: Optional[int] = None
    component_id: Optional[int] = None


@dataclass
class Candidate:
    """Type-first candidate (v3).
    
    Attributes:
        candidate_id: Unique ID for this candidate.
        pattern_type: Detected pattern type.
        relation: Spatial relation.
        snippet: Short text snippet (≤120 chars).
        region_text: Full region text (≤300 chars).
        features: Geometric and structural features.
        block_id: Source block ID.
        field_hint: Optional field name hint (from label matching).
        label_block_id: Optional label block ID if found.
    """
    
    candidate_id: str
    pattern_type: PatternType
    relation: str
    snippet: str
    region_text: str
    features: CandidateFeatures
    block_id: int
    field_hint: Optional[str] = None
    label_block_id: Optional[int] = None


def build_candidate_sets(
    blocks: List[Block],
    layout: LayoutGraph,
    schema_fields: List[SchemaField],
    profile: DocProfile,
    tables: List[TableStructure] = None,
) -> Dict[str, List['Candidate']]:
    """Build candidate sets by pattern type before matching to schema.
    
    Args:
        blocks: List of text blocks.
        layout: LayoutGraph with spatial structure.
        schema_fields: List of schema fields to match.
        profile: Document profile for adaptive thresholds.
        tables: Optional list of detected tables.
    
    Returns:
        Dictionary mapping field_name -> list of Candidate objects.
    """
    if not blocks:
        return {field.name: [] for field in schema_fields}
    
    # Get layout structures
    graph_v2 = getattr(layout, "graph_v2", None)
    grid = getattr(layout, "grid", None)
    neighborhood = getattr(layout, "neighborhood", {})
    section_id_by_block = getattr(layout, "section_id_by_block", {})
    column_id_by_block = getattr(layout, "column_id_by_block", {})
    
    # Get component IDs from GraphV2
    component_id_by_block = {}
    if graph_v2 and isinstance(graph_v2, dict):
        component_id_by_block = graph_v2.get("component_id", {})
        style_by_block = graph_v2.get("style", {})
    else:
        style_by_block = {}
    
    # Build table lookup
    table_by_block: Dict[int, Tuple[str, int, int]] = {}  # block_id -> (table_id, row, col)
    if tables:
        for table in tables:
            table_id = table.id
            # Build cell lookup by ID
            cell_by_id = {cell.id: cell for cell in table.cells}
            for row_idx, row in enumerate(table.rows):
                # Get cells for this row using cell_ids
                for col_idx, cell_id in enumerate(row.cell_ids):
                    cell = cell_by_id.get(cell_id)
                    if cell:
                        for block_id in cell.block_ids:
                            table_by_block[block_id] = (table_id, row_idx, col_idx)
    
    # Find label blocks for each field (lightweight: Jaccard/Levenshtein)
    label_blocks_by_field: Dict[str, List[int]] = {}
    for field in schema_fields:
        label_blocks = _find_label_blocks_lightweight(field, blocks, profile)
        label_blocks_by_field[field.name] = label_blocks
    
    # Generate candidates by pattern type
    candidates_by_field: Dict[str, List[Candidate]] = {field.name: [] for field in schema_fields}
    
    # Group blocks by pattern type
    blocks_by_pattern: Dict[PatternType, List[Block]] = {}
    for block in blocks:
        pattern = detect_pattern(block.text or "")
        if pattern not in blocks_by_pattern:
            blocks_by_pattern[pattern] = []
        blocks_by_pattern[pattern].append(block)
    
    # For each field, generate candidates
    for field in schema_fields:
        field_candidates = []
        label_blocks = label_blocks_by_field.get(field.name, [])
        
        # 1. Position-based (if position_hint and no labels found OR if labels found but need additional candidates)
        # IMPROVEMENT: Also generate position candidates when labels are found but might need fallback
        if field.meta.get("position_hint"):
            if not label_blocks or len(field_candidates) == 0:
                position_candidates = _generate_position_candidates(
                    field, blocks, layout, profile, style_by_block, component_id_by_block
                )
                field_candidates.extend(position_candidates)
        
        # 2. Table lookup (if label block is in table)
        if label_blocks and tables:
            table_candidates = _generate_table_candidates(
                field, label_blocks, tables, table_by_block, blocks, profile
            )
            field_candidates.extend(table_candidates)
        
        # 3. Spatial neighborhood (same_line_right_of, same_block, first_below_same_column)
        if label_blocks:
            spatial_candidates = _generate_spatial_candidates(
                field,
                label_blocks,
                blocks,
                layout,
                grid,
                graph_v2,
                neighborhood,
                profile,
                style_by_block,
                component_id_by_block,
                section_id_by_block,
                column_id_by_block,
            )
            field_candidates.extend(spatial_candidates)
        
        # 4. Pattern-based (type-first): scan blocks matching expected pattern
        pattern_candidates = _generate_pattern_candidates(
            field,
            blocks,
            blocks_by_pattern,
            layout,
            profile,
            style_by_block,
            component_id_by_block,
            table_by_block,
            section_id_by_block,
        )
        field_candidates.extend(pattern_candidates)
        
        # 5. Global enum scan (for enum fields)
        if field.type == "enum" and field.meta.get("enum_options"):
            enum_candidates = _generate_enum_candidates(
                field,
                blocks,
                layout,
                profile,
                style_by_block,
                component_id_by_block,
            )
            field_candidates.extend(enum_candidates)
        
        # Deduplicate and filter
        field_candidates = _deduplicate_candidates(field_candidates)
        field_candidates = _filter_candidates(field_candidates, field, profile)
        
        candidates_by_field[field.name] = field_candidates
    
    return candidates_by_field


def _find_label_blocks_lightweight(
    field: SchemaField, blocks: List[Block], profile: DocProfile
) -> List[int]:
    """Find label blocks using lightweight Jaccard/Levenshtein matching.
    
    IMPROVEMENT: Also checks individual lines in multi-line blocks to find labels
    that may be in blocks containing multiple labels/values.
    
    Args:
        field: Schema field.
        blocks: List of blocks.
        profile: Document profile.
        
    Returns:
        List of block IDs that match field name/synonyms.
    """
    from ..matching.matcher import _label_score, _normalize_text
    
    label_blocks = []
    field_tokens = [field.name]
    if field.synonyms:
        field_tokens.extend(field.synonyms)
    
    # Get threshold with adaptive lowering for multi-line blocks
    base_threshold = profile.thresholds.get("tau_label", 0.35)
    
    for block in blocks:
        block_text = block.text or ""
        if not block_text:
            continue
        
        # Strategy 1: Check full block text (original behavior)
        for token in field_tokens:
            score = _label_score(token, block_text, min_threshold=0.0)
            if score >= base_threshold:
                label_blocks.append(block.id)
                break
        
        # Strategy 2: For multi-line blocks, check each line individually
        # This handles cases like "Inscrição\nSeccional\nSubseção"
        if "\n" in block_text:
            lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
            if len(lines) > 1:
                # Use slightly lower threshold for line-level matching
                # (more permissive since we're matching a substring)
                line_threshold = base_threshold * 0.85
                
                for line in lines:
                    for token in field_tokens:
                        # Check if line contains the token or matches closely
                        score = _label_score(token, line, min_threshold=0.0)
                        if score >= line_threshold:
                            # Additional check: line should be short (label-like)
                            if len(line.split()) <= 5:  # Labels are usually short
                                if block.id not in label_blocks:
                                    label_blocks.append(block.id)
                                break
                    if block.id in label_blocks:
                        break
    
    return label_blocks


def _generate_position_candidates(
    field: SchemaField,
    blocks: List[Block],
    layout: LayoutGraph,
    profile: DocProfile,
    style_by_block: Dict[int, Tuple[float, bool]],
    component_id_by_block: Dict[int, int],
) -> List[Candidate]:
    """Generate candidates from position hints.
    
    Args:
        field: Schema field with position_hint.
        blocks: List of blocks.
        layout: Layout graph.
        profile: Document profile.
        style_by_block: Style info (font_z, bold) by block ID.
        component_id_by_block: Component IDs by block.
    
    Returns:
        List of position-based candidates.
    """
    candidates = []
    position_hint = field.meta.get("position_hint", "").lower()
    
    if not blocks:
        return candidates
    
    # Determine quadrant
    page_width = max(b.bbox[2] for b in blocks) if blocks else 1.0
    page_height = max(b.bbox[3] for b in blocks) if blocks else 1.0
    
    # IMPROVEMENT: Use more flexible quadrant matching (allows slight overlap)
    # Also prioritize blocks by how well they match the position
    quadrant_candidates = []
    
    for block in blocks:
        x_center = (block.bbox[0] + block.bbox[2]) / 2.0
        y_center = (block.bbox[1] + block.bbox[3]) / 2.0
        
        # Calculate position match score (0.0 to 1.0)
        position_score = 0.0
        in_quadrant = False
        
        if "top" in position_hint and "left" in position_hint:
            in_quadrant = x_center < page_width * 0.55 and y_center < page_height * 0.55  # More flexible
            if in_quadrant:
                # Score based on how close to ideal position (top-left corner)
                x_score = 1.0 - (x_center / (page_width * 0.5))  # Closer to left = higher
                y_score = 1.0 - (y_center / (page_height * 0.5))  # Closer to top = higher
                position_score = (x_score + y_score) / 2.0
        elif "top" in position_hint and "right" in position_hint:
            in_quadrant = x_center >= page_width * 0.45 and y_center < page_height * 0.55
            if in_quadrant:
                x_score = (x_center - page_width * 0.5) / (page_width * 0.5)  # Closer to right = higher
                y_score = 1.0 - (y_center / (page_height * 0.5))
                position_score = (x_score + y_score) / 2.0
        elif "bottom" in position_hint and "left" in position_hint:
            in_quadrant = x_center < page_width * 0.55 and y_center >= page_height * 0.45
            if in_quadrant:
                x_score = 1.0 - (x_center / (page_width * 0.5))
                y_score = (y_center - page_height * 0.5) / (page_height * 0.5)
                position_score = (x_score + y_score) / 2.0
        elif "bottom" in position_hint and "right" in position_hint:
            in_quadrant = x_center >= page_width * 0.45 and y_center >= page_height * 0.45
            if in_quadrant:
                x_score = (x_center - page_width * 0.5) / (page_width * 0.5)
                y_score = (y_center - page_height * 0.5) / (page_height * 0.5)
                position_score = (x_score + y_score) / 2.0
        
        if in_quadrant and position_score > 0.3:  # Minimum position match
            pattern = detect_pattern(block.text or "")
            features = CandidateFeatures(
                relation="position_based",
                font_z=style_by_block.get(block.id, (0.0, False))[0],
                bold=style_by_block.get(block.id, (0.0, False))[1],
                component_id=component_id_by_block.get(block.id),
            )
            
            candidate = Candidate(
                candidate_id=f"pos_{block.id}",
                field_hint=field.name,
                pattern_type=pattern,
                relation="position_based",
                snippet=_truncate_text(block.text or "", 120),
                region_text=_truncate_text(block.text or "", 300),
                features=features,
                block_id=block.id,
            )
            # Store position score for sorting
            candidate.position_score = position_score
            quadrant_candidates.append(candidate)
    
    # Sort by position score (best matches first)
    quadrant_candidates.sort(key=lambda c: getattr(c, 'position_score', 0.0), reverse=True)
    
    return quadrant_candidates


def _generate_table_candidates(
    field: SchemaField,
    label_blocks: List[int],
    tables: List[TableStructure],
    table_by_block: Dict[int, Tuple[str, int, int]],
    blocks: List[Block],
    profile: DocProfile,
) -> List[Candidate]:
    """Generate candidates from table lookups.
    
    Args:
        field: Schema field.
        label_blocks: List of label block IDs.
        tables: List of table structures.
        table_by_block: Mapping block_id -> (table_id, row, col).
        blocks: List of all blocks.
        profile: Document profile.
    
    Returns:
        List of table-based candidates.
    """
    candidates = []
    block_by_id = {b.id: b for b in blocks}
    
    for label_block_id in label_blocks[:3]:  # Top 3 label blocks
        if label_block_id not in table_by_block:
            continue
        
        table_id, label_row, label_col = table_by_block[label_block_id]
        
        # Find table
        table = next((t for t in tables if t.id == table_id), None)
        if not table:
            continue
        
        # Find cell in same row
        if label_row < len(table.rows):
            row = table.rows[label_row]
            # Skip header row if detected (check if row is header based on first row or metadata)
            # For now, skip first row if it looks like a header (simple heuristic)
            if label_row == 0 and len(table.rows) > 1:
                # Could be header, but continue anyway for now
                pass
            
            # Build cell lookup by ID
            cell_by_id = {cell.id: cell for cell in table.cells}
            for col_idx, cell_id in enumerate(row.cell_ids):
                cell = cell_by_id.get(cell_id)
                if not cell:
                    continue
                if col_idx == label_col:
                    continue  # Skip label column
                
                for block_id in cell.block_ids:
                    block = block_by_id.get(block_id)
                    if not block:
                        continue
                    pattern = detect_pattern(block.text or "")
                    features = CandidateFeatures(
                        relation="same_table_row",
                        in_table=(table_id, label_row, col_idx),
                        row_consistency=1.0,  # Same row = full consistency
                    )
                    
                    candidate = Candidate(
                        candidate_id=f"table_{table_id}_{label_row}_{col_idx}",
                        field_hint=field.name,
                        pattern_type=pattern,
                        relation="same_table_row",
                        snippet=_truncate_text(block.text or "", 120),
                        region_text=_truncate_text(block.text or "", 300),
                        features=features,
                        block_id=block.id,
                        label_block_id=label_block_id,
                    )
                    candidates.append(candidate)
    
    return candidates


def _generate_spatial_candidates(
    field: SchemaField,
    label_blocks: List[int],
    blocks: List[Block],
    layout: LayoutGraph,
    grid,
    graph_v2,
    neighborhood: Dict,
    profile: DocProfile,
    style_by_block: Dict[int, Tuple[float, bool]],
    component_id_by_block: Dict[int, int],
    section_id_by_block: Dict[int, int],
    column_id_by_block: Dict[int, int],
) -> List[Candidate]:
    """Generate candidates from spatial neighborhood.
    
    Args:
        field: Schema field.
        label_blocks: List of label block IDs.
        blocks: List of all blocks.
        layout: Layout graph.
        grid: Grid structure.
        graph_v2: GraphV2 structure.
        neighborhood: Neighborhood index.
        profile: Document profile.
        style_by_block: Style info by block ID.
        component_id_by_block: Component IDs by block.
        section_id_by_block: Section IDs by block.
        column_id_by_block: Column IDs by block.
    
    Returns:
        List of spatial candidates.
    """
    candidates = []
    block_by_id = {b.id: b for b in blocks}
    
    for label_block_id in label_blocks[:5]:  # Top 5 label blocks
        label_block = block_by_id.get(label_block_id)
        if not label_block:
            continue
        
        label_x_center = (label_block.bbox[0] + label_block.bbox[2]) / 2.0
        label_y_center = (label_block.bbox[1] + label_block.bbox[3]) / 2.0
        
        # Same line right of
        if label_block_id in neighborhood:
            nb = neighborhood[label_block_id]
            right_id = nb.right_on_same_line if nb.right_on_same_line else None
            if right_id:
                right_block = block_by_id.get(right_id)
                if not right_block:
                    continue
                
                pattern = detect_pattern(right_block.text or "")
                dx = (right_block.bbox[0] - label_block.bbox[2]) / profile.thresholds.get("tau_gap_x", 0.05)
                dy = abs((right_block.bbox[1] + right_block.bbox[3]) / 2.0 - label_y_center) / profile.thresholds.get("tau_gap_y", 0.02)
                
                style = style_by_block.get(right_id, (0.0, False))
                features = CandidateFeatures(
                    relation="same_line_right_of",
                    dist_xy=(dx, dy),
                    same_col=column_id_by_block.get(right_id) == column_id_by_block.get(label_block_id),
                    font_z=style[0],
                    bold=style[1],
                    section_id=section_id_by_block.get(right_id),
                    component_id=component_id_by_block.get(right_id),
                )
                
                candidate = Candidate(
                    candidate_id=f"same_line_{right_id}",
                    field_hint=field.name,
                    pattern_type=pattern,
                    relation="same_line_right_of",
                    snippet=_truncate_text(right_block.text or "", 120),
                    region_text=_truncate_text(right_block.text or "", 300),
                    features=features,
                    block_id=right_id,
                    label_block_id=label_block_id,
                )
                candidates.append(candidate)
        
        # Same block (multiline)
        # Extract text from same block or blocks below in same column
        same_block_text = _extract_same_block_text(
            field, label_block_id, blocks, layout, grid, graph_v2, profile
        )
        if same_block_text and same_block_text != (label_block.text or ""):
            pattern = detect_pattern(same_block_text)
            features = CandidateFeatures(
                relation="same_block",
                same_col=True,
                section_id=section_id_by_block.get(label_block_id),
                component_id=component_id_by_block.get(label_block_id),
            )
            
            candidate = Candidate(
                candidate_id=f"same_block_{label_block_id}",
                field_hint=field.name,
                pattern_type=pattern,
                relation="same_block",
                snippet=_truncate_text(same_block_text, 120),
                region_text=_truncate_text(same_block_text, 300),
                features=features,
                block_id=label_block_id,
                label_block_id=label_block_id,
            )
            candidates.append(candidate)
        
        # First below same column
        if label_block_id in neighborhood:
            nb = neighborhood[label_block_id]
            below_id = nb.below_on_same_column if nb.below_on_same_column else None
            if below_id:
                below_block = block_by_id.get(below_id)
                if not below_block:
                    continue
                
                pattern = detect_pattern(below_block.text or "")
                dx = abs((below_block.bbox[0] + below_block.bbox[2]) / 2.0 - label_x_center) / profile.thresholds.get("tau_gap_x", 0.05)
                dy = (below_block.bbox[1] - label_block.bbox[3]) / profile.thresholds.get("tau_gap_y", 0.02)
                
                style = style_by_block.get(below_id, (0.0, False))
                features = CandidateFeatures(
                    relation="first_below_same_column",
                    dist_xy=(dx, dy),
                    same_col=True,
                    font_z=style[0],
                    bold=style[1],
                    section_id=section_id_by_block.get(below_id),
                    component_id=component_id_by_block.get(below_id),
                )
                
                candidate = Candidate(
                    candidate_id=f"below_{below_id}",
                    field_hint=field.name,
                    pattern_type=pattern,
                    relation="first_below_same_column",
                    snippet=_truncate_text(below_block.text or "", 120),
                    region_text=_truncate_text(below_block.text or "", 300),
                    features=features,
                    block_id=below_id,
                    label_block_id=label_block_id,
                )
                candidates.append(candidate)
    
    return candidates


def _generate_pattern_candidates(
    field: SchemaField,
    blocks: List[Block],
    blocks_by_pattern: Dict[PatternType, List[Block]],
    layout: LayoutGraph,
    profile: DocProfile,
    style_by_block: Dict[int, Tuple[float, bool]],
    component_id_by_block: Dict[int, int],
    table_by_block: Dict[int, Tuple[str, int, int]],
    section_id_by_block: Dict[int, int],
) -> List[Candidate]:
    """Generate candidates by matching pattern to field type.
    
    Args:
        field: Schema field.
        blocks: List of all blocks.
        blocks_by_pattern: Blocks grouped by pattern type.
        layout: Layout graph.
        profile: Document profile.
        style_by_block: Style info by block ID.
        component_id_by_block: Component IDs by block.
        table_by_block: Table mapping.
        section_id_by_block: Section IDs by block.
    
    Returns:
        List of pattern-based candidates.
    """
    from ..validation.patterns import type_gate_generic
    
    candidates = []
    
    # Determine expected pattern from field type
    expected_patterns = _get_expected_patterns_for_type(field.type)
    
    # Scan blocks matching expected patterns
    for pattern_type in expected_patterns:
        if pattern_type not in blocks_by_pattern:
            continue
        
        for block in blocks_by_pattern[pattern_type]:
            # Type gate: check if pattern is compatible
            if not type_gate_generic(block.text or "", field.type or "text"):
                continue
            
            # Skip if in repeated footer
            if block.id in profile.header_repetition_blocks:
                continue
            
            pattern = detect_pattern(block.text or "")
            style = style_by_block.get(block.id, (0.0, False))
            
            # Determine relation (heuristic: if in table, use table; otherwise "pattern_scan")
            relation = "pattern_scan"
            in_table = None
            if block.id in table_by_block:
                table_id, row, col = table_by_block[block.id]
                relation = "in_table"
                in_table = (table_id, row, col)
            
            features = CandidateFeatures(
                relation=relation,
                font_z=style[0],
                bold=style[1],
                in_table=in_table,
                section_id=section_id_by_block.get(block.id),
                component_id=component_id_by_block.get(block.id),
                in_repeated_footer=block.id in profile.header_repetition_blocks,
            )
            
            candidate = Candidate(
                candidate_id=f"pattern_{block.id}",
                pattern_type=pattern,
                relation=relation,
                snippet=_truncate_text(block.text or "", 120),
                region_text=_truncate_text(block.text or "", 300),
                features=features,
                block_id=block.id,
            )
            candidates.append(candidate)
    
    return candidates


def _generate_enum_candidates(
    field: SchemaField,
    blocks: List[Block],
    layout: LayoutGraph,
    profile: DocProfile,
    style_by_block: Dict[int, Tuple[float, bool]],
    component_id_by_block: Dict[int, int],
) -> List[Candidate]:
    """Generate candidates for enum fields by scanning all blocks.
    
    Args:
        field: Schema field (must have enum_options).
        blocks: List of all blocks.
        layout: Layout graph.
        profile: Document profile.
        style_by_block: Style info by block ID.
        component_id_by_block: Component IDs by block.
    
    Returns:
        List of enum candidates.
    """
    candidates = []
    enum_options = field.meta.get("enum_options", [])
    
    if not enum_options:
        return candidates
    
    # Normalize options (case-insensitive, accent-insensitive)
    import unicodedata
    normalized_options = {}
    for opt in enum_options:
        norm = unicodedata.normalize("NFD", opt.upper()).encode("ascii", "ignore").decode("ascii")
        normalized_options[norm] = opt
    
    for block in blocks:
        block_text = block.text or ""
        block_text_norm = unicodedata.normalize("NFD", block_text.upper()).encode("ascii", "ignore").decode("ascii")
        
        # Check if block text matches any enum option
        for norm_opt, orig_opt in normalized_options.items():
            if norm_opt in block_text_norm or block_text_norm in norm_opt:
                style = style_by_block.get(block.id, (0.0, False))
                features = CandidateFeatures(
                    relation="global_enum_scan",
                    font_z=style[0],
                    bold=style[1],
                    component_id=component_id_by_block.get(block.id),
                )
                
                candidate = Candidate(
                    candidate_id=f"enum_{block.id}",
                    field_hint=field.name,
                    pattern_type="text",
                    relation="global_enum_scan",
                    snippet=_truncate_text(block_text, 120),
                    region_text=_truncate_text(block_text, 300),
                    features=features,
                    block_id=block.id,
                )
                candidates.append(candidate)
                break  # Only one match per block
    
    return candidates


def _get_expected_patterns_for_type(field_type: Optional[str]) -> List[PatternType]:
    """Get expected pattern types for a field type.
    
    Args:
        field_type: Field type (e.g., "date", "money", "int").
    
    Returns:
        List of compatible pattern types.
    """
    if not field_type:
        return ["text"]
    
    type_to_patterns = {
        "date": ["date_like"],
        "money": ["money_like", "digits_with_separators"],
        "int": ["digits_only", "digits_with_separators"],
        "float": ["digits_only", "digits_with_separators", "money_like"],
        "percent": ["digits_with_separators", "digits_only"],
        "uf": ["isolated_letters"],
        "cep": ["digits_only", "digits_with_separators"],
        "cpf": ["digits_only", "digits_with_separators"],
        "cnpj": ["digits_only", "digits_with_separators"],
        "phone_br": ["digits_only", "digits_with_separators"],
        "alphanum_code": ["alphanumeric", "digits_with_separators"],
        "text": ["text", "alphanumeric"],
        "enum": ["text", "isolated_letters"],
    }
    
    return type_to_patterns.get(field_type, ["text"])


def _extract_same_block_text(
    field: SchemaField,
    label_block_id: int,
    blocks: List[Block],
    layout: LayoutGraph,
    grid,
    graph_v2,
    profile: DocProfile,
) -> str:
    """Extract text from same block or blocks below in same column (multiline).
    
    Args:
        label_block_id: Label block ID.
        blocks: List of all blocks.
        layout: Layout graph.
        grid: Grid structure.
        profile: Document profile.
    
    Returns:
        Extracted text (may include label).
    """
    from ..extraction.text_extractor import _build_roi_multiline, _decide_keep_label
    
    label_block = next((b for b in blocks if b.id == label_block_id), None)
    if not label_block:
        return ""
    
    # Use existing ROI multiline logic
    roi_text = _build_roi_multiline(label_block, grid, blocks)
    if not roi_text:
        return ""
    
    # Decide if we should keep label
    # _decide_keep_label returns (final_text, keep_label)
    final_text, keep_label = _decide_keep_label(
        field,
        label_block.text or "",
        roi_text,
        graph_v2,
    )
    
    return final_text if keep_label else roi_text


def _truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, preserving word boundaries if possible.
    
    Args:
        text: Text to truncate.
        max_chars: Maximum characters.
    
    Returns:
        Truncated text.
    """
    if len(text) <= max_chars:
        return text
    
    truncated = text[:max_chars]
    # Try to cut at word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.7:  # If space is not too early
        truncated = truncated[:last_space]
    
    return truncated + "..."


def _deduplicate_candidates(candidates: List[Candidate]) -> List[Candidate]:
    """Remove duplicate candidates (same block_id, relation).
    
    Args:
        candidates: List of candidates.
    
    Returns:
        Deduplicated list (keeps first occurrence).
    """
    seen = set()
    unique = []
    
    for cand in candidates:
        key = (cand.block_id, cand.relation)
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    
    return unique


def _filter_candidates(
    candidates: List[Candidate], field: SchemaField, profile: DocProfile
) -> List[Candidate]:
    """Filter candidates by type gate and footer penalty.
    
    Args:
        candidates: List of candidates.
        field: Schema field.
        profile: Document profile.
    
    Returns:
        Filtered list of candidates.
    """
    from ..validation.patterns import type_gate_generic
    
    filtered = []
    
    for cand in candidates:
        # Hard type gate - use region_text (more complete) instead of snippet
        text_for_gate = cand.region_text if cand.region_text else cand.snippet
        if not type_gate_generic(text_for_gate, field.type or "text"):
            continue
        
        # Footer penalty: skip if in repeated footer (unless very high confidence)
        if cand.features.in_repeated_footer:
            # Can still use if it's a very strong match, but penalize
            pass  # Will be penalized in scoring
        
        filtered.append(cand)
    
    return filtered

