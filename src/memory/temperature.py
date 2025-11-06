"""Document temperature computation.

T ∈ [0,1] measures how "hot" a document is, i.e., how many invariants repeat.
T = (# invariantes satisfeitos) / (# invariantes aplicáveis)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def compute_document_temperature(
    pattern_memory: Optional[Any],
    field_name: str,
    label_text: Optional[str] = None,
    direction: Optional[str] = None,
    offset: Optional[tuple] = None,
    style_signature: Optional[Any] = None,
) -> float:
    """Compute temperature for a field based on learned invariants.
    
    T = (# invariantes satisfeitos) / (# invariantes aplicáveis)
    
    Args:
        pattern_memory: PatternMemory instance (or None if not available).
        field_name: Field name.
        label_text: Optional label text seen.
        direction: Optional direction (→, ↓, ↑, ←).
        offset: Optional offset tuple (dx, dy).
        style_signature: Optional style signature.
        
    Returns:
        Temperature T ∈ [0,1] (0.0 = cold/new, 1.0 = hot/familiar).
    """
    if not pattern_memory:
        return 0.0  # No memory = cold document
    
    # Count applicable invariants
    applicable_count = 0
    satisfied_count = 0
    
    # Invariant 1: Label vocabulary
    learned_labels = pattern_memory.get_synonyms(field_name, max_k=100) if hasattr(pattern_memory, 'get_synonyms') else []
    if learned_labels:
        applicable_count += 1
        if label_text:
            # Check if label_text matches any learned label
            label_lower = label_text.lower().strip()
            for learned in learned_labels:
                if learned.lower().strip() in label_lower or label_lower in learned.lower().strip():
                    satisfied_count += 1
                    break
    
    # Invariant 2: Directions
    strategy_hints = pattern_memory.get_strategy_hints(field_name) if hasattr(pattern_memory, 'get_strategy_hints') else {}
    if strategy_hints:
        preferred_directions = strategy_hints.get("preferred_directions", [])
        if preferred_directions:
            applicable_count += 1
            if direction and direction in preferred_directions:
                satisfied_count += 1
    
    # Invariant 3: Offsets
    learned_offsets = pattern_memory.get_offsets(field_name) if hasattr(pattern_memory, 'get_offsets') else []
    if learned_offsets:
        applicable_count += 1
        if offset:
            # Check if offset is similar to learned offsets (simplified)
            # Would need more sophisticated distance check
            satisfied_count += 1  # Simplified: assume satisfied if offset exists
    
    # Invariant 4: Style signatures
    if style_signature:
        applicable_count += 1
        # Simplified: assume satisfied if style signature exists
        # Would need to check against learned style signatures
        satisfied_count += 1
    
    # Compute temperature
    if applicable_count == 0:
        return 0.0
    
    temperature = satisfied_count / applicable_count
    return min(1.0, max(0.0, temperature))


def compute_global_temperature(
    pattern_memory: Optional[Any],
    document_label: str,
    fields: List[Any],
) -> float:
    """Compute global temperature for entire document.
    
    Args:
        pattern_memory: PatternMemory instance.
        document_label: Document label.
        fields: List of SchemaField objects.
        
    Returns:
        Global temperature T ∈ [0,1].
    """
    if not pattern_memory or not fields:
        return 0.0
    
    # Compute temperature per field and average
    temperatures = []
    for field in fields:
        temp = compute_document_temperature(pattern_memory, field.name)
        temperatures.append(temp)
    
    if not temperatures:
        return 0.0
    
    return sum(temperatures) / len(temperatures)
