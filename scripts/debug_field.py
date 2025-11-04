"""Debug a specific field extraction for a PDF."""

import json
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline
from src.core.schema import enrich_schema
from src.io.pdf_loader import extract_blocks, load_document
from src.layout.builder import build_layout
from src.matching.matcher import match_fields

# Load first entry from dataset
dataset_path = Path("data/samples/dataset.json")
samples_dir = Path("data/samples")

with open(dataset_path, "r", encoding="utf-8") as f:
    dataset = json.load(f)

entry = dataset[0]  # oab_1.pdf
label = entry["label"]
schema = entry["extraction_schema"]
pdf_name = entry["pdf_path"]
pdf_path = samples_dir / pdf_name

print(f"Debugging: {pdf_name}")
print(f"Field: 'nome'")
print("=" * 80)

# Load document
doc = load_document(str(pdf_path), label=label)
blocks = extract_blocks(doc)

# Build layout
layout = build_layout(doc, blocks)

# Enrich schema
enriched = enrich_schema(label, schema)
schema_fields = enriched.fields

# Find nome field
nome_field = next((f for f in schema_fields if f.name == "nome"), None)
if not nome_field:
    print("Field 'nome' not found in schema!")
    sys.exit(1)

print(f"\nField schema:")
print(f"  Name: {nome_field.name}")
print(f"  Type: {nome_field.type}")
print(f"  Synonyms: {nome_field.synonyms}")
print(f"  Description: {nome_field.description}")

# Match fields
cands_map = match_fields(
    schema_fields,
    layout,
    validate=None,
    top_k=5,
    semantic_seeds={},
    pattern_memory=None,
    memory_cfg=None,
)

candidates = cands_map.get("nome", [])
print(f"\nFound {len(candidates)} candidates for 'nome':")
for i, cand in enumerate(candidates, 1):
    block = next((b for b in layout.blocks if b.id == cand.node_id), None)
    print(f"\n  Candidate {i}:")
    print(f"    Relation: {cand.relation}")
    print(f"    Scores: {cand.scores}")
    print(f"    Block ID: {cand.node_id}")
    if block:
        print(f"    Block text: {repr(block.text[:200])}")
        print(f"    Block bbox: {block.bbox}")
    print(f"    Source label block ID: {cand.source_label_block_id}")
    label_block = next((b for b in layout.blocks if b.id == cand.source_label_block_id), None)
    if label_block:
        print(f"    Label block text: {repr(label_block.text[:200])}")

# Also check categoria
print("\n" + "=" * 80)
print(f"Field: 'categoria'")
categoria_field = next((f for f in schema_fields if f.name == "categoria"), None)
if categoria_field:
    print(f"\nField schema:")
    print(f"  Name: {categoria_field.name}")
    print(f"  Type: {categoria_field.type}")
    print(f"  Synonyms: {categoria_field.synonyms}")
    print(f"  Enum options: {categoria_field.meta.get('enum_options')}")
    
    categoria_cands = cands_map.get("categoria", [])
    print(f"\nFound {len(categoria_cands)} candidates for 'categoria':")
    for i, cand in enumerate(categoria_cands, 1):
        block = next((b for b in layout.blocks if b.id == cand.node_id), None)
        print(f"\n  Candidate {i}:")
        print(f"    Relation: {cand.relation}")
        print(f"    Scores: {cand.scores}")
        if block:
            print(f"    Block text: {repr(block.text[:200])}")
    
    # Check all blocks for enum values
    print(f"\nScanning all blocks for enum values...")
    from src.validation.validators import validate_and_normalize
    enum_opts = categoria_field.meta.get("enum_options")
    found_enums = []
    for block in layout.blocks:
        lines = block.text.splitlines() if block.text else []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            ok, normalized = validate_and_normalize("enum", line, enum_options=enum_opts)
            if ok:
                found_enums.append((block.id, line, normalized))
    
    if found_enums:
        print(f"  Found {len(found_enums)} enum matches:")
        for bid, line, norm in found_enums:
            print(f"    Block {bid}: '{line}' -> '{norm}'")
    else:
        print("  No enum matches found in any block")
