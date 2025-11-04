"""Debug extraction issues for specific fields."""

import json
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline
from src.io.pdf_loader import load_document, extract_blocks
from src.layout.builder import build_layout
from src.core.schema import enrich_schema
from src.matching.matcher import match_fields
from src.extraction.text_extractor import extract_from_candidate


def debug_field(pdf_path: str, label: str, schema_dict: dict, field_name: str):
    """Debug extraction for a specific field."""
    print(f"Debugging field '{field_name}' in {pdf_path}\n")
    
    # Load document
    doc = load_document(pdf_path, label=label)
    blocks = extract_blocks(doc)
    
    # Build layout
    layout = build_layout(doc, blocks)
    
    # Enrich schema
    enriched = enrich_schema(label, schema_dict)
    schema_fields = enriched.fields
    
    # Find the field
    field = next((f for f in schema_fields if f.name == field_name), None)
    if not field:
        print(f"Field '{field_name}' not found in schema")
        return
    
    print(f"Field: {field.name}")
    print(f"  Type: {field.type}")
    print(f"  Description: {field.description}")
    print(f"  Synonyms: {field.synonyms}")
    print()
    
    # Match fields
    cands_map = match_fields(
        [field],
        layout,
        validate=None,
        top_k=5,
        semantic_seeds={},
        pattern_memory=None,
        memory_cfg=None,
    )
    
    candidates = cands_map.get(field_name, [])
    print(f"Found {len(candidates)} candidates:\n")
    
    for i, cand in enumerate(candidates[:3]):
        print(f"Candidate {i+1}:")
        print(f"  Relation: {cand.relation}")
        print(f"  Node ID: {cand.node_id}")
        print(f"  Source label block ID: {cand.source_label_block_id}")
        print(f"  Scores: {cand.scores}")
        
        # Get blocks
        label_block = next((b for b in layout.blocks if b.id == cand.source_label_block_id), None)
        value_block = next((b for b in layout.blocks if b.id == cand.node_id), None)
        
        if label_block:
            print(f"  Label block text: '{label_block.text[:100]}'")
        if value_block:
            print(f"  Value block text: '{value_block.text[:100]}'")
        
        # Try extraction
        value, conf, trace = extract_from_candidate(field, cand, layout)
        print(f"  Extracted value: '{value}'")
        print(f"  Confidence: {conf}")
        print(f"  Trace: {trace}")
        print()


if __name__ == "__main__":
    dataset_path = Path("data/samples/dataset.json")
    samples_dir = Path("data/samples")
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    
    # Debug first OAB entry, field "nome"
    entry = dataset[0]
    pdf_path = samples_dir / entry["pdf_path"]
    
    print("=" * 80)
    debug_field(str(pdf_path), entry["label"], entry["extraction_schema"], "nome")
    print("=" * 80)
    debug_field(str(pdf_path), entry["label"], entry["extraction_schema"], "categoria")

