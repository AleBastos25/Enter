"""Textual shape analysis and distance computation (v2).

Shape-based matching for OCR error correction and candidate filtering.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple


def to_shape(text: str) -> str:
    """Convert text to shape string (char classes with run compression).

    Maps chars to classes:
    - U: A-Z (uppercase)
    - L: a-z (lowercase)
    - D: 0-9 (digits)
    - P: punctuation
    - S: space
    - O: other

    Compresses runs: "AAA-1234" -> "U3-P-D4"

    Args:
        text: Input text string.

    Returns:
        Shape string with compressed runs.
    """
    if not text:
        return ""

    shape_chars: list[str] = []
    for char in text:
        if char.isupper():
            shape_chars.append("U")
        elif char.islower():
            shape_chars.append("L")
        elif char.isdigit():
            shape_chars.append("D")
        elif char.isspace():
            shape_chars.append("S")
        elif char in ".,;:!?-_()[]{}\"'/\\":
            shape_chars.append("P")
        else:
            shape_chars.append("O")

    # Compress runs
    compressed: list[str] = []
    if not shape_chars:
        return ""

    current_char = shape_chars[0]
    current_count = 1

    for i in range(1, len(shape_chars)):
        if shape_chars[i] == current_char:
            current_count += 1
        else:
            # Output current run
            if current_count == 1:
                compressed.append(current_char)
            else:
                compressed.append(f"{current_char}{current_count}")
            current_char = shape_chars[i]
            current_count = 1

    # Output last run
    if current_count == 1:
        compressed.append(current_char)
    else:
        compressed.append(f"{current_char}{current_count}")

    return "".join(compressed)


def damerau_levenshtein_shape(shape1: str, shape2: str) -> int:
    """Compute Damerau-Levenshtein distance between shape strings.

    This is a simplified version that works on shape strings (not full
    Damerau-Levenshtein which handles transpositions). For shape strings,
    we use regular Levenshtein since transpositions are less meaningful.

    Args:
        shape1: First shape string.
        shape2: Second shape string.

    Returns:
        Edit distance (insertions, deletions, substitutions).
    """
    if not shape1:
        return len(shape2)
    if not shape2:
        return len(shape1)

    # Use Levenshtein distance (simplified for shape strings)
    # Create matrix
    m, n = len(shape1), len(shape2)
    dp: list[list[int]] = [[0] * (n + 1) for _ in range(m + 1)]

    # Initialize
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    # Fill matrix
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if shape1[i - 1] == shape2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(
                    dp[i - 1][j] + 1,  # deletion
                    dp[i][j - 1] + 1,  # insertion
                    dp[i - 1][j - 1] + 1,  # substitution
                )

    return dp[m][n]


def normalize_for_validation(text: str, field_type: str) -> Tuple[str, str]:
    """Normalize text before validation using generic patterns (v2).

    Uses pattern detection instead of hardcoded type-specific rules.
    This ensures the system is generic and works for any type.

    Args:
        text: Raw text to normalize.
        field_type: Field type hint (used for pattern detection, not hardcoded rules).

    Returns:
        Tuple of (normalized_text, original_text).
        original_text is kept for output, normalized_text is for validation.
    """
    from .patterns import detect_pattern, normalize_by_pattern, is_isolated_token

    original_text = text.strip()
    if not original_text:
        return ("", original_text)

    # Detect pattern generically (without hardcoding types)
    pattern = detect_pattern(original_text)

    # For types expecting isolated letters (uf, code, sigla), use isolation gate
    field_type_lower = field_type.lower()
    if field_type_lower in ("uf", "code", "sigla"):
        # Check if pattern is isolated_letters
        if pattern == "isolated_letters":
            # Extract token and verify isolation
            match = re.search(r"\b([A-Z]{2,4})\b", original_text.upper())
            if match:
                token = match.group(1)
                if is_isolated_token(original_text, token):
                    return (token, original_text)
            # Not isolated, reject
            return ("", original_text)

    # Use generic pattern-based normalization
    normalized, _ = normalize_by_pattern(original_text, pattern)
    return (normalized, original_text)

