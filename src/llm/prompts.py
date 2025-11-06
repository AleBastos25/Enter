"""Prompt templates and response parsing for LLM fallback."""

from __future__ import annotations

import json
import re
from typing import Optional


def _get_type_examples(field_type: str) -> str:
    """Get short examples for a field type (generic, no locale-specific assumptions)."""
    examples = {
        "date": "YYYY-MM-DD, DD/MM/YYYY, or DD-MM-YYYY",
        "money": "numbers with optional decimal separators (e.g., 1234.56, 1,234.56)",
        "id_simple": "alphanumeric codes (e.g., ABC123, 101943)",
        "code": "short codes (2-4 uppercase letters)",
        "enum": "one of the provided options",
        "text": "any text",
        "text_multiline": "multi-line text",
        "int": "whole numbers",
        "float": "decimal numbers",
        "percent": "percentage values",
    }
    return examples.get(field_type.lower(), "any text")


def build_prompt(
    field_name: str,
    field_type: str,
    context_text: str,
    *,
    enum_options: Optional[list[str]] = None,
    regex_hint: Optional[str] = None,
    field_description: Optional[str] = None,
) -> str:
    """Build prompt for LLM extraction (generic, no locale assumptions).

    Args:
        field_name: Name of the field.
        field_type: Type of the field (date, money, etc.).
        context_text: Context snippet (candidate + neighbors).
        enum_options: Optional enum options (for enum type).
        regex_hint: Optional regex pattern hint.
        field_description: Optional field description for better context.

    Returns:
        Formatted prompt string.
    """
    type_examples = _get_type_examples(field_type)

    # Build type hint
    type_hint = field_type.upper()
    if field_type == "enum" and enum_options:
        type_hint = f"ENUM[{', '.join(enum_options[:5])}]"  # Limit to 5 options

    prompt = f"""You are an extractor. Given a text snippet from a PDF, identify EXPLICIT values only.

FIELD TO EXTRACT:
- Name: {field_name}"""
    
    if field_description:
        prompt += f"\n- Description: {field_description}"
    
    prompt += f"""
- Type: {type_hint}
- Examples: {type_examples}"""

    if field_type == "enum" and enum_options:
        prompt += f"\n- Valid options: {', '.join(enum_options)}"

    if regex_hint:
        prompt += f"\n- Pattern hint: {regex_hint}"

    prompt += f"""

TEXT SNIPPET:
<<<
{context_text}
>>>

RULES:
- Extract ONLY values that are literally present in the snippet (or immediate neighbors).
- If unclear, return null for that field.
- Do not normalize beyond the obvious (e.g., spaces). Do not invent data.
- Return JSON: {{"value": "<extracted-or-null>"}}
"""

    return prompt


def build_batch_prompt(
    fields: list[dict],
    context_text: str,
    neighbor_above: str = "",
    neighbor_below: str = "",
) -> str:
    """Build batch prompt for multiple fields (generic, no locale assumptions).
    
    Args:
        fields: List of field dicts with keys: name, type, description, enum_options.
        context_text: Main candidate text (max 300 chars).
        neighbor_above: Text from line above (optional).
        neighbor_below: Text from line below (optional).
    
    Returns:
        Formatted prompt string for batch extraction.
    """
    prompt = """You are an extractor. Given a text snippet from a PDF, identify EXPLICIT values for multiple fields.

TEXT SNIPPET:
<<<
"""
    prompt += context_text[:300]  # Limit to 300 chars
    
    if neighbor_above or neighbor_below:
        prompt += "\n\nNEIGHBORS:\n"
        if neighbor_above:
            prompt += f"- Above: {neighbor_above[:100]}\n"
        if neighbor_below:
            prompt += f"- Below: {neighbor_below[:100]}\n"
    
    prompt += "\n>>>\n\nFIELDS TO EXTRACT (independent):\n"
    
    for i, field in enumerate(fields, 1):
        field_name = field.get("name", "")
        field_type = field.get("type", "text")
        field_desc = field.get("description", "")
        enum_opts = field.get("enum_options")
        
        prompt += f"\n{i}. {field_name} (type: {field_type.upper()})"
        if field_desc:
            prompt += f"\n   Description: {field_desc[:100]}"
        if enum_opts:
            prompt += f"\n   Options: {', '.join(enum_opts[:5])}"
    
    prompt += """

RULES:
- Extract ONLY values that are literally present in the snippet (or neighbors).
- If unclear, return null for that field.
- Do not normalize beyond the obvious (e.g., spaces). Do not invent data.
- Return JSON: {"results": {"field_name": value|null, ...}}
"""
    
    return prompt


