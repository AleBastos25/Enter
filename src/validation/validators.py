"""Soft validation functions for preliminary type checking."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.models import SchemaField

# Simple regex patterns for soft validation
DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
MONEY_RE = re.compile(r"\b(?:R\$)?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b")
ID_SIMPLE_RE = re.compile(r"^[A-Za-z0-9\-\.]{3,}$")


def validate_soft(field: "SchemaField", raw: str) -> bool:
    """Soft validation: checks if raw text appears to match the field type.

    This is a preliminary check during matching; full normalization/validation
    happens later in the extraction step.

    Args:
        field: SchemaField with type information.
        raw: Raw text string to validate.

    Returns:
        True if raw text appears to match the field type, False otherwise.
    """
    field_type = (field.type or "text").lower()
    text = raw.strip()

    if field_type == "date":
        return bool(DATE_RE.search(text))
    if field_type == "money":
        return bool(MONEY_RE.search(text))
    if field_type == "id_simple":
        return bool(ID_SIMPLE_RE.search(text))
    # text: always ok
    return True

