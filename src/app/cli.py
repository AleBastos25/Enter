"""CLI interface for document extraction system."""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.models import Document  # noqa: E402
from src.core.pipeline import Pipeline  # noqa: E402
from src.io.pdf_loader import extract_blocks, load_document  # noqa: E402
from src.layout.builder import build_layout, dump_layout_debug  # noqa: E402


def main() -> None:
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(description="Document extraction system CLI")
    ap.add_argument("--probe", action="store_true", help="Print first blocks extracted from PDF")
    ap.add_argument("--run", action="store_true", help="Run full pipeline extraction")
    ap.add_argument("--layout-debug", action="store_true", help="Print layout debug (lines, columns, sections)")
    ap.add_argument("--pdf", type=str, help="Path to a one-page PDF")
    ap.add_argument("--label", type=str, default="unknown", help="Document label/type")
    ap.add_argument("--schema", type=str, help="Path to schema.json (name->description)")
    args = ap.parse_args()

    if args.probe:
        if not args.pdf:
            ap.error("--probe requires --pdf")
        try:
            doc = load_document(args.pdf, label=args.label)
            blocks = extract_blocks(doc)
            print(
                json.dumps(
                    [
                        {
                            "id": b.id,
                            "text": b.text,
                            "bbox": b.bbox,
                            "bold": b.bold,
                            "font_size": b.font_size,
                        }
                        for b in blocks[:8]
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.layout_debug:
        if not args.pdf:
            ap.error("--layout-debug requires --pdf")
        try:
            doc = load_document(args.pdf, label=args.label)
            blocks = extract_blocks(doc)
            layout = build_layout(doc, blocks)
            dump_layout_debug(layout)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.run:
        if not args.pdf or not args.label or not args.schema:
            ap.error("--run requires --pdf, --label, and --schema")
        try:
            schema_dict = json.loads(Path(args.schema).read_text(encoding="utf-8"))
            pipe = Pipeline()
            out = pipe.run(args.label, schema_dict, args.pdf)
            print(json.dumps(out, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

