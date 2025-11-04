"""Prompt templates and response parsing for LLM fallback."""

from __future__ import annotations

import json
import re
from typing import Optional


def _get_type_examples(field_type: str) -> str:
    """Get short examples for a field type."""
    examples = {
        "date": "2024-01-15, 15/01/2024",
        "money": "1234.56, R$ 1.234,56",
        "id_simple": "ABC123, 101943",
        "uf": "PR, SP, RJ",
        "cep": "12345-678, 12345678",
        "enum": "one of the provided options",
        "text": "any text",
        "text_multiline": "multi-line text",
    }
    return examples.get(field_type.lower(), "any text")


def build_prompt(
    field_name: str,
    field_type: str,
    context_text: str,
    *,
    enum_options: Optional[list[str]] = None,
    regex_hint: Optional[str] = None,
) -> str:
    """Build prompt for LLM extraction.

    Args:
        field_name: Name of the field.
        field_type: Type of the field (date, money, etc.).
        context_text: Context snippet (candidate + neighbors).
        enum_options: Optional enum options (for enum type).
        regex_hint: Optional regex pattern hint.

    Returns:
        Formatted prompt string.
    """
    type_examples = _get_type_examples(field_type)

    # Build type hint
    type_hint = field_type.upper()
    if field_type == "enum" and enum_options:
        type_hint = f"ENUM[{', '.join(enum_options[:5])}]"  # Limit to 5 options

    prompt = f"""You receive a small text snippet extracted from a PDF. Extract ONLY the value for the field below.

- Field: {field_name}
- Type: {type_hint}
- Acceptable examples: {type_examples}"""

    if regex_hint:
        prompt += f"\n- Pattern hint: {regex_hint}"

    if field_type == "enum" and enum_options:
        prompt += f"\n- Valid options: {', '.join(enum_options)}"

    prompt += f"""

CONTEXT (may include label, value, neighbors):

```
{context_text}
```

Return ONLY a JSON object:
{{"value": "<extracted-or-empty>"}}

No commentary. If the value is not found, return {{"value": ""}}.
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

