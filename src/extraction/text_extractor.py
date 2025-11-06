"""Text extraction from field candidates with multi-line/multi-token scoring."""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple

from ..core.models import Block, FieldCandidate, GraphV2, Grid, LayoutGraph, SchemaField
from ..validation.validators import validate_and_normalize, validate_soft

LABEL_SEP_RE = re.compile(r"[:：]\s*")  # ':' variants


def _percentile(data: list[float], p: float) -> float:
    """Compute percentile p (0-100) of data."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100.0)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


def _build_roi_multiline(label_block: Block, grid: Grid, blocks: list[Block]) -> str:
    """Build multiline ROI anchored at label block.

    Args:
        label_block: Label block (L).
        grid: Grid structure.
        blocks: All blocks in the document.

    Returns:
        Concatenated text window from ROI respecting reading order (line→column).
    """
    # H = (L.bbox.y1 - L.bbox.y0)
    H = label_block.bbox[3] - label_block.bbox[1]

    # α = clamp(1.2, 1.8); gap_cap = P40(Δy)
    row_y = grid["row_y"]
    gaps_y: list[float] = []
    for i in range(len(row_y) - 1):
        gaps_y.append(row_y[i + 1] - row_y[i])
    gap_cap = _percentile(gaps_y, 40) if gaps_y else 0.01

    # y_top = L.bbox.y0; y_bot = min(y_top + α·H, y_top + 2·gap_cap)
    alpha = min(max(1.2, 1.8), 1.8)  # clamp(1.2, 1.8)
    y_top = label_block.bbox[1]
    y_bot = min(y_top + alpha * H, y_top + 2.0 * gap_cap)

    # δ_right = min(0.15, P35(width))
    block_widths = [b.bbox[2] - b.bbox[0] for b in blocks]
    delta_right = min(0.15, _percentile(block_widths, 35) if block_widths else 0.15)

    # ROI horizontal: [L.bbox.x0, L.bbox.x1 + δ_right]
    roi_x0 = label_block.bbox[0]
    roi_x1 = label_block.bbox[2] + delta_right

    # Agregue linhas virtuais cujo row_y intersecta [y_top, y_bot]
    intersecting_rows: list[int] = []
    for row_idx, row_y_val in enumerate(row_y):
        if y_top <= row_y_val <= y_bot:
            intersecting_rows.append(row_idx)

    # Encontre blocos que intersectam ROI
    roi_blocks: list[Block] = []
    for block in blocks:
        block_x0, block_y0, block_x1, block_y1 = block.bbox
        # Check if block intersects ROI
        if not (block_x1 < roi_x0 or block_x0 > roi_x1 or block_y1 < y_top or block_y0 > y_bot):
            roi_blocks.append(block)

    # Ordenar por linha→coluna (reading order)
    # Primeiro por Y, depois por X
    roi_blocks.sort(key=lambda b: ((b.bbox[1] + b.bbox[3]) / 2.0, (b.bbox[0] + b.bbox[2]) / 2.0))

    # Concatenação respeitando ordem de leitura
    text_parts: list[str] = []
    for block in roi_blocks:
        text_parts.append(block.text)

    text_window = " ".join(text_parts).strip()
    return text_window


def _decide_keep_label(
    field: SchemaField, label_text: str, text_window: str, graph: Optional[GraphV2]
) -> Tuple[str, bool]:
    """Decide whether to keep label in final value.

    Returns:
        Tuple of (final_value, keep_label_flag).
    """
    label_text_lower = label_text.lower().strip()
    synonyms = field.synonyms or [field.name]

    # Regra 1: Se existe ":" imediatamente após o label, não manter
    for syn in synonyms:
        syn_lower = syn.lower().strip()
        pattern = re.compile(re.escape(syn_lower) + r"\s*[:：]\s*", re.IGNORECASE)
        if pattern.search(text_window):
            # Encontra posição após ":"
            match = pattern.search(text_window)
            if match:
                after_colon = text_window[match.end():].strip()
                if after_colon:
                    return (after_colon, False)

    # Regra 2: Se não existe ":" e field.type == 'enum' e enum_option ∈ text_window → manter se ≤3 tokens
    if field.type == "enum":
        enum_options = field.meta.get("enum_options") if field.meta else None
        if enum_options:
            text_tokens = text_window.split()
            for option in enum_options:
                if option.lower() in text_window.lower():
                    # Contar tokens: se label + opção ≤ 3 tokens, manter
                    label_tokens = label_text.split()
                    option_tokens = option.split()
                    total_tokens = len(label_tokens) + len(option_tokens)
                    if total_tokens <= 3:
                        return (text_window, True)

    # Regra 3: Se text_window tem tokens curtos UPPER (2–4) e font_z similar → manter
    if graph:
        label_block_id = None
        # Try to find label block (simplified: assume first block with label text)
        for block_id, style_info in graph.get("style", {}).items():
            # This is simplified; in practice we'd need to pass label_block_id
            pass

        text_tokens = text_window.split()
        upper_tokens = [t for t in text_tokens if t.isupper() and 2 <= len(t) <= 4]
        if len(upper_tokens) >= 2:
            # Check font_z similarity (simplified: assume similar if tokens are short UPPER)
            return (text_window, True)

    # Regra 4: Separar pelo melhor split, mas só se sufixo passar validate_soft(type)
    # Se não passar, manter tudo (conservador)
    best_split = None
    best_syn_len = 0

    for syn in synonyms:
        syn_lower = syn.lower().strip()
        if not syn_lower:
            continue
        # Try to find synonym in text_window (word boundary preferred)
        # Try word boundary match first
        pattern = re.compile(r'\b' + re.escape(syn_lower) + r'\b', re.IGNORECASE)
        match = pattern.search(text_window.lower())
        if match:
            if len(syn) > best_syn_len:
                best_syn_len = len(syn)
                # Get text after synonym
                after_syn = text_window[match.end():].lstrip(" :\u200b\t")
                if after_syn:
                    best_split = after_syn
        else:
            # Fallback: substring match
            idx = text_window.lower().find(syn_lower)
            if idx >= 0:
                if len(syn) > best_syn_len:
                    best_syn_len = len(syn)
                    # Get text after synonym
                    after_syn = text_window[idx + len(syn):].lstrip(" :\u200b\t")
                    if after_syn:
                        best_split = after_syn

    if best_split:
        # Teste se sufixo passa validate_soft(type)
        if validate_soft(field, best_split):
            return (best_split, False)
        else:
            # Não passa → manter tudo (conservador)
            return (text_window, True)

    # Regra 5: Generic label detection and removal (no language-specific assumptions)
    # Check if text_window is exactly a label or starts with label prefix
    # Use field synonyms to detect if text_window is just the label
    text_window_lower = text_window.lower().strip()
    
    # Check if text_window is exactly a synonym (just label, no value)
    for syn in synonyms:
        syn_lower = syn.lower().strip()
        if syn_lower and text_window_lower == syn_lower:
            # Text is exactly the label, reject
            return ("", False)
        # Check if text starts with synonym and has no meaningful content after
        if syn_lower and text_window_lower.startswith(syn_lower):
            after_label = text_window[len(syn):].lstrip(" :\u200b\t")
            if len(after_label.strip()) < 2:
                # Text is just label with minimal text, reject
                return ("", False)
            # Check if after_label is just another label word (not a value)
            after_lower = after_label.lower().strip()
            # If after_label matches another synonym, it's likely just labels
            for other_syn in synonyms:
                if other_syn != syn and other_syn.lower().strip() == after_lower:
                    return ("", False)
    
    # For enum fields: if text_window doesn't contain enum value, reject
    if field.type == "enum":
        enum_options = field.meta.get("enum_options") if field.meta else None
        if enum_options:
            from ..validation.validators import validate_and_normalize
            # Check if text_window contains any enum value
            ok, _ = validate_and_normalize("enum", text_window, enum_options=enum_options)
            if not ok:
                # Text doesn't contain enum value, might be just label
                # Check if it's exactly a label word (match with synonyms)
                text_tokens = text_window_lower.split()
                if len(text_tokens) <= 2:
                    # Short text, check if it matches any synonym
                    for syn in synonyms:
                        syn_lower = syn.lower().strip()
                        if syn_lower in text_tokens or text_window_lower == syn_lower:
                            return ("", False)

    # Default: manter tudo
    return (text_window, True)


def _text_candidates(
    dst_block: Block,
    layout: LayoutGraph,
    field_type: str = "text",
    max_lines_window: int = 3,
    max_tokens: int = 12,
) -> list[str]:
    """Generate text candidates from destination block.

    Returns a ranked list of small text snippets to try:
    1) Individual lines (first N lines)
    2) 2-line and 3-line windows (joined with space)
    3) First K tokens of the first 1-2 lines (sliding windows of up to 3 tokens)

    For text_multiline, limits windows to same section to avoid leaking.

    Args:
        dst_block: Destination block.
        layout: LayoutGraph for section metadata.
        field_type: Field type (text_multiline uses section-aware logic).
        max_lines_window: Maximum lines to consider for windows.
        max_tokens: Maximum tokens to extract per line.

    Returns:
        List of candidate text strings (deduplicated, preserving order).
    """
    lines = [ln.strip() for ln in dst_block.text.splitlines() if ln.strip()]
    if not lines:
        return []

    # Get section of this block (for text_multiline)
    section_by_block = getattr(layout, "section_id_by_block", {})
    dst_section = section_by_block.get(dst_block.id)

    candidates: list[str] = []
    seen = set()

    # 1) Individual lines (first N lines)
    for line in lines[:max_lines_window]:
        if line and line not in seen:
            seen.add(line)
            candidates.append(line)

    # 2) 2-line and 3-line windows
    # For text_multiline, limit to same section (only if we have section info)
    if field_type == "text_multiline" and dst_section is not None:
        # Only create windows within this block (assume same section)
        for window_size in [2, 3]:
            for i in range(len(lines) - window_size + 1):
                window_text = " ".join(lines[i : i + window_size])
                if window_text and window_text not in seen:
                    seen.add(window_text)
                    candidates.append(window_text)
    else:
        # Normal behavior for other types
        for window_size in [2, 3]:
            for i in range(len(lines) - window_size + 1):
                window_text = " ".join(lines[i : i + window_size])
                if window_text and window_text not in seen:
                    seen.add(window_text)
                    candidates.append(window_text)

    # 3) Token windows from first 1-2 lines
    max_lines_for_tokens = min(2, len(lines))
    for i in range(max_lines_for_tokens):
        tokens = re.findall(r"\S+", lines[i])
        tokens = tokens[:max_tokens]

        # Individual tokens
        for token in tokens:
            if token and token not in seen:
                seen.add(token)
                candidates.append(token)

        # Sliding windows of 2-3 tokens
        for n in [2, 3]:
            for j in range(len(tokens) - n + 1):
                window = " ".join(tokens[j : j + n])
                if window and window not in seen:
                    seen.add(window)
                    candidates.append(window)

    return candidates


def _position_bonus(field_meta: dict[str, object] | None, bbox: tuple[float, float, float, float]) -> float:
    """Returns 0.0 or small bonus (e.g., 0.05) if bbox center falls into the hinted quadrant.

    Args:
        field_meta: SchemaField meta dict (may contain position_hint).
        bbox: Normalized bbox (x0, y0, x1, y1) in [0,1].

    Returns:
        Bonus score (0.0 or 0.05).
    """
    if not field_meta:
        return 0.0

    position_hint = field_meta.get("position_hint")
    if not position_hint:
        return 0.0

    x0, y0, x1, y1 = bbox
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0

    # Determine quadrant
    is_left = center_x < 0.5
    is_top = center_y < 0.5

    if position_hint == "top-left" and is_left and is_top:
        return 0.05
    if position_hint == "top-right" and not is_left and is_top:
        return 0.05
    if position_hint == "bottom-left" and is_left and not is_top:
        return 0.05
    if position_hint == "bottom-right" and not is_left and not is_top:
        return 0.05

    return 0.0


def _score_candidate(
    field_type: str, text: str, relation: str, base_ok: bool, position_bonus: float = 0.0
) -> float:
    """Score a candidate text for a field (field-agnostic).

    Args:
        field_type: Field type string.
        text: Candidate text.
        relation: Spatial relation ("same_line_right_of" or "first_below_same_column").
        base_ok: Whether validator returned ok.

    Returns:
        Score between 0.0 and 1.0.
    """
    # Base score: 70% weight on validation
    score = 0.7 * (1.0 if base_ok else 0.0)

    # Spatial bonus: 10% for same_line
    if relation == "same_line_right_of":
        score += 0.1

    # Type-specific bonuses (independent of document)
    field_type = field_type.lower()
    if field_type == "id_simple" and re.search(r"[A-Za-z0-9./-]{3,}", text):
        score += 0.05
    if field_type == "uf" and re.search(r"\b[A-Z]{2}\b", text):
        score += 0.05
    if field_type == "date" and re.search(r"\d", text):
        score += 0.05
    if field_type == "money" and re.search(r"\d", text):
        score += 0.05

    # Position bonus
    score += position_bonus

    return min(score, 1.0)


def _normalize_text(s: str) -> str:
    """Normalize text: lowercase, remove accents, collapse spaces."""
    import unicodedata
    import re

    # Remove accents
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Lowercase
    s = s.lower()
    # Collapse spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_by_label(text: str, synonyms: list[str]) -> Optional[str]:
    """Split text by label and return the part after the label.

    Args:
        text: Block text.
        synonyms: List of synonyms to search for.

    Returns:
        Text after the first found synonym, or None if not found.
    """
    if not text:
        return None

    # Process line by line for better accuracy
    lines = text.splitlines()
    t_norm = _normalize_text(text)

    # Sort synonyms by length (longest first) to match more specific ones first
    sorted_syns = sorted(synonyms, key=len, reverse=True)

    for syn in sorted_syns:
        if not syn or not syn.strip():
            continue
        s_norm = _normalize_text(syn.strip())
        
        # Check each line for the synonym
        for line in lines:
            line_norm = _normalize_text(line)
            # Use word boundary to avoid substring matches
            import re
            pattern = r'\b' + re.escape(s_norm) + r'\b'
            if re.search(pattern, line_norm):
                # Found synonym in this line, get text after it
                syn_original = syn.strip()
                idx_orig = line.lower().find(syn_original.lower())
                if idx_orig >= 0:
                    # Get text after the synonym, stripping common separators
                    after = line[idx_orig + len(syn_original):].lstrip(" :\u200b\t")
                    if after:
                        return after
                # Fallback: try normalized position
                idx = line_norm.find(s_norm)
                if idx >= 0:
                    after = line[idx:].lstrip(" :\u200b\t")
                    # Remove the synonym itself if it's at the start
                    after_lower = after.lower()
                    if after_lower.startswith(syn_original.lower()):
                        after = after[len(syn_original):].lstrip(" :\u200b\t")
                    if after:
                        return after
        
        # Fallback: whole text search (less accurate)
        idx = t_norm.find(s_norm)
        if idx >= 0:
            syn_original = syn.strip()
            idx_orig = text.lower().find(syn_original.lower())
            if idx_orig >= 0:
                after = text[idx_orig + len(syn_original):].lstrip(" :\u200b\t")
                if after:
                    return after
            after = text[idx:].lstrip(" :\u200b\t")
            # Remove the synonym itself if it's at the start
            if after.lower().startswith(syn_original.lower()):
                after = after[len(syn_original):].lstrip(" :\u200b\t")
            if after:
                return after
    return None


def _validate_plausibility(field: SchemaField, value: str) -> float:
    """Validate if a value makes semantic sense for a field type.
    
    Returns a plausibility score (0.0-1.0) indicating how likely the value
    is correct for this field type. This helps filter out values that pass
    type validation but are semantically incorrect (e.g., "2300" for inscricao,
    or CEP for cidade).
    
    Args:
        field: SchemaField being validated.
        value: Value to check.
        
    Returns:
        Plausibility score (0.0-1.0), where 1.0 is highly plausible.
    """
    if not value or not value.strip():
        return 0.0
    
    value_clean = value.strip()
    field_type = (field.type or "text").lower()
    field_name_lower = (field.name or "").lower()
    
    # id_simple: typically 3-10 chars, often alphanumeric
    if field_type == "id_simple" or "inscricao" in field_name_lower:
        # Too short or too long
        if len(value_clean) < 3:
            return 0.3
        if len(value_clean) > 15:
            return 0.4
        # Pure numbers with 4+ digits might be addresses (e.g., "2300")
        if re.match(r"^\d{4,}$", value_clean):
            return 0.5  # Somewhat plausible but could be address
        # Alphanumeric with digits is more plausible
        if re.search(r"\d", value_clean) and re.search(r"[A-Za-z]", value_clean):
            return 0.9
        # Just digits (3-6 chars) is plausible for numeric IDs
        if re.match(r"^\d{3,6}$", value_clean):
            return 0.8
        # Just letters is less plausible
        if re.match(r"^[A-Za-z]+$", value_clean):
            return 0.6
    
    # text field named "cidade": should not be just numbers (likely CEP)
    if field_type == "text" and "cidade" in field_name_lower:
        # Pure numbers (likely CEP) - very low plausibility
        if re.match(r"^\d+$", value_clean):
            return 0.1  # Very low plausibility for numbers as city names
        # Too short
        if len(value_clean) < 3:
            return 0.3
        # Has letters (good sign) - city names should have letters
        if re.search(r"[A-Za-zÀ-ÿ]", value_clean):
            return 0.95  # High plausibility for text with letters
    
    # text field named "inscricao": similar to id_simple
    if field_type == "text" and "inscricao" in field_name_lower:
        if len(value_clean) < 3:
            return 0.3
        if len(value_clean) > 15:
            return 0.4
        if re.match(r"^\d{4,}$", value_clean):
            return 0.5  # Could be address number
        if re.search(r"\d", value_clean):
            return 0.8  # Has digits, more plausible
    
    # uf: should be 2 uppercase letters
    if field_type == "uf":
        if re.match(r"^[A-Z]{2}$", value_clean):
            return 1.0
        if re.match(r"^[a-z]{2}$", value_clean):
            return 0.7  # Lowercase, less ideal
        return 0.3
    
    # Default: assume plausible if passes basic checks
    return 1.0


def _parse_structured_block(block_text: str, field: SchemaField) -> Optional[str]:
    """Extract value from structured blocks using generic separators (v2).
    
    Generic approach: uses common separators (:, -, spaces) and field synonyms
    to find values, without hardcoding specific patterns for cidade, UF, CEP, etc.
    
    Args:
        block_text: Full text of the block.
        field: SchemaField to extract.
        
    Returns:
        Extracted value or None if pattern not found.
    """
    if not block_text or not field:
        return None
    
    from ..validation.patterns import detect_pattern, is_isolated_token, type_gate_generic
    
    # Build search terms: field name + synonyms
    search_terms = [field.name or ""]
    if field.synonyms:
        search_terms.extend(field.synonyms)
    
    # Remove empty terms
    search_terms = [t.lower() for t in search_terms if t]
    if not search_terms:
        return None
    
    # Generic separators (no language-specific assumptions)
    GENERIC_SEPS = r"[:,;•\-–—]"  # Common separators: colon, comma, semicolon, bullet, dash, en-dash, em-dash
    
    # Try each search term
    for term in search_terms:
        # Pattern: <term><separator><value>
        # Value ends at: next separator, end of line, or next known label pattern
        patterns = [
            # Pattern 1: "term: value" or "term : value" (colon separator)
            re.compile(
                rf"{re.escape(term)}\s*:?\s*([^:\n]+?)(?:\s*(?:$|[\n\r]|{GENERIC_SEPS}))",
                re.IGNORECASE
            ),
            # Pattern 2: "term - value" or "term- value" (dash separator)
            re.compile(
                rf"{re.escape(term)}\s*-?\s*([^-\n]+?)(?:\s*(?:$|[\n\r]|{GENERIC_SEPS}))",
                re.IGNORECASE
            ),
            # Pattern 3: "term, value" (comma separator)
            re.compile(
                rf"{re.escape(term)}\s*,\s*([^,\n]+?)(?:\s*(?:$|[\n\r]|{GENERIC_SEPS}))",
                re.IGNORECASE
            ),
            # Pattern 4: "term; value" (semicolon separator)
            re.compile(
                rf"{re.escape(term)}\s*;\s*([^;\n]+?)(?:\s*(?:$|[\n\r]|{GENERIC_SEPS}))",
                re.IGNORECASE
            ),
            # Pattern 5: "term value" (space-separated, value until next separator or end)
            re.compile(
                rf"{re.escape(term)}\s+([^\n]+?)(?:\s*(?:$|[\n\r]|{GENERIC_SEPS}))",
                re.IGNORECASE
            ),
        ]
        
        for pattern in patterns:
            match = pattern.search(block_text)
            if match:
                value = match.group(1).strip()
                # Clean up value: remove trailing punctuation, extra whitespace
                value = re.sub(r'[^\w\sÀ-ÿ-]+$', '', value).strip()
                value = value.strip(" :\t-")
                
                if not value or len(value) < 2:
                    continue
                
                # Type gate: reject if value doesn't match expected type pattern (generic)
                field_type = (field.type or "text").lower()
                if not type_gate_generic(value, field_type):
                    continue  # Skip values that don't match type pattern
                
                # For fields expecting isolated letters (uf, code, sigla), verify isolation
                if field_type in ("uf", "code", "sigla"):
                    # Check if value looks like isolated letters
                    isolated_match = re.search(r"\b([A-Z]{2,4})\b", value.upper())
                    if isolated_match:
                        token = isolated_match.group(1)
                        if is_isolated_token(block_text, token):
                            return token.upper()
                    continue  # Try next pattern
                
                # For text fields: ensure they have at least one letter (not pure numbers/symbols)
                if field_type == "text":
                    if not re.search(r'[A-Za-zÀ-ÿ]', value):
                        continue  # Skip values without letters for text fields
                
                return value
    
    # If no single match found, try to extract from multiple label:value pairs in same line
    # This handles cases like "Cidade: X UF: Y CEP: Z" in one line (generic, no language assumptions)
    lines = block_text.splitlines()
    for line in lines:
        # Find all potential label:value pairs using generic separators
        # Pattern: (\w+(?:\s+\w+)*)\s*[:;•\-–—]\s*([^:;•\-–—\n]+)
        pairs = re.findall(r'(\w+(?:\s+\w+)*)\s*[:;•\-–—]\s*([^:;•\-–—\n]+)', line)
        if len(pairs) >= 2:  # Multiple pairs in same line
            # Try to match field name/synonyms with labels in pairs using label matching
            for label_part, value_part in pairs:
                label_part_lower = label_part.lower().strip()
                for syn in search_terms:
                    syn_lower = syn.lower().strip()
                    # Simple token overlap check (generic, no language assumptions)
                    label_tokens = set(label_part_lower.split())
                    syn_tokens = set(syn_lower.split())
                    if label_tokens & syn_tokens:  # Any common tokens
                        value_clean = value_part.strip()
                        if value_clean and len(value_clean) >= 2:
                            # Type gate check
                            if type_gate_generic(value_clean, field_type):
                                return value_clean
    
    return None


def extract_from_candidate(
    field: SchemaField, cand: "FieldCandidate | dict[str, Any]", layout: LayoutGraph
) -> tuple[Optional[str], float, dict]:
    """Given a Candidate (v2) or FieldCandidate (legacy), produce a (value, confidence, trace) tuple.

    v2: Candidate already has text_window extracted, so this function just validates and normalizes.
    Legacy: FieldCandidate requires text extraction (backward compatibility).

    Args:
        field: SchemaField being extracted.
        cand: Candidate (v2) or FieldCandidate (legacy) with node_id/block_id and relation.
        layout: LayoutGraph with blocks.

    Returns:
        Tuple of (value, confidence, trace_dict).
        If no candidate passes validation, returns (None, 0.0, trace_with_reason).
    """
    from ..core.models import FieldCandidate
    from ..validation.patterns import type_gate_generic
    
    # Check if v2 Candidate (has text_window)
    is_candidate_v2 = isinstance(cand, dict) and "text_window" in cand
    
    if is_candidate_v2:
        # v2: Candidate already has text_window extracted
        candidate: dict[str, Any] = cand  # type: ignore
        text_window = candidate.get("text_window", "")
        block_id = candidate.get("block_id")
        relation = candidate.get("relation", "unknown")
        label_block_id = candidate.get("label_block_id")
        score_tuple = candidate.get("score_tuple", ())
        roi_info = candidate.get("roi_info", {})
        
        # Remove common label prefixes from text_window before validation (generic)
        # This prevents extracting labels as values
        text_window_clean = text_window
        text_window_lower = text_window.lower().strip()
        
        # Enhanced label-only rejection (corrige erro #1)
        # Check if text_window is exactly a field synonym (just label, no value) - generic check
        field_synonyms = field.synonyms or [field.name]
        
        # List of known labels that should NEVER be extracted as values
        KNOWN_LABELS = [
            "inscrição", "inscricao", "seccional", "subseção", "subsecao",
            "categoria", "endereço", "endereco", "telefone", "situação", "situacao",
            "nome", "data", "valor", "sistema", "produto", "conselho seccional",
            "endereço profissional", "endereco profissional", "telefone profissional"
        ]
        
        # Check 1: Is text_window exactly a known label?
        if text_window_lower.strip() in [label.lower() for label in KNOWN_LABELS]:
            return (None, 0.0, {
                "relation": relation,
                "block_id": block_id,
                "reason": "label_only_known_label",
                "text_window": text_window[:100],
            })
        
        # Check 2: Is text_window exactly a field synonym?
        for syn in field_synonyms:
            syn_lower = syn.lower().strip()
            if syn_lower and text_window_lower == syn_lower:
                return (None, 0.0, {
                    "relation": relation,
                    "block_id": block_id,
                    "reason": "label_only_field_synonym",
                    "text_window": text_window[:100],
                })
            
            # Check 3: Is text_window very similar to label (likely just label)
            if syn_lower:
                from ..matching.matcher import _label_score
                label_match_score = _label_score(text_window_lower, syn_lower, min_threshold=0.9)
                if label_match_score > 0.0 and len(text_window_lower) <= len(syn_lower) + 2:
                    # Text is very similar to label and short - likely just label
                    return (None, 0.0, {
                        "relation": relation,
                        "block_id": block_id,
                        "reason": "label_only_similar",
                        "text_window": text_window[:100],
                    })
        
        # Check 4: Is text_window a sequence of known labels? (e.g., "Inscrição Seccional Subseção")
        text_words = text_window_lower.split()
        if len(text_words) <= 3:
            known_label_count = sum(1 for word in text_words if word in [label.lower() for label in KNOWN_LABELS])
            if known_label_count >= len(text_words) * 0.7:  # 70% or more are known labels
                return (None, 0.0, {
                    "relation": relation,
                    "block_id": block_id,
                    "reason": "label_only_sequence",
                        "text_window": text_window[:100],
                    })
        
        # Remove label prefixes (generic)
        common_labels_prefix = [
            "profissional", "endereço profissional", "endereco profissional",
            "telefone profissional", "endereço", "endereco", "telefone"
        ]
        for label in sorted(common_labels_prefix, key=len, reverse=True):
            if text_window_lower.startswith(label):
                after_label = text_window[len(label):].lstrip(" :\u200b\t")
                if len(after_label.strip()) >= 2:
                    text_window_clean = after_label.strip()
                    break
        
        # Validate and normalize
        from ..validation.validators import validate_and_normalize
        
        ok, normalized_value = validate_and_normalize(field, text_window_clean)
        
        if ok and normalized_value:
            # Calculate confidence from score_tuple
            # Use type_gate (index 2) and spatial_quality (index 6) as confidence hints
            confidence = 0.7  # Base confidence
            if len(score_tuple) > 2 and score_tuple[2] == 1:  # type_gate passed
                confidence = 0.85
            if len(score_tuple) > 0 and score_tuple[0] == 1:  # sufficiency_flag
                confidence = 0.95
            
            trace = {
                "relation": relation,
                "block_id": block_id,
                "label_block_id": label_block_id,
                "score_tuple": score_tuple,
                "roi_info": roi_info,
                "source": "heuristic",
            }
            return (normalized_value, confidence, trace)
        else:
            return (None, 0.0, {
                "relation": relation,
                "block_id": block_id,
                "reason": "validation_failed",
                "text_window": text_window[:100],
            })
    else:
        # Legacy: FieldCandidate - extract text_window (backward compatibility)
        field_cand: FieldCandidate = cand  # type: ignore
        # Get destination block
        dst_block = next((b for b in layout.blocks if b.id == field_cand.node_id), None)
        if not dst_block:
            return None, 0.0, {"node_id": field_cand.node_id, "relation": field_cand.relation, "reason": "block_not_found"}

        # Get label block for line-based extraction
        label_block = None
        if hasattr(field_cand, 'source_label_block_id') and field_cand.source_label_block_id:
            label_block = next((b for b in layout.blocks if b.id == field_cand.source_label_block_id), None)

        # Get Grid and GraphV2 (v2) if available
        grid = getattr(layout, "grid", None)
        graph_v2 = getattr(layout, "graph_v2", None)

        # For same_block, use ROI multiline + keep_label (v2)
        cand_texts: list[str] = []
        structured_parse_result = None  # Track if we have a structured parse result
        if field_cand.relation == "same_block" and label_block and grid:
            # Build ROI multiline
            text_window = _build_roi_multiline(label_block, grid, layout.blocks)
            
            # Decide keep_label
            label_text = label_block.text or ""
            final_value, keep_label = _decide_keep_label(field, label_text, text_window, graph_v2)
            
            # IMPROVEMENT: Reject titles/headers before adding to candidates
            # Add final_value as primary candidate
            if final_value:
                # Reject if it's a title/header (ends with ":" and is long)
                if final_value.strip().endswith(":") and len(final_value.strip()) > 10:
                    title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
                    final_lower = final_value.lower().strip()
                    if any(indicator in final_lower for indicator in title_indicators):
                        # Skip - it's a title/header
                        pass
                    else:
                        cand_texts.append(final_value)
                else:
                    cand_texts.append(final_value)
            
            # Also try structured parsing as fallback (for patterns like "Cidade: X U.F: Y CEP: Z")
            structured_value = _parse_structured_block(dst_block.text or "", field)
            if structured_value:
                structured_parse_result = structured_value
                cand_texts.append(structured_value)  # High priority
        elif field_cand.relation == "same_block":
            # Fallback: old logic if Grid not available
            # First, try structured parsing for common patterns (e.g., "Cidade: X U.F: Y CEP: Z")
            structured_value = _parse_structured_block(dst_block.text or "", field)
            if structured_value:
                structured_parse_result = structured_value
                cand_texts.append(structured_value)  # Highest priority
            
            # Try to split by label and use the part after the label as primary candidate
            primary = _split_by_label(dst_block.text or "", field.synonyms or [field.name])
            if primary and len(primary.strip()) > 0:
                # IMPROVEMENT: Reject titles/headers before adding to candidates
                if primary.strip().endswith(":") and len(primary.strip()) > 10:
                    title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
                    primary_lower = primary.lower().strip()
                    if any(indicator in primary_lower for indicator in title_indicators):
                        # Skip - it's a title/header
                        pass
                    else:
                        cand_texts.append(primary)  # Try first the "after label" part
                else:
                    cand_texts.append(primary)  # Try first the "after label" part
            
            # For enum fields, after split, try to find enum token in the "after label" part
            if field.type == "enum" and primary:
                enum_options = field.meta.get("enum_options") if field.meta else None
                if enum_options:
                    # Try to extract enum value from the split result
                    from ..validation.validators import normalize_enum
                    enum_value = normalize_enum(primary, enum_options)
                    if enum_value:
                        # Add the normalized enum value as a high-priority candidate
                        cand_texts.insert(0, enum_value)  # Highest priority for enum
            
            # Also try to find the actual value block (right neighbor if available)
            neighborhood = getattr(layout, "neighborhood", {})
            nb = neighborhood.get(field_cand.node_id)
            if nb and nb.right_on_same_line:
                right_block = next((b for b in layout.blocks if b.id == nb.right_on_same_line), None)
                if right_block:
                    # Use right block as candidate (it's likely the value)
                    right_text = right_block.text.splitlines()[0] if right_block.text else ""
                    # IMPROVEMENT: Reject titles/headers before adding to candidates
                    if right_text.strip().endswith(":") and len(right_text.strip()) > 10:
                        title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
                        right_lower = right_text.lower().strip()
                        if any(indicator in right_lower for indicator in title_indicators):
                            # Skip - it's a title/header
                            pass
                        else:
                            cand_texts.append(right_text)
                    else:
                        cand_texts.append(right_text)
        
        # For first_below_same_column with multi-line blocks, try to extract the corresponding line
        # This helps when labels are in one block and values in another: "Inscrição\nSeccional" -> "101943\nPR"
        # IMPROVEMENT: Also handles same_block relations with multi-line blocks
        is_multiline_relation = field_cand.relation in ["first_below_same_column", "same_block"]
        
        if is_multiline_relation and label_block:
            label_lines = [ln.strip() for ln in (label_block.text or "").splitlines() if ln.strip()]
            dst_lines = [ln.strip() for ln in (dst_block.text or "").splitlines() if ln.strip()]
            
            # Find which line of the label block contains this field's label
            field_name_lower = field.name.lower()
            field_synonyms_lower = [s.lower().strip() for s in (field.synonyms or [])]
            
            label_line_idx = None
            for i, label_line in enumerate(label_lines):
                label_line_norm = _normalize_text(label_line)
                # Check if this line contains the field name or synonyms (word boundary match)
                import re
                if field_name_lower:
                    pattern = r'\b' + re.escape(field_name_lower) + r'\b'
                    if re.search(pattern, label_line_norm):
                        label_line_idx = i
                        break
                for syn in field_synonyms_lower:
                    if syn:
                        pattern = r'\b' + re.escape(syn) + r'\b'
                        if re.search(pattern, label_line_norm):
                            label_line_idx = i
                            break
                if label_line_idx is not None:
                    break
            
            # If we found the label line and there's a corresponding value line, extract it
            if label_line_idx is not None and label_line_idx < len(dst_lines):
                # Extract the corresponding line from value block
                value_line = dst_lines[label_line_idx]
                if value_line:
                    # Clean the value line (remove common prefixes/suffixes)
                    value_clean = value_line.strip()
                    
                    # Additional processing: if value line contains multiple tokens that might be
                    # part of the value, try to extract the most relevant part
                    # For structured data like "101943\nPR\nCONSELHO SECCIONAL - PARANÁ",
                    # we want just "101943" for inscricao, "PR" for seccional, etc.
                    
                    # Check if this is a structured line (multiple space-separated parts)
                    value_parts = value_clean.split()
                    
                    # For numeric/short fields, prefer shorter parts
                    if field.type in ["number", "id_simple", "uf", "alphanum_code"]:
                        # For short types, prefer the shortest part that passes type-gate
                        for part in value_parts:
                            if type_gate_generic(part, field.type):
                                value_clean = part
                                break
                        # If no part passes, try the whole value
                        if not type_gate_generic(value_clean, field.type):
                            # Try first part if it's short
                            if len(value_parts) > 0 and len(value_parts[0]) <= 10:
                                value_clean = value_parts[0]
                    elif field.type == "text" and len(value_parts) > 3:
                        # For text fields, if line has many parts, might be structured
                        # Try to extract just the relevant part (first few tokens)
                        # But keep more context for longer fields
                        if len(value_clean) > 50:  # Long text, might need truncation
                            # Keep first 50 chars or first 5 words
                            value_clean = " ".join(value_parts[:5])
                    
                    # IMPROVEMENT: Reject titles/headers before adding to candidates
                    # Check if value_clean is a title/header (ends with ":" and is long)
                    if value_clean.strip().endswith(":") and len(value_clean.strip()) > 10:
                        title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
                        value_lower_check = value_clean.lower().strip()
                        if any(indicator in value_lower_check for indicator in title_indicators):
                            # Skip this candidate - it's a title/header
                            pass  # Don't add to cand_texts
                        else:
                            # Use the extracted line as the text window (highest priority)
                            if value_clean and value_clean != (dst_block.text or ""):
                                cand_texts.insert(0, value_clean)  # Insert at beginning for highest priority
                    else:
                        # Use the extracted line as the text window (highest priority)
                        if value_clean and value_clean != (dst_block.text or ""):
                            cand_texts.insert(0, value_clean)  # Insert at beginning for highest priority
            elif label_line_idx is not None and len(dst_lines) > 0:
                # Label found but no corresponding line - use first line of value block as fallback
                # This handles cases where label and value are in different blocks but not perfectly aligned
                first_value_line = dst_lines[0].strip() if dst_lines else ""
                if first_value_line:
                    # Extract first part for short fields
                    if field.type in ["number", "id_simple", "uf", "alphanum_code"]:
                        parts = first_value_line.split()
                        if parts:
                            for part in parts:
                                if type_gate_generic(part, field.type):
                                    cand_texts.insert(0, part)
                                    break
                    else:
                        cand_texts.insert(0, first_value_line)

        # Generate candidates (section-aware for text_multiline)
        # Skip if same_block and we already have split candidates (to avoid labels)
        # BUT: if we have a structured parse result, we want to keep it prioritized, so only add generic candidates after
        if field_cand.relation != "same_block" or not cand_texts:
            cands = _text_candidates(dst_block, layout, field.type or "text", max_lines_window=3, max_tokens=12)
            # IMPROVEMENT: Filter out titles/headers before adding to candidates
            for cand in cands:
                if cand.strip().endswith(":") and len(cand.strip()) > 10:
                    title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
                    cand_lower = cand.lower().strip()
                    if any(indicator in cand_lower for indicator in title_indicators):
                        continue  # Skip titles/headers
                cand_texts.append(cand)
        elif structured_parse_result:
            # If we have structured parse, still add generic candidates but structured will have much higher score
            cands = _text_candidates(dst_block, layout, field.type or "text", max_lines_window=3, max_tokens=12)
            # IMPROVEMENT: Filter out titles/headers before adding to candidates
            for cand in cands:
                if cand.strip().endswith(":") and len(cand.strip()) > 10:
                    title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
                    cand_lower = cand.lower().strip()
                    if any(indicator in cand_lower for indicator in title_indicators):
                        continue  # Skip titles/headers
                cand_texts.append(cand)

        best = (None, 0.0, None)  # (value, score, chosen_text)

        # Get enum_options from field meta if available
        enum_options = field.meta.get("enum_options") if field.meta else None

        # Calculate position bonus once
        position_bonus = _position_bonus(field.meta, dst_block.bbox)
        
        # If we have a structured parse result and it validates, return it immediately (highest priority)
        # Structured parsing is very reliable and should take precedence over generic extraction
        if structured_parse_result and field_cand.relation == "same_block":
            ok_struct, normalized_struct = validate_and_normalize(
                field.type or "text", structured_parse_result, enum_options=enum_options
            )
            if ok_struct and normalized_struct:
                # Structured parse results are highly reliable - skip plausibility check and return immediately
                # The parsing logic already filters out invalid patterns (e.g., pure numbers for cities)
                page_index = getattr(layout, "page_index", 0)
                return (
                normalized_struct,
                0.90,  # High confidence for structured parse
                    {
                        "node_id": field_cand.node_id,
                        "relation": field_cand.relation,
                        "page_index": page_index,
                        "notes": "Value extracted via structured pattern parsing",
                        "evidence": {"candidate_text": normalized_struct},
                    },
            )
    
        # For global_enum_scan, we already have the validated value in local_context
        # Use it directly if available (before processing other candidates)
        if field_cand.relation == "global_enum_scan" and field_cand.local_context:
            # The local_context for global_enum_scan contains the normalized enum value directly
            # (set by matcher after validation)
            normalized_value = field_cand.local_context.strip()
            # Verify it's still valid (should be, but double-check)
            if normalized_value:
                # Check if it matches enum options (if enum type)
                if field.type == "enum" and enum_options:
                    # Already normalized, just verify it's in options
                    if normalized_value in enum_options:
                        page_index = getattr(layout, "page_index", 0)
                        return (
                        normalized_value,
                        0.75,  # confidence for global_enum_scan
                        {
                            "node_id": field_cand.node_id,
                            "relation": field_cand.relation,
                            "page_index": page_index,
                            "notes": "Value found via global enum scan across document",
                            "evidence": {"candidate_text": normalized_value},
                        },
                    )
                else:
                    # Not enum or no options, use as-is
                    page_index = getattr(layout, "page_index", 0)
                    return (
                        normalized_value,
                        0.75,
                        {
                            "node_id": field_cand.node_id,
                            "relation": field_cand.relation,
                            "page_index": page_index,
                            "notes": "Value found via global enum scan across document",
                            "evidence": {"candidate_text": normalized_value},
                        },
                    )

    # Get field type once before the loop
    field_type = (field.type or "text").lower()
    
    for idx, txt in enumerate(cand_texts):
        # IMPROVEMENT: Early rejection of titles/headers (before any processing)
        # Check if text is clearly a title/header (ends with ":" and is long)
        if txt.strip().endswith(":") and len(txt.strip()) > 10:
            # Check for title indicators
            title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
            txt_lower_check = txt.lower().strip()
            if any(indicator in txt_lower_check for indicator in title_indicators):
                continue  # Skip titles/headers early
        
        # Check if this is the structured parse result (first candidate from same_block)
        is_structured = (idx == 0 and field_cand.relation == "same_block" and structured_parse_result and txt == structured_parse_result)
        
        # Remove "label: " if present, but preserve structured parsing results
        # If the text was from structured parsing and already clean, don't split
        if is_structured:
            # Structured parse result is already clean, use as-is
            txt_clean = txt.strip()
        else:
            txt_clean = LABEL_SEP_RE.split(txt, 1)[-1] if ":" in txt else txt.strip()
        
        # Additional cleanup: if the text starts with a known label/synonym, remove it
        # This prevents extracting labels as values
        field_synonyms_lower = [s.lower().strip() for s in (field.synonyms or []) + [field.name]]
        txt_lower = txt_clean.lower().strip()
        
        # Check if text is ONLY a label (no value after it) - reject these
        is_only_label = False
        for syn in field_synonyms_lower:
            if syn and txt_lower == syn:
                is_only_label = True
                break
            # Also check if text starts with label and has no meaningful content after
            if syn and txt_lower.startswith(syn):
                after_label = txt_clean[len(syn):].lstrip(" :\u200b\t")
                # If after removing label there's less than 2 chars or it's just punctuation, skip
                if len(after_label) < 2 or not any(c.isalnum() for c in after_label):
                    is_only_label = True
                    break
                # Remove the synonym and clean up
                txt_clean = after_label
                break
        
        # Skip if text is only a label
        if is_only_label:
            continue
        
        # Removed field-specific validation for "cidade" - rely on semantic embeddings and LLM
        
        # IMPROVEMENT: Check if field has low confidence and value might be from wrong field
        # If confidence is very low (<0.4) and field has enum options, validate against enum
        # This helps reject values that don't match expected enum options
        if field.type == "enum" and enum_options:
            # For enum fields, only accept values in the options list
            txt_normalized_upper = txt_clean.upper().strip()
            options_upper = [opt.upper().strip() for opt in enum_options]
            if txt_normalized_upper not in options_upper:
                # Check if it's a partial match or similar (e.g., "CONSIGNADO" in "SISTEMA CONSIGNADO")
                is_partial_match = False
                for opt in options_upper:
                    if len(opt) > 3:  # Only check partial for longer options
                        if txt_normalized_upper in opt or opt in txt_normalized_upper:
                            # Extract the matching part
                            if opt in txt_normalized_upper:
                                txt_clean = opt  # Use the full enum option
                                txt_normalized_upper = opt
                                is_partial_match = True
                                break
                            elif txt_normalized_upper in opt:
                                # Value is part of option - might be valid if it's a significant part
                                if len(txt_normalized_upper) >= len(opt) * 0.7:  # At least 70% of option
                                    txt_clean = opt  # Use the full enum option
                                    txt_normalized_upper = opt
                                    is_partial_match = True
                                    break
                if not is_partial_match:
                    # Reject - not a valid enum value
                    continue
        
        # Additional check: reject common field labels that shouldn't be values
        # IMPROVEMENT: More comprehensive list and better detection logic
        common_labels = [
            "inscrição", "inscricao", "inscriçao", "inscriç", "inscri",
            "seccional", "seccion", "secc",
            "subseção", "subsecao", "subsec",
            "categoria", "categor", "categ",
            "endereço", "endereco", "endereç", "enderec",
            "telefone", "telefon", "telef",
            "situação", "situacao", "situaç", "situac",
            "nome", "name",
            "data", "date",
            "valor", "value",
            "sistema", "system",
            "produto", "product",
            "endereço profissional", "endereco profissional", "endereço prof", "endereco prof",
            "telefone profissional", "telefone prof", "telef prof",
            "profissional", "profiss", "prof",
            "conselho seccional", "conselho sec", "cons sec",
            "pesquisa", "pesquis", "pesq",
            "tipo", "type",
            "parcela", "parcel",
            "cidade", "city",
            "referencia", "referência", "ref",
            "seleção", "selecao", "selec",
            "total", "tot",
        ]
        txt_lower_clean = txt_clean.lower().strip()
        
        # Strategy 1: Exact match rejection
        if txt_lower_clean in common_labels:
            continue
        
        # Strategy 2: Prefix/suffix match (labels often end with separators or are prefixes)
        # Reject if text starts with a known label prefix
        for label in common_labels:
            if txt_lower_clean.startswith(label) and len(txt_lower_clean) <= len(label) + 3:
                # Text is essentially just the label (maybe with separator)
                continue
        
        # Strategy 3: Reject sequences of labels (e.g., "Inscrição Seccional Subseção")
        words = txt_lower_clean.split()
        if len(words) <= 3:
            # Check if all or most words are labels
            label_words = sum(1 for w in words if w in common_labels or any(w.startswith(lbl) for lbl in common_labels))
            if label_words >= len(words) * 0.7:  # 70% or more are labels
                continue
        
        # Strategy 4: Reject short text (1-2 words) that matches labels
        # BUT: Only if it's clearly just a label (not a value that happens to contain label word)
        if len(words) <= 2:
            words_lower = [w.lower().strip() for w in words]
            # Check if text is EXACTLY a label (not just contains one)
            if txt_lower_clean in common_labels:
                continue
            # Check if all words are labels (e.g., "Inscrição Seccional")
            if len(words_lower) == 2 and all(w in common_labels for w in words_lower):
                continue
            # For single words, only reject if it's exactly a label
            if len(words_lower) == 1 and words_lower[0] in common_labels:
                continue
        
        # Generic label removal: if text starts with known label prefix, try to remove it
        # This works for any field, not just specific ones
        # Also handle multi-word labels like "Endereço Profissional"
        for label in sorted(common_labels, key=len, reverse=True):  # Try longer labels first
            if txt_lower_clean.startswith(label):
                # Check if there's meaningful content after label
                after_label = txt_clean[len(label):].lstrip(" :\u200b\t")
                if len(after_label.strip()) >= 2:
                    # Use text after label
                    txt_clean = after_label.strip()
                    txt_lower = txt_clean.lower().strip()
                    break
        
        # Correction 5: Remove UF prefix from long text fields
        # If text starts with a UF (2 uppercase letters) followed by longer text, remove the UF
        if field_type == "text" and len(txt_clean) >= 6:  # Only for longer text
            # Check if starts with 2 uppercase letters (potential UF) followed by space and more text
            uf_prefix_match = re.match(r"^([A-Z]{2})\s+(.+)$", txt_clean)
            if uf_prefix_match:
                potential_uf = uf_prefix_match.group(1)
                rest_text = uf_prefix_match.group(2)
                # If rest_text is substantial (>= 4 chars), remove UF prefix
                if len(rest_text.strip()) >= 4:
                    txt_clean = rest_text.strip()
                    # Update txt_lower for subsequent checks
                    txt_lower = txt_clean.lower().strip()
        
        # Require minimum length for text fields (avoid 2-letter values unless they're UF codes)
        if field_type == "text" and len(txt_clean.strip()) < 4:
            # Allow if it's a valid UF code (2 letters) - but this shouldn't happen for text fields
            if not re.match(r"^[A-Z]{2}$", txt_clean.strip()):
                continue  # Reject short text values (likely incomplete extraction)

        # IMPROVEMENT: Check if this value looks like it belongs to a different field
        # This helps prevent extracting values that are clearly for other fields
        # Example: extracting date "12/10/2025" for field "sistema" when it should be null or "CONSIGNADO"
        field_name_lower = (field.name or "").lower()
        import re
        
        # If field name suggests it's not a date field, but value is a date, be suspicious
        if field_type != "date" and not ("data" in field_name_lower or "venc" in field_name_lower or "referencia" in field_name_lower):
            # Check if extracted value looks like a date
            date_patterns = [
                r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
                r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
                r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
            ]
            if any(re.search(pattern, txt_clean) for pattern in date_patterns):
                # Value looks like a date but field is not date-related
                # Reject unless it's from structured parse or explicit label match
                if field_cand.relation not in ["same_block", "same_line_right_of"]:
                    # Not from structured parse or explicit label - likely wrong field
                    continue
        
        # IMPROVEMENT: If field is enum but value doesn't match options, reject
        # This prevents extracting random values for enum fields
        if field.type == "enum" and enum_options:
            txt_normalized_upper = txt_clean.upper().strip()
            options_upper = [opt.upper().strip() for opt in enum_options]
            if txt_normalized_upper not in options_upper:
                # Check for partial match (e.g., "CONSIGNADO" in "SISTEMA CONSIGNADO")
                is_partial = any(txt_normalized_upper in opt or opt in txt_normalized_upper for opt in options_upper if len(opt) > 3)
                if not is_partial:
                    # Not a valid enum value - reject
                    continue
        
        # IMPROVEMENT: If field is money but value looks like a date, reject
        if field_type == "money" or "valor" in field_name_lower or "parcela" in field_name_lower:
            # Check if value looks like a date instead of money
            if re.search(r'\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}', txt_clean):
                # Looks like date, not money - reject
                continue
        
        # IMPROVEMENT: If field is text but value looks like money, be suspicious
        if field_type == "text" and ("sistema" in field_name_lower or "produto" in field_name_lower):
            # Check if value looks like money (has currency symbols or format)
            if re.search(r'[\d.,]+\s*(?:R\$|reais?|RS|USD|\$)', txt_clean, re.IGNORECASE) or re.search(r'\d+[,.]\d{2}$', txt_clean):
                # Looks like money, not text - reject unless high confidence
                if field_cand.relation not in ["same_block", "same_line_right_of"]:
                    continue
        
        # IMPROVEMENT: Reject values that are clearly section titles/headers (end with ":")
        # These are not values, they're labels/titles
        # Check BEFORE any other processing to catch early
        if txt_clean.strip().endswith(":"):
            # Looks like a title/header (e.g., "Detalhamento de saldos por parcelas:")
            # Reject if longer than 10 chars (definitely a title, not a value)
            if len(txt_clean.strip()) > 10:
                continue
            # Also reject if it contains common title words and ends with ":"
            title_indicators = ["detalhamento", "resumo", "informações", "dados", "campos", "seção", "secao"]
            txt_lower_check = txt_clean.lower().strip()
            if any(indicator in txt_lower_check for indicator in title_indicators) and txt_clean.strip().endswith(":"):
                continue
        
        # IMPROVEMENT: Reject values that are all uppercase and look like titles/headers
        # (unless they're enum values which are often uppercase)
        if txt_clean.isupper() and len(txt_clean.split()) > 2:
            # All uppercase with multiple words - likely a title/header
            # Only accept if it's a valid enum value
            if field.type != "enum" or not enum_options:
                # Not enum or no options - reject uppercase titles
                continue
            # For enum, check if it matches - if not, reject
            if enum_options and txt_clean.upper().strip() not in [opt.upper().strip() for opt in enum_options]:
                continue
        
        # IMPROVEMENT: Additional check for title-like patterns
        # Reject if text contains common title patterns (e.g., "Detalhamento de saldos por parcelas:")
        title_patterns = [
            r"detalhamento.*parcelas",
            r"resumo.*saldos",
            r"informações.*opera",
            r"dados.*opera",
        ]
        txt_lower_pattern = txt_clean.lower().strip()
        for pattern in title_patterns:
            if re.search(pattern, txt_lower_pattern):
                # Matches a title pattern - reject
                continue
        
        # Validate and normalize (with enum_options if enum type)
        # For UF fields, pass context block for gate validation
        if field_type == "uf":
            from ..validation.validators import validate_uf
            ok, normalized = validate_uf(txt_clean, context_block=dst_block.text)
        elif field_type == "city" or (field_type == "text" and "cidade" in (field.name or "").lower()):
            from ..validation.validators import validate_city
            ok, normalized = validate_city(txt_clean)
        else:
            ok, normalized = validate_and_normalize(
                field.type or "text", txt_clean, enum_options=enum_options
            )

        # IMPROVEMENT: For fields with enum options, check if value matches BEFORE scoring
        # This prevents low-confidence enum extractions
        if field.type == "enum" and enum_options:
            txt_normalized_upper = txt_clean.upper().strip()
            options_upper = [opt.upper().strip() for opt in enum_options]
            if txt_normalized_upper not in options_upper:
                # Reject if not a valid enum value (already checked above, but double-check)
                continue
        
        # Score candidate (with position bonus)
        base_score = _score_candidate(
            field.type or "text", txt_clean, cand.relation, ok, position_bonus
        )
        
        # IMPROVEMENT: Penalize low-confidence candidates for fields that should be null if not found
        # Fields like "produto", "selecao_de_parcelas" that often should be null
        field_name_lower = (field.name or "").lower()
        if field_name_lower in ["produto", "selecao_de_parcelas", "quantidade_parcelas", "tipo_de_operacao", "tipo_de_sistema"]:
            # These fields should only accept values with high confidence
            # Penalize if relation is not explicit (same_block, same_line_right_of)
            if field_cand.relation not in ["same_block", "same_line_right_of", "same_table_row"]:
                base_score *= 0.5  # Reduce score by 50% for indirect relations
        
        # Give significant boost to structured parse results (they're highly reliable)
        # Structured parse results are very reliable and should be prioritized
        if is_structured:
            score = min(1.0, base_score + 0.30)  # +0.30 boost for structured parse (very high priority)
        else:
            score = base_score
        
        # Type-specific prioritization: boost score for values that better match the field type
        type_boost = 0.0
        
        if field_type == "uf":
            # For UF fields, prioritize 2-letter uppercase codes (PR, SP, etc) over numbers
            if re.match(r"^[A-Z]{2}$", txt_clean.strip()):
                type_boost = 0.15  # Strong boost for UF codes
            elif re.match(r"^\d+$", txt_clean.strip()):
                type_boost = -0.10  # Penalty for pure numbers (likely not UF)
        elif field_type == "id_simple":
            # For id_simple, prioritize alphanumeric with digits over pure text
            if re.search(r"\d", txt_clean) and re.search(r"[A-Za-z]", txt_clean):
                type_boost = 0.05  # Boost for alphanumeric with digits
            elif re.match(r"^[A-Z]{2}$", txt_clean.strip()):
                type_boost = -0.10  # Penalty for UF codes (likely not id_simple)
        
        score = min(1.0, score + type_boost)  # Cap at 1.0
        
        # Apply plausibility check: penalize values that don't make semantic sense
        plausibility_score = _validate_plausibility(field, txt_clean)
        # Adjust score: 70% base score + 30% plausibility adjustment
        score = score * (0.7 + 0.3 * plausibility_score)
        
        # Embeddings removed - semantic similarity boost no longer used
        semantic_similarity_boost = 0.0
        score = min(1.0, score + semantic_similarity_boost)

        if ok and score > best[1]:
            best = (normalized, score, txt_clean)

    if best[0] is None:
        # Still return evidence for LLM fallback
        evidence = _build_evidence(dst_block, layout, cand)
        page_index = getattr(layout, "page_index", 0)
        notes = f"Validation failed for candidate text: {evidence.get('candidate_text', '')[:50]}"
        return None, 0.0, {
            "node_id": cand.node_id,
            "relation": cand.relation,
            "page_index": page_index,
            "reason": "validation_failed",
            "notes": notes,
            "evidence": evidence,
        }

    # Confidence based on relation type
    if cand.relation == "same_line_right_of":
        confidence = 0.90
    elif cand.relation in ("same_block", "same_table_row"):
        confidence = 0.85
    elif cand.relation == "first_below_same_column":
        confidence = 0.80
    elif cand.relation == "global_enum_scan":
        confidence = 0.75
    else:
        confidence = 0.80  # default safe value

    # Build evidence for LLM context (even when value found, for potential fallback)
    # Use the actual extracted value in candidate_text, not the whole block
    evidence = _build_evidence(dst_block, layout, cand)
    if best[0] and best[2]:  # If we have a value and the chosen text
        # Update candidate_text to show the actual extracted value, not the whole block
        evidence["candidate_text"] = best[2]  # Use the chosen text that was extracted
    page_index = getattr(layout, "page_index", 0)
    
    # Generate descriptive notes based on relation
    relation_notes = {
        "same_line_right_of": "Value found to the right of label on the same line",
        "same_table_row": "Value found in the same table row as label",
        "same_block": "Value extracted from the same text block as label",
        "first_below_same_column": "Value found below label in the same column",
        "global_enum_scan": "Value found via global enum scan across document",
    }
    notes = relation_notes.get(cand.relation, f"Value found via {cand.relation} relation")

    return (
        best[0],
        confidence,
        {
            "node_id": cand.node_id,
            "relation": cand.relation,
            "page_index": page_index,
            "notes": notes,
            "evidence": evidence,
        },
    )


def _build_evidence(dst_block: Block, layout: LayoutGraph, cand: FieldCandidate) -> dict[str, str]:
    """Build evidence snippets for LLM context.

    Args:
        dst_block: Destination block.
        layout: LayoutGraph.
        cand: FieldCandidate.

    Returns:
        Dictionary with 'candidate_text' and 'neighbors'.
    """
    # Candidate text (winner or first line)
    candidate_text = dst_block.text.splitlines()[0][:300] if dst_block.text else ""

    # Neighbors: lines above/below and left/right blocks
    neighbors: list[str] = []

    # Get line nodes for this block
    line_id_by_block = getattr(layout, "line_id_by_block", {})
    block_line_ids = line_id_by_block.get(dst_block.id, [])

    if block_line_ids:
        line_nodes = [rn for rn in layout.reading_nodes if rn.type == "line"]
        line_by_id = {ln.id: ln for ln in line_nodes}

        # Find current line
        if block_line_ids:
            current_line_id = block_line_ids[0]
            current_line_idx = next(
                (i for i, ln in enumerate(line_nodes) if ln.id == current_line_id), None
            )

            if current_line_idx is not None:
                # Line above
                if current_line_idx > 0:
                    prev_line = line_nodes[current_line_idx - 1]
                    prev_block_id = prev_line.ref_block_ids[0] if prev_line.ref_block_ids else None
                    if prev_block_id:
                        prev_block = next((b for b in layout.blocks if b.id == prev_block_id), None)
                        if prev_block:
                            neighbors.append(f"Above: {prev_block.text.splitlines()[0][:150]}")

                # Line below
                if current_line_idx < len(line_nodes) - 1:
                    next_line = line_nodes[current_line_idx + 1]
                    next_block_id = next_line.ref_block_ids[0] if next_line.ref_block_ids else None
                    if next_block_id:
                        next_block = next((b for b in layout.blocks if b.id == next_block_id), None)
                        if next_block:
                            neighbors.append(f"Below: {next_block.text.splitlines()[0][:150]}")

    # Check if from table - include full row
    tables = getattr(layout, "tables", [])
    if tables and cand.relation == "same_table_row":
        for table in tables:
            for cell in table.cells:
                if dst_block.id in cell.block_ids:
                    # Get all cells in same row
                    row_cells = [c for c in table.cells if c.row_id == cell.row_id]
                    row_text = " | ".join(c.text[:50] for c in row_cells)
                    neighbors.append(f"Table row: {row_text[:200]}")
                    break

    # Left/right blocks (if available)
    neighborhood = getattr(layout, "neighborhood", {})
    nb = neighborhood.get(cand.node_id)
    if nb:
        block_by_id = {b.id: b for b in layout.blocks}
        if nb.left_on_same_line:
            left_block = block_by_id.get(nb.left_on_same_line)
            if left_block:
                neighbors.append(f"Left: {left_block.text.splitlines()[0][:100]}")
        if nb.right_on_same_line:
            right_block = block_by_id.get(nb.right_on_same_line)
            if right_block:
                neighbors.append(f"Right: {right_block.text.splitlines()[0][:100]}")

    return {
        "candidate_text": candidate_text,
        "neighbors": "\n".join(neighbors) if neighbors else "",
    }
