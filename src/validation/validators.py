"""Soft and hard validation functions for type checking and normalization."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from ..core.models import SchemaField

from .shape import normalize_for_validation

# Simple regex patterns for soft validation
DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
# Improved money regex: accepts 1.234.567,89 and 123,45 formats
MONEY_RE = re.compile(r"\b(?:R\$)?\s*(?:\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+[.,]\d{2})\b")
ID_SIMPLE_RE = re.compile(r"(?=[A-Za-z0-9.\-/]*\d)[A-Za-z0-9.\-/]{3,}")  # Must have at least 1 digit

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
      \d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})  # thousand-separated with cents: 1.234.567,89
      |\d{1,3}(?:[.,]\d{3})*[.,]\d{2}     # or: 123,45 or 1.234,56
      |\d+[.,]\d{2}                       # or: 123,45 (simple format)
    )
""",
    re.VERBOSE,
)
ID_SIMPLE_HARD_RE = re.compile(r"(?=[A-Za-z0-9.\-/]*\d)[A-Za-z0-9.\-/]{3,}")  # Must have at least 1 digit, 3+ chars
# UF: exactly 2 uppercase letters as isolated token (word boundary required)
# Must be word boundary before and after (not part of a longer word)
UF_RE = re.compile(r"(?<!\w)[A-Z]{2}(?!\w)")  # Two uppercase letters, isolated word
CEP_RE = re.compile(r"\b(\d{5})-?(\d{3})\b")  # CEP: NNNNN-NNN or NNNNNNNN
INT_RE = re.compile(r"\b\d+\b")  # Integer
FLOAT_RE = re.compile(r"\b\d+[.,]\d+\b")  # Float with decimal separator
PERCENT_RE = re.compile(r"\b(\d+[,.]?\d*)\s*%\b")  # Percent: "12,5%" or "12.5%"

# Brazilian-specific patterns
CPF_RE = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")  # CPF: 000.000.000-00 or 00000000000
CNPJ_RE = re.compile(r"\b(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})\b")  # CNPJ: 00.000.000/0000-00
EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
)  # Email (basic, not exhaustive)
PHONE_BR_RE = re.compile(
    r"\b(?:\+?55\s*)?(?:\(?(\d{2})\)?\s*)?(\d{4,5})-?(\d{4})\b"
)  # Phone: +55 (11) 91234-5678 or 11912345678
PLACA_MERCOSUL_RE = re.compile(
    r"\b([A-Z]{3})(\d)([A-Z])(\d{2})\b"
)  # Placa Mercosul: AAA1A23
PLACA_ANTIGA_RE = re.compile(r"\b([A-Z]{3})-?(\d{4})\b")  # Placa antiga: AAA-1234
CNH_RE = re.compile(r"\b(\d{11})\b")  # CNH: 11 digits
PIS_PASEP_RE = re.compile(r"\b(\d{3})\.?(\d{5})\.?(\d{2})-?(\d{1})\b")  # PIS/PASEP: 000.00000.00-0
CHAVE_NF_RE = re.compile(r"\b(\d{44})\b")  # Chave NF: 44 digits
RG_RE = re.compile(
    r"\b(\d{1,2})\.?(\d{3})\.?(\d{3})-?(\d{1})\b"
)  # RG: various formats (light regex, no DV check)
ALPHANUM_CODE_RE = re.compile(r"(?=[A-Za-z0-9.\-/]*\d)[A-Za-z0-9.\-/]{3,}")  # Alphanumeric with at least 1 digit


def validate_soft(field: "SchemaField", raw: str) -> bool:
    """Soft validation: checks if raw text appears to match the field type.

    This is a preliminary check during matching; full normalization/validation
    happens later in the extraction step.

    Uses pre-normalization based on field type (v2).

    Args:
        field: SchemaField with type information.
        raw: Raw text string to validate.

    Returns:
        True if raw text appears to match the field type, False otherwise.
    """
    field_type = (field.type or "text").lower()
    
    # Pre-normalize based on type (v2)
    normalized_text, original_text = normalize_for_validation(raw, field_type)
    
    # For code/sigla/uf fields: check if pattern is isolated_letters (generic, no locale assumptions)
    if field_type in ("uf", "code", "sigla"):
        if not normalized_text:
            return False
        # Generic check: ensure it's isolated letters (2-4 uppercase letters)
        # Use pattern-based check instead of hardcoded UF_RE
        from .patterns import detect_pattern, is_isolated_token
        pattern = detect_pattern(normalized_text)
        if pattern == "isolated_letters":
            # Extract token and check isolation
            match = re.search(r"\b([A-Z]{2,4})\b", normalized_text.upper())
            if match:
                token = match.group(1)
                return is_isolated_token(normalized_text, token)
        return False
    
    # Use normalized text for validation
    text = normalized_text if normalized_text else original_text

    if field_type == "date":
        return bool(DATE_RE.search(text))
    if field_type == "money":
        return bool(MONEY_RE.search(text))
    if field_type == "id_simple":
        return bool(ID_SIMPLE_RE.search(text))
    if field_type in ("cpf", "cnpj", "cep", "phone"):
        # After normalization, should be only digits
        return len(normalized_text) > 0 and normalized_text.isdigit()
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
    """Normalize money to a dot-decimal string (e.g., 'R$ 1.234,56' -> '1234.56', '123,45' -> '123.45').

    Handles formats:
    - 1.234.567,89 (thousands with dots, decimal with comma)
    - 123,45 (simple format with comma decimal)
    - 1234.56 (simple format with dot decimal)
    
    Returns None if no monetary pattern.
    """
    m = MONEY_HARD_RE.search(text)
    if not m:
        return None

    s = m.group(0)
    s = s.replace("R$", "").strip().replace(" ", "")
    
    # Handle different formats
    if "," in s and "." in s:
        # Format: 1.234.567,89 (thousands with dots, decimal with comma)
        # Count dots before last comma - if 2+ dots, they're thousand separators
        last_comma_idx = s.rfind(",")
        dots_before_comma = s[:last_comma_idx].count(".")
        
        if dots_before_comma >= 1:
            # Thousands format: 1.234.567,89 -> remove dots, replace comma with dot
            s = s.replace(".", "").replace(",", ".")
        else:
            # Ambiguous: assume dot is decimal, comma is thousand (rare but possible)
            s = s.replace(",", "").replace(".", ".")
    elif "," in s:
        # Format: 123,45 or 1.234,56 (simple with comma decimal)
        # Check if there are dots before comma (thousand separators)
        last_comma_idx = s.rfind(",")
        if "." in s[:last_comma_idx]:
            # Has dots before comma: 1.234,56 -> remove dots, replace comma with dot
            s = s.replace(".", "").replace(",", ".")
        else:
            # No dots: 123,45 -> replace comma with dot
            s = s.replace(",", ".")
    elif "." in s:
        # Format: 1234.56 (simple with dot decimal) - keep as is
        pass
    
    # Extract only digits and one dot
    parts = re.findall(r"\d+|\.", s)
    normalized = "".join(parts)
    
    # Collapse multiple dots (keep last)
    if normalized.count(".") > 1:
        head, _, tail = normalized.rpartition(".")
        normalized = head.replace(".", "") + "." + tail
    
    # Validate final format: digits with optional .XX (1-2 decimal places)
    if re.match(r"^\d+(\.\d{1,2})?$", normalized):
        return normalized
    
    return None


def normalize_id_simple(text: str) -> Optional[str]:
    """Extract an id-like token (alnum with .-/, length>=3, must have at least 1 digit). Picks the first match."""
    m = ID_SIMPLE_HARD_RE.search(text.strip())
    return m.group(0) if m else None


