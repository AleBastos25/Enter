"""Style signature computation for text units (TUs).

Implements S(TU) = (font_family_id, font_size_bin, is_bold, is_italic, 
color_cluster, caps_ratio_bin, letter_spacing_bin).

TUs with identical S belong to the same style class.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..core.models import Block


@dataclass(frozen=True)
class StyleSignature:
    """Style signature for a text unit.
    
    Attributes:
        font_family_id: Clustered font family ID.
        font_size_bin: Quantile bin for font size.
        is_bold: Whether text is bold.
        is_italic: Whether text is italic.
        color_cluster: Color cluster ID (if available).
        caps_ratio_bin: Quantile bin for uppercase ratio.
        letter_spacing_bin: Quantile bin for average letter spacing.
    """
    
    font_family_id: int
    font_size_bin: int
    is_bold: bool
    is_italic: bool
    color_cluster: int
    caps_ratio_bin: int
    letter_spacing_bin: int
    
    def __eq__(self, other) -> bool:
        """Two signatures are equal if all components match."""
        if not isinstance(other, StyleSignature):
            return False
        return (
            self.font_family_id == other.font_family_id
            and self.font_size_bin == other.font_size_bin
            and self.is_bold == other.is_bold
            and self.is_italic == other.is_italic
            and self.color_cluster == other.color_cluster
            and self.caps_ratio_bin == other.caps_ratio_bin
            and self.letter_spacing_bin == other.letter_spacing_bin
        )


def _cluster_font_families(blocks: List[Block]) -> Dict[Optional[str], int]:
    """Cluster font families into IDs.
    
    Uses simple string matching (case-insensitive) to group similar families.
    
    Args:
        blocks: List of blocks to analyze.
        
    Returns:
        Dictionary mapping font_family -> cluster_id.
    """
    # Get unique font families (from spans if available, else None)
    families = set()
    for block in blocks:
        if block.spans:
            for span in block.spans:
                # Font family would come from span metadata if available
                # For now, use a placeholder
                families.add(None)
        else:
            families.add(None)
    
    # Simple clustering: assign same ID for same string (case-insensitive)
    family_to_id: Dict[Optional[str], int] = {}
    next_id = 0
    
    for family in families:
        if family not in family_to_id:
            # Check if similar family already exists (case-insensitive)
            found_match = False
            for existing_family, existing_id in family_to_id.items():
                if existing_family and family:
                    if existing_family.lower() == family.lower():
                        family_to_id[family] = existing_id
                        found_match = True
                        break
            
            if not found_match:
                family_to_id[family] = next_id
                next_id += 1
    
    return family_to_id


def _quantile_bins(data: List[float], n_bins: int = 5) -> Dict[float, int]:
    """Assign values to quantile bins.
    
    Args:
        data: List of values to bin.
        n_bins: Number of bins (default 5).
        
    Returns:
        Dictionary mapping value -> bin_id (0..n_bins-1).
    """
    if not data:
        return {}
    
    sorted_data = sorted(data)
    value_to_bin: Dict[float, int] = {}
    
    # For each value, find its quantile and assign bin
    for val in data:
        if len(sorted_data) == 1:
            bin_id = 0
        else:
            # Find percentile
            percentile = (sorted_data.index(val) / (len(sorted_data) - 1)) * 100
            # Map to bin
            bin_id = min(int(percentile / (100 / n_bins)), n_bins - 1)
        value_to_bin[val] = bin_id
    
    return value_to_bin


def _compute_caps_ratio(text: str) -> float:
    """Compute ratio of uppercase letters.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Ratio of uppercase letters (0.0 to 1.0).
    """
    if not text:
        return 0.0
    
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    
    uppercase = sum(1 for c in letters if c.isupper())
    return uppercase / len(letters)


def _compute_letter_spacing(text: str, bbox_width: float) -> float:
    """Compute average letter spacing (gap between characters).
    
    Args:
        text: Text content.
        bbox_width: Width of bounding box.
        
    Returns:
        Average spacing per character (normalized).
    """
    if not text or bbox_width <= 0:
        return 0.0
    
    # Remove spaces and count non-space characters
    non_space_chars = len([c for c in text if not c.isspace()])
    if non_space_chars <= 1:
        return 0.0
    
    # Average spacing = (width - estimated_char_width * n_chars) / (n_chars - 1)
    # Estimate char width as width / len(text) (rough)
    avg_char_width = bbox_width / len(text) if text else 0
    estimated_text_width = avg_char_width * non_space_chars
    
    if non_space_chars <= 1:
        return 0.0
    
    avg_spacing = (bbox_width - estimated_text_width) / max(1, non_space_chars - 1)
    return avg_spacing


def compute_style_signatures(blocks: List[Block]) -> Dict[int, StyleSignature]:
    """Compute style signatures for all blocks.
    
    Args:
        blocks: List of blocks to analyze.
        
    Returns:
        Dictionary mapping block_id -> StyleSignature.
    """
    if not blocks:
        return {}
    
    # Cluster font families
    family_to_id = _cluster_font_families(blocks)
    
    # Collect font sizes for binning
    font_sizes = [b.font_size for b in blocks if b.font_size is not None]
    font_size_bins = _quantile_bins(font_sizes, n_bins=5) if font_sizes else {}
    
    # Collect caps ratios for binning
    caps_ratios = [_compute_caps_ratio(b.text or "") for b in blocks]
    caps_ratio_bins = _quantile_bins(caps_ratios, n_bins=5)
    
    # Collect letter spacing for binning
    letter_spacings = []
    for block in blocks:
        bbox_width = block.bbox[2] - block.bbox[0]
        spacing = _compute_letter_spacing(block.text or "", bbox_width)
        letter_spacings.append(spacing)
    letter_spacing_bins = _quantile_bins(letter_spacings, n_bins=5)
    
    # Compute signatures
    signatures: Dict[int, StyleSignature] = {}
    
    for block in blocks:
        # Font family ID
        font_family = None  # Would come from spans if available
        font_family_id = family_to_id.get(font_family, 0)
        
        # Font size bin
        font_size = block.font_size or 0.0
        font_size_bin = font_size_bins.get(font_size, 0)
        
        # Bold/italic (from block or spans)
        is_bold = block.bold
        is_italic = False  # Would come from spans if available
        
        # Color cluster (placeholder, would need color info from spans)
        color_cluster = 0
        
        # Caps ratio bin
        caps_ratio = _compute_caps_ratio(block.text or "")
        caps_ratio_bin = caps_ratio_bins.get(caps_ratio, 0)
        
        # Letter spacing bin
        bbox_width = block.bbox[2] - block.bbox[0]
        letter_spacing = _compute_letter_spacing(block.text or "", bbox_width)
        letter_spacing_bin = letter_spacing_bins.get(letter_spacing, 0)
        
        signatures[block.id] = StyleSignature(
            font_family_id=font_family_id,
            font_size_bin=font_size_bin,
            is_bold=is_bold,
            is_italic=is_italic,
            color_cluster=color_cluster,
            caps_ratio_bin=caps_ratio_bin,
            letter_spacing_bin=letter_spacing_bin,
        )
    
    return signatures

