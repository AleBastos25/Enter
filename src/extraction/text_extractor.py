"""Text extraction from field candidates with multi-line/multi-token scoring."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..core.models import Block, FieldCandidate, LayoutGraph, SchemaField
from ..validation.validators import validate_and_normalize

LABEL_SEP_RE = re.compile(r"[:：]\s*")  # ':' variants


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
    """Try to extract value from structured patterns common in PDFs.
    
    This handles cases where multiple fields are in the same block, e.g.:
    "Cidade: Mozarlândia U.F .: GO CEP: 76709970"
    
    Args:
        block_text: Full text of the block.
        field: SchemaField to extract.
        
    Returns:
        Extracted value or None if pattern not found.
    """
    if not block_text or not field:
        return None
    
    field_name_lower = (field.name or "").lower()
    field_type = (field.type or "text").lower()
    
    # Pattern for cidade: "Cidade: [City Name] U.F .: [UF] CEP: [CEP]"
    if "cidade" in field_name_lower:
        # Try multiple patterns to catch different formats
        patterns = [
            # Pattern 1: "Cidade: [Name] U.F .: [UF] CEP: [CEP]"
            re.compile(r"cidade\s*:?\s*([^UuFfCcEePp]+?)(?:\s*(?:U\.?F\.?|UF|CEP|$))", re.IGNORECASE),
            # Pattern 2: "Cidade: [Name]" (just cidade, no UF/CEP)
            re.compile(r"cidade\s*:?\s*([^:\n]+?)(?:\s*$|[\n\r])", re.IGNORECASE),
            # Pattern 3: Look for cidade anywhere and extract following text until UF/CEP
            re.compile(r"cidade\s*:?\s*([A-Za-zÀ-ÿ\s-]+?)(?:\s*(?:U\.?F\.?|UF|CEP))", re.IGNORECASE),
        ]
        
        for pattern in patterns:
            match = pattern.search(block_text)
            if match:
                cidade_name = match.group(1).strip()
                # Remove trailing punctuation and whitespace
                cidade_name = re.sub(r'[^\w\sÀ-ÿ-]+$', '', cidade_name).strip()
                cidade_name = cidade_name.strip(" :\t")
                # Filter out pure numbers (likely CEP)
                if cidade_name and len(cidade_name) >= 3 and not re.match(r'^\d+$', cidade_name):
                    # Ensure it has at least one letter
                    if re.search(r'[A-Za-zÀ-ÿ]', cidade_name):
                        return cidade_name
    
    # Pattern for inscricao: "Inscrição: [ID]"
    if "inscricao" in field_name_lower or field_type == "id_simple":
        pattern = re.compile(
            r"inscri[çc][ãa]o\s*:?\s*([A-Z0-9]{3,15})",
            re.IGNORECASE
        )
        match = pattern.search(block_text)
        if match:
            inscricao = match.group(1).strip()
            if inscricao:
                return inscricao
    
    # Pattern for UF/seccional: "U.F .: [UF]" or "Seccional: [UF]"
    if field_type == "uf" or "seccional" in field_name_lower or "uf" in field_name_lower:
        pattern = re.compile(
            r"(?:uf|seccional|u\.?f\.?)\s*:?\s*([A-Z]{2})",
            re.IGNORECASE
        )
        match = pattern.search(block_text)
        if match:
            uf = match.group(1).strip().upper()
            if uf:
                return uf
    
    # Pattern for CEP: "CEP: [CEP]"
    if "cep" in field_name_lower:
        pattern = re.compile(
            r"cep\s*:?\s*(\d{5}-?\d{3}|\d{8})",
            re.IGNORECASE
        )
        match = pattern.search(block_text)
        if match:
            cep = match.group(1).strip()
            if cep:
                return cep
    
    return None


def extract_from_candidate(
    field: SchemaField, cand: FieldCandidate, layout: LayoutGraph, embed_client: Optional[Any] = None
) -> tuple[Optional[str], float, dict]:
    """Given a FieldCandidate, produce a (value, confidence, trace) tuple.

    Generates multiple candidates (lines, windows, tokens) and scores them,
    returning the best one.

    Args:
        field: SchemaField being extracted.
        cand: FieldCandidate with node_id and relation.
        layout: LayoutGraph with blocks.

    Returns:
        Tuple of (value, confidence, trace_dict).
        If no candidate passes validation, returns (None, 0.0, trace_with_reason).
    """
    # Get destination block
    dst_block = next((b for b in layout.blocks if b.id == cand.node_id), None)
    if not dst_block:
        return None, 0.0, {"node_id": cand.node_id, "relation": cand.relation, "reason": "block_not_found"}

    # Get label block for line-based extraction
    label_block = None
    if hasattr(cand, 'source_label_block_id') and cand.source_label_block_id:
        label_block = next((b for b in layout.blocks if b.id == cand.source_label_block_id), None)

    # For same_block, prioritize splitting by label to avoid extracting labels
    cand_texts: list[str] = []
    structured_parse_result = None  # Track if we have a structured parse result
    if cand.relation == "same_block":
        # First, try structured parsing for common patterns (e.g., "Cidade: X U.F: Y CEP: Z")
        structured_value = _parse_structured_block(dst_block.text or "", field)
        if structured_value:
            structured_parse_result = structured_value
            cand_texts.append(structured_value)  # Highest priority
        
        # If local_context is provided (e.g., from semantic matching), use it as a candidate
        # This allows embeddings/LLM to pre-extract values when appropriate
        if cand.local_context and len(cand.local_context.strip()) >= 3:
            # Basic check: don't use if it's just a label
            ctx_lower = cand.local_context.lower().strip()
            common_labels = ["cidade", "inscricao", "nome", "endereco", "telefone", "seccional"]
            if ctx_lower not in common_labels:
                cand_texts.append(cand.local_context.strip())
        
        # Try to split by label and use the part after the label as primary candidate
        # This is critical for same_block: split "SITUAÇÃO REGULAR" -> "REGULAR"
        primary = _split_by_label(dst_block.text or "", field.synonyms or [field.name])
        if primary and len(primary.strip()) > 0:
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
        nb = neighborhood.get(cand.node_id)
        if nb and nb.right_on_same_line:
            right_block = next((b for b in layout.blocks if b.id == nb.right_on_same_line), None)
            if right_block:
                # Use right block as candidate (it's likely the value)
                cand_texts.append(right_block.text.splitlines()[0] if right_block.text else "")
    
    # For first_below_same_column with multi-line blocks, try to extract the corresponding line
    # This helps when labels are in one block and values in another: "Inscrição\nSeccional" -> "101943\nPR"
    if cand.relation == "first_below_same_column" and label_block and label_block.id != dst_block.id:
        label_lines = [ln.strip() for ln in label_block.text.splitlines() if ln.strip()]
        dst_lines = [ln.strip() for ln in dst_block.text.splitlines() if ln.strip()]
        
        # Find which line of the label block contains this field's label
        field_name_lower = field.name.lower()
        field_synonyms_lower = [s.lower().strip() for s in (field.synonyms or [])]
        
        label_line_idx = None
        for i, label_line in enumerate(label_lines):
            label_line_norm = _normalize_text(label_line)
            # Check if this line contains the field name or synonyms
            if field_name_lower in label_line_norm:
                label_line_idx = i
                break
            for syn in field_synonyms_lower:
                if syn and syn in label_line_norm:
                    label_line_idx = i
                    break
            if label_line_idx is not None:
                break
        
        # If we found the label line and there's a corresponding value line, prioritize it
        if label_line_idx is not None and label_line_idx < len(dst_lines):
            corresponding_line = dst_lines[label_line_idx]
            if corresponding_line and len(corresponding_line.strip()) > 0:
                # Add this as the first candidate (highest priority)
                cand_texts.insert(0, corresponding_line)

    # Generate candidates (section-aware for text_multiline)
    # Skip if same_block and we already have split candidates (to avoid labels)
    # BUT: if we have a structured parse result, we want to keep it prioritized, so only add generic candidates after
    if cand.relation != "same_block" or not cand_texts:
        cands = _text_candidates(dst_block, layout, field.type or "text", max_lines_window=3, max_tokens=12)
        cand_texts.extend(cands)
    elif structured_parse_result:
        # If we have structured parse, still add generic candidates but structured will have much higher score
        cands = _text_candidates(dst_block, layout, field.type or "text", max_lines_window=3, max_tokens=12)
        cand_texts.extend(cands)

    best = (None, 0.0, None)  # (value, score, chosen_text)

    # Get enum_options from field meta if available
    enum_options = field.meta.get("enum_options") if field.meta else None

    # Calculate position bonus once
    position_bonus = _position_bonus(field.meta, dst_block.bbox)
    
    # If we have a structured parse result and it validates, return it immediately (highest priority)
    # Structured parsing is very reliable and should take precedence over generic extraction
    if structured_parse_result and cand.relation == "same_block":
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
                    "node_id": cand.node_id,
                    "relation": cand.relation,
                    "page_index": page_index,
                    "notes": "Value extracted via structured pattern parsing",
                    "evidence": {"candidate_text": normalized_struct},
                },
            )
    
    # For global_enum_scan, we already have the validated value in local_context
    # Use it directly if available (before processing other candidates)
    if cand.relation == "global_enum_scan" and cand.local_context:
        # The local_context for global_enum_scan contains the normalized enum value directly
        # (set by matcher after validation)
        normalized_value = cand.local_context.strip()
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
                            "node_id": cand.node_id,
                            "relation": cand.relation,
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
                            "node_id": cand.node_id,
                            "relation": cand.relation,
                            "page_index": page_index,
                            "notes": "Value found via global enum scan across document",
                            "evidence": {"candidate_text": normalized_value},
                        },
                    )

    # Get field type once before the loop
    field_type = (field.type or "text").lower()
    
    for idx, txt in enumerate(cand_texts):
        # Check if this is the structured parse result (first candidate from same_block)
        is_structured = (idx == 0 and cand.relation == "same_block" and structured_parse_result and txt == structured_parse_result)
        
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
        
        # Additional check: reject common field labels that shouldn't be values
        # This is especially important for text fields that might match labels
        common_labels = [
            "inscrição", "inscricao", "seccional", "subseção", "subsecao",
            "categoria", "endereço", "endereco", "telefone", "situação", "situacao",
            "nome", "data", "valor", "sistema", "produto", "endereço profissional",
            "telefone profissional", "profissional", "subseção", "subsecao"
        ]
        txt_lower_clean = txt_clean.lower().strip()
        # If the text is exactly one of these common labels, reject it
        if txt_lower_clean in common_labels:
            continue
        
        # Reject if text is just a sequence of common labels (e.g., "Inscrição Seccional Subseção")
        words = txt_lower_clean.split()
        if len(words) <= 3 and all(w in common_labels for w in words):
            continue
        # Reject if text is just 1-2 words that match common labels
        words = txt_clean.split()
        if len(words) <= 2:
            words_lower = [w.lower().strip() for w in words]
            if any(w in common_labels for w in words_lower):
                continue
        
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

        # Score candidate (with position bonus)
        base_score = _score_candidate(
            field.type or "text", txt_clean, cand.relation, ok, position_bonus
        )
        
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
        
        # Apply semantic similarity boost using embeddings (if available)
        semantic_similarity_boost = 0.0
        if embed_client and ok and normalized:
            try:
                # Build field description query (similar to embedding query)
                field_query_parts = [field.name]
                if field.description:
                    field_query_parts.append(field.description[:100])
                if field.synonyms:
                    field_query_parts.extend(field.synonyms[:2])  # Top 2 synonyms
                field_query = " ".join(field_query_parts)
                
                # Embed both the extracted value and the field description
                value_text = normalized[:200]  # Limit length for embedding
                texts_to_embed = [field_query, value_text]
                embeddings = embed_client.embed(texts_to_embed)
                
                if len(embeddings) == 2:
                    import numpy as np
                    field_emb = np.array(embeddings[0])
                    value_emb = np.array(embeddings[1])
                    
                    # Calculate cosine similarity
                    dot_product = np.dot(field_emb, value_emb)
                    norm_field = np.linalg.norm(field_emb)
                    norm_value = np.linalg.norm(value_emb)
                    
                    if norm_field > 0 and norm_value > 0:
                        cosine_sim = dot_product / (norm_field * norm_value)
                        # Boost score by 15% of semantic similarity (capped at 0.15 boost)
                        semantic_similarity_boost = 0.15 * max(0.0, cosine_sim)
            except Exception:
                # If embedding fails, continue without boost
                pass
        
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
