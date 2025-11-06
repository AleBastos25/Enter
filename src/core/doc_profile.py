"""Document profile for adaptive thresholding and feature detection.

This module builds a profile of document characteristics to calibrate
thresholds and strategies per document, rather than using global magic numbers.
"""

from dataclasses import dataclass
from typing import Dict, List, Literal, Set

from .models import Block
from ..layout.graph_v2 import GraphV2


@dataclass
class DocProfile:
    """Profile of document characteristics for adaptive processing.
    
    Attributes:
        reading_order: Forced to "ltr_td" (left-to-right, top-down).
        column_count: Number of detected columns.
        columniness: Score 0..1 indicating column structure clarity.
        grid_likeness: Score 0..1 indicating grid/table structure.
        header_repetition_blocks: Set of block IDs that appear in headers/footers.
        noise_score: Score 0..1 indicating text noise (strange chars).
        thresholds: Adaptive thresholds keyed by feature name.
    """
    
    reading_order: Literal["ltr_td"] = "ltr_td"
    column_count: int = 1
    columniness: float = 0.0
    grid_likeness: float = 0.0
    header_repetition_blocks: Set[int] = None
    noise_score: float = 0.0
    thresholds: Dict[str, float] = None
    
    def __post_init__(self):
        if self.header_repetition_blocks is None:
            self.header_repetition_blocks = set()
        if self.thresholds is None:
            self.thresholds = {}


def build_doc_profile(
    blocks: List[Block],
    lines: List = None,  # VecLine type (avoid circular import)
    graph_v2: GraphV2 = None,
    grid = None,
) -> DocProfile:
    """Build document profile from blocks, lines, and layout structures.
    
    Args:
        blocks: List of text blocks from the document.
        lines: Optional list of vector lines from PDF.
        graph_v2: Optional GraphV2 structure for component analysis.
        grid: Optional Grid structure for grid analysis.
    
    Returns:
        DocProfile with calibrated characteristics.
    """
    profile = DocProfile()
    
    if not blocks:
        return profile
    
    # 1. Reading order: forced LTR/TD, but measure violations
    # For now, assume LTR/TD (as requested)
    profile.reading_order = "ltr_td"
    
    # 2. Column detection and columniness
    if len(blocks) > 0:
        # Cluster X-centroids to detect columns
        x_centers = [(b.bbox[0] + b.bbox[2]) / 2.0 for b in blocks]
        x_centers_sorted = sorted(set(x_centers))
        
        # Simple clustering: if centers are within 5% of page width, same column
        if len(x_centers) > 0:
            page_width = max(b.bbox[2] for b in blocks) if blocks else 1.0
            threshold_x = page_width * 0.05
            
            clusters = []
            for x in x_centers_sorted:
                if not clusters or abs(x - clusters[-1][-1]) > threshold_x:
                    clusters.append([x])
                else:
                    clusters[-1].append(x)
            
            profile.column_count = len(clusters)
            
            # Columniness: how well-separated are columns?
            if len(clusters) > 1:
                # Measure dispersion
                cluster_centers = [sum(cl) / len(cl) for cl in clusters]
                cluster_centers.sort()
                gaps = [cluster_centers[i+1] - cluster_centers[i] 
                       for i in range(len(cluster_centers) - 1)]
                avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
                profile.columniness = min(1.0, avg_gap / (page_width * 0.3))
            else:
                profile.columniness = 0.0
        else:
            profile.column_count = 1
            profile.columniness = 0.0
    
    # 3. Grid likeness (from grid structure if available)
    if grid is not None:
        # Check if grid has consistent spans (table-like structure)
        # spans is Dict[block_id, Tuple[col_start, col_end]]
        spans = grid.get("spans", {}) if isinstance(grid, dict) else getattr(grid, "spans", {})
        if spans:
            # Count spans by column span width (col_end - col_start + 1)
            span_widths = []
            for span_value in spans.values():
                if isinstance(span_value, tuple) and len(span_value) >= 2:
                    col_start, col_end = span_value[0], span_value[1]
                    span_width = col_end - col_start + 1
                    span_widths.append(span_width)
            
            # Consistency: do most spans have similar widths?
            if span_widths:
                # Check if most spans have similar width (within 1 column)
                if len(span_widths) > 0:
                    avg_width = sum(span_widths) / len(span_widths)
                    consistency = sum(1 for w in span_widths 
                                    if abs(w - avg_width) <= 1) / len(span_widths)
                    profile.grid_likeness = consistency
                else:
                    profile.grid_likeness = 0.0
            else:
                profile.grid_likeness = 0.0
        else:
            profile.grid_likeness = 0.0
    elif lines:
        # Fallback: count vector lines (horizontal + vertical)
        h_lines = [l for l in lines if hasattr(l, 'is_horizontal') and l.is_horizontal()]
        v_lines = [l for l in lines if hasattr(l, 'is_vertical') and l.is_vertical()]
        total_lines = len(h_lines) + len(v_lines)
        # Rough estimate: if many lines, likely grid-like
        profile.grid_likeness = min(1.0, total_lines / max(10, len(blocks) * 0.1))
    else:
        profile.grid_likeness = 0.0
    
    # 4. Header/footer repetition detection
    # Hash blocks by text+font_z+bbox_position to find duplicates
    block_hashes = {}
    for block in blocks:
        # Normalize bbox to page-relative position (bucket by 5% of page)
        page_height = max(b.bbox[3] for b in blocks) if blocks else 1.0
        page_width = max(b.bbox[2] for b in blocks) if blocks else 1.0
        
        y_bucket = int((block.bbox[1] + block.bbox[3]) / 2.0 / page_height * 20)
        text_hash = hash(block.text.strip().lower()[:50])  # First 50 chars
        font_z = getattr(block, 'font_z', 0.0)
        font_z_bucket = int(font_z * 10) if font_z else 0
        
        block_hash = (text_hash, font_z_bucket, y_bucket)
        
        if block_hash not in block_hashes:
            block_hashes[block_hash] = []
        block_hashes[block_hash].append(block.id)
    
    # Blocks that appear 2+ times are likely headers/footers
    repeated_blocks = set()
    for block_ids in block_hashes.values():
        if len(block_ids) >= 2:
            repeated_blocks.update(block_ids)
    
    profile.header_repetition_blocks = repeated_blocks
    
    # 5. Noise score: rate of strange characters
    total_chars = 0
    strange_chars = 0
    
    for block in blocks:
        text = block.text or ""
        for char in text:
            total_chars += 1
            # Check if char is "normal" (alphanumeric, common punctuation, diacritics)
            if not (char.isalnum() or char in '.,;:!?()-[]{}"\'' or ord(char) < 128):
                strange_chars += 1
    
    profile.noise_score = strange_chars / max(1, total_chars)
    
    # 6. Adaptive thresholds
    # Calibrate based on document characteristics
    profile.thresholds = {
        "tau_label": 0.35,  # Base label matching threshold
        "tau_gap_x": 0.05 if profile.columniness > 0.5 else 0.03,  # X gap for same_line
        "tau_gap_y": 0.02,  # Y gap for same column
        "tau_footer_penalty": 0.35,  # Penalty for footer blocks
        "tau_grid_consistency": 0.6,  # Minimum consistency for grid activation
        "tau_min_score": 0.60,  # Minimum score to accept assignment
    }
    
    # Adjust thresholds based on noise
    if profile.noise_score > 0.1:
        # More noise -> more lenient thresholds
        profile.thresholds["tau_label"] *= 0.9
        profile.thresholds["tau_gap_x"] *= 1.1
    
    return profile

