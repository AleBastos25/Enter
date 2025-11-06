"""Compare batch processing results with ground truth and generate detailed report."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict


def normalize_value(value: Any) -> Any:
    """Normalize values for comparison (handle null, whitespace, encoding)."""
    if value is None:
        return None
    if isinstance(value, str):
        # Normalize whitespace and handle encoding issues
        value = " ".join(value.split())
        # Handle encoding issues ( character)
        if "" in value:
            # Try to decode common replacements
            value = value.replace("", "Á").replace("", "É").replace("", "Í").replace("", "Ó").replace("", "Ú")
            value = value.replace("", "á").replace("", "é").replace("", "í").replace("", "ó").replace("", "ú")
            value = value.replace("", "Ã").replace("", "Õ")
        return value.strip() if value else None
    return value


def compare_results(
    ground_truth: List[Dict[str, Any]],
    results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare results with ground truth and generate detailed report."""
    
    # Build lookup maps
    gt_map = {entry["pdf"]: entry for entry in ground_truth}
    result_map = {entry["pdf"]: entry for entry in results}
    
    report = {
        "summary": {
            "total_pdfs": len(ground_truth),
            "processed_pdfs": len(results),
            "missing_pdfs": [],
            "extra_pdfs": [],
        },
        "by_pdf": {},
        "field_stats": defaultdict(lambda: {
            "total": 0,
            "correct": 0,
            "missing": 0,
            "incorrect": 0,
            "extra": 0,
        }),
        "accuracy_by_pdf": {},
    }
    
    all_pdfs = set(gt_map.keys()) | set(result_map.keys())
    
    for pdf_name in sorted(all_pdfs):
        gt_entry = gt_map.get(pdf_name)
        result_entry = result_map.get(pdf_name)
        
        if not gt_entry:
            report["summary"]["extra_pdfs"].append(pdf_name)
            continue
        
        if not result_entry:
            report["summary"]["missing_pdfs"].append(pdf_name)
            continue
        
        gt_result = gt_entry.get("result", {})
        result_result = result_entry.get("result", {})
        
        pdf_comparison = {
            "pdf": pdf_name,
            "label": gt_entry.get("label"),
            "fields": {},
            "correct_count": 0,
            "total_count": 0,
            "missing_count": 0,
            "incorrect_count": 0,
            "extra_count": 0,
        }
        
        # Compare fields from ground truth
        all_fields = set(gt_result.keys()) | set(result_result.keys())
        
        for field_name in sorted(all_fields):
            gt_value = gt_result.get(field_name)
            result_value = result_result.get(field_name)
            
            gt_norm = normalize_value(gt_value)
            result_norm = normalize_value(result_value)
            
            field_stat = report["field_stats"][field_name]
            field_stat["total"] += 1
            
            pdf_comparison["total_count"] += 1
            
            field_comparison = {
                "expected": gt_value,
                "actual": result_value,
                "match": gt_norm == result_norm,
            }
            
            if field_name not in gt_result:
                # Field only in results (extra)
                field_comparison["status"] = "extra"
                pdf_comparison["extra_count"] += 1
                field_stat["extra"] += 1
            elif field_name not in result_result:
                # Field missing in results
                field_comparison["status"] = "missing"
                pdf_comparison["missing_count"] += 1
                field_stat["missing"] += 1
            elif gt_norm == result_norm:
                # Correct match
                field_comparison["status"] = "correct"
                pdf_comparison["correct_count"] += 1
                field_stat["correct"] += 1
            else:
                # Incorrect value
                field_comparison["status"] = "incorrect"
                pdf_comparison["incorrect_count"] += 1
                field_stat["incorrect"] += 1
            
            pdf_comparison["fields"][field_name] = field_comparison
        
        # Calculate accuracy for this PDF
        if pdf_comparison["total_count"] > 0:
            accuracy = pdf_comparison["correct_count"] / pdf_comparison["total_count"]
            pdf_comparison["accuracy"] = accuracy
            report["accuracy_by_pdf"][pdf_name] = accuracy
        
        report["by_pdf"][pdf_name] = pdf_comparison
    
    # Calculate overall statistics
    total_fields = sum(stat["total"] for stat in report["field_stats"].values())
    total_correct = sum(stat["correct"] for stat in report["field_stats"].values())
    total_missing = sum(stat["missing"] for stat in report["field_stats"].values())
    total_incorrect = sum(stat["incorrect"] for stat in report["field_stats"].values())
    
    report["summary"]["overall_accuracy"] = total_correct / total_fields if total_fields > 0 else 0.0
    report["summary"]["total_fields"] = total_fields
    report["summary"]["total_correct"] = total_correct
    report["summary"]["total_missing"] = total_missing
    report["summary"]["total_incorrect"] = total_incorrect
    
    # Calculate average accuracy by PDF
    if report["accuracy_by_pdf"]:
        report["summary"]["average_pdf_accuracy"] = sum(report["accuracy_by_pdf"].values()) / len(report["accuracy_by_pdf"])
    else:
        report["summary"]["average_pdf_accuracy"] = 0.0
    
    return report


