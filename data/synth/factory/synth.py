"""CLI for generating synthetic document datasets."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from .annotate import annotate_from_context, save_labels_jsonl
from .dsl import Page, Sample
from .fakerx import generate_pairs_for_schema, generate_value
from .noise import apply_font_jitter, apply_noise_to_pdf
from .render_html import html_to_pdf, render_page_to_html
from .registry import ARCHETYPES, get_archetype, sample_archetype


def load_schema(schema_path: Path) -> Dict[str, str]:
    """Load schema from JSON file."""
    with open(schema_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # If it's a list, take first item's extraction_schema
    if isinstance(data, list):
        if data and "extraction_schema" in data[0]:
            return data[0]["extraction_schema"]
        return {}
    # If it's a dict with extraction_schema
    if isinstance(data, dict) and "extraction_schema" in data:
        return data["extraction_schema"]
    # If it's already a schema dict
    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        return data
    return {}


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from YAML."""
    default_config = {
        "engine": "weasyprint",
        "count_per_run": 500,
        "columns_k": [1, 2, 3],
        "relations": ["right_of", "below", "same_block"],
        "table": {
            "p_use": 0.6,
            "grid_with_rules_p": 0.5,
            "rows": [2, 12],
            "cols": [2, 6],
        },
        "noise": {
            "enabled": True,
            "rotate_deg_max": 2.0,
            "jpeg_quality_range": [35, 90],
            "blur_sigma_range": [0.0, 0.8],
        },
        "fonts": ["Inter", "Roboto", "Times New Roman", "Arial", "Liberation Serif"],
        "badges": {
            "positions": ["bottom-right", "top-right", "bottom-left"],
        },
    }

    if config_path and config_path.exists():
        try:
            import yaml
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f) or {}
            # Merge
            default_config.update(user_config)
        except Exception:
            pass

    return default_config


def generate_document(
    schema: Dict[str, str],
    archetype_name: Optional[str],
    label: str,
    doc_id: int,
    config: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    """Generate a single synthetic document.

    Returns:
        Dict with keys: label, extraction_schema, pdf_path, answers
    """
    # Choose archetype
    if archetype_name:
        archetype = get_archetype(archetype_name)
    else:
        archetype = sample_archetype()

    if not archetype:
        raise ValueError(f"Unknown archetype: {archetype_name}")

    # Build page
    page = archetype.builder(schema)

    # Prepare context with generated values
    pairs = generate_pairs_for_schema(schema, coverage=random.uniform(0.6, 1.0))
    context: Dict[str, Any] = {
        "pairs": pairs,
        "doc_title": f"Documento {label} {doc_id}",
        "section_title": "Seção de Detalhes",
    }

    # Add enum values to context
    for field_name, description in schema.items():
        if any(word in field_name.lower() or word in description.lower() for word in ["situacao", "status", "categoria"]):
            value = generate_value(field_name, description, enum_options=None)
            context[f"enum_{field_name}"] = value

    # Add field values to context
    for field_name, label_text, value in pairs:
        context[f"value_{field_name}"] = value

    # Render HTML
    html, elements = render_page_to_html(page, context)

    # Apply font jitter if enabled
    if config.get("noise", {}).get("enabled", False):
        html = apply_font_jitter(html, config)

    # Save HTML (for debugging)
    html_path = output_dir / "html" / f"doc_{doc_id}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Convert to PDF
    pdf_path_temp = output_dir / "pdfs_temp" / f"doc_{doc_id}.pdf"
    pdf_path_temp.parent.mkdir(parents=True, exist_ok=True)
    html_to_pdf(html, pdf_path_temp, engine=config.get("engine", "weasyprint"))

    # Apply noise
    pdf_path = output_dir / "pdfs" / f"doc_{doc_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    apply_noise_to_pdf(pdf_path_temp, pdf_path, config.get("noise", {}))

    # Clean up temp
    pdf_path_temp.unlink(missing_ok=True)

    # Build ground truth
    answers = annotate_from_context(context, schema)

    # Calculate relative path (assuming output_dir is data/synth/<label>)
    # pdf_path should be relative to data/ or workspace root
    try:
        # Try relative to data/
        rel_path = pdf_path.relative_to(output_dir.parent.parent)
    except ValueError:
        # Fallback: relative to output_dir
        rel_path = pdf_path.relative_to(output_dir)

    return {
        "label": label,
        "extraction_schema": schema,
        "pdf_path": str(rel_path),
        "answers": answers,
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate synthetic document dataset")
    parser.add_argument("--schema", type=Path, required=True, help="Schema JSON file")
    parser.add_argument("--label", type=str, required=True, help="Document label")
    parser.add_argument("--n", type=int, default=500, help="Number of documents to generate")
    parser.add_argument(
        "--archetypes",
        type=str,
        default=None,
        help="Comma-separated list of archetype names (or 'all')",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument("--engine", type=str, default="weasyprint", choices=["weasyprint", "wkhtmltopdf"])
    parser.add_argument("--with-bboxes", action="store_true", help="Include bbox extraction (not yet implemented)")
    parser.add_argument("--with-noise", action="store_true", default=True, help="Apply noise/perturbations")
    parser.add_argument("--config", type=Path, default=None, help="Config YAML file")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    # Load schema
    schema = load_schema(args.schema)
    if not schema:
        print(f"Error: Could not load schema from {args.schema}")
        return 1

    # Load config
    config = load_config(args.config)
    config["engine"] = args.engine
    if not args.with_noise:
        config["noise"]["enabled"] = False

    # Determine archetypes
    archetype_names: List[Optional[str]] = [None]  # None = sample randomly
    if args.archetypes:
        if args.archetypes == "all":
            archetype_names = list(ARCHETYPES.keys())
        else:
            archetype_names = [name.strip() for name in args.archetypes.split(",")]

    # Generate documents
    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = []
    print(f"Generating {args.n} documents...")

    for i in range(args.n):
        archetype_name = random.choice(archetype_names) if len(archetype_names) > 1 else archetype_names[0]
        try:
            entry = generate_document(
                schema=schema,
                archetype_name=archetype_name,
                label=args.label,
                doc_id=i,
                config=config,
                output_dir=output_dir,
            )
            labels.append(entry)
            if (i + 1) % 50 == 0:
                print(f"  Generated {i + 1}/{args.n} documents...")
        except Exception as e:
            print(f"  Error generating document {i}: {e}")
            continue

    # Save labels
    labels_path = output_dir / "labels.jsonl"
    save_labels_jsonl(labels, labels_path)
    print(f"\nGenerated {len(labels)} documents")
    print(f"Labels saved to: {labels_path}")
    print(f"PDFs saved to: {output_dir / 'pdfs'}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

