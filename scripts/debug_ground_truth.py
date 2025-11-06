"""Script to debug pipeline results against ground truth."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def load_ground_truth(ground_truth_path: str) -> Dict[str, Dict[str, Any]]:
    """Load ground truth and index by PDF name."""
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    
    # Index by PDF name
    gt_by_pdf = {}
    for entry in gt_data:
        pdf_name = entry.get("pdf")
        if pdf_name:
            gt_by_pdf[pdf_name] = entry
    
    return gt_by_pdf


def load_dataset(dataset_path: str) -> Dict[str, Dict[str, Any]]:
    """Load dataset and index by PDF name."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset_data = json.load(f)
    
    # Index by PDF name
    schema_by_pdf = {}
    for entry in dataset_data:
        pdf_name = Path(entry.get("pdf_path", "")).name
        if pdf_name and entry.get("label") and entry.get("extraction_schema"):
            schema_by_pdf[pdf_name] = {
                "label": entry.get("label"),
                "schema": entry.get("extraction_schema"),
            }
    
    return schema_by_pdf


def compare_results(
    pdf_name: str,
    expected: Dict[str, Any],
    actual: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Compare expected vs actual results and return list of errors."""
    errors = []
    
    expected_result = expected.get("result", {})
    actual_result = actual.get("results", {})
    
    # Check all expected fields
    for field_name, expected_value in expected_result.items():
        actual_field_data = actual_result.get(field_name)
        
        if actual_field_data is None:
            errors.append({
                "pdf": pdf_name,
                "field": field_name,
                "error_type": "missing_field",
                "expected": expected_value,
                "actual": None,
                "message": f"Field '{field_name}' not found in results",
            })
            continue
        
        # Extract value from actual result (may be dict with 'value' key or direct value)
        if isinstance(actual_field_data, dict):
            actual_value = actual_field_data.get("value")
            actual_confidence = actual_field_data.get("confidence", 0.0)
            actual_source = actual_field_data.get("source", "none")
            actual_trace = actual_field_data.get("trace", {})
        else:
            actual_value = actual_field_data
            actual_confidence = 0.0
            actual_source = "unknown"
            actual_trace = {}
        
        # Compare values (handle None/null)
        expected_is_none = expected_value is None
        actual_is_none = actual_value is None
        
        if expected_is_none and actual_is_none:
            continue  # Both None, correct
        
        if expected_is_none and not actual_is_none:
            errors.append({
                "pdf": pdf_name,
                "field": field_name,
                "error_type": "unexpected_value",
                "expected": None,
                "actual": actual_value,
                "confidence": actual_confidence,
                "source": actual_source,
                "trace": actual_trace,
                "message": f"Expected None but got '{actual_value}'",
            })
        elif not expected_is_none and actual_is_none:
            errors.append({
                "pdf": pdf_name,
                "field": field_name,
                "error_type": "missing_value",
                "expected": expected_value,
                "actual": None,
                "confidence": actual_confidence,
                "source": actual_source,
                "trace": actual_trace,
                "message": f"Expected '{expected_value}' but got None",
            })
        elif expected_value != actual_value:
            errors.append({
                "pdf": pdf_name,
                "field": field_name,
                "error_type": "value_mismatch",
                "expected": expected_value,
                "actual": actual_value,
                "confidence": actual_confidence,
                "source": actual_source,
                "trace": actual_trace,
                "message": f"Expected '{expected_value}' but got '{actual_value}'",
            })
    
    return errors


def main():
    """Main entry point."""
    ground_truth_path = Path(__file__).parent.parent / "ground_truth.json"
    dataset_path = Path(__file__).parent.parent / "data" / "samples" / "dataset.json"
    samples_dir = Path(__file__).parent.parent / "data" / "samples"
    
    if not ground_truth_path.exists():
        print(f"ERROR: Ground truth file not found: {ground_truth_path}", file=sys.stderr)
        sys.exit(1)
    
    if not dataset_path.exists():
        print(f"ERROR: Dataset file not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)
    
    # Load ground truth and dataset
    gt_by_pdf = load_ground_truth(str(ground_truth_path))
    schema_by_pdf = load_dataset(str(dataset_path))
    
    print(f"Loaded {len(gt_by_pdf)} ground truth entries", file=sys.stderr)
    print(f"Loaded {len(schema_by_pdf)} schema entries", file=sys.stderr)
    
    # Initialize pipeline
    pipeline = Pipeline()
    
    # Process each PDF in ground truth
    all_errors = []
    all_results = []
    
    for pdf_name, expected in gt_by_pdf.items():
        print(f"\n{'='*80}", file=sys.stderr)
        print(f"Processing: {pdf_name}", file=sys.stderr)
        print(f"{'='*80}", file=sys.stderr)
        
        # Get schema for this PDF
        if pdf_name not in schema_by_pdf:
            print(f"  ERROR: No schema found for {pdf_name}", file=sys.stderr)
            all_errors.append({
                "pdf": pdf_name,
                "field": "ALL",
                "error_type": "schema_not_found",
                "message": f"No schema found in dataset.json for {pdf_name}",
            })
            continue
        
        schema_info = schema_by_pdf[pdf_name]
        label = schema_info["label"]
        schema_dict = schema_info["schema"]
        
        # Find PDF file
        pdf_path = samples_dir / pdf_name
        if not pdf_path.exists():
            print(f"  ERROR: PDF file not found: {pdf_path}", file=sys.stderr)
            all_errors.append({
                "pdf": pdf_name,
                "field": "ALL",
                "error_type": "pdf_not_found",
                "message": f"PDF file not found: {pdf_path}",
            })
            continue
        
        # Run pipeline
        try:
            print(f"  Running pipeline with label='{label}', fields={list(schema_dict.keys())}", file=sys.stderr)
            actual = pipeline.run(label, schema_dict, str(pdf_path), debug=True)
            all_results.append(actual)
            
            # Compare with ground truth
            errors = compare_results(pdf_name, expected, actual)
            
            if errors:
                print(f"  Found {len(errors)} error(s):", file=sys.stderr)
                for error in errors:
                    print(f"    - {error['field']}: {error['message']}", file=sys.stderr)
                    if error.get("trace"):
                        print(f"      Trace: {json.dumps(error['trace'], indent=6)}", file=sys.stderr)
                all_errors.extend(errors)
            else:
                print(f"  ✓ All fields match ground truth!", file=sys.stderr)
        
        except Exception as e:
            import traceback
            print(f"  ERROR: Exception during processing: {e}", file=sys.stderr)
            if True:  # Always show traceback
                print(traceback.format_exc(), file=sys.stderr)
            all_errors.append({
                "pdf": pdf_name,
                "field": "ALL",
                "error_type": "exception",
                "message": str(e),
                "traceback": traceback.format_exc(),
            })
    
    # Print summary
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"SUMMARY", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    print(f"Total PDFs processed: {len(gt_by_pdf)}", file=sys.stderr)
    print(f"Total errors: {len(all_errors)}", file=sys.stderr)
    
    # Group errors by type
    errors_by_type = {}
    for error in all_errors:
        error_type = error.get("error_type", "unknown")
        if error_type not in errors_by_type:
            errors_by_type[error_type] = []
        errors_by_type[error_type].append(error)
    
    print(f"\nErrors by type:", file=sys.stderr)
    for error_type, errors in errors_by_type.items():
        print(f"  {error_type}: {len(errors)}", file=sys.stderr)
    
    # Group errors by PDF
    errors_by_pdf = {}
    for error in all_errors:
        pdf_name = error.get("pdf", "unknown")
        if pdf_name not in errors_by_pdf:
            errors_by_pdf[pdf_name] = []
        errors_by_pdf[pdf_name].append(error)
    
    print(f"\nErrors by PDF:", file=sys.stderr)
    for pdf_name, errors in errors_by_pdf.items():
        print(f"  {pdf_name}: {len(errors)} error(s)", file=sys.stderr)
    
    # Output detailed errors as JSON
    output = {
        "summary": {
            "total_pdfs": len(gt_by_pdf),
            "total_errors": len(all_errors),
            "errors_by_type": {k: len(v) for k, v in errors_by_type.items()},
            "errors_by_pdf": {k: len(v) for k, v in errors_by_pdf.items()},
        },
        "errors": all_errors,
        "results": all_results,
    }
    
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

