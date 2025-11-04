"""Test pipeline on synthetically generated PDFs.

This script:
1. Generates a small dataset of synthetic PDFs
2. Runs the extraction pipeline on each PDF
3. Compares results with ground truth
4. Reports metrics (coverage, accuracy)
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def load_labels_jsonl(labels_path: Path) -> list[dict]:
    """Load labels from JSONL file."""
    labels = []
    if not labels_path.exists():
        return labels
    
    with open(labels_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                labels.append(json.loads(line))
    
    return labels


def compare_results(predicted: dict, ground_truth: dict, schema: dict) -> dict:
    """Compare predicted results with ground truth.
    
    Returns:
        Dictionary with metrics: coverage, accuracy, field_metrics
    """
    results = predicted.get("results", {})
    answers = ground_truth.get("answers", {})
    
    total_fields = len(schema)
    found_fields = 0
    correct_fields = 0
    field_metrics = {}
    
    for field_name in schema.keys():
        pred_value = results.get(field_name, {}).get("value")
        true_value = answers.get(field_name)
        
        found = pred_value is not None
        correct = pred_value == true_value if found and true_value else False
        
        if found:
            found_fields += 1
        if correct:
            correct_fields += 1
        
        field_metrics[field_name] = {
            "found": found,
            "correct": correct,
            "predicted": pred_value,
            "ground_truth": true_value,
        }
    
    coverage = found_fields / total_fields if total_fields > 0 else 0.0
    accuracy = correct_fields / found_fields if found_fields > 0 else 0.0
    
    return {
        "coverage": coverage,
        "accuracy": accuracy,
        "found_fields": found_fields,
        "correct_fields": correct_fields,
        "total_fields": total_fields,
        "field_metrics": field_metrics,
    }


def main():
    """Main test function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test pipeline on synthetic PDFs")
    parser.add_argument("--labels", type=Path, required=True, help="Path to labels.jsonl file")
    parser.add_argument("--base-dir", type=Path, default=None, help="Base directory for PDF paths (default: same as labels parent)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed field-by-field results")
    args = parser.parse_args()
    
    labels_path = args.labels
    if not labels_path.exists():
        print(f"Error: Labels file not found: {labels_path}", file=sys.stderr)
        sys.exit(1)
    
    # Determine base directory
    if args.base_dir:
        base_dir = args.base_dir
    else:
        base_dir = labels_path.parent
    
    # Load labels
    labels = load_labels_jsonl(labels_path)
    
    if not labels:
        print(f"Error: No labels found in {labels_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loaded {len(labels)} labeled documents")
    print(f"Base directory: {base_dir}")
    print("-" * 80)
    
    # Initialize pipeline
    pipeline = Pipeline()
    
    # Test each document
    all_metrics = []
    for i, entry in enumerate(labels, 1):
        label = entry.get("label", "unknown")
        schema = entry.get("extraction_schema", {})
        pdf_path_str = entry.get("pdf_path", "")
        answers = entry.get("answers", {})
        
        # Resolve PDF path
        if pdf_path_str.startswith("data/"):
            # Relative to project root
            pdf_path = Path(__file__).parent.parent / pdf_path_str
        else:
            # Relative to base_dir
            pdf_path = base_dir / pdf_path_str
        
        if not pdf_path.exists():
            print(f"[{i}/{len(labels)}] SKIP: PDF not found: {pdf_path}", file=sys.stderr)
            continue
        
        print(f"\n[{i}/{len(labels)}] Testing: {pdf_path.name} (label: {label})")
        
        try:
            # Run pipeline
            result = pipeline.run(label, schema, str(pdf_path))
            
            # Compare with ground truth
            metrics = compare_results(result, entry, schema)
            all_metrics.append(metrics)
            
            # Print summary
            print(f"  Coverage: {metrics['coverage']:.1%} ({metrics['found_fields']}/{metrics['total_fields']} fields)")
            print(f"  Accuracy: {metrics['accuracy']:.1%} ({metrics['correct_fields']}/{metrics['found_fields']} correct)")
            
            if args.verbose:
                print("  Field details:")
                for field_name, field_metric in metrics["field_metrics"].items():
                    status = "✓" if field_metric["correct"] else ("?" if field_metric["found"] else "✗")
                    pred = field_metric["predicted"] or "<null>"
                    true = field_metric["ground_truth"] or "<null>"
                    print(f"    {status} {field_name}: pred={pred[:30]}, true={true[:30]}")
        
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            continue
    
    # Overall summary
    if all_metrics:
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)
        
        avg_coverage = sum(m["coverage"] for m in all_metrics) / len(all_metrics)
        avg_accuracy = sum(m["accuracy"] for m in all_metrics) / len(all_metrics)
        total_found = sum(m["found_fields"] for m in all_metrics)
        total_correct = sum(m["correct_fields"] for m in all_metrics)
        total_fields = sum(m["total_fields"] for m in all_metrics)
        
        print(f"Documents tested: {len(all_metrics)}")
        print(f"Average coverage: {avg_coverage:.1%}")
        print(f"Average accuracy: {avg_accuracy:.1%}")
        print(f"Total fields: {total_fields}")
        print(f"Total found: {total_found} ({total_found/total_fields:.1%})")
        print(f"Total correct: {total_correct} ({total_correct/total_found:.1%} of found)")
        
        # Field-level statistics
        field_stats = {}
        for metrics in all_metrics:
            for field_name, field_metric in metrics["field_metrics"].items():
                if field_name not in field_stats:
                    field_stats[field_name] = {"found": 0, "correct": 0, "total": 0}
                field_stats[field_name]["total"] += 1
                if field_metric["found"]:
                    field_stats[field_name]["found"] += 1
                if field_metric["correct"]:
                    field_stats[field_name]["correct"] += 1
        
        print("\nField-level statistics:")
        for field_name, stats in sorted(field_stats.items()):
            coverage = stats["found"] / stats["total"] if stats["total"] > 0 else 0.0
            accuracy = stats["correct"] / stats["found"] if stats["found"] > 0 else 0.0
            print(f"  {field_name}: coverage={coverage:.1%}, accuracy={accuracy:.1%}")


if __name__ == "__main__":
    main()

