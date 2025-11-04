"""Debug script to visualize layout structure: lines, columns, sections."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.io.pdf_loader import load_document, extract_blocks
from src.layout.builder import build_layout, dump_layout_debug


def main():
    """Run layout debug on a sample PDF."""
    pdf_path = "data/samples/oab_1.pdf"
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    print(f"Loading PDF: {pdf_path}")
    doc = load_document(pdf_path, label="debug_test")
    blocks = extract_blocks(doc)

    print(f"Extracted {len(blocks)} blocks")
    print("\nBuilding layout...")
    layout = build_layout(doc, blocks)

    print("\n" + "=" * 60)
    dump_layout_debug(layout)
    print("=" * 60)

    # Additional details
    line_nodes = [rn for rn in layout.reading_nodes if rn.type == "line"]
    column_by_block = getattr(layout, "column_id_by_block", {})
    section_by_block = getattr(layout, "section_id_by_block", {})

    print(f"\nColumn distribution:")
    col_counts: dict[int, int] = {}
    for col_id in column_by_block.values():
        col_counts[col_id] = col_counts.get(col_id, 0) + 1
    for col_id, count in sorted(col_counts.items()):
        print(f"  Column {col_id}: {count} blocks")

    print(f"\nSection distribution:")
    sec_counts: dict[int, int] = {}
    for sec_id in section_by_block.values():
        sec_counts[sec_id] = sec_counts.get(sec_id, 0) + 1
    for sec_id, count in sorted(sec_counts.items()):
        print(f"  Section {sec_id}: {count} blocks")


if __name__ == "__main__":
    main()

