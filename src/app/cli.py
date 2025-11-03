"""CLI interface for document extraction system."""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.models import Document  # noqa: E402
from src.io.pdf_loader import extract_blocks, load_document  # noqa: E402


def main() -> None:
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(description="Document extraction system CLI")
    ap.add_argument("--probe", action="store_true", help="Print first blocks extracted from PDF")
    ap.add_argument("--pdf", type=str, help="Path to a one-page PDF")
    ap.add_argument("--label", type=str, default="unknown", help="Document label/type")
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
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