def print_report(report: Dict[str, Any]):
    """Print a human-readable report."""
    print("=" * 80)
    print("COMPARISON REPORT: Results vs Ground Truth")
    print("=" * 80)
    
    summary = report["summary"]
    print(f"\nSUMMARY:")
    print(f"  Total PDFs: {summary['total_pdfs']}")
    print(f"  Processed PDFs: {summary['processed_pdfs']}")
    print(f"  Missing PDFs: {len(summary['missing_pdfs'])}")
    if summary['missing_pdfs']:
        print(f"    - {', '.join(summary['missing_pdfs'])}")
    print(f"  Extra PDFs: {len(summary['extra_pdfs'])}")
    if summary['extra_pdfs']:
        print(f"    - {', '.join(summary['extra_pdfs'])}")
    
    print(f"\n  Overall Accuracy: {summary['overall_accuracy']:.2%}")
    print(f"  Average PDF Accuracy: {summary['average_pdf_accuracy']:.2%}")
    print(f"  Total Fields: {summary['total_fields']}")
    print(f"  Correct: {summary['total_correct']}")
    print(f"  Missing: {summary['total_missing']}")
    print(f"  Incorrect: {summary['total_incorrect']}")
    
    print(f"\nFIELD STATISTICS:")
    for field_name, stats in sorted(report["field_stats"].items()):
        accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0
        print(f"  {field_name}:")
        print(f"    Accuracy: {accuracy:.2%} ({stats['correct']}/{stats['total']})")
        print(f"    Missing: {stats['missing']}, Incorrect: {stats['incorrect']}, Extra: {stats['extra']}")
    
    print(f"\nPER-PDF DETAILS:")
    for pdf_name, pdf_data in sorted(report["by_pdf"].items()):
        print(f"\n  {pdf_name} ({pdf_data.get('label', 'unknown')})")
        print(f"    Accuracy: {pdf_data.get('accuracy', 0):.2%}")
        print(f"    Correct: {pdf_data['correct_count']}, Missing: {pdf_data['missing_count']}, Incorrect: {pdf_data['incorrect_count']}, Extra: {pdf_data['extra_count']}")
        
        # Show incorrect/missing fields
        incorrect_fields = [
            (name, comp) for name, comp in pdf_data["fields"].items()
            if comp["status"] in ["incorrect", "missing"]
        ]
        if incorrect_fields:
            print(f"    Issues:")
            for field_name, comp in incorrect_fields[:5]:  # Show first 5
                status = comp["status"]
                expected = comp["expected"]
                actual = comp["actual"]
                print(f"      - {field_name} ({status}):")
                print(f"        Expected: {repr(expected)}")
                print(f"        Actual:   {repr(actual)}")
            if len(incorrect_fields) > 5:
                print(f"      ... and {len(incorrect_fields) - 5} more")


def main():
    """Main function."""
    import argparse
    
    ap = argparse.ArgumentParser(
        description="Compare batch processing results with ground truth"
    )
    ap.add_argument("--results", type=str, required=True, help="Path to results JSON file")
    ap.add_argument("--ground-truth", type=str, default="ground_truth.json", help="Path to ground truth JSON file")
    ap.add_argument("--output", type=str, help="Path to save detailed JSON report")
    ap.add_argument("--print", action="store_true", help="Print human-readable report to stdout")
    
    args = ap.parse_args()
    
    # Load files
    results_path = Path(args.results)
    gt_path = Path(args.ground_truth)
    
    if not results_path.exists():
        print(f"Error: Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)
    
    if not gt_path.exists():
        print(f"Error: Ground truth file not found: {gt_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    
    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)
    
    # Compare
    report = compare_results(ground_truth, results)
    
    # Print report
    if args.print:
        print_report(report)
    
    # Save detailed report
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nDetailed report saved to: {output_path}", file=sys.stderr)
    
    # Exit with error code if accuracy is low
    if report["summary"]["overall_accuracy"] < 0.5:
        print(f"\nWARNING: Overall accuracy is below 50%!", file=sys.stderr)
        sys.exit(1)
    
    return report


if __name__ == "__main__":
    main()