def parse_llm_response(response: str) -> Optional[str]:
    """Parse LLM response to extract value.

    Args:
        response: Raw LLM response text.

    Returns:
        Extracted value string, or None if parsing failed.
    """
    if not response or not response.strip():
        return None

    # Try to find JSON object in response
    # Look for {...} pattern
    json_match = re.search(r"\{[^}]*\"value\"[^}]*\}", response, re.IGNORECASE)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            value = obj.get("value", "")
            if value and isinstance(value, str):
                return value.strip()
        except (json.JSONDecodeError, AttributeError):
            pass

    # Fallback: try parsing entire response as JSON
    try:
        obj = json.loads(response.strip())
        value = obj.get("value", "")
        if value and isinstance(value, str):
            return value.strip()
    except json.JSONDecodeError:
        pass

    return None


def build_scorer_prompt(
    fields: list,
    candidate_sets: dict,
    profile,
) -> str:
    """Build prompt for LLM scorer (score matrix in batch).
    
    Args:
        fields: List of SchemaField objects.
        candidate_sets: Dictionary mapping field_name -> list of Candidate objects.
        profile: DocProfile for context.
    
    Returns:
        Formatted prompt string.
    """
    prompt = """Você é um ranqueador de candidatos. Para cada CAMPO, atribua um score 0..1 a cada CANDIDATO com base na compatibilidade entre:
(1) a descrição do campo e tipo esperado; (2) o texto do candidato (snippet/region_text);
(3) as pistas geométricas/estruturais (relation, in_table, header_near, same_col, dist_bucket, bold, font_z_bucket, repeated_footer).

Regras:
- Se TYPE=enum e não existir o literal no snippet/region_text, score ≤ 0.2.
- Se repeated_footer=true, penalize fortemente salvo se o contexto indicar que o valor só existe no rodapé.
- Se TYPE=date/money e não houver padrão correspondente, score ≤ 0.3.
- Não invente valores; só pontue.

CAMPOS:
"""
    
    for field in fields:
        prompt += f"\n- {field.name}: {field.description or field.name} (type={field.type or 'text'})"
        if field.type == "enum" and field.meta.get("enum_options"):
            prompt += f" [options: {', '.join(field.meta['enum_options'][:10])}]"
    
    prompt += "\n\nCANDIDATOS:\n"
    
    for field in fields:
        candidates = candidate_sets.get(field.name, [])
        if not candidates:
            continue
        
        prompt += f"\n[{field.name}]:\n"
        for cand in candidates[:10]:  # Limit to 10 candidates per field
            features_str = f"relation={cand.features.relation}"
            if cand.features.in_table:
                features_str += f", in_table={cand.features.in_table[0]}"
            if cand.features.in_repeated_footer:
                features_str += ", repeated_footer=true"
            if cand.features.same_col:
                features_str += ", same_col=true"
            if cand.features.bold:
                features_str += ", bold=true"
            
            prompt += f"  - {cand.candidate_id}: snippet='{cand.snippet[:120]}', region='{cand.region_text[:300]}', {features_str}\n"
    
    prompt += """
Responda JSON: {"scores": {"<field>":{"<cand_id>":float,...},...}}
"""
    
    return prompt


def parse_scorer_response(
    response: str, fields: list, candidate_sets: dict
) -> dict[str, dict[str, float]]:
    """Parse scorer response JSON.
    
    Args:
        response: LLM response string (should be JSON).
        fields: List of SchemaField objects.
        candidate_sets: Dictionary mapping field_name -> list of Candidate objects.
    
    Returns:
        Dictionary mapping field_name -> {candidate_id: score, ...}.
    """
    scores = {field.name: {} for field in fields}
    
    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*"scores"[^{}]*\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
        else:
            data = json.loads(response)
        
        response_scores = data.get("scores", {})
        
        for field in fields:
            field_scores = response_scores.get(field.name, {})
            candidates = candidate_sets.get(field.name, [])
            
            for cand in candidates:
                # Get score from response, default to 0.5 if not found
                score = field_scores.get(cand.candidate_id, 0.5)
                # Clamp to [0, 1]
                score = max(0.0, min(1.0, float(score)))
                scores[field.name][cand.candidate_id] = score
    
    except Exception:
        # Fallback: return dummy scores
        for field in fields:
            candidates = candidate_sets.get(field.name, [])
            scores[field.name] = {cand.candidate_id: 0.5 for cand in candidates}
    
    return scores


