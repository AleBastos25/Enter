"""Table extraction: find cells by label patterns."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, Optional, Pattern, Union

from ..core.models import TableCell, TableRow, TableStructure


def _normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove accents."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower()


def _matches_pattern(text: str, pattern: Union[str, Pattern[str]]) -> bool:
    """Check if text matches pattern (case-insensitive, accent-insensitive)."""
    text_norm = _normalize_text(text)
    if isinstance(pattern, str):
        pattern_norm = _normalize_text(pattern)
        return pattern_norm in text_norm
    else:
        # Regex pattern
        return bool(pattern.search(text_norm))


def _match_header_by_token_overlap(header_text: str, field_name: str, field_synonyms: list[str]) -> float:
    """Match header text to field using token overlap (case/accent-insensitive).
    
    Returns similarity score (0.0-1.0) based on token overlap.
    """
    import unicodedata
    import re
    
    def normalize_token(t: str) -> str:
        """Normalize token: lowercase, remove accents."""
        t = unicodedata.normalize("NFD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        return t.lower()
    
    # Normalize header and extract tokens
    header_tokens = set(normalize_token(t) for t in re.findall(r'\b\w+\b', header_text.lower()))
    
    # Normalize field name and synonyms
    field_tokens = set()
    field_tokens.add(normalize_token(field_name))
    for syn in field_synonyms:
        field_tokens.add(normalize_token(syn))
        # Also extract tokens from synonyms
        syn_tokens = re.findall(r'\b\w+\b', syn.lower())
        field_tokens.update(normalize_token(t) for t in syn_tokens)
    
    # Calculate overlap
    if not field_tokens:
        return 0.0
    
    overlap = len(header_tokens & field_tokens)
    return overlap / max(len(field_tokens), 1)


def find_cell_by_label(
    tables: list[TableStructure],
    label_patterns: list[Union[str, Pattern[str]]],
    *,
    search_in: Literal["any", "header", "first_col"] = "any",
    return_type: Literal["row", "cell"] = "cell",
    field_name: Optional[str] = None,
    field_synonyms: Optional[list[str]] = None,
) -> Optional[Union[TableCell, TableRow]]:
    """Find cell/row by matching label patterns with header-aware matching.

    Args:
        tables: List of TableStructure objects.
        label_patterns: List of strings or regex patterns to match.
        search_in: Where to search:
            - "any": any cell in the table
            - "header": only header cells (with header-aware matching)
            - "first_col": only first column cells
        return_type: What to return:
            - "cell": the matching cell (or value cell for KV)
            - "row": the row containing the match
        field_name: Optional field name for header-aware matching.
        field_synonyms: Optional field synonyms for header-aware matching.

    Returns:
        TableCell or TableRow if found, None otherwise.
    """
    for table in tables:
        if table.type == "kv":
            # KV-list: search in col 0 (label), return col 1 (value) from same row
            for row in table.rows:
                # Get label cell (col 0)
                label_cell = next((c for c in table.cells if c.row_id == row.id and c.col_id == 0), None)
                if not label_cell:
                    continue

                # Check if label matches
                for pattern in label_patterns:
                    if _matches_pattern(label_cell.text, pattern):
                        # Return value cell (col 1) from same row
                        value_cell = next((c for c in table.cells if c.row_id == row.id and c.col_id == 1), None)
                        if value_cell:
                            return value_cell if return_type == "cell" else row
                        break

        elif table.type == "grid":
            # Grid table: search based on search_in parameter
            if search_in == "header":
                # Search in header row with header-aware matching
                header_row = next((r for r in table.rows if any(c.header for c in table.cells if c.row_id == r.id)), None)
                if header_row:
                    header_cells = [c for c in table.cells if c.row_id == header_row.id]
                    
                    # First, try pattern matching (existing logic)
                    best_match = None
                    best_score = 0.0
                    
                    for header_cell in header_cells:
                        # Pattern matching
                        for pattern in label_patterns:
                            if _matches_pattern(header_cell.text, pattern):
                                # Find next non-header row, same column
                                next_row = next((r for r in table.rows if r.id > header_row.id), None)
                                if next_row:
                                    value_cell = next(
                                        (c for c in table.cells if c.row_id == next_row.id and c.col_id == header_cell.col_id),
                                        None,
                                    )
                                    if value_cell:
                                        return value_cell if return_type == "cell" else next_row
                                break
                        
                        # Header-aware matching: token overlap + embedding (if field_name provided)
                        if field_name and field_synonyms:
                            overlap_score = _match_header_by_token_overlap(
                                header_cell.text, field_name, field_synonyms
                            )
                            if overlap_score > best_score and overlap_score >= 0.3:  # Threshold for token overlap
                                best_score = overlap_score
                                best_match = header_cell
                    
                    # If we found a good header match, return the value from that column
                    if best_match:
                        next_row = next((r for r in table.rows if r.id > header_row.id), None)
                        if next_row:
                            value_cell = next(
                                (c for c in table.cells if c.row_id == next_row.id and c.col_id == best_match.col_id),
                                None,
                            )
                            if value_cell:
                                return value_cell if return_type == "cell" else next_row

            elif search_in == "first_col":
                # Search in first column, return same row, next column
                for row in table.rows:
                    first_cell = next((c for c in table.cells if c.row_id == row.id and c.col_id == 0), None)
                    if not first_cell:
                        continue

                    for pattern in label_patterns:
                        if _matches_pattern(first_cell.text, pattern):
                            # Return next column in same row
                            value_cell = next((c for c in table.cells if c.row_id == row.id and c.col_id == 1), None)
                            if value_cell:
                                return value_cell if return_type == "cell" else row
                            break

            else:  # search_in == "any"
                # Search in any cell, return same row
                for cell in table.cells:
                    if cell.header and search_in != "any":
                        continue

                    for pattern in label_patterns:
                        if _matches_pattern(cell.text, pattern):
                            # Return the row
                            row = next((r for r in table.rows if r.id == cell.row_id), None)
                            if row:
                                return cell if return_type == "cell" else row
                            break

    return None


def find_table_for_block(block_id: int, tables: list[TableStructure]) -> Optional[TableStructure]:
    """Find table structure that contains a given block ID.

    Args:
        block_id: Block ID to search for.
        tables: List of TableStructure objects.

    Returns:
        TableStructure if block is in any cell, None otherwise.
    """
    for table in tables:
        for cell in table.cells:
            if block_id in cell.block_ids:
                return table
    return None

