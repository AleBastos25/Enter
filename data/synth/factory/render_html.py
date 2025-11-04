"""HTML/CSS renderer for synthetic documents."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .dsl import Page, resolve_widget
from .primitives import (
    RenderedElement,
    render_badge,
    render_formgrid,
    render_heading,
    render_kvlist,
    render_paragraph,
    render_table,
    render_watermark,
)


def render_page_to_html(page: Page, context: Dict[str, Any]) -> Tuple[str, List[RenderedElement]]:
    """Render a Page DSL to HTML string and list of elements with IDs.

    Returns:
        (html_string, list_of_elements)
    """
    # Resolve page-level attributes
    margin = page.margin if isinstance(page.margin, int) else page.margin.get("all", 12)
    page_size = page.size
    orientation = page.orientation

    # Build HTML structure
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<style>",
        _get_css_styles(page_size, orientation, margin),
        "</style>",
        "</head>",
        "<body>",
        '<div class="page-container">',
    ]

    all_elements: List[RenderedElement] = []

    # Render widgets
    for widget in page.widgets:
        resolved_widget = resolve_widget(widget, context)

        # Dispatch to appropriate renderer
        if isinstance(resolved_widget, Heading):
            elem = render_heading(resolved_widget, context)
            html_parts.append(elem.html)
            all_elements.append(elem)

        elif isinstance(resolved_widget, Paragraph):
            elem = render_paragraph(resolved_widget, context)
            html_parts.append(elem.html)
            all_elements.append(elem)

        elif isinstance(resolved_widget, KVList):
            elems = render_kvlist(resolved_widget, context)
            for elem in elems:
                html_parts.append(elem.html)
                all_elements.append(elem)

        elif isinstance(resolved_widget, Table):
            elem = render_table(resolved_widget, context)
            html_parts.append(elem.html)
            all_elements.append(elem)

        elif isinstance(resolved_widget, Badge):
            elem = render_badge(resolved_widget, context)
            html_parts.append(elem.html)
            all_elements.append(elem)

        elif isinstance(resolved_widget, FormGrid):
            elems = render_formgrid(resolved_widget, context)
            # First element is container
            if elems:
                html_parts.append(elems[0].html)
                all_elements.extend(elems)

        elif isinstance(resolved_widget, Watermark):
            elem = render_watermark(resolved_widget, context)
            html_parts.append(elem.html)
            all_elements.append(elem)

    html_parts.extend([
        "</div>",
        "</body>",
        "</html>",
    ])

    html = "\n".join(html_parts)
    return html, all_elements


def _get_css_styles(page_size: str, orientation: str, margin: int) -> str:
    """Generate CSS styles for page."""
    # Page dimensions (A4: 210mm x 297mm)
    if page_size == "A4":
        if orientation == "portrait":
            width = "210mm"
            height = "297mm"
        else:
            width = "297mm"
            height = "210mm"
    else:
        # Default to A4
        width = "210mm"
        height = "297mm"

    return f"""
    @page {{
        size: {page_size} {orientation};
        margin: 0;
    }}
    body {{
        margin: 0;
        padding: 0;
        font-family: Arial, sans-serif;
    }}
    .page-container {{
        width: {width};
        min-height: {height};
        margin: {margin}mm;
        padding: 0;
        position: relative;
        box-sizing: border-box;
    }}
    """


def html_to_pdf(html: str, output_path: Path, engine: str = "weasyprint") -> None:
    """Convert HTML to PDF using specified engine.

    Args:
        html: HTML string.
        output_path: Output PDF path.
        engine: "weasyprint" or "wkhtmltopdf".
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if engine == "weasyprint":
        try:
            from weasyprint import HTML
            HTML(string=html).write_pdf(str(output_path))
        except ImportError:
            raise ImportError("weasyprint not installed. Install with: pip install weasyprint")
    elif engine == "wkhtmltopdf":
        try:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
                f.write(html)
                html_path = f.name

            try:
                subprocess.run(
                    ["wkhtmltopdf", html_path, str(output_path)],
                    check=True,
                    capture_output=True,
                )
            finally:
                Path(html_path).unlink()
        except (ImportError, FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError("wkhtmltopdf not available. Install system package or use weasyprint.")
    else:
        raise ValueError(f"Unknown engine: {engine}")

