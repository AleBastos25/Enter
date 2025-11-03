"""PDF loader for extracting normalized text blocks from one-page OCR'd PDFs."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from ..core.models import Block, Document, InlineSpan


__all__ = ["load_document", "extract_blocks"]


def _normalize_bbox(
    bbox: tuple[float, float, float, float], width: float, height: float
) -> tuple[float, float, float, float]:
    """Normalize bbox coordinates to [0, 1] range.

    Args:
        bbox: Raw bbox (x0, y0, x1, y1) in page coordinates.
        width: Page width in points.
        height: Page height in points.

    Returns:
        Normalized bbox (x0, y0, x1, y1) clamped to [0, 1] with x0 < x1, y0 < y1.
    """
    x0, y0, x1, y1 = bbox
    # Normalize
    x0_norm = max(0.0, min(1.0, x0 / width))
    y0_norm = max(0.0, min(1.0, y0 / height))
    x1_norm = max(0.0, min(1.0, x1 / width))
    y1_norm = max(0.0, min(1.0, y1 / height))
    # Ensure x0 < x1 and y0 < y1
    if x0_norm >= x1_norm:
        x1_norm = min(1.0, x0_norm + 0.001)
    if y0_norm >= y1_norm:
        y1_norm = min(1.0, y0_norm + 0.001)
    return (x0_norm, y0_norm, x1_norm, y1_norm)


def _clean_text(s: str) -> str:
    """Clean text: collapse whitespace, strip, remove zero-width chars.

    Args:
        s: Raw text string.

    Returns:
        Cleaned text string.
    """
    # Remove zero-width characters
    s = re.sub(r"[\u200b-\u200d\ufeff]", "", s)
    # Collapse runs of whitespace to single space
    s = re.sub(r"\s+", " ", s)
    # Strip leading/trailing whitespace
    return s.strip()


def _is_bold(font_name: str, flags: Optional[int] = None) -> bool:
    """Check if font indicates bold styling.

    Args:
        font_name: Font name string.
        flags: Optional font flags from PyMuPDF.

    Returns:
        True if font name suggests bold or flags indicate bold.
    """
    if font_name:
        font_lower = font_name.lower()
        if any(keyword in font_lower for keyword in ["bold", "black", "semi", "semibold"]):
            return True
    # Check flags if available (bit 4 indicates bold in PyMuPDF)
    if flags is not None:
        if flags & 16:  # Bit 4 (0-indexed) is bold
            return True
    return False


def _spans_from_line(line_dict: dict) -> list[InlineSpan]:
    """Convert PyMuPDF line span entries to InlineSpan objects.

    Args:
        line_dict: PyMuPDF line dictionary with 'spans' key.

    Returns:
        List of InlineSpan objects.
    """
    spans = []
    for span_dict in line_dict.get("spans", []):
        text = span_dict.get("text", "")
        if not text:
            continue
        font_name = span_dict.get("font", "")
        flags = span_dict.get("flags", None)
        font_size = span_dict.get("size", None)
        bold = _is_bold(font_name, flags)
        spans.append(InlineSpan(text=text, bold=bold, font_size=font_size))
    return spans


def load_document(
    pdf_path: str, *, label: Optional[str] = None, doc_id: Optional[str] = None
) -> Document:
    """Create a Document instance from a PDF file path.

    Args:
        pdf_path: Path to the PDF file.
        label: Optional document type label (can be None).
        doc_id: Optional document ID. If not provided, uses filename without extension
                or a short hash.

    Returns:
        Document instance with path set and data=None.

    Raises:
        FileNotFoundError: If pdf_path does not exist.
        ValueError: If PDF has more than one page.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Generate doc_id if not provided
    if doc_id is None:
        stem = Path(pdf_path).stem
        if stem:
            doc_id = stem
        else:
            # Fallback to hash of path
            doc_id = hashlib.md5(pdf_path.encode()).hexdigest()[:8]

    # Validate one-page constraint
    doc = fitz.open(pdf_path)
    try:
        if len(doc) != 1:
            raise ValueError(
                f"Only 1-page PDFs are supported in MVP0. Found {len(doc)} pages in {pdf_path}."
            )
    finally:
        doc.close()

    filename = os.path.basename(pdf_path)
    meta = {"filename": filename}

    return Document(
        id=doc_id, label=label or "unknown", path=pdf_path, data=None, meta=meta
    )


def extract_blocks(document: Document) -> list[Block]:
    """Extract normalized text blocks from a Document.

    Opens the PDF (from document.path or document.data) and returns a sorted list
    of Block items with normalized geometry.

    Args:
        document: Document instance with path or data set.

    Returns:
        Sorted list of Block objects (sorted by y0, then x0).

    Raises:
        ValueError: If neither path nor data is set, or if PDF has more than one page.
    """
    # Open PDF
    if document.path:
        doc = fitz.open(document.path)
    elif document.data:
        doc = fitz.open(stream=document.data, filetype="pdf")
    else:
        raise ValueError("Document must have either path or data set.")

    try:
        # Validate page count
        if len(doc) != 1:
            raise ValueError(
                f"Only 1-page PDFs are supported in MVP0. Found {len(doc)} pages."
            )

        page = doc[0]
        width = page.rect.width
        height = page.rect.height

        # Extract text blocks using dict format
        text_dict = page.get_text("dict")

        blocks = []
        block_id = 0

        # Iterate through blocks in the page
        for block_dict in text_dict.get("blocks", []):
            # Skip non-text blocks (images, etc.)
            if block_dict.get("type") != 0:  # 0 = text block
                continue

            # Collect all lines and spans in this block
            block_text_parts = []
            all_spans = []
            block_bbox = None

            for line_dict in block_dict.get("lines", []):
                # Get line bbox (use block bbox if available, else line bbox)
                line_bbox = line_dict.get("bbox", block_dict.get("bbox"))
                if block_bbox is None:
                    block_bbox = line_bbox
                else:
                    # Expand block bbox to include line
                    block_bbox = (
                        min(block_bbox[0], line_bbox[0]),
                        min(block_bbox[1], line_bbox[1]),
                        max(block_bbox[2], line_bbox[2]),
                        max(block_bbox[3], line_bbox[3]),
                    )

                # Extract spans from this line
                line_spans = _spans_from_line(line_dict)
                all_spans.extend(line_spans)

                # Collect text
                for span in line_spans:
                    block_text_parts.append(span.text)

            # Use block bbox if line aggregation didn't work
            if block_bbox is None:
                block_bbox = block_dict.get("bbox", (0, 0, width, height))

            # Clean and assemble text
            raw_text = "".join(block_text_parts)
            cleaned_text = _clean_text(raw_text)

            # Skip empty blocks
            if not cleaned_text:
                continue

            # Normalize bbox
            normalized_bbox = _normalize_bbox(block_bbox, width, height)

            # Compute bold (any span is bold)
            is_bold = any(span.bold for span in all_spans)

            # Compute font size (mean of spans)
            font_sizes = [span.font_size for span in all_spans if span.font_size is not None]
            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else None

            # Create Block
            block = Block(
                id=block_id,
                text=cleaned_text,
                bbox=normalized_bbox,
                page=0,
                font_size=avg_font_size,
                bold=is_bold,
                rotation=0,  # MVP0: assume no rotation
                spans=all_spans,
            )

            blocks.append(block)
            block_id += 1

        # Sort blocks: primary by y0 (ascending), secondary by x0 (ascending)
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))

        return blocks

    finally:
        doc.close()