def normalize_uf(text: str, context_block: Optional[str] = None) -> Optional[str]:
    """Extract a UF (state code) - exactly 2 uppercase letters as isolated token.
    
    Gate of context: if the same block contains long words (e.g., "SUPLEMENTAR"),
    the candidate is invalid for UF field.

    Args:
        text: Text to extract UF from.
        context_block: Optional full block text for context validation.
        
    Returns:
        UF code (2 uppercase letters) or None if not found/invalid.
    """
    text_upper = text.strip().upper()
    m = UF_RE.search(text_upper)
    if not m:
        return None
    
    val = m.group(0)
    # Ensure it's exactly 2 uppercase letters
    if len(val) != 2 or not val.isalpha():
        return None
    
    # Gate of context: if block contains long words starting with the UF candidate, reject
    if context_block:
        context_upper = context_block.upper()
        # Look for words that start with the UF code but are longer (e.g., "SUPLEMENTAR" if UF is "SU")
        # This is a heuristic: if we find a word that starts with the UF and is 4+ chars, it's likely not a UF
        pattern = re.compile(rf"\b{re.escape(val)}\w{{2,}}", re.IGNORECASE)
        if pattern.search(context_upper):
            # Found a word starting with UF but longer - likely not a UF
            return None
    
    return val


def validate_text(text: str) -> Tuple[bool, Optional[str]]:
    """Validate text type: take first non-empty line."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return (True, line)
    return (False, None)


def normalize_city(text: str) -> Optional[str]:
    """Extract city name: tokens with letters (accents ok), size >= 2; reject tokens with only digits.
    
    City names should contain at least one letter (may have accents).
    Pure numeric tokens are rejected (likely CEP or other numeric data).
    
    Args:
        text: Text to extract city name from.
        
    Returns:
        City name (normalized) or None if not valid.
    """
    text_clean = text.strip()
    if not text_clean or len(text_clean) < 2:
        return None
    
    # Reject pure numbers (likely CEP or numeric data)
    if re.match(r"^\d+$", text_clean):
        return None
    
    # Must contain at least one letter (with or without accents)
    # Check for letters (including accented characters)
    if not re.search(r"[A-Za-zÀ-ÿ]", text_clean):
        return None
    
    # Return normalized (trim, but preserve accents)
    return text_clean


def validate_city(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize city name.
    
    City names must:
    - Have at least 2 characters
    - Contain at least one letter (with or without accents)
    - Not be pure numbers
    """
    val = normalize_city(text)
    return (val is not None, val)


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


