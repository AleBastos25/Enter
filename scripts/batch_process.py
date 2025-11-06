"""Batch process PDFs from a folder and return consolidated JSON output."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def process_folder(
    folder_path: str,
    output_path: str = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """Process all PDFs in a folder and return consolidated results.
    
    Automatically detects schema from dataset.json in the folder.
    Each PDF is processed with its corresponding schema from dataset.json.
    
    Args:
        folder_path: Path to folder containing PDFs and dataset.json
        output_path: Optional path to save output JSON
        debug: Enable debug diagnostics
        
    Returns:
        Dictionary with consolidated results for all PDFs
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")
    
    # Look for dataset.json in the folder
    dataset_file = folder / "dataset.json"
    if not dataset_file.exists():
        raise ValueError(f"dataset.json not found in folder: {folder_path}")
    
    # Load dataset
    dataset_data = json.loads(dataset_file.read_text(encoding="utf-8"))
    
    if not isinstance(dataset_data, list):
        raise ValueError(f"dataset.json must be a list of entries, got {type(dataset_data)}")
    
    # Build mapping: pdf_name -> (label, schema_dict)
    pdf_to_schema = {}
    for entry in dataset_data:
        pdf_name = entry.get("pdf_path")
        if not pdf_name:
            continue
        
        # Normalize PDF name (remove path if present)
        pdf_name = Path(pdf_name).name
        
        label = entry.get("label")
        schema_dict = entry.get("extraction_schema", {})
        
        if label and schema_dict:
            pdf_to_schema[pdf_name] = (label, schema_dict)
    
    if not pdf_to_schema:
        raise ValueError("No valid entries found in dataset.json (missing label or extraction_schema)")
    
    # Find all PDFs
    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        raise ValueError(f"No PDF files found in folder: {folder_path}")
    
    print(f"Found {len(pdf_files)} PDF files in {folder_path}", file=sys.stderr)
    print(f"Found {len(pdf_to_schema)} schema entries in dataset.json", file=sys.stderr)
    
    # Initialize pipeline
    pipeline = Pipeline()
    
    # Process each PDF
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    
    for i, pdf_path in enumerate(pdf_files, 1):
        pdf_name = pdf_path.name
        print(f"[{i}/{len(pdf_files)}] Processing: {pdf_name}", file=sys.stderr)
        
        # Find schema for this PDF
        if pdf_name not in pdf_to_schema:
            error_info = {
                "pdf_name": pdf_name,
                "pdf_path": str(pdf_path),
                "error": f"No schema found in dataset.json for {pdf_name}",
                "error_type": "SchemaNotFound",
            }
            errors.append(error_info)
            print(f"  ERROR: No schema found in dataset.json for {pdf_name}", file=sys.stderr)
            continue
        
        label, schema_dict = pdf_to_schema[pdf_name]
        print(f"  Using label: {label}, schema fields: {len(schema_dict)}", file=sys.stderr)
        
        try:
            result = pipeline.run(label, schema_dict, str(pdf_path), debug=debug)
            
            # Add PDF name to result
            result["pdf_name"] = pdf_name
            result["pdf_path"] = str(pdf_path)
            result["label"] = label  # Ensure label is in result
            
            results.append(result)
        except Exception as e:
            import traceback
            error_info = {
                "pdf_name": pdf_name,
                "pdf_path": str(pdf_path),
                "label": label,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }
            errors.append(error_info)
            print(f"  ERROR: {e}", file=sys.stderr)
            if debug:
                print(traceback.format_exc(), file=sys.stderr)
    
    # Convert to canonical format: [{"pdf": "...", "label": "...", "result": {"field": value}}]
    canonical_results = []
    for result in results:
        pdf_name = result.get("pdf_name", "unknown.pdf")
        label = result.get("label", "unknown")
        results_dict = result.get("results", {})
        
        # Extract only values (ignore confidence, source, trace)
        canonical_result = {}
        for field_name, field_data in results_dict.items():
            if isinstance(field_data, dict):
                value = field_data.get("value")
            else:
                value = field_data
            canonical_result[field_name] = value
        
        canonical_results.append({
            "pdf": pdf_name,
            "label": label,
            "result": canonical_result
        })
    
    # Return canonical format directly (list of results)
    output = canonical_results
    
    # Save to file if specified
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\nOutput saved to: {output_path}", file=sys.stderr)
    
    return output


def main():
    """CLI entry point."""
    import argparse
    
    ap = argparse.ArgumentParser(
        description="Batch process PDFs from a folder and return consolidated JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process folder with dataset.json (automatic schema detection):
  python scripts/batch_process.py --folder data/samples --out output.json
  
The script will:
  1. Look for dataset.json in the folder
  2. Match each PDF with its schema from dataset.json (by pdf_path)
  3. Process each PDF with its corresponding label and schema
  4. Return consolidated JSON with all results
        """
    )
    ap.add_argument("--folder", type=str, required=True, help="Path to folder containing PDFs and dataset.json")
    ap.add_argument("--out", type=str, required=True, help="Path to save output JSON file (required)")
    ap.add_argument("--debug", action="store_true", help="Enable debug diagnostics")
    
    args = ap.parse_args()
    
    try:
        output = process_folder(
            args.folder,
            output_path=args.out,
            debug=args.debug,
        )
        
        # Print to stdout
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

