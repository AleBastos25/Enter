"""Debug script to check candidate generation."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.io.pdf_loader import load_document, extract_blocks
from src.core.schema import enrich_schema
from src.layout.builder import build_layout
from src.core.doc_profile import build_doc_profile
from src.matching.candidates import build_candidate_sets
from src.tables.detector import detect_tables
import json

# Load first PDF
pdf_path = "data/samples/oab_1.pdf"
label = "carteira_oab"

# Load schema from dataset.json
dataset_path = Path("data/samples/dataset.json")
with open(dataset_path, "r", encoding="utf-8") as f:
    dataset = json.load(f)
# Find schema for this label
schema_dict = {}
for entry in dataset:
    if entry.get("label") == label:
        schema_dict = entry.get("extraction_schema", {})
        break

print(f"Schema dict: {schema_dict}")

# Load document
doc = load_document(pdf_path, label=label)
blocks = extract_blocks(doc)

print(f"Loaded {len(blocks)} blocks")

# Build layout
layout = build_layout(doc, blocks)
print(f"Layout built with {len(layout.blocks)} blocks")

# Detect tables
pdf_lines = getattr(layout, "pdf_lines", None)
tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
print(f"Detected {len(tables)} tables")

# Build profile
grid = getattr(layout, "grid", None)
graph_v2 = getattr(layout, "graph_v2", None)
profile = build_doc_profile(blocks, pdf_lines, graph_v2, grid)
print(f"Profile: columns={profile.column_count}, grid_likeness={profile.grid_likeness:.2f}")

# Enrich schema
enriched = enrich_schema(label, schema_dict)
schema_fields = enriched.fields
print(f"Schema has {len(schema_fields)} fields")

# Build candidate sets (check BEFORE filtering)
print("\n=== BEFORE FILTERING ===")
for field in schema_fields:
    # Temporarily build without filtering to see what's being rejected
    from src.matching.candidates import _find_label_blocks_lightweight, _generate_spatial_candidates, _generate_pattern_candidates
    from src.validation.patterns import detect_pattern, type_gate_generic
    
    label_blocks = _find_label_blocks_lightweight(field, blocks, profile)
    print(f"{field.name} (type={field.type}): {len(label_blocks)} label blocks")
    
    # Check pattern candidates
    blocks_by_pattern = {}
    for block in blocks:
        pattern = detect_pattern(block.text or "")
        if pattern not in blocks_by_pattern:
            blocks_by_pattern[pattern] = []
        blocks_by_pattern[pattern].append(block)
    
    # Check what patterns match
    expected_patterns = []
    if field.type in ("cpf", "cnpj", "cep", "phone", "id_simple", "inscricao"):
        expected_patterns = ["digits_only", "digits_with_separators"]
    elif field.type == "money":
        expected_patterns = ["money_like"]
    elif field.type == "date":
        expected_patterns = ["date_like"]
    elif field.type in ("uf", "code", "sigla"):
        expected_patterns = ["isolated_letters"]
    else:
        expected_patterns = ["text", "alphanumeric"]
    
    print(f"  Expected patterns: {expected_patterns}")
    for pattern_type in expected_patterns:
        if pattern_type in blocks_by_pattern:
            matching_blocks = blocks_by_pattern[pattern_type]
            print(f"  Found {len(matching_blocks)} blocks with pattern '{pattern_type}'")
            for block in matching_blocks[:3]:
                gate_result = type_gate_generic(block.text or "", field.type or "text")
                print(f"    Block {block.id}: '{block.text[:50]}' (gate={gate_result})")

# Build candidate sets
candidate_sets = build_candidate_sets(
    blocks,
    layout,
    schema_fields,
    profile,
    tables,
)

print("\nCandidate sets:")
from src.validation.patterns import type_gate_generic
for field_name, candidates in candidate_sets.items():
    field = next((f for f in schema_fields if f.name == field_name), None)
    field_type = field.type if field else "text"
    print(f"  {field_name} (type={field_type}): {len(candidates)} candidates")
    
    # Check BEFORE filtering
    all_candidates = build_candidate_sets(blocks, layout, [field], profile, tables) if field else {}
    before_filter = all_candidates.get(field_name, []) if field else []
    print(f"    BEFORE filter: {len(before_filter)} candidates")
    
    for i, cand in enumerate(candidates[:3]):  # Show first 3
        text_for_gate = cand.region_text if cand.region_text else cand.snippet
        gate_result = type_gate_generic(text_for_gate, field_type)
        print(f"    [{i}] {cand.candidate_id}: {cand.relation} - '{cand.snippet[:50]}' (gate={gate_result})")
    if len(candidates) > 3:
        print(f"    ... and {len(candidates) - 3} more")

