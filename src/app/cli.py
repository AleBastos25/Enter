"""CLI interface for document extraction system."""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.models import Document  # noqa: E402
from src.core.pipeline import Pipeline  # noqa: E402
from src.io.pdf_loader import extract_blocks, iter_page_blocks, load_document  # noqa: E402
from src.layout.builder import build_layout, dump_layout_debug  # noqa: E402
from src.tables.detector import detect_tables  # noqa: E402


def main() -> None:
    """Main CLI entry point."""
    ap = argparse.ArgumentParser(description="Document extraction system CLI")
    ap.add_argument("--probe", action="store_true", help="Print first blocks extracted from PDF")
    ap.add_argument("--run", action="store_true", help="Run full pipeline extraction")
    ap.add_argument("--layout-debug", action="store_true", help="Print layout debug (lines, columns, sections)")
    ap.add_argument("--dump-tables", action="store_true", help="Dump detected tables from PDF")
    ap.add_argument("--multi-page", action="store_true", help="Enable multi-page processing")
    ap.add_argument("--llm", action="store_true", help="Enable LLM fallback (default: from config)")
    ap.add_argument("--no-llm", action="store_true", help="Disable LLM fallback")
    # Embeddings removed - --no-embedding option no longer needed
    ap.add_argument("--pdf", type=str, help="Path to PDF file (supports multi-page)")
    ap.add_argument("--label", type=str, default="unknown", help="Document label/type")
    ap.add_argument("--schema", type=str, help="Path to schema.json (name->description)")
    ap.add_argument("--out", type=str, help="Save output JSON to file (for --run)")
    ap.add_argument("--debug", action="store_true", help="Enable debug diagnostics (candidates, page signals, etc.)")
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
    elif args.layout_debug:
        if not args.pdf:
            ap.error("--layout-debug requires --pdf")
        try:
            doc = load_document(args.pdf, label=args.label)
            blocks = extract_blocks(doc)
            layout = build_layout(doc, blocks)
            dump_layout_debug(layout)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.dump_tables:
        if not args.pdf:
            ap.error("--dump-tables requires --pdf")
        try:
            doc = load_document(args.pdf, label=args.label)
            for page_index, blocks in iter_page_blocks(doc):
                layout = build_layout(doc, blocks)
                pdf_lines = getattr(layout, "pdf_lines", None)
                tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
                print(f"\n=== Page {page_index + 1} ===")
                print(f"Tables found: {len(tables)}")
                for table in tables:
                    print(f"  Table {table.id}: type={table.type}, rows={len(table.rows)}, cols={table.col_count}")
                    for row in table.rows[:3]:  # Show first 3 rows
                        row_cells = [c for c in table.cells if c.row_id == row.id]
                        print(f"    Row {row.id}: {[c.text[:30] for c in row_cells[:4]]}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.run:
        if not args.pdf or not args.label or not args.schema:
            ap.error("--run requires --pdf, --label, and --schema")
        try:
            import yaml
            from pathlib import Path as PathLib

            schema_data = json.loads(Path(args.schema).read_text(encoding="utf-8"))
            
            # Handle both list and dict formats
            if isinstance(schema_data, list):
                # If it's a list, try to find entry with matching label
                schema_dict = None
                for entry in schema_data:
                    if entry.get("label") == args.label:
                        schema_dict = entry.get("extraction_schema", {})
                        break
                if schema_dict is None and schema_data:
                    # Fallback: use first entry's schema
                    schema_dict = schema_data[0].get("extraction_schema", {})
                if not schema_dict:
                    ap.error(f"Could not find extraction_schema for label '{args.label}' in schema file")
            elif isinstance(schema_data, dict):
                if "extraction_schema" in schema_data:
                    schema_dict = schema_data["extraction_schema"]
                else:
                    # Assume it's already a schema dict
                    schema_dict = schema_data
            else:
                ap.error(f"Schema file must be a JSON object or array, got {type(schema_data)}")

            # Override configs based on flags
            if args.no_llm:
                llm_config_path = PathLib("configs/llm.yaml")
                if llm_config_path.exists():
                    with open(llm_config_path, "r", encoding="utf-8") as f:
                        llm_config = yaml.safe_load(f) or {}
                    llm_config["enabled"] = False
                    with open(llm_config_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(llm_config, f)

            # Embeddings removed - no longer needed

            if args.multi_page:
                runtime_config_path = PathLib("configs/runtime.yaml")
                if runtime_config_path.exists():
                    with open(runtime_config_path, "r", encoding="utf-8") as f:
                        runtime_config = yaml.safe_load(f) or {}
                    runtime_config["multi_page"] = True
                    with open(runtime_config_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(runtime_config, f)
                else:
                    # Create default runtime config with multi_page enabled
                    runtime_config = {"multi_page": True}
                    runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(runtime_config_path, "w", encoding="utf-8") as f:
                        yaml.safe_dump(runtime_config, f)

            pipe = Pipeline()
            out = pipe.run(args.label, schema_dict, args.pdf, debug=args.debug)
            
            # v2: Canonical output - only {field: value/null} for --run
            if not args.debug:
                # Extract only field values (no trace)
                canonical_output = {}
                results = out.get("results", {})
                for field_name, field_result in results.items():
                    canonical_output[field_name] = field_result.get("value")
                
                # Save canonical to file if --out specified
            if args.out:
                output_path = Path(args.out)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(canonical_output, f, ensure_ascii=False, indent=2)
                print(f"Output saved to: {output_path}", file=sys.stderr)
            
                # Print canonical to stdout
                print(json.dumps(canonical_output, ensure_ascii=False, indent=2))
            else:
                # --debug: show full trace on console (but still save canonical if --out)
                if args.out:
                    # Save canonical version to file
                    canonical_output = {}
                    results = out.get("results", {})
                    for field_name, field_result in results.items():
                        canonical_output[field_name] = field_result.get("value")
                    output_path = Path(args.out)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(canonical_output, f, ensure_ascii=False, indent=2)
                    print(f"Canonical output saved to: {output_path}", file=sys.stderr)
                
                # Print full trace to console
            print(json.dumps(out, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

