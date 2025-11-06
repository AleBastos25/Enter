"""Test script that compares pipeline results with ground_truth.json.

Shows detailed errors for each field that doesn't match.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def load_ground_truth(ground_truth_path: str) -> Dict[str, Dict[str, Any]]:
    """Load ground truth and index by PDF name.
    
    Args:
        ground_truth_path: Path to ground_truth.json.
        
    Returns:
        Dictionary mapping pdf_name -> ground truth entry.
    """
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
    """Load dataset and index by PDF name.
    
    Args:
        dataset_path: Path to dataset.json.
        
    Returns:
        Dictionary mapping pdf_name -> {label, schema_dict}.
    """
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    
    # Index by PDF name
    schema_by_pdf = {}
    for entry in dataset:
        pdf_path = entry.get("pdf_path", "")
        pdf_name = Path(pdf_path).name if pdf_path else None
        if pdf_name and entry.get("label") and entry.get("extraction_schema"):
            schema_by_pdf[pdf_name] = {
                "label": entry.get("label"),
                "schema": entry.get("extraction_schema", {}),
            }
    
    return schema_by_pdf


def normalize_value(value: Any) -> Optional[str]:
    """Normalize value for comparison (handle None, empty strings, etc.).
    
    Args:
        value: Value to normalize.
        
    Returns:
        Normalized string or None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return str(value).strip() if str(value).strip() else None


