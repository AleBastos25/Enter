"""Debug script to visualize layout structure: lines, columns, sections, and Grid (v2)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.io.pdf_loader import load_document, extract_blocks
from src.layout.builder import build_layout, dump_layout_debug
from src.layout.grid import debug_render_grid


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

    # Grid v2 debug
    grid = getattr(layout, "grid", None)
    if grid:
        print("\n" + "=" * 60)
        print("Grid v2 Debug:")
        print(f"  Virtual rows: {len(grid['row_y'])}")
        print(f"  Columns: {len(grid['col_x'])}")
        print(f"  Blocks with cells: {len(grid['cell_map'])}")
        print(f"  Blocks with spans: {len(grid['spans'])}")
        print(f"  Thresholds: {grid['thresholds']}")
        print("=" * 60)

        # Render SVG
        svg_path = Path(pdf_path).stem + "_grid_debug.svg"
        debug_render_grid(grid, blocks, svg_path)
        print(f"\nGrid visualization saved to: {svg_path}")

        # Show some spans
        if grid["spans"]:
            print("\nSample spans:")
            for block_id, (first_col, last_col) in list(grid["spans"].items())[:5]:
                block = next((b for b in blocks if b.id == block_id), None)
                if block:
                    text_preview = block.text[:50] if block.text else ""
                    print(f"  Block {block_id}: cols {first_col}-{last_col} '{text_preview}'")

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

