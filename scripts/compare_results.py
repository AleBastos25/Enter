#!/usr/bin/env python3
"""Compare batch process results with ground truth."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

def load_json(path: str) -> Any:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def compare_results(ground_truth: List[Dict], results: List[Dict]) -> Dict[str, Any]:
    """Compare results with ground truth.
    
    Returns:
        Dictionary with comparison metrics and detailed differences.
    """
    # Build index by (pdf, label)
    gt_index = {}
    for entry in ground_truth:
        key = (entry["pdf"], entry["label"])
        gt_index[key] = entry["result"]
    
    results_index = {}
    for entry in results:
        key = (entry["pdf"], entry["label"])
        results_index[key] = entry["result"]
    
    # Compare
    comparison = {
        "total_pdfs": len(ground_truth),
        "processed_pdfs": len(results),
        "matches": [],
        "mismatches": [],
        "missing": [],
        "extra": [],
        "metrics": {
            "total_fields": 0,
            "correct_fields": 0,
            "incorrect_fields": 0,
            "missing_fields": 0,
            "extra_fields": 0,
        }
    }
    
    # Compare each PDF
    for gt_key, gt_result in gt_index.items():
        pdf_name, label = gt_key
        result_data = results_index.get(gt_key, {})
        
        if not result_data:
            comparison["missing"].append({
                "pdf": pdf_name,
                "label": label,
                "expected_fields": list(gt_result.keys())
            })
            comparison["metrics"]["missing_fields"] += len(gt_result)
            continue
        
        # Compare fields
        pdf_comparison = {
            "pdf": pdf_name,
            "label": label,
            "fields": {},
            "correct": 0,
            "incorrect": 0,
            "missing": 0,
            "extra": 0,
        }
        
        # Check expected fields
        for field_name, expected_value in gt_result.items():
            comparison["metrics"]["total_fields"] += 1
            actual_value = result_data.get(field_name)
            
            # Normalize None/null values
            if expected_value is None:
                expected_value = None
            if actual_value is None:
                actual_value = None
            
            # Compare values
            if expected_value == actual_value:
                pdf_comparison["fields"][field_name] = {
                    "status": "correct",
                    "expected": expected_value,
                    "actual": actual_value,
                }
                pdf_comparison["correct"] += 1
                comparison["metrics"]["correct_fields"] += 1
            else:
                pdf_comparison["fields"][field_name] = {
                    "status": "incorrect",
                    "expected": expected_value,
                    "actual": actual_value,
                }
                pdf_comparison["incorrect"] += 1
                comparison["metrics"]["incorrect_fields"] += 1
        
        # Check extra fields
        for field_name in result_data:
            if field_name not in gt_result:
                pdf_comparison["fields"][field_name] = {
                    "status": "extra",
                    "expected": None,
                    "actual": result_data[field_name],
                }
                pdf_comparison["extra"] += 1
                comparison["metrics"]["extra_fields"] += 1
        
        # Categorize PDF
        if pdf_comparison["incorrect"] == 0 and pdf_comparison["missing"] == 0 and pdf_comparison["extra"] == 0:
            comparison["matches"].append(pdf_comparison)
        else:
            comparison["mismatches"].append(pdf_comparison)
    
    # Check for extra PDFs (in results but not in ground truth)
    for result_key in results_index:
        if result_key not in gt_index:
            comparison["extra"].append({
                "pdf": result_key[0],
                "label": result_key[1],
                "fields": list(results_index[result_key].keys())
            })
    
    # Calculate accuracy
    if comparison["metrics"]["total_fields"] > 0:
        comparison["metrics"]["accuracy"] = (
            comparison["metrics"]["correct_fields"] / comparison["metrics"]["total_fields"]
        )
    else:
        comparison["metrics"]["accuracy"] = 0.0
    
    return comparison

def main():
    """CLI entry point."""
    import argparse
    
    ap = argparse.ArgumentParser(
        description="Compare batch process results with ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--ground-truth", type=str, required=True, help="Path to ground truth JSON file")
    ap.add_argument("--results", type=str, required=True, help="Path to results JSON file")
    ap.add_argument("--output", type=str, help="Optional path to save comparison JSON")
    
    args = ap.parse_args()
    
    # Load files
    ground_truth = load_json(args.ground_truth)
    results = load_json(args.results)
    
    # Compare
    comparison = compare_results(ground_truth, results)
    
    # Print summary
    print("=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"Total PDFs in ground truth: {comparison['total_pdfs']}")
    print(f"PDFs processed: {comparison['processed_pdfs']}")
    print(f"PDFs missing: {len(comparison['missing'])}")
    print(f"PDFs extra: {len(comparison['extra'])}")
    print()
    print("Field-level metrics:")
    print(f"  Total fields: {comparison['metrics']['total_fields']}")
    print(f"  Correct: {comparison['metrics']['correct_fields']}")
    print(f"  Incorrect: {comparison['metrics']['incorrect_fields']}")
    print(f"  Missing: {comparison['metrics']['missing_fields']}")
    print(f"  Extra: {comparison['metrics']['extra_fields']}")
    print(f"  Accuracy: {comparison['metrics']['accuracy']:.2%}")
    print()
    print(f"Perfect matches: {len(comparison['matches'])}")
    print(f"Mismatches: {len(comparison['mismatches'])}")
    
    # Print mismatches
    if comparison["mismatches"]:
        print("\n" + "=" * 60)
        print("MISMATCHES:")
        print("=" * 60)
        for mismatch in comparison["mismatches"]:
            print(f"\n{mismatch['pdf']} ({mismatch['label']}):")
            print(f"  Correct: {mismatch['correct']}, Incorrect: {mismatch['incorrect']}, Missing: {mismatch['missing']}, Extra: {mismatch['extra']}")
            for field_name, field_info in mismatch["fields"].items():
                if field_info["status"] != "correct":
                    print(f"    {field_name}:")
                    print(f"      Expected: {field_info['expected']}")
                    print(f"      Actual: {field_info['actual']}")
                    print(f"      Status: {field_info['status']}")
    
    # Print missing PDFs
    if comparison["missing"]:
        print("\n" + "=" * 60)
        print("MISSING PDFs:")
        print("=" * 60)
        for missing in comparison["missing"]:
            print(f"  {missing['pdf']} ({missing['label']}): {len(missing['expected_fields'])} fields")
    
    # Save if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)
        print(f"\nComparison saved to: {args.output}")
    
    # Exit with error code if there are issues
    if comparison["metrics"]["incorrect_fields"] > 0 or len(comparison["missing"]) > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()