def compare_field(
    field_name: str,
    expected_value: Any,
    actual_value: Any,
    actual_trace: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Compare expected vs actual value for a field.
    
    Args:
        field_name: Field name.
        expected_value: Expected value from ground truth.
        actual_value: Actual value from pipeline.
        actual_trace: Optional trace from pipeline result.
        
    Returns:
        Error dict if mismatch, None if match.
    """
    expected_norm = normalize_value(expected_value)
    actual_norm = normalize_value(actual_value)
    
    # Both None: correct
    if expected_norm is None and actual_norm is None:
        return None
    
    # One is None, other is not: error
    if expected_norm is None and actual_norm is not None:
        return {
            "field": field_name,
            "error_type": "extra_extraction",
            "expected": None,
            "actual": actual_norm,
            "message": f"Field '{field_name}': Expected null but got '{actual_norm}'",
            "trace": actual_trace,
        }
    
    if expected_norm is not None and actual_norm is None:
        return {
            "field": field_name,
            "error_type": "missing_extraction",
            "expected": expected_norm,
            "actual": None,
            "message": f"Field '{field_name}': Expected '{expected_norm}' but got null",
            "trace": actual_trace,
        }
    
    # Both not None: compare strings (case-insensitive, normalize spaces)
    expected_clean = expected_norm.lower().strip()
    actual_clean = actual_norm.lower().strip()
    
    # Normalize spaces
    expected_clean = " ".join(expected_clean.split())
    actual_clean = " ".join(actual_clean.split())
    
    if expected_clean != actual_clean:
        return {
            "field": field_name,
            "error_type": "wrong_value",
            "expected": expected_norm,
            "actual": actual_norm,
            "message": f"Field '{field_name}': Expected '{expected_norm}' but got '{actual_norm}'",
            "trace": actual_trace,
        }
    
    return None  # Match


def compare_results(
    pdf_name: str,
    expected: Dict[str, Any],
    actual: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Compare expected vs actual results and return list of errors.
    
    Args:
        pdf_name: PDF name.
        expected: Expected result from ground truth.
        actual: Actual result from pipeline.
        
    Returns:
        List of error dicts.
    """
    errors = []
    
    expected_result = expected.get("result", {})
    actual_result = actual.get("results", {})
    
    # Get all field names from both
    all_fields = set(expected_result.keys()) | set(actual_result.keys())
    
    # Check each field
    for field_name in sorted(all_fields):
        expected_value = expected_result.get(field_name)
        actual_field_data = actual_result.get(field_name)
        
        # Extract value and trace from actual result
        if actual_field_data is None:
            actual_value = None
            actual_trace = None
        elif isinstance(actual_field_data, dict):
            actual_value = actual_field_data.get("value")
            actual_trace = actual_field_data.get("trace", {})
        else:
            actual_value = actual_field_data
            actual_trace = {}
        
        # Compare
        error = compare_field(field_name, expected_value, actual_value, actual_trace)
        if error:
            error["pdf"] = pdf_name
            errors.append(error)
    
    return errors


def print_error_summary(errors: List[Dict[str, Any]]) -> None:
    """Print summary of errors by type.
    
    Args:
        errors: List of error dicts.
    """
    if not errors:
        return
    
    by_type = {}
    for error in errors:
        error_type = error.get("error_type", "unknown")
        if error_type not in by_type:
            by_type[error_type] = []
        by_type[error_type].append(error)
    
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"ERROR SUMMARY BY TYPE", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    for error_type, type_errors in sorted(by_type.items()):
        print(f"  {error_type}: {len(type_errors)} error(s)", file=sys.stderr)
        # Show first 3 examples
        for error in type_errors[:3]:
            print(f"    - {error.get('pdf')}: {error.get('field')} - {error.get('message', '')[:60]}", file=sys.stderr)
        if len(type_errors) > 3:
            print(f"    ... and {len(type_errors) - 3} more", file=sys.stderr)


def main():
    """Main entry point."""
    # Paths
    project_root = Path(__file__).parent.parent
    ground_truth_path = project_root / "ground_truth.json"
    dataset_path = project_root / "data" / "samples" / "dataset.json"
    samples_dir = project_root / "data" / "samples"
    
    # Check paths
    if not ground_truth_path.exists():
        print(f"ERROR: {ground_truth_path} not found", file=sys.stderr)
        sys.exit(1)
    
    if not dataset_path.exists():
        print(f"ERROR: {dataset_path} not found", file=sys.stderr)
        sys.exit(1)
    
    if not samples_dir.exists():
        print(f"ERROR: {samples_dir} not found", file=sys.stderr)
        sys.exit(1)
    
    # Load data
    print(f"Loading ground truth from {ground_truth_path}", file=sys.stderr)
    gt_by_pdf = load_ground_truth(str(ground_truth_path))
    
    print(f"Loading dataset from {dataset_path}", file=sys.stderr)
    schema_by_pdf = load_dataset(str(dataset_path))
    
    # Initialize pipeline
    pipeline = Pipeline()
    
    # Process each PDF
    all_errors: List[Dict[str, Any]] = []
    processed_count = 0
    
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"TESTING AGAINST GROUND TRUTH", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    
    for pdf_name in sorted(gt_by_pdf.keys()):
        expected = gt_by_pdf[pdf_name]
        schema_info = schema_by_pdf.get(pdf_name)
        
        if not schema_info:
            print(f"  WARNING: {pdf_name} not found in dataset.json, skipping", file=sys.stderr)
            continue
        
        label = schema_info["label"]
        schema_dict = schema_info["schema"]
        pdf_path = samples_dir / pdf_name
        
        if not pdf_path.exists():
            print(f"  WARNING: {pdf_path} not found, skipping", file=sys.stderr)
            continue
        
        print(f"\n  Processing {pdf_name} (label='{label}')", file=sys.stderr)
        
        # Run pipeline
        try:
            actual = pipeline.run(label, schema_dict, str(pdf_path), debug=False)
            processed_count += 1
            
            # Compare with ground truth
            errors = compare_results(pdf_name, expected, actual)
            
            if errors:
                print(f"  ✗ Found {len(errors)} error(s):", file=sys.stderr)
                for error in errors:
                    print(f"    - {error['field']}: {error['message']}", file=sys.stderr)
                    if error.get("trace"):
                        # Show key trace info
                        trace = error["trace"]
                        if "relation" in trace:
                            print(f"      Relation: {trace['relation']}", file=sys.stderr)
                        if "reason" in trace:
                            print(f"      Reason: {trace['reason']}", file=sys.stderr)
                        if "block_id" in trace:
                            print(f"      Block ID: {trace['block_id']}", file=sys.stderr)
                all_errors.extend(errors)
            else:
                print(f"  ✓ All fields match ground truth!", file=sys.stderr)
        
        except Exception as e:
            import traceback
            print(f"  ERROR: Exception during processing: {e}", file=sys.stderr)
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
    print(f"FINAL SUMMARY", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    print(f"Total PDFs processed: {processed_count}", file=sys.stderr)
    print(f"Total errors: {len(all_errors)}", file=sys.stderr)
    
    if all_errors:
        print_error_summary(all_errors)
        
        # Print detailed errors
        print(f"\n{'='*80}", file=sys.stderr)
        print(f"DETAILED ERRORS", file=sys.stderr)
        print(f"{'='*80}", file=sys.stderr)
        
        for error in all_errors:
            print(f"\nPDF: {error.get('pdf')}", file=sys.stderr)
            print(f"  Field: {error.get('field')}", file=sys.stderr)
            print(f"  Type: {error.get('error_type')}", file=sys.stderr)
            print(f"  Expected: {error.get('expected')}", file=sys.stderr)
            print(f"  Got: {error.get('actual')}", file=sys.stderr)
            print(f"  Message: {error.get('message')}", file=sys.stderr)
            if error.get("trace"):
                print(f"  Trace: {json.dumps(error['trace'], indent=4)}", file=sys.stderr)
        
        sys.exit(1)
    else:
        print(f"\n✓ All tests passed! No errors found.", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
