"""Smoke test for the matching module."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.models import SchemaField
from src.io.pdf_loader import extract_blocks, load_document
from src.layout.builder import build_layout
from src.matching.matcher import match_fields
from src.validation.validators import validate_soft

if __name__ == "__main__":
    # Example schema fields
    schema_fields = [
        SchemaField(
            name="inscricao",
            description="Número de inscrição na OAB",
            type="id_simple",
            synonyms=["inscrição", "nº oab", "registro"],
        ),
        SchemaField(
            name="seccional",
            description="Seccional (UF)",
            type="text",
            synonyms=["seccional"],
        ),
    ]

    # Load PDF (adjust path as needed)
    pdf_path = "data/samples/oab_1.pdf"
    if not Path(pdf_path).exists():
        print(f"Warning: {pdf_path} not found. Please adjust the path.")
        sys.exit(1)

    doc = load_document(pdf_path, label="carteira_oab")
    blocks = extract_blocks(doc)
    layout = build_layout(doc, blocks)

    # Match fields
    matches = match_fields(schema_fields, layout, validate=validate_soft, top_k=2)

    # Print results
    for name, cands in matches.items():
        print(f"\nFIELD: {name}")
        if not cands:
            print("  (no candidates found)")
        else:
            for i, c in enumerate(cands, 1):
                score_total = 0.65 * c.scores.get("type", 0.0) + 0.35 * c.scores.get("spatial", 0.0)
                print(
                    f"  {i}. {c.relation} | node_id={c.node_id} | "
                    f"scores={c.scores} | total={score_total:.2f}"
                )
                print(f"     context: {repr(c.local_context)}")

