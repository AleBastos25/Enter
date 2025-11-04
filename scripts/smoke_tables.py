"""Smoke test for table detection and extraction."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.io.pdf_loader import load_document, extract_blocks
from src.layout.builder import build_layout
from src.tables.detector import detect_tables
from src.tables.extractor import find_cell_by_label


def main():
    """Test table detection on a sample PDF."""
    pdf_path = "data/samples/tela_sistema_2.pdf"
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    print(f"Loading PDF: {pdf_path}")
    doc = load_document(pdf_path, label="tela")
    blocks = extract_blocks(doc)
    print(f"Extracted {len(blocks)} blocks")

    print("\nBuilding layout...")
    layout = build_layout(doc, blocks)

    print("\nDetecting tables...")
    pdf_lines = getattr(layout, "pdf_lines", None)
    tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)

    print(f"\nFound {len(tables)} tables:")
    for i, t in enumerate(tables):
        print(f"  Table {i}: type={t.type}, rows={len(t.rows)}, cells={len(t.cells)}, cols={t.col_count}")

    # Example: search for "total" in tables
    print("\nSearching for 'total' in tables...")
    cell = find_cell_by_label(tables, [re.compile(r"total", re.I)], search_in="any")
    if cell:
        print(f"  Found cell: text='{cell.text[:120]}'")
        print(f"    row_id={cell.row_id}, col_id={cell.col_id}, header={cell.header}")
    else:
        print("  Not found")

    # Example: search for specific field patterns
    print("\nSearching for common field patterns...")
    patterns = [
        (["data", "date", "emissao"], "data"),
        (["valor", "total", "amount"], "valor"),
        (["uf", "estado", "seccional"], "uf"),
    ]

    for pattern_list, field_name in patterns:
        cell = find_cell_by_label(tables, pattern_list, search_in="any")
        if cell:
            print(f"  {field_name}: '{cell.text[:80]}'")
        else:
            print(f"  {field_name}: not found")

    # Show first few cells of each table
    print("\nFirst 5 cells of each table:")
    for i, t in enumerate(tables):
        print(f"\n  Table {i} ({t.type}):")
        for cell in t.cells[:5]:
            print(f"    Cell [{cell.row_id},{cell.col_id}]: '{cell.text[:60]}' (header={cell.header})")


if __name__ == "__main__":
    main()

