"""Primitive widgets that render to HTML/CSS and expose bboxes."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .dsl import (
    Badge,
    FormGrid,
    Heading,
    KVList,
    Paragraph,
    Table,
    Watermark,
    resolve_value,
)

# Font families (fallback-safe)
FONTS = [
    "Arial, sans-serif",
    "Times New Roman, serif",
    "Courier New, monospace",
    "Georgia, serif",
    "Verdana, sans-serif",
]


@dataclass
class RenderedElement:
    """A rendered element with HTML and bbox info."""

    html: str
    element_id: str
    bbox: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1) normalized
    field_name: Optional[str] = None  # If this element represents a field value
    field_label: Optional[str] = None  # If this element represents a field label


def render_heading(widget: Heading, context: Dict[str, Any]) -> RenderedElement:
    """Render heading widget."""
    level = resolve_value(widget.level, context)
    text = resolve_value(widget.text, context)
    font_size = resolve_value(widget.font_size, context) if widget.font_size else None
    bold = resolve_value(widget.bold, context)

    element_id = widget.get_id("heading")
    font_family = random.choice(FONTS)

    if not font_size:
        # Default sizes by level
        font_size = {1: 24, 2: 20, 3: 18, 4: 16}.get(level, 16)

    font_weight = "bold" if bold else "normal"
    style = f"font-family: {font_family}; font-size: {font_size}px; font-weight: {font_weight}; margin: 8px 0;"
    style += widget.style.get("extra", "")

    html = f'<h{level} id="{element_id}" style="{style}">{text}</h{level}>'
    return RenderedElement(html=html, element_id=element_id)


def render_paragraph(widget: Paragraph, context: Dict[str, Any]) -> RenderedElement:
    """Render paragraph widget."""
    lines = resolve_value(widget.lines, context)
    text = resolve_value(widget.text, context)

    element_id = widget.get_id("para")
    font_family = random.choice(FONTS)
    font_size = random.randint(10, 14)

    if not text:
        # Generate Lorem-like text
        words = [
            "Lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit",
            "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore",
            "magna", "aliqua", "Ut", "enim", "ad", "minim", "veniam", "quis", "nostrud",
        ]
        sentences = []
        for _ in range(lines):
            sentence = " ".join(random.choices(words, k=random.randint(8, 15)))
            sentences.append(sentence.capitalize() + ".")
        text = " ".join(sentences)

    style = f"font-family: {font_family}; font-size: {font_size}px; line-height: 1.5; margin: 8px 0;"
    style += widget.style.get("extra", "")

    html = f'<p id="{element_id}" style="{style}">{text}</p>'
    return RenderedElement(html=html, element_id=element_id)


def render_kvlist(widget: KVList, context: Dict[str, Any]) -> List[RenderedElement]:
    """Render KV list widget. Returns list of elements (label + value pairs)."""
    pairs = resolve_value(widget.pairs, context)
    mode = resolve_value(widget.mode, context)
    gap = resolve_value(widget.gap, context)

    if not pairs:
        return []

    elements = []
    font_family = random.choice(FONTS)

    for field_name, label, value in pairs:
        label_id = widget.get_id(f"label_{field_name}")
        value_id = widget.get_id(f"value_{field_name}")

        if mode == "right_of":
            # Label on left, value on right (same line)
            html = f'''
            <div style="display: flex; gap: {gap}px; margin: 4px 0;">
                <span id="{label_id}" style="font-family: {font_family}; font-weight: bold; font-size: 12px;">{label}:</span>
                <span id="{value_id}" style="font-family: {font_family}; font-size: 12px;">{value}</span>
            </div>
            '''
            container_id = widget.get_id(f"kv_{field_name}")
            elements.append(RenderedElement(
                html=html,
                element_id=container_id,
                field_name=field_name,
                field_label=label,
            ))

        elif mode == "below":
            # Label on top, value below
            html = f'''
            <div style="margin: 4px 0;">
                <div id="{label_id}" style="font-family: {font_family}; font-weight: bold; font-size: 11px; margin-bottom: 2px;">{label}:</div>
                <div id="{value_id}" style="font-family: {font_family}; font-size: 12px;">{value}</div>
            </div>
            '''
            container_id = widget.get_id(f"kv_{field_name}")
            elements.append(RenderedElement(
                html=html,
                element_id=container_id,
                field_name=field_name,
                field_label=label,
            ))

        else:  # same_block
            # Label and value in same block (inline)
            html = f'''
            <div style="margin: 4px 0;">
                <span id="{label_id}" style="font-family: {font_family}; font-weight: bold; font-size: 12px;">{label}</span>
                <span id="{value_id}" style="font-family: {font_family}; font-size: 12px;"> {value}</span>
            </div>
            '''
            container_id = widget.get_id(f"kv_{field_name}")
            elements.append(RenderedElement(
                html=html,
                element_id=container_id,
                field_name=field_name,
                field_label=label,
            ))

    return elements


def render_table(widget: Table, context: Dict[str, Any]) -> RenderedElement:
    """Render table widget."""
    shape = resolve_value(widget.shape, context)
    headers = resolve_value(widget.headers, context)
    with_rules = resolve_value(widget.with_rules, context)
    data = widget.data or []

    element_id = widget.get_id("table")
    font_family = random.choice(FONTS)

    if isinstance(shape, tuple):
        rows, cols = shape
    else:
        rows, cols = 3, 3

    # Generate data if not provided
    if not data:
        data = []
        if headers:
            header_row = [f"Col{i+1}" for i in range(cols)]
            data.append(header_row)
        for r in range(rows - (1 if headers else 0)):
            row = [f"Valor{r+1}_{c+1}" for c in range(cols)]
            data.append(row)

    border_style = "1px solid #ccc" if with_rules else "none"
    html_parts = [f'<table id="{element_id}" style="font-family: {font_family}; font-size: 11px; border-collapse: collapse; width: 100%;">']

    for i, row in enumerate(data):
        is_header = headers and i == 0
        tag = "th" if is_header else "td"
        weight = "bold" if is_header else "normal"
        bg = "#f0f0f0" if is_header else "transparent"

        html_parts.append("<tr>")
        for cell_text in row:
            html_parts.append(
                f'<{tag} style="border: {border_style}; padding: 6px; text-align: left; font-weight: {weight}; background: {bg};">{cell_text}</{tag}>'
            )
        html_parts.append("</tr>")

    html_parts.append("</table>")
    html = "".join(html_parts)

    return RenderedElement(html=html, element_id=element_id)


def render_badge(widget: Badge, context: Dict[str, Any]) -> RenderedElement:
    """Render badge widget."""
    text = resolve_value(widget.text, context)
    anchor = resolve_value(widget.anchor, context)
    style_type = widget.style_type

    element_id = widget.get_id("badge")
    font_family = random.choice(FONTS)

    # Position based on anchor
    position_map = {
        "bottom-right": "position: absolute; bottom: 20px; right: 20px;",
        "top-right": "position: absolute; top: 20px; right: 20px;",
        "bottom-left": "position: absolute; bottom: 20px; left: 20px;",
        "top-left": "position: absolute; top: 20px; left: 20px;",
    }
    position = position_map.get(anchor, position_map["bottom-right"])

    if style_type == "chip":
        style = f"font-family: {font_family}; font-size: 10px; padding: 4px 8px; background: #e0e0e0; border-radius: 12px; display: inline-block; {position}"
    else:
        style = f"font-family: {font_family}; font-size: 11px; padding: 6px 12px; background: #f0f0f0; border: 1px solid #ccc; display: inline-block; {position}"

    html = f'<div id="{element_id}" style="{style}">{text}</div>'
    return RenderedElement(html=html, element_id=element_id)


def render_formgrid(widget: FormGrid, context: Dict[str, Any]) -> List[RenderedElement]:
    """Render form grid widget."""
    rows = resolve_value(widget.rows, context)
    cols = resolve_value(widget.cols, context)
    pairs = widget.pairs or []
    underline = resolve_value(widget.underline, context)

    element_id = widget.get_id("formgrid")
    font_family = random.choice(FONTS)

    # Generate pairs if not provided
    if not pairs:
        pairs = [(f"Campo{i+1}", f"Valor{i+1}") for i in range(rows * cols)]

    elements = []
    html_parts = [f'<div id="{element_id}" style="display: grid; grid-template-columns: repeat({cols}, 1fr); gap: 12px; font-family: {font_family}; font-size: 11px;">']

    for i, (label, value) in enumerate(pairs[:rows * cols]):
        label_id = widget.get_id(f"form_label_{i}")
        value_id = widget.get_id(f"form_value_{i}")

        border_style = "border-bottom: 1px dotted #ccc;" if underline else ""

        html_parts.append(f'''
        <div style="display: flex; flex-direction: column;">
            <label id="{label_id}" style="font-weight: bold; margin-bottom: 4px;">{label}:</label>
            <div id="{value_id}" style="{border_style} padding: 4px 0;">{value}</div>
        </div>
        ''')

        # Track field mapping if applicable
        field_name = None
        if isinstance(label, tuple) and len(label) == 3:
            field_name = label[0]

        elements.append(RenderedElement(
            html="",  # Will be part of container
            element_id=value_id,
            field_name=field_name,
            field_label=label if isinstance(label, str) else label[1] if isinstance(label, tuple) else None,
        ))

    html_parts.append("</div>")
    html = "".join(html_parts)

    # Return container + individual elements
    container = RenderedElement(html=html, element_id=element_id)
    return [container] + elements


def render_watermark(widget: Watermark, context: Dict[str, Any]) -> RenderedElement:
    """Render watermark widget."""
    text = resolve_value(widget.text, context)
    angle = resolve_value(widget.angle, context)
    opacity = widget.opacity

    element_id = widget.get_id("watermark")
    font_family = random.choice(FONTS)

    style = f'''
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate({angle}deg);
    font-family: {font_family};
    font-size: 72px;
    color: #ccc;
    opacity: {opacity};
    pointer-events: none;
    z-index: -1;
    '''

    html = f'<div id="{element_id}" style="{style}">{text}</div>'
    return RenderedElement(html=html, element_id=element_id)