def validate_uf(text: str, context_block: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Validate and normalize UF (state code) with context gate.
    
    Args:
        text: Text to validate.
        context_block: Optional full block text for context validation.
    """
    val = normalize_uf(text, context_block)
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


def validate_text_multiline(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize text_multiline: join up to 2-3 lines if needed.

    Returns first non-empty line or joined lines (up to 3).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return (False, None)

    # Join up to 3 lines
    merged = " ".join(lines[:3])
    return (True, merged)


def normalize_enum(text: str, enum_options: list[str] | None) -> Optional[str]:
    """Normalize enum value: case-insensitive, accent-insensitive matching.

    Improved: Better handling of multi-word enum values and partial matches.
    
    Args:
        text: Text to normalize.
        enum_options: List of valid enum options.
        
    Returns:
        Normalized enum value (exact match from options) or None.
    """
    if not enum_options:
        return None

    import unicodedata

    text_clean = text.strip()
    text_norm = unicodedata.normalize("NFD", text_clean)
    text_norm = "".join(c for c in text_norm if unicodedata.category(c) != "Mn")
    text_norm = text_norm.upper()

    # Try to match against options (prioritize exact matches, then substring matches)
    # First: try exact match (case-insensitive, accent-insensitive)
    for option in enum_options:
        option_norm = unicodedata.normalize("NFD", option)
        option_norm = "".join(c for c in option_norm if unicodedata.category(c) != "Mn")
        option_norm = option_norm.upper()
        
        # Exact match (whole text matches option)
        if text_norm == option_norm:
            return option  # Return canonical form
    
    # Second: try substring match (option is in text, or text is in option)
    # This handles cases where enum value appears in larger text
    for option in enum_options:
        option_norm = unicodedata.normalize("NFD", option)
        option_norm = "".join(c for c in option_norm if unicodedata.category(c) != "Mn")
        option_norm = option_norm.upper()

        # Check if option is contained in text (for multi-word enum values)
        if option_norm in text_norm:
            # Extract the matching part (for multi-word enums like "CONSELHO SECCIONAL")
            # Try to find word boundaries
            import re
            # Pattern: word boundary + option + word boundary (or end/start of text)
            pattern = re.compile(r'\b' + re.escape(option_norm) + r'\b', re.IGNORECASE)
            if pattern.search(text_clean):
                return option
            # Fallback: if option is a substring, return it
            return option
        
        # Check if text is contained in option (for partial matches)
        if text_norm in option_norm and len(text_norm) >= 3:  # At least 3 chars for partial match
            # Only accept if text is substantial (not just 1-2 chars)
            return option
    
    # Third: try token-by-token matching (for single-word enum values in multi-word text)
    tokens = text_clean.split()
    for token in tokens:
        if len(token) < 2:  # Skip very short tokens
            continue
        token_norm = unicodedata.normalize("NFD", token.upper())
        token_norm = "".join(c for c in token_norm if unicodedata.category(c) != "Mn")
        
        for option in enum_options:
            option_norm = unicodedata.normalize("NFD", option)
            option_norm = "".join(c for c in option_norm if unicodedata.category(c) != "Mn")
            option_norm = option_norm.upper()
            
            if token_norm == option_norm:
                return option  # Return canonical form
    return None


def validate_enum_with_options(text: str, enum_options: list[str] | None) -> Tuple[bool, Optional[str]]:
    """Validate and normalize enum with options provided."""
    val = normalize_enum(text, enum_options)
    return (val is not None, val)


def _validate_cpf_dv(cpf_digits: str) -> bool:
    """Validate CPF check digits."""
    if len(cpf_digits) != 11:
        return False
    if cpf_digits == cpf_digits[0] * 11:  # All same digit
        return False

    # Calculate first check digit
    sum1 = sum(int(cpf_digits[i]) * (10 - i) for i in range(9))
    digit1 = 11 - (sum1 % 11)
    if digit1 >= 10:
        digit1 = 0

    if int(cpf_digits[9]) != digit1:
        return False

    # Calculate second check digit
    sum2 = sum(int(cpf_digits[i]) * (11 - i) for i in range(10))
    digit2 = 11 - (sum2 % 11)
    if digit2 >= 10:
        digit2 = 0

    return int(cpf_digits[10]) == digit2


def normalize_cpf(text: str) -> Optional[str]:
    """Extract and normalize CPF to ###.###.###-## format.

    Validates check digits.
    """
    m = CPF_RE.search(text)
    if not m:
        return None

    digits = "".join(m.groups())
    if len(digits) != 11:
        return None

    # Validate check digits
    if not _validate_cpf_dv(digits):
        return None

    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def validate_cpf(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize CPF."""
    val = normalize_cpf(text)
    return (val is not None, val)


def _validate_cnpj_dv(cnpj_digits: str) -> bool:
    """Validate CNPJ check digits."""
    if len(cnpj_digits) != 14:
        return False
    if cnpj_digits == cnpj_digits[0] * 14:  # All same digit
        return False

    # Calculate first check digit
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum1 = sum(int(cnpj_digits[i]) * weights1[i] for i in range(12))
    digit1 = sum1 % 11
    digit1 = 0 if digit1 < 2 else 11 - digit1

    if int(cnpj_digits[12]) != digit1:
        return False

    # Calculate second check digit
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum2 = sum(int(cnpj_digits[i]) * weights2[i] for i in range(13))
    digit2 = sum2 % 11
    digit2 = 0 if digit2 < 2 else 11 - digit2

    return int(cnpj_digits[13]) == digit2


def normalize_cnpj(text: str) -> Optional[str]:
    """Extract and normalize CNPJ to ##.###.###/####-## format.

    Validates check digits.
    """
    m = CNPJ_RE.search(text)
    if not m:
        return None

    digits = "".join(m.groups())
    if len(digits) != 14:
        return None

    # Validate check digits
    if not _validate_cnpj_dv(digits):
        return None

    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def validate_cnpj(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize CNPJ."""
    val = normalize_cnpj(text)
    return (val is not None, val)


def normalize_email(text: str) -> Optional[str]:
    """Extract and normalize email (lowercase, strip spaces)."""
    m = EMAIL_RE.search(text)
    if not m:
        return None

    email = m.group(0).lower().strip()
    # Remove any hidden spaces
    email = email.replace(" ", "").replace("\u200b", "")
    return email if "@" in email and "." in email.split("@")[1] else None


def validate_email(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize email."""
    val = normalize_email(text)
    return (val is not None, val)


def normalize_phone_br(text: str) -> Optional[str]:
    """Extract and normalize Brazilian phone to E.164 format (+5511912345678)."""
    m = PHONE_BR_RE.search(text)
    if not m:
        return None

    ddd, part1, part2 = m.groups()
    if not ddd:
        ddd = "11"  # Default São Paulo if not provided (could be improved)

    # Normalize to E.164
    phone = f"+55{ddd}{part1}{part2}"
    # Validate length (should be 13-14 digits total: +55 + 2 DDD + 8-9 digits)
    if len(phone) < 13 or len(phone) > 14:
        return None

    return phone


def validate_phone_br(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize Brazilian phone."""
    val = normalize_phone_br(text)
    return (val is not None, val)


def normalize_placa_mercosul(text: str) -> Optional[str]:
    """Extract and normalize Mercosul plate (AAA1A23 format, uppercase, no hyphen)."""
    # Try Mercosul format first
    m = PLACA_MERCOSUL_RE.search(text.upper())
    if m:
        return "".join(m.groups())

    # Try old format
    m = PLACA_ANTIGA_RE.search(text.upper())
    if m:
        return "".join(m.groups())

    return None


def validate_placa_mercosul(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize Mercosul plate."""
    val = normalize_placa_mercosul(text)
    return (val is not None, val)


def normalize_cnh(text: str) -> Optional[str]:
    """Extract CNH (11 digits)."""
    m = CNH_RE.search(text)
    if not m:
        return None

    digits = m.group(1)
    if len(digits) != 11:
        return None

    # Simple validation: check if all same (invalid)
    if digits == digits[0] * 11:
        return None

    return digits


def validate_cnh(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize CNH."""
    val = normalize_cnh(text)
    return (val is not None, val)


def normalize_pis_pasep(text: str) -> Optional[str]:
    """Extract and normalize PIS/PASEP to 000.00000.00-0 format."""
    m = PIS_PASEP_RE.search(text)
    if not m:
        return None

    digits = "".join(m.groups())
    if len(digits) != 11:
        return None

    return f"{digits[:3]}.{digits[3:8]}.{digits[8:10]}-{digits[10]}"


def validate_pis_pasep(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize PIS/PASEP."""
    val = normalize_pis_pasep(text)
    return (val is not None, val)


def normalize_chave_nf(text: str) -> Optional[str]:
    """Extract Chave NF (44 digits)."""
    m = CHAVE_NF_RE.search(text)
    if not m:
        return None

    digits = m.group(1)
    if len(digits) != 44:
        return None

    return digits


def validate_chave_nf(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize Chave NF."""
    val = normalize_chave_nf(text)
    return (val is not None, val)


def normalize_rg(text: str) -> Optional[str]:
    """Extract RG (light validation, no DV check)."""
    m = RG_RE.search(text)
    if not m:
        return None

    # Join digits (format varies, return simplified)
    digits = "".join(m.groups())
    if len(digits) < 8 or len(digits) > 9:
        return None

    return digits


def validate_rg(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize RG (light, no DV check)."""
    val = normalize_rg(text)
    return (val is not None, val)


def normalize_alphanum_code(text: str) -> Optional[str]:
    """Extract alphanumeric code (at least 1 digit, 3+ chars)."""
    m = ALPHANUM_CODE_RE.search(text)
    return m.group(0) if m else None


def validate_alphanum_code(text: str) -> Tuple[bool, Optional[str]]:
    """Validate and normalize alphanumeric code."""
    val = normalize_alphanum_code(text)
    return (val is not None, val)


# Registry of validators by type
VALIDATOR_REGISTRY: dict[str, callable] = {
    "text": validate_text,
    "text_multiline": validate_text_multiline,
    "id_simple": validate_id_simple,
    "date": validate_date,
    "money": validate_money,
    "uf": validate_uf,
    "city": validate_city,  # New: city name validator
    "cep": validate_cep,
    "enum": validate_enum_with_options,  # Special: needs enum_options
    "int": validate_int,
    "float": validate_float,
    "percent": validate_percent,
    # Brazilian-specific validators
    "cpf": validate_cpf,
    "cnpj": validate_cnpj,
    "email": validate_email,
    "phone_br": validate_phone_br,
    "placa_mercosul": validate_placa_mercosul,
    "placa": validate_placa_mercosul,  # Alias
    "cnh": validate_cnh,
    "pis_pasep": validate_pis_pasep,
    "pis": validate_pis_pasep,  # Alias
    "chave_nf": validate_chave_nf,
    "rg": validate_rg,
    "alphanum_code": validate_alphanum_code,
}


def validate_and_normalize(
    field_or_type: "SchemaField | str",
    raw_text: str,
    *,
    enum_options: list[str] | None = None,
) -> Tuple[bool, Optional[str]]:
    """HARD validator: returns (ok, normalized_value). If not ok, normalized_value is None.

    Can accept either a SchemaField or a type string directly.

    Uses the validator registry to find the appropriate validator by field type.
    Falls back to text validator if type is unknown.

    Uses pre-normalization based on field type (v2).

    Args:
        field_or_type: SchemaField or type string.
        raw_text: Raw text to validate.
        enum_options: Optional enum options (used only for 'enum' type).

    Returns:
        Tuple of (ok, normalized_value). normalized_value is original_text for output,
        but validation uses normalized_text.
    """
    if isinstance(field_or_type, str):
        ftype = field_or_type.lower()
    else:
        ftype = (field_or_type.type or "text").lower()
        # Extract enum_options from SchemaField meta if available
        if hasattr(field_or_type, "meta") and enum_options is None:
            enum_options = field_or_type.meta.get("enum_options")

    # Pre-normalize using generic patterns (v2)
    normalized_text, original_text = normalize_for_validation(raw_text, ftype)
    
    # Get validator
    validator = VALIDATOR_REGISTRY.get(ftype, validate_text)

    # For types that expect digits (cpf, cnpj, cep, phone, id_simple, etc.)
    # Use pattern-based normalization: normalized_text is digits only
    if ftype in ("cpf", "cnpj", "cep", "phone", "id_simple", "inscricao"):
        # Normalized should be digits only
        if not normalized_text or not normalized_text.isdigit():
            return (False, None)
        # Use original_text for validator (it has regex patterns that expect formatting)
        ok, val = validator(original_text)
        if ok:
            # Return normalized (digits only) for output
            return (True, normalized_text)
        return (False, None)
    
    # For money/date, normalization already returns normalized format
    if ftype in ("money", "date"):
        if normalized_text != original_text:
            # Normalization succeeded, use normalized for validation
            ok, val = validator(normalized_text)
            if ok:
                return (True, val)  # Return normalized value
        # Fallback to original validation
        return validator(original_text)
    
    # For UF/code/sigla, use normalized (isolated letters) for validation
    if ftype in ("uf", "code", "sigla"):
        if not normalized_text:
            return (False, None)
        return validator(normalized_text)
    
    # For enum, special handling
    if ftype == "enum":
        return validate_enum_with_options(original_text.strip(), enum_options)

    # For other types, use original text
    return validator(original_text.strip())

