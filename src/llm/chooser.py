"""LLM chooser for breaking ties between candidates.

LLM is used ONLY as a chooser when Pareto + tie-breakers leave >1 candidates.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from ..core.models import LayoutGraph, SchemaField


# Simple cache for LLM chooser responses
_chooser_cache: Dict[str, Dict[str, Any]] = {}


def _hash_candidates(field: SchemaField, candidates: List[Dict[str, Any]]) -> str:
    """Hash candidates for cache key.
    
    Args:
        field: SchemaField.
        candidates: List of candidate dicts.
        
    Returns:
        Cache key string.
    """
    # Create hash from field name, enum options, and candidate text windows
    key_parts = [field.name]
    if field.meta and field.meta.get("enum_options"):
        key_parts.append(str(sorted(field.meta["enum_options"])))
    
    for cand in candidates[:3]:  # Only first 3
        text = cand.get("text_window", "")
        relation = cand.get("relation", "")
        key_parts.append(f"{relation}:{text[:50]}")
    
    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def _build_chooser_prompt(
    field: SchemaField,
    candidates: List[Dict[str, Any]],
    layout: LayoutGraph,
    document_label: str,
) -> str:
    """Build compact prompt for LLM chooser.
    
    Args:
        field: SchemaField being extracted.
        candidates: List of candidate dicts (max 3).
        layout: LayoutGraph.
        document_label: Document label.
        
    Returns:
        Prompt string.
    """
    # Field info
    field_desc = field.description or ""
    enum_options = field.meta.get("enum_options") if field.meta else None
    
    prompt_parts = [
        f"Document type: {document_label}",
        f"Field: {field.name}",
        f"Description: {field_desc}",
    ]
    
    if enum_options:
        prompt_parts.append(f"Valid options: {', '.join(enum_options)}")
    
    prompt_parts.append("\nCandidates (choose one index 0-{k} or -1 for none):")
    
    # Candidate info
    block_by_id = {b.id: b for b in layout.blocks}
    
    for i, cand in enumerate(candidates[:3]):  # Max 3
        text_window = cand.get("text_window", "")
        relation = cand.get("relation", "")
        block_id = cand.get("block_id")
        label_block_id = cand.get("label_block_id")
        
        # Get label text if available
        label_text = ""
        if label_block_id:
            label_block = block_by_id.get(label_block_id)
            if label_block:
                label_text = label_block.text or ""
                if len(label_text) > 40:
                    label_text = label_text[:40] + "..."
        
        # Get neighbors (±1 block) for context
        neighbors = []
        neighborhood = getattr(layout, "neighborhood", {})
        nb = neighborhood.get(block_id)
        if nb:
            if nb.left_on_same_line:
                left_block = block_by_id.get(nb.left_on_same_line)
                if left_block:
                    neighbors.append(f"left: {left_block.text[:30]}")
            if nb.right_on_same_line:
                right_block = block_by_id.get(nb.right_on_same_line)
                if right_block:
                    neighbors.append(f"right: {right_block.text[:30]}")
        
        # Get style summary
        graph_v2 = getattr(layout, "graph_v2", None)
        style_info = ""
        if graph_v2 and block_id:
            style = graph_v2.get("style", {}).get(block_id)
            if style:
                font_z, bold = style
                style_info = f"font_z={font_z:.1f}, bold={bold}"
        
        prompt_parts.append(
            f"  [{i}] value='{text_window[:60]}' direction={relation}"
            + (f" label='{label_text}'" if label_text else "")
            + (f" neighbors=[{', '.join(neighbors)}]" if neighbors else "")
            + (f" style={style_info}" if style_info else "")
        )
    
    prompt_parts.append("\nRespond with JSON: {\"pick\": <index or -1>, \"why\": \"<explanation in 1 sentence>\"}")
    
    return "\n".join(prompt_parts)


def _parse_chooser_response(response: str) -> Optional[Dict[str, Any]]:
    """Parse LLM chooser response.
    
    Args:
        response: LLM response string.
        
    Returns:
        Dict with 'pick' (int) and 'why' (str), or None if parse fails.
    """
    try:
        # Try to extract JSON from response
        # Look for JSON object in response
        import re
        json_match = re.search(r'\{[^{}]*"pick"[^{}]*\}', response)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            pick = result.get("pick")
            why = result.get("why", "")
            
            if isinstance(pick, int):
                return {"pick": pick, "why": why}
    except Exception:
        pass
    
    # Fallback: try to find number in response
    try:
        import re
        numbers = re.findall(r'-?\d+', response)
        if numbers:
            pick = int(numbers[0])
            if -1 <= pick < 10:  # Reasonable range
                return {"pick": pick, "why": "Parsed from response"}
    except Exception:
        pass
    
    return None


def llm_chooser(
    field: SchemaField,
    candidates: List[Dict[str, Any]],
    layout: LayoutGraph,
    llm_client: Any,
    document_label: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """Use LLM to choose between candidates (only when Pareto + tie-breakers leave >1).
    
    Args:
        field: SchemaField being extracted.
        candidates: List of candidate dicts (max 3, already filtered by Pareto).
        layout: LayoutGraph.
        llm_client: LLM client instance.
        document_label: Document label.
        
    Returns:
        Selected candidate dict, or None if LLM couldn't choose or chose -1.
    """
    if not candidates or len(candidates) == 0:
        return None
    
    if len(candidates) == 1:
        return candidates[0]
    
    # Limit to 3 candidates
    candidates = candidates[:3]
    
    # Check cache
    cache_key = _hash_candidates(field, candidates)
    if cache_key in _chooser_cache:
        cached_result = _chooser_cache[cache_key]
        pick = cached_result.get("pick")
        if pick is not None and 0 <= pick < len(candidates):
            return candidates[pick]
        elif pick == -1:
            return None  # LLM chose none
    
    # Build prompt
    prompt = _build_chooser_prompt(field, candidates, layout, document_label)
    
    # Call LLM
    try:
        response = llm_client.generate(prompt, max_tokens=256, timeout=2.0)
        parsed = _parse_chooser_response(response)
        
        if parsed:
            pick = parsed["pick"]
            why = parsed.get("why", "")
            
            # Cache result
            _chooser_cache[cache_key] = {"pick": pick, "why": why}
            
            if pick == -1:
                return None  # LLM chose none
            
            if 0 <= pick < len(candidates):
                selected = candidates[pick]
                # Revalidate with type-gate before returning
                from ..validation.patterns import type_gate_generic
                text_window = selected.get("text_window", "")
                if type_gate_generic(text_window, field.type or "text"):
                    return selected
                else:
                    # Type-gate failed, return None
                    return None
        
        # Parse failed, return None
        return None
    
    except Exception as e:
        import logging
        logging.warning(f"LLM chooser exception: {e}")
        return None
