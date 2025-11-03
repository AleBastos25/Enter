"""Soft and hard validation functions for type checking and normalization."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from ..core.models import SchemaField

# Simple regex patterns for soft validation
DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
MONEY_RE = re.compile(r"\b(?:R\$)?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b")
ID_SIMPLE_RE = re.compile(r"^[A-Za-z0-9\-\.]{3,}$")

# Hard validation regexes (more strict, for normalization)
DATE_HARD_RE = re.compile(
    r"\b(?:([0-3]?\d)[/.-]([01]?\d)[/.-]((?:\d{2})?\d{2})|(\d{4})-([01]\d)-([0-3]\d))\b"
)
MONEY_HARD_RE = re.compile(
    r"""
    (?:
      R\$\s*                             # optional currency
    )?
    (?:
      \d{1,3}(?:[.,]\d{3})*              # thousand-separated integer
      |\d+                               # or plain integer
    )
    (?:[.,]\d{2})?                       # optional cents
""",
    re.VERBOSE,
)
ID_SIMPLE_HARD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-/]{2,}")  # 3+ chars
UF_RE = re.compile(r"\b[A-Z]{2}\b")  # Two uppercase letters (UF/state code)
CEP_RE = re.compile(r"\b(\d{5})-?(\d{3})\b")  # CEP: NNNNN-NNN or NNNNNNNN
INT_RE = re.compile(r"\b\d+\b")  # Integer
FLOAT_RE = re.compile(r"\b\d+[.,]\d+\b")  # Float with decimal separator
PERCENT_RE = re.compile(r"\b(\d+[,.]?\d*)\s*%\b")  # Percent: "12,5%" or "12.5%"


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
    if field_type == "uf":
        return bool(UF_RE.search(text))
    # text: always ok
    return True


# ============================================================================
# Hard validation & normalization
# ============================================================================


def normalize_date(text: str) -> Optional[str]:
    """Normalize DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY or YYYY-MM-DD to ISO YYYY-MM-DD.

    Returns None if not parseable.
    """
    m = DATE_HARD_RE.search(text)
    if not m:
        return None

    if m.group(4):  # ISO style captured
        y, mo, d = m.group(4), m.group(5), m.group(6)
    else:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        # expand 2-digit years to 20xx heuristically if needed
        if len(y) == 2:
            y = "20" + y

    # zero-pad
    try:
        d = f"{int(d):02d}"
        mo = f"{int(mo):02d}"
        y = f"{int(y):04d}"
        return f"{y}-{mo}-{d}"
    except Exception:
        return None


def normalize_money(text: str) -> Optional[str]:
    """Normalize money to a dot-decimal string (e.g., 'R$ 1.234,56' -> '1234.56').

    Returns None if no monetary pattern.
    """
    m = MONEY_HARD_RE.search(text)
    if not m:
        return None

    s = m.group(0)
    s = s.replace("R$", "").strip()
    # choose decimal separator: if comma present at last 3 chars -> decimal
    s = s.replace(" ", "")
    if "," in s and "." in s:
        # assume thousands with '.', decimal with ','
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    # keep only digits and one dot
    parts = re.findall(r"\d+|\.", s)
    normalized = "".join(parts)
    # collapse multiple dots (keep last)
    if normalized.count(".") > 1:
        head, _, tail = normalized.rpartition(".")
        normalized = head.replace(".", "") + "." + tail
    return normalized if re.match(r"^\d+(\.\d{1,2})?$", normalized) else None


def normalize_id_simple(text: str) -> Optional[str]:
    """Extract an id-like token (alnum with .-/, length>=3). Picks the first match."""
    m = ID_SIMPLE_HARD_RE.search(text.strip())
    return m.group(0) if m else None


def normalize_uf(text: str) -> Optional[str]:
    """Extract a UF (state code) - exactly 2 uppercase letters.

    Returns None if not found.
    """
    m = UF_RE.search(text.strip().upper())
    if m:
        val = m.group(0)
        # Ensure it's exactly 2 uppercase letters
        if len(val) == 2 and val.isalpha():
            return val
    return None


def validate_text(text: str) -> Tuple[bool, Optional[str]]:
    """Validate text type: take first non-empty line."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return (True, line)
    return (False, None)


def validate_id_simple(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize id_simple."""
    val = normalize_id_simple(text)
    return (val is not None, val)


def validate_date(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize date."""
    val = normalize_date(text)
    return (val is not None, val)


def validate_money(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize money."""
    val = normalize_money(text)
    return (val is not None, val)


def validate_uf(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize UF (state code)."""
    val = normalize_uf(text)
    return (val is not None, val)


def normalize_cep(text: str) -> Optional[str]:
    """Normalize CEP to 8 digits (NNNNNNNN).

    Accepts NNNNN-NNN or NNNNNNNN format.
    """
    m = CEP_RE.search(text)
    if m:
        part1, part2 = m.groups()
        return part1 + part2
    return None


def validate_cep(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize CEP."""
    val = normalize_cep(text)
    return (val is not None, val)


def normalize_int(text: str) -> Optional[str]:
    """Extract integer from text."""
    m = INT_RE.search(text)
    return m.group(0) if m else None


def validate_int(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize integer."""
    val = normalize_int(text)
    return (val is not None, val)


def normalize_float(text: str) -> Optional[str]:
    """Extract float from text, converting comma to dot."""
    m = FLOAT_RE.search(text)
    if not m:
        return None
    val = m.group(0)
    # Convert comma to dot for decimal
    val = val.replace(",", ".")
    # Ensure valid float format
    try:
        float(val)
        return val
    except ValueError:
        return None


def validate_float(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize float."""
    val = normalize_float(text)
    return (val is not None, val)


def normalize_percent(text: str) -> Optional[str]:
    """Extract percent value, converting comma to dot."""
    m = PERCENT_RE.search(text)
    if not m:
        return None
    val = m.group(1)
    # Convert comma to dot
    val = val.replace(",", ".")
    try:
        float(val)
        return val
    except ValueError:
        return None


def validate_percent(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize percent."""
    val = normalize_percent(text)
    return (val is not None, val)


# Registry of validators by type
VALIDATOR_REGISTRY: dict[str, callable] = {
    "text": validate_text,
    "id_simple": validate_id_simple,
    "date": validate_date,
    "money": validate_money,
    "uf": validate_uf,
    "cep": validate_cep,
    "int": validate_int,
    "float": validate_float,
    "percent": validate_percent,
}


def validate_and_normalize(field_or_type: "SchemaField | str", raw_text: str) -> Tuple[bool, Optional[str]]:
    """HARD validator: returns (ok, normalized_value). If not ok, normalized_value is None.

    Can accept either a SchemaField or a type string directly.

    Uses the validator registry to find the appropriate validator by field type.
    Falls back to text validator if type is unknown.
    """
    if isinstance(field_or_type, str):
        ftype = field_or_type.lower()
    else:
        ftype = (field_or_type.type or "text").lower()

    validator = VALIDATOR_REGISTRY.get(ftype, validate_text)
    return validator(raw_text.strip())

