"""Inspect role assignment for debugging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.io.pdf_loader import extract_blocks, load_document
from src.layout.builder import build_layout
from src.graph.spacing_model import compute_spacing_thresholds
from src.graph.orthogonal_edges import build_orthogonal_graph
from src.graph.roles_rules import assign_roles, _rule_value, _rule_label, _rule_header
from src.layout.style_signature import compute_style_signatures
from src.core.schema import enrich_schema, build_lexicon
from src.validation.type_gates import type_gate


def inspect_roles(pdf_path: str, label: str, schema_dict: dict):
    """Inspect role assignment for a PDF."""
    # Load
    doc = load_document(pdf_path, label=label)
    blocks = extract_blocks(doc)
    
    # Build layout
    layout = build_layout(doc, blocks)
    
    # Build orthogonal graph
    style_signatures = compute_style_signatures(blocks)
    thresholds = compute_spacing_thresholds(blocks)
    orthogonal_graph = build_orthogonal_graph(blocks, thresholds)
    block_by_id = {block.id: block for block in blocks}
    orthogonal_graph["block_by_id"] = block_by_id
    
    # Enrich schema
    enriched = enrich_schema(label, schema_dict)
    schema_fields = enriched.fields
    
    # Build lexicons
    schema_lexicons = {}
    field_types = {}
    for field in schema_fields:
        lexicon = build_lexicon(field)
        schema_lexicons[field.name] = lexicon
        field_types[field.name] = field.type or "text"
    
    # Assign roles
    block_roles = assign_roles(
        blocks,
        orthogonal_graph,
        style_signatures,
        schema_lexicons=schema_lexicons,
        field_types=field_types,
    )
    
    # Print inspection
    print("=" * 80)
    print("ROLE INSPECTION")
    print("=" * 80)
    
    combined_lexicon = set()
    for lexicon in schema_lexicons.values():
        combined_lexicon.update(lexicon)
    
    combined_field_type = next(iter(field_types.values()), None) if field_types else None
    
    for block in blocks:
        role = block_roles.get(block.id, "UNKNOWN")
        text = (block.text or "").strip()
        
        print(f"\nBlock {block.id}: {repr(text[:50])}")
        print(f"  Role: {role}")
        print(f"  Font size: {block.font_size}")
        
        # Check each rule
        is_header = _rule_header(block, blocks, orthogonal_graph, style_signatures)
        is_label = _rule_label(block, orthogonal_graph, combined_field_type, combined_lexicon)
        is_value = _rule_value(block, block_roles, orthogonal_graph, combined_field_type)
        
        print(f"  R-H* (HEADER): {is_header}")
        print(f"  R-L* (LABEL): {is_label}")
        print(f"  R-V* (VALUE): {is_value}")
        
        # Check type-gate
        if combined_field_type:
            passes_gate = type_gate(text, combined_field_type)
            print(f"  Type-gate ({combined_field_type}): {passes_gate}")
        
        # Check neighbors
        if block.id in orthogonal_graph.get("adj", {}):
            adj = orthogonal_graph["adj"][block.id]
            print(f"  Neighbors:")
            for direction in ["up", "down", "left", "right"]:
                neighbor_ids = adj.get(direction, [])
                if neighbor_ids:
                    neighbor_texts = [orthogonal_graph["block_by_id"][nid].text[:30] if nid in orthogonal_graph["block_by_id"] else "?" for nid in neighbor_ids]
                    neighbor_roles = [block_roles.get(nid, "UNKNOWN") for nid in neighbor_ids]
                    print(f"    {direction}: {neighbor_texts} (roles: {neighbor_roles})")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    role_counts = {}
    for role in block_roles.values():
        role_counts[role] = role_counts.get(role, 0) + 1
    for role, count in sorted(role_counts.items()):
        print(f"  {role}: {count}")


if __name__ == "__main__":
    import json
    
    # Load from dataset
    dataset_path = Path("data/samples/dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    
    entry = next((e for e in dataset if e.get("pdf_path") == "oab_1.pdf"), None)
    if not entry:
        print("Error: oab_1.pdf not found in dataset")
        sys.exit(1)
    
    pdf_path = Path("data/samples/oab_1.pdf")
    label = entry["label"]
    schema_dict = entry["extraction_schema"]
    
    inspect_roles(str(pdf_path), label, schema_dict)

