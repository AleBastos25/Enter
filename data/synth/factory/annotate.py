"""Annotation module: extract ground truth from rendered PDFs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .primitives import RenderedElement


def extract_bboxes_from_pdf(pdf_path: Path) -> Dict[str, Tuple[float, float, float, float]]:
    """Extract bboxes from PDF by element IDs (if available).

    This is a placeholder - in practice, you'd:
    1. Parse the PDF structure
    2. Match element IDs to text blocks
    3. Extract normalized bboxes

    For now, returns empty dict.
    """
    # TODO: Implement actual bbox extraction
    # This would require parsing the PDF structure and matching IDs
    return {}


def build_ground_truth(
    elements: List[RenderedElement],
    pdf_path: Path,
    schema: Dict[str, str],
) -> Dict[str, Any]:
    """Build ground truth answers from rendered elements.

    Args:
        elements: List of rendered elements with field_name/field_label.
        pdf_path: Path to generated PDF.
        schema: Original schema dict.

    Returns:
        Dict with 'answers' mapping field_name -> value.
    """
    answers: Dict[str, str] = {}

    # Map elements to fields
    for elem in elements:
        if elem.field_name and elem.field_name in schema:
            # Extract value from element (simple: assume it's in HTML)
            # In practice, you'd parse the PDF or use the value directly from context
            # For now, we'll need to track values during generation
            pass

    return {"answers": answers}


def annotate_from_context(
    context: Dict[str, Any],
    schema: Dict[str, str],
) -> Dict[str, str]:
    """Build ground truth from generation context (where values are stored).

    Args:
        context: Generation context with field values.
        schema: Original schema dict.

    Returns:
        Dict mapping field_name -> value.
    """
    answers: Dict[str, str] = {}

    # Look for field values in context
    for field_name in schema.keys():
        # Context keys might be like "value_{field_name}" or stored in pairs
        if f"value_{field_name}" in context:
            answers[field_name] = context[f"value_{field_name}"]
        elif "pairs" in context:
            # Look in pairs
            for pair in context["pairs"]:
                if isinstance(pair, (list, tuple)) and len(pair) >= 3:
                    name, label, value = pair[0], pair[1], pair[2]
                    if name == field_name:
                        answers[field_name] = value
                        break

    return answers


def save_labels_jsonl(
    entries: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    """Save labels in JSONL format compatible with dataset.json structure.

    Args:
        entries: List of dicts with keys: label, extraction_schema, pdf_path, answers
        output_path: Output JSONL file path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_labels_jsonl(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load labels from JSONL file."""
    entries = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries

