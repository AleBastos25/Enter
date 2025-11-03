"""PDF loader for extracting normalized text blocks from one-page OCR'd PDFs."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import fitz  # PyMuPDF

from ..core.models import Block, Document, InlineSpan

__all__ = ["load_document", "extract_blocks"]

# Heuristic: if horizontal gap (in points) between spans is larger than this
# factor * reference_font_size, we will inject a space when concatenating spans.
_GAP_FACTOR_CHARS = 0.33

# Minimal bbox width/height (normalized) to avoid zero-size boxes after clamping.
_MIN_NORM_EXTENT = 0.001


def _normalize_bbox(
    bbox: Tuple[float, float, float, float], width: float, height: float
) -> Tuple[float, float, float, float]:
    """Normalize bbox coordinates to [0, 1] range and ensure x0<x1, y0<y1.

    Args:
        bbox: Raw bbox (x0, y0, x1, y1) in page coordinates.
        width: Page width in points.
        height: Page height in points.
    """
    x0, y0, x1, y1 = bbox
    x0_n = max(0.0, min(1.0, x0 / width))
    y0_n = max(0.0, min(1.0, y0 / height))
    x1_n = max(0.0, min(1.0, x1 / width))
    y1_n = max(0.0, min(1.0, y1 / height))
    # Ensure positive extents
    if x0_n >= x1_n:
        x1_n = min(1.0, x0_n + _MIN_NORM_EXTENT)
    if y0_n >= y1_n:
        y1_n = min(1.0, y0_n + _MIN_NORM_EXTENT)
    return (x0_n, y0_n, x1_n, y1_n)


_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
_WS_RE = re.compile(r"[ \t\r\f]+")


def _clean_text(s: str, *, preserve_newlines: bool = True) -> str:
    """Clean text: remove zero-width chars, collapse spaces, keep optional newlines.

    If ``preserve_newlines=True``, newlines are kept and spaces are collapsed per line.
    """
    s = _ZERO_WIDTH_RE.sub("", s)
    if preserve_newlines:
        # Normalize spaces around newlines while preserving line breaks
        lines = [ln.strip() for ln in s.splitlines()]
        lines = [
            _WS_RE.sub(" ", ln) for ln in lines if ln != ""
        ]  # collapse spaces but keep empties out
        return "\n".join(lines).strip()
    else:
        s = _WS_RE.sub(" ", s)
        return s.strip()


def _is_bold(font_name: str | None, flags: Optional[int] = None) -> bool:
    """Heuristic bold detection using font name and flags.

    - Font names containing: bold, semibold, demi, black, heavy
    - PyMuPDF flags bit 4 (16) indicates bold in many cases
    """
    if font_name:
        f = font_name.lower()
        if any(k in f for k in ("bold", "semibold", "semi", "demi", "black", "heavy")):
            return True
    if flags is not None and (flags & 16):
        return True
    return False


def _span_info(span_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Extract minimal info from a PyMuPDF span dict (kept local, not in models)."""
    text = span_dict.get("text", "") or ""
    bbox = span_dict.get("bbox")  # (x0, y0, x1, y1) in page coords
    size = span_dict.get("size")
    flags = span_dict.get("flags")
    font = span_dict.get("font")
    return {
        "text": text,
        "bbox": bbox,
        "size": size,
        "bold": _is_bold(font, flags),
        "font": font,
        "flags": flags,
    }


def _concat_line_spans(span_infos: List[Dict[str, Any]]) -> tuple[str, List[InlineSpan]]:
    """Concatenate spans into a single line string using spacing heuristics.

    Rules:
      - Insert a space if both previous last char and current first char are alnum.
      - Also insert a space if horizontal gap > _GAP_FACTOR_CHARS * ref_font_size.
      - Otherwise, concatenate directly.
    Returns the concatenated line string and a list of InlineSpan (without bbox).
    """
    if not span_infos:
        return "", []

    line_text_parts: List[str] = []
    inline_spans: List[InlineSpan] = []

    def first_char(s: str) -> str:
        return next((c for c in s if not c.isspace()), "")

    def last_char(s: str) -> str:
        for c in reversed(s):
            if not c.isspace():
                return c
        return ""

    prev_text = ""
    prev_x1: Optional[float] = None
    prev_size: Optional[float] = None

    for si in span_infos:
        t = si["text"]
        if not t:
            continue
        # Prepare spacing decision
        add_space = False
        fc = first_char(t)
        lc_prev = last_char(prev_text)
        if prev_text:
            if lc_prev.isalnum() and fc.isalnum():
                add_space = True
            # Gap-based spacing (if bbox available for both)
            x0, x1 = None, None
            if si.get("bbox") is not None and prev_x1 is not None:
                x0 = si["bbox"][0]
                gap = x0 - prev_x1
                ref_size = prev_size or si.get("size") or 10.0
                if gap > (_GAP_FACTOR_CHARS * ref_size):
                    add_space = True
        # Append with optional space
        if add_space:
            line_text_parts.append(" ")
        line_text_parts.append(t)

        # Track for next iteration
        prev_text = t
        if si.get("bbox") is not None:
            prev_x1 = si["bbox"][2]
        prev_size = si.get("size") or prev_size

        # Collect InlineSpan (for bold/font_size aggregation)
        inline_spans.append(
            InlineSpan(text=t, bold=bool(si.get("bold")), font_size=si.get("size"))
        )

    return "".join(line_text_parts), inline_spans


def load_document(
    pdf_path: str, *, label: Optional[str] = None, doc_id: Optional[str] = None
) -> Document:
    """Create a Document instance from a PDF file path.

    - Ensures the PDF has exactly one page (MVP0 constraint).
    - Uses filename stem as doc_id if none is provided.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Generate doc_id if not provided
    if doc_id is None:
        stem = Path(pdf_path).stem
        doc_id = stem or hashlib.md5(pdf_path.encode()).hexdigest()[:8]

    # Validate one-page constraint eagerly
    doc = fitz.open(pdf_path)
    try:
        if len(doc) != 1:
            raise ValueError(
                f"Only 1-page PDFs are supported in MVP0. Found {len(doc)} pages in {pdf_path}."
            )
    finally:
        doc.close()

    meta = {"filename": os.path.basename(pdf_path)}
    return Document(id=doc_id, label=label or "unknown", path=pdf_path, data=None, meta=meta)


def extract_blocks(document: Document) -> List[Block]:
    """Extract normalized text blocks from a one-page Document.

    - Opens the PDF by path or bytes.
    - Iterates text blocks, concatenates spans with spacing heuristics, joins lines with "\n".
    - Returns blocks sorted by (y0, x0) with normalized bbox in [0,1].
    """
    # Open PDF
    if document.path:
        doc = fitz.open(document.path)
    elif document.data:
        doc = fitz.open(stream=document.data, filetype="pdf")
    else:
        raise ValueError("Document must have either path or data set.")

    try:
        if len(doc) != 1:
            raise ValueError(f"Only 1-page PDFs are supported in MVP0. Found {len(doc)} pages.")

        page = doc[0]
        width, height = page.rect.width, page.rect.height

        text_dict = page.get_text("dict")
        blocks: List[Block] = []
        block_id = 0

        for block_dict in text_dict.get("blocks", []):
            if block_dict.get("type") != 0:  # 0 = text block
                continue

            block_bbox: Optional[Tuple[float, float, float, float]] = None
            block_line_texts: List[str] = []
            all_inline_spans: List[InlineSpan] = []

            for line_dict in block_dict.get("lines", []):
                # Update/expand block bbox
                line_bbox = tuple(line_dict.get("bbox", block_dict.get("bbox")))  # type: ignore
                if block_bbox is None:
                    block_bbox = line_bbox
                else:
                    block_bbox = (
                        min(block_bbox[0], line_bbox[0]),
                        min(block_bbox[1], line_bbox[1]),
                        max(block_bbox[2], line_bbox[2]),
                        max(block_bbox[3], line_bbox[3]),
                    )

                # Build spans for this line with spacing heuristics
                span_infos = [_span_info(sd) for sd in line_dict.get("spans", [])]
                line_text, inline_spans = _concat_line_spans(span_infos)
                line_text = _clean_text(line_text, preserve_newlines=False)

                # (Optional) simple de-hyphenation across lines: if current line ends with "-",
                # we will merge with the next line without inserting a space/newline when joining below.
                block_line_texts.append(line_text)
                all_inline_spans.extend(inline_spans)

            if block_bbox is None:
                # Fallback to the block bbox if lines were empty
                block_bbox = tuple(block_dict.get("bbox", (0, 0, width, height)))  # type: ignore

            # Join lines with newlines, but handle hyphen join (end-with-'-')
            joined_lines: List[str] = []
            for i, ln in enumerate(block_line_texts):
                if i > 0 and joined_lines:
                    prev = joined_lines[-1]
                    if prev.endswith("-"):
                        # remove hyphen and concatenate without space
                        joined_lines[-1] = prev[:-1] + ln.lstrip()
                    else:
                        joined_lines.append("\n" + ln)
                else:
                    joined_lines.append(ln)
            raw_text = "".join(joined_lines)

            cleaned_text = _clean_text(raw_text, preserve_newlines=True)
            if not cleaned_text:
                continue

            normalized_bbox = _normalize_bbox(block_bbox, width, height)

            # Bold aggregation & avg font size
            is_bold = any(sp.bold for sp in all_inline_spans)
            font_sizes = [sp.font_size for sp in all_inline_spans if sp.font_size is not None]
            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else None

            blocks.append(
                Block(
                    id=block_id,
                    text=cleaned_text,
                    bbox=normalized_bbox,
                    page=0,
                    font_size=avg_font_size,
                    bold=is_bold,
                    rotation=0,
                    spans=all_inline_spans,
                )
            )
            block_id += 1

        # Sort blocks: primary by y0 (asc), secondary by x0 (asc)
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        return blocks

    finally:
        doc.close()
