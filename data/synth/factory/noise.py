"""Noise and perturbation module for OCR-like effects."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import numpy as np
    from PIL import Image, ImageFilter, ImageEnhance
    HAS_IMAGE_LIBS = True
except ImportError:
    HAS_IMAGE_LIBS = False


def apply_noise_to_pdf(
    pdf_path: Path,
    output_path: Path,
    config: Dict,
) -> None:
    """Apply noise/perturbations to a PDF.

    Args:
        pdf_path: Input PDF path.
        output_path: Output PDF path.
        config: Noise configuration dict with keys:
            - rotate_deg_max: float
            - jpeg_quality_range: [min, max]
            - blur_sigma_range: [min, max]
            - enabled: bool
    """
    if not config.get("enabled", True):
        # Just copy
        import shutil
        shutil.copy(pdf_path, output_path)
        return

    if not HAS_IMAGE_LIBS:
        # Fallback: just copy
        import shutil
        shutil.copy(pdf_path, output_path)
        return

    # Convert PDF to images, apply noise, convert back
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # Fallback: just copy
        import shutil
        shutil.copy(pdf_path, output_path)
        return

    doc = fitz.open(pdf_path)
    output_doc = fitz.open()

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=2.0)  # 2x resolution for better quality

        # Convert to PIL Image
        img_data = pix.tobytes("png")
        import io
        img = Image.open(io.BytesIO(img_data))

        # Apply perturbations
        img = apply_image_noise(img, config)

        # Convert back to PDF page
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        new_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=img_bytes.getvalue())

    output_doc.save(output_path)
    output_doc.close()
    doc.close()


def apply_image_noise(img, config: Dict) -> Image.Image:
    """Apply noise to a PIL Image."""
    if not HAS_IMAGE_LIBS:
        return img

    # Rotation/tilt
    rotate_max = config.get("rotate_deg_max", 2.0)
    if rotate_max > 0:
        angle = random.uniform(-rotate_max, rotate_max)
        img = img.rotate(angle, expand=False, fillcolor="white")

    # Blur
    blur_range = config.get("blur_sigma_range", [0.0, 0.8])
    if blur_range[1] > 0:
        sigma = random.uniform(blur_range[0], blur_range[1])
        if sigma > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=sigma))

    # JPEG compression (if quality range specified)
    jpeg_range = config.get("jpeg_quality_range")
    if jpeg_range:
        quality = random.randint(int(jpeg_range[0]), int(jpeg_range[1]))
        import io
        jpeg_bytes = io.BytesIO()
        img.save(jpeg_bytes, format="JPEG", quality=quality)
        jpeg_bytes.seek(0)
        img = Image.open(jpeg_bytes)

    return img


def apply_font_jitter(html: str, config: Dict) -> str:
    """Apply font jitter to HTML (vary font families, sizes within text blocks)."""
    # This is a simple implementation - could be more sophisticated
    import re

    # Randomly vary font sizes in some spans
    font_size_pattern = r'font-size:\s*(\d+)px'
    def replace_size(match):
        size = int(match.group(1))
        jitter = random.randint(-1, 1)
        new_size = max(8, min(24, size + jitter))
        return f"font-size: {new_size}px"

    html = re.sub(font_size_pattern, replace_size, html)

    # Randomly vary font families
    fonts = config.get("fonts", ["Arial", "Times New Roman", "Courier New"])
    font_pattern = r"font-family:\s*([^;]+);"
    def replace_font(match):
        new_font = random.choice(fonts)
        return f"font-family: {new_font}, sans-serif;"

    # Only replace some instances (50% chance)
    if random.random() < 0.5:
        html = re.sub(font_pattern, replace_font, html, count=random.randint(1, 3))

    return html

