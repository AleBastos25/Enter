"""Debug script for v3.0 pipeline - detailed inspection of each step."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline
from src.core.schema import enrich_schema, build_lexicon
from src.io.pdf_loader import extract_blocks, load_document
from src.layout.builder import build_layout
from src.graph.spacing_model import compute_spacing_thresholds
from src.graph.orthogonal_edges import build_orthogonal_graph
from src.graph.roles_rules import assign_roles
from src.layout.style_signature import compute_style_signatures
from src.matching.candidates import build_candidate_sets
from src.matching.label_value import find_label_value_pairs
from src.matching.assign import solve_assignment
from src.core.doc_profile import build_doc_profile
from src.tables.detector import detect_tables


def debug_single_pdf(
    pdf_path: str,
    label: str,
    schema_dict: Dict[str, str],
    output_path: str = None,
) -> Dict[str, Any]:
    """Debug a single PDF through the v3.0 pipeline.
    
    Args:
        pdf_path: Path to PDF file
        label: Document label
        schema_dict: Schema dictionary
        output_path: Optional path to save debug output
        
    Returns:
        Dictionary with debug information
    """
    debug_info = {
        "pdf_path": pdf_path,
        "label": label,
        "schema": schema_dict,
        "steps": {},
    }
    
    print("=" * 80)
    print(f"DEBUG: {Path(pdf_path).name}")
    print("=" * 80)
    
    # Step 1: Load document
    print("\n[1] Loading document...")
    doc = load_document(pdf_path, label=label)
    blocks = extract_blocks(doc)
    debug_info["steps"]["load"] = {
        "blocks_count": len(blocks),
        "first_block_text": blocks[0].text[:50] if blocks else None,
    }
    print(f"  ✓ Loaded {len(blocks)} blocks")
    
    # Step 2: Build layout
    print("\n[2] Building layout...")
    layout = build_layout(doc, blocks)
    debug_info["steps"]["layout"] = {
        "has_graph_v2": hasattr(layout, "graph_v2"),
        "has_grid": hasattr(layout, "grid"),
        "blocks_count": len(layout.blocks) if hasattr(layout, "blocks") else 0,
    }
    print(f"  ✓ Layout built")
    
    # Step 3: Detect tables
    print("\n[3] Detecting tables...")
    pdf_lines = getattr(layout, "pdf_lines", None)
    tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
    debug_info["steps"]["tables"] = {
        "tables_count": len(tables),
        "table_types": [t.type for t in tables] if tables else [],
    }
    print(f"  ✓ Found {len(tables)} tables")
    
    # Step 3.5: Enrich schema (needed for roles and other steps)
    print("\n[3.5] Enriching schema...")
    enriched = enrich_schema(label, schema_dict)
    schema_fields = enriched.fields
    debug_info["steps"]["schema"] = {
        "fields_count": len(schema_fields),
        "field_names": [f.name for f in schema_fields],
    }
    print(f"  ✓ Schema enriched: {len(schema_fields)} fields")
    
    # Step 4: Build orthogonal graph
    print("\n[4] Building orthogonal graph...")
    style_signatures = compute_style_signatures(blocks)
    thresholds = compute_spacing_thresholds(blocks)
    orthogonal_graph = build_orthogonal_graph(blocks, thresholds)
    debug_info["steps"]["orthogonal_graph"] = {
        "has_graph": orthogonal_graph is not None,
        "adj_keys": list(orthogonal_graph.get("adj", {}).keys())[:10] if orthogonal_graph else [],
        "thresholds": {
            "tau_same_line": thresholds.tau_same_line if hasattr(thresholds, "tau_same_line") else None,
            "tau_same_column": thresholds.tau_same_column if hasattr(thresholds, "tau_same_column") else None,
        },
    }
    print(f"  ✓ Orthogonal graph built")
    if orthogonal_graph:
        adj_count = sum(len(v) for v in orthogonal_graph.get("adj", {}).values())
        print(f"    Total edges: {adj_count}")
    
    # Step 5: Assign roles
    print("\n[5] Assigning roles...")
    try:
        # Build lexicons and field types for roles
        schema_lexicons = {}
        field_types = {}
        for field in schema_fields:
            lexicon = build_lexicon(field)
            schema_lexicons[field.name] = lexicon
            field_types[field.name] = field.type or "text"
        
        block_roles = assign_roles(
            blocks,
            orthogonal_graph,
            style_signatures,
            schema_lexicons,
            field_types,
        )
        debug_info["steps"]["roles"] = {
            "roles_count": len(block_roles),
            "role_distribution": {
                role: sum(1 for r in block_roles.values() if r == role)
                for role in ["HEADER", "LABEL", "VALUE"]
            },
        }
        print(f"  ✓ Roles assigned: {len(block_roles)} blocks")
        for role, count in debug_info["steps"]["roles"]["role_distribution"].items():
            print(f"    {role}: {count}")
    except Exception as e:
        print(f"  ✗ Error assigning roles: {e}")
        debug_info["steps"]["roles"] = {"error": str(e)}
    
    # Step 6: Build lexicons
    print("\n[7] Building lexicons...")
    lexicons = {}
    for field in schema_fields:
        lexicon = build_lexicon(field)
        lexicons[field.name] = list(lexicon)[:10]  # First 10 tokens
    debug_info["steps"]["lexicons"] = lexicons
    print(f"  ✓ Lexicons built for {len(lexicons)} fields")
    
    # Step 7: Build doc profile
    print("\n[8] Building doc profile...")
    grid = getattr(layout, "grid", None)
    graph_v2 = getattr(layout, "graph_v2", None)
    profile = build_doc_profile(blocks, pdf_lines, graph_v2, grid)
    debug_info["steps"]["profile"] = {
        "has_profile": profile is not None,
    }
    print(f"  ✓ Doc profile built")
    
    # Step 8: Build candidate sets
    print("\n[9] Building candidate sets...")
    try:
        candidate_sets = build_candidate_sets(
            blocks,
            layout,
            schema_fields,
            profile,
            tables,
        )
        debug_info["steps"]["candidates"] = {}
        total_candidates = 0
        for field_name, candidates in candidate_sets.items():
            count = len(candidates)
            total_candidates += count
            debug_info["steps"]["candidates"][field_name] = {
                "count": count,
                "first_candidate": {
                    "candidate_id": candidates[0].candidate_id if candidates else None,
                    "relation": candidates[0].relation if candidates else None,
                    "snippet": candidates[0].snippet[:50] if candidates else None,
                } if candidates else None,
            }
        debug_info["steps"]["candidates"]["total"] = total_candidates
        print(f"  ✓ Candidate sets built: {total_candidates} total candidates")
        for field_name, info in debug_info["steps"]["candidates"].items():
            if field_name != "total":
                print(f"    {field_name}: {info['count']} candidates")
    except Exception as e:
        print(f"  ✗ Error building candidates: {e}")
        import traceback
        debug_info["steps"]["candidates"] = {"error": str(e), "traceback": traceback.format_exc()}
        candidate_sets = {}
    
    # Step 9: Find label-value pairs
    print("\n[10] Finding label-value pairs...")
    try:
        # Attach orthogonal graph and roles to layout
        object.__setattr__(layout, "orthogonal_graph", orthogonal_graph)
        object.__setattr__(layout, "style_signatures", style_signatures)
        object.__setattr__(layout, "block_roles", block_roles if "block_roles" in locals() else {})
        
        label_value_pairs = {}
        # Need to build block_by_id for orthogonal graph
        block_by_id = {block.id: block for block in blocks}
        orthogonal_graph_with_blocks = {
            **orthogonal_graph,
            "block_by_id": block_by_id,
        }
        
        for field in schema_fields:
            lexicon = build_lexicon(field)
            pairs = find_label_value_pairs(
                orthogonal_graph_with_blocks,
                blocks,
                block_roles if "block_roles" in locals() else {},
                field,
                lexicon,
                style_signatures,
            )
            label_value_pairs[field.name] = len(pairs)
        debug_info["steps"]["label_value_pairs"] = label_value_pairs
        print(f"  ✓ Label-value pairs found")
        for field_name, count in label_value_pairs.items():
            print(f"    {field_name}: {count} pairs")
    except Exception as e:
        print(f"  ✗ Error finding label-value pairs: {e}")
        import traceback
        debug_info["steps"]["label_value_pairs"] = {"error": str(e), "traceback": traceback.format_exc()}
    
    # Step 10: Run full pipeline
    print("\n[11] Running full pipeline...")
    try:
        pipeline = Pipeline()
        result = pipeline.run(label, schema_dict, pdf_path, debug=False)
        
        debug_info["steps"]["pipeline_result"] = {}
        results = result.get("results", {})
        for field_name in schema_dict.keys():
            field_result = results.get(field_name, {})
            value = field_result.get("value") if isinstance(field_result, dict) else field_result
            source = field_result.get("source", "unknown") if isinstance(field_result, dict) else "unknown"
            debug_info["steps"]["pipeline_result"][field_name] = {
                "value": value,
                "source": source,
            }
        
        print(f"  ✓ Pipeline completed")
        for field_name, info in debug_info["steps"]["pipeline_result"].items():
            value_str = str(info["value"])[:50] if info["value"] else "null"
            print(f"    {field_name}: {value_str} (source: {info['source']})")
    except Exception as e:
        print(f"  ✗ Error in pipeline: {e}")
        import traceback
        debug_info["steps"]["pipeline_result"] = {"error": str(e), "traceback": traceback.format_exc()}
    
    # Save debug output
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(debug_info, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n✓ Debug info saved to: {output_path}")
    
    return debug_info


def main():
    """Main function."""
    import argparse
    
    ap = argparse.ArgumentParser(description="Debug v3.0 pipeline for a single PDF")
    ap.add_argument("--pdf", type=str, required=True, help="Path to PDF file")
    ap.add_argument("--label", type=str, required=True, help="Document label")
    ap.add_argument("--schema", type=str, help="Path to schema JSON file (or use dataset.json)")
    ap.add_argument("--dataset", type=str, default="data/samples/dataset.json", help="Path to dataset.json")
    ap.add_argument("--output", type=str, help="Path to save debug output JSON")
    
    args = ap.parse_args()
    
    # Load schema
    if args.schema:
        with open(args.schema, "r", encoding="utf-8") as f:
            schema_dict = json.load(f)
    else:
        # Load from dataset.json
        dataset_path = Path(args.dataset)
        if not dataset_path.exists():
            print(f"Error: Dataset file not found: {dataset_path}", file=sys.stderr)
            sys.exit(1)
        
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
        
        # Find matching entry
        pdf_name = Path(args.pdf).name
        entry = next((e for e in dataset if e.get("pdf_path") == pdf_name), None)
        if not entry:
            print(f"Error: No entry found in dataset for {pdf_name}", file=sys.stderr)
            sys.exit(1)
        
        schema_dict = entry.get("extraction_schema", {})
        label = entry.get("label", args.label)
    
    # Run debug
    debug_info = debug_single_pdf(
        args.pdf,
        label,
        schema_dict,
        args.output,
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