def build_retry_prompt(
    field: dict,
    candidates: list,
) -> str:
    """Build prompt for directed retry (single field).
    
    Args:
        field: Field dict with keys: name, type, description, enum_options.
        candidates: List of Candidate objects.
    
    Returns:
        Formatted prompt string.
    """
    prompt = f"""Você é um extrator. Campo: {field['name']} (type={field.get('type', 'text')}).
Descrição: {field.get('description', '')}.

Candidatos (id, snippet, region_text, relation, in_table, header_near, same_col, dist_bucket):
"""
    
    for cand in candidates[:5]:  # Limit to 5 candidates
        features_str = f"relation={cand.features.relation}"
        if cand.features.in_table:
            features_str += f", in_table={cand.features.in_table[0]}"
        if cand.features.same_col:
            features_str += ", same_col=true"
        
        prompt += f"  - {cand.candidate_id}: snippet='{cand.snippet}', region='{cand.region_text}', {features_str}\n"
    
    prompt += """
Escolha 1 id ou null. Se escolher, retorne {"chosen_id":"...", "value_raw":"..."}.
Se não houver evidência clara, retorne {"chosen_id": null, "value_raw": null}.
"""
    
    return prompt


def parse_retry_response(response: str) -> dict[str, Optional[str]]:
    """Parse retry response JSON.
    
    Args:
        response: LLM response string (should be JSON).
    
    Returns:
        Dictionary with keys: chosen_id, value_raw (both can be None).
    """
    try:
        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            data = json.loads(json_match.group(0))
        else:
            data = json.loads(response)
        
        return {
            "chosen_id": data.get("chosen_id"),
            "value_raw": data.get("value_raw"),
        }
    except Exception:
        return {"chosen_id": None, "value_raw": None}


def parse_batch_response(response: str) -> dict[str, Optional[str]]:
    """Parse batch LLM response to extract values for multiple fields.
    
    Args:
        response: Raw LLM response text.
    
    Returns:
        Dictionary mapping field_name -> value (or None if not found).
    """
    if not response or not response.strip():
        return {}
    
    results = {}
    
    # Try to find JSON object with "results" key
    json_match = re.search(r"\{[^{}]*\"results\"[^{}]*\{[^}]+\}[^}]*\}", response, re.IGNORECASE | re.DOTALL)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            results_dict = obj.get("results", {})
            if isinstance(results_dict, dict):
                for field_name, value in results_dict.items():
                    if isinstance(value, str):
                        results[field_name] = value.strip() if value.strip() else None
                    elif value is None:
                        results[field_name] = None
                    else:
                        results[field_name] = str(value).strip() if str(value).strip() else None
        except (json.JSONDecodeError, AttributeError):
            pass
    
    # Fallback: try parsing entire response as JSON
    if not results:
        try:
            obj = json.loads(response.strip())
            if "results" in obj:
                results_dict = obj.get("results", {})
                if isinstance(results_dict, dict):
                    for field_name, value in results_dict.items():
                        if isinstance(value, str):
                            results[field_name] = value.strip() if value.strip() else None
                        elif value is None:
                            results[field_name] = None
                        else:
                            results[field_name] = str(value).strip() if str(value).strip() else None
            else:
                # Try direct field mapping (if response is just {field: value})
                if isinstance(obj, dict):
                    for field_name, value in obj.items():
                        if isinstance(value, str):
                            results[field_name] = value.strip() if value.strip() else None
                        elif value is None:
                            results[field_name] = None
                        else:
                            results[field_name] = str(value).strip() if str(value).strip() else None
        except json.JSONDecodeError:
            pass
    
    return results

