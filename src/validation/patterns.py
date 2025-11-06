"""Generic pattern detection and normalization (v2).

Pattern-based approach without hardcoding specific types.
Uses shape, structure, and context rather than type-specific rules.
"""

from __future__ import annotations

import re
from typing import Literal, Optional, Tuple

PatternType = Literal[
    "digits_only",
    "digits_with_separators",
    "isolated_letters",
    "money_like",
    "date_like",
    "alphanumeric",
    "text",
]


def detect_pattern(text: str) -> PatternType:
    """Detect generic pattern in text without knowing specific type.

    Args:
        text: Text to analyze.

    Returns:
        PatternType detected.
    """
    if not text or not text.strip():
        return "text"

    text_clean = text.strip()

    # Money-like: contains currency symbols, digits with separators
    if re.search(r"[R$€$]|[\d.,]+(?:[.,]\d{2})", text_clean):
        # Check if it looks like money format
        if re.search(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+[.,]\d{2}", text_clean):
            return "money_like"

    # Date-like: contains date separators with digits
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}", text_clean):
        return "date_like"

    # Digits only: pure digits (no separators)
    if re.match(r"^\d+$", text_clean):
        return "digits_only"

    # Digits with separators: digits with dots, dashes, slashes, spaces
    if re.search(r"\d", text_clean) and re.search(r"[.\-/\s]", text_clean):
        # Check if mostly digits with separators
        digits = len(re.findall(r"\d", text_clean))
        total_chars = len(re.sub(r"\s", "", text_clean))
        if digits >= total_chars * 0.7:  # At least 70% digits
            return "digits_with_separators"

    # Isolated letters: 2-4 uppercase letters as isolated tokens
    isolated_letters_match = re.search(r"\b([A-Z]{2,4})\b", text_clean)
    if isolated_letters_match and len(text_clean.strip()) <= 6:
        # Check if it's mostly isolated letters
        letters = len(re.findall(r"[A-Z]", text_clean))
        total = len(text_clean.replace(" ", ""))
        if letters >= total * 0.8:  # At least 80% letters
            return "isolated_letters"

    # Alphanumeric: mix of letters and digits
    if re.search(r"[A-Za-z]", text_clean) and re.search(r"\d", text_clean):
        return "alphanumeric"

    # Default: text
    return "text"


def is_isolated_token(text: str, token: str, min_token_len: int = 2) -> bool:
    """Check if token is isolated (not substring of larger word).

    Generic function that works for any token, not just specific types.

    Args:
        text: Text to search in.
        token: Token to check isolation for.
        min_token_len: Minimum token length to consider (default 2).

    Returns:
        True if token is isolated, False if it's part of a larger word.
    """
    if not token or len(token) < min_token_len:
        return False

    token_upper = token.upper()
    text_upper = text.upper()

    # Find all words in text
    words = re.findall(r"\w+", text_upper)

    for word in words:
        # If word starts with token and is longer, token is not isolated
        if len(word) > len(token) and word.startswith(token_upper):
            # Check if it's a prefix match (not just coincidence)
            # Allow some tolerance for compound words
            if len(word) > len(token) + 1:  # At least 1 char longer
                return False

    # Also check if token appears as substring in middle of words
    # Look for pattern: <non-word-char><token><more-chars>
    pattern = re.compile(rf"\W{re.escape(token_upper)}\w+", re.IGNORECASE)
    if pattern.search(text_upper):
        return False

    # Token appears isolated
    return True


def normalize_by_pattern(text: str, pattern: PatternType) -> Tuple[str, str]:
    """Normalize text based on detected pattern, not specific type.

    Returns both normalized and original text.
    Normalization removes formatting but preserves structure when needed.

    Args:
        text: Raw text to normalize.
        pattern: PatternType detected.

    Returns:
        Tuple of (normalized_text, original_text).
    """
    original_text = text.strip()

    if pattern == "digits_only":
        # Already digits only, return as is
        return (original_text, original_text)

    if pattern == "digits_with_separators":
        # Remove all non-digit characters
        normalized = re.sub(r"[^\d]", "", original_text)
        return (normalized, original_text)

    if pattern == "isolated_letters":
        # Extract isolated letters (first match)
        match = re.search(r"\b([A-Z]{2,4})\b", original_text.upper())
        if match:
            return (match.group(1), original_text)
        return ("", original_text)

    if pattern == "money_like":
        # Normalize money to decimal format
        # Use existing normalize_money logic (import to avoid circular dependency)
        from .validators import normalize_money

        normalized = normalize_money(original_text)
        if normalized:
            return (normalized, original_text)
        return (original_text, original_text)

    if pattern == "date_like":
        # Normalize date to ISO format
        from .validators import normalize_date

        normalized = normalize_date(original_text)
        if normalized:
            return (normalized, original_text)
        return (original_text, original_text)

    if pattern == "alphanumeric":
        # Keep as is, but remove extra whitespace
        normalized = re.sub(r"\s+", " ", original_text).strip()
        return (normalized, original_text)

    # text: no normalization
    return (original_text, original_text)


def type_gate_generic(
    candidate_text: str, field_type: str, shape_hint: Optional[str] = None
) -> bool:
    """Generic type gate using patterns and shape, not hardcoded rules.

    Args:
        candidate_text: Text candidate to validate.
        field_type: Field type hint (used for pattern detection, not hardcoded rules).
        shape_hint: Optional expected shape hint.

    Returns:
        True if candidate appears compatible with field type using generic patterns.
    """
    if not candidate_text or not candidate_text.strip():
        return False

    # Detect pattern in candidate
    pattern = detect_pattern(candidate_text)

    # For fields that expect digits (cpf, cnpj, cep, phone, id_simple, etc.)
    if field_type.lower() in ("cpf", "cnpj", "cep", "phone", "id_simple", "inscricao"):
        # Accept digits_only or digits_with_separators
        if pattern in ("digits_only", "digits_with_separators"):
            return True
        # Also accept money_like if it's mostly digits (could be formatted CPF/CNPJ)
        if pattern == "money_like":
            # Check if it's mostly digits (at least 70% digits)
            digits = len([c for c in candidate_text if c.isdigit()])
            total = len(candidate_text.replace(" ", ""))
            if total > 0 and digits >= total * 0.7:
                return True
        return False

    # For fields that expect money
    if field_type.lower() == "money":
        return pattern == "money_like"

    # For fields that expect date
    if field_type.lower() == "date":
        return pattern == "date_like"

    # For fields that expect isolated letters (uf, code, etc.)
    if field_type.lower() in ("uf", "code", "sigla"):
        # Check if pattern is isolated_letters AND token is actually isolated
        if pattern == "isolated_letters":
            # Extract token and check isolation
            match = re.search(r"\b([A-Z]{2,4})\b", candidate_text.upper())
            if match:
                token = match.group(1)
                return is_isolated_token(candidate_text, token)
        return False

    # For enum fields, check if text matches enum options (case-insensitive, accent-insensitive)
    if field_type.lower() == "enum":
        # Basic check: if text is too long or contains patterns that don't match enum values,
        # reject early (e.g., dates, money)
        if len(candidate_text.strip()) > 50:  # Enum values are usually short
            return False
        # Reject if looks like date
        if detect_pattern(candidate_text) == "date_like":
            return False
        # Reject if looks like money
        if detect_pattern(candidate_text) == "money_like":
            return False
        # Otherwise, accept (detailed validation happens in validators)
        return True

    # For text fields, accept any pattern
    if field_type.lower() == "text":
        return True

    # Default: accept if pattern detected
    return pattern != "text" or len(candidate_text.strip()) > 0

