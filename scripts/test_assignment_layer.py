"""Test assignment layer vs traditional matching on dataset."""

import json
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline
import yaml


def test_with_assignment(enabled: bool):
    """Test pipeline with assignment layer enabled/disabled."""
    # Update config
    config_path = Path("configs/layout.yaml")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if "matching" not in config:
        config["matching"] = {}
    if "assignment" not in config["matching"]:
        config["matching"]["assignment"] = {}

    config["matching"]["assignment"]["enabled"] = enabled

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)

    # Load dataset
    dataset_path = Path("data/samples/dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    samples_dir = Path("data/samples")
    pipeline = Pipeline()

    results = []
    for entry in dataset:
        label = entry["label"]
        schema = entry["extraction_schema"]
        pdf_name = entry["pdf_path"]
        pdf_path = samples_dir / pdf_name

        if not pdf_path.exists():
            continue

        try:
            result = pipeline.run(label, schema, str(pdf_path))
            found = sum(1 for r in result["results"].values() if r.get("value") is not None)
            total = len(result["results"])
            results.append({"pdf": pdf_name, "found": found, "total": total})
        except Exception as e:
            print(f"Error with {pdf_name}: {e}", file=sys.stderr)
            results.append({"pdf": pdf_name, "found": 0, "total": 0})

    return results


def main():
    """Compare assignment layer vs traditional matching."""
    print("=" * 80)
    print("Testing Assignment Layer vs Traditional Matching")
    print("=" * 80)

    # Test traditional
    print("\n[1/2] Testing TRADITIONAL matching (assignment layer OFF)...")
    results_traditional = test_with_assignment(False)
    total_found_trad = sum(r["found"] for r in results_traditional)
    total_fields_trad = sum(r["total"] for r in results_traditional)

    print(f"  Traditional: {total_found_trad}/{total_fields_trad} fields found")

    # Test assignment
    print("\n[2/2] Testing ASSIGNMENT LAYER (assignment layer ON)...")
    results_assignment = test_with_assignment(True)
    total_found_ass = sum(r["found"] for r in results_assignment)
    total_fields_ass = sum(r["total"] for r in results_assignment)

    print(f"  Assignment: {total_found_ass}/{total_fields_ass} fields found")

    # Comparison
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)
    print(f"Traditional: {total_found_trad}/{total_fields_trad} ({100*total_found_trad/total_fields_trad:.1f}%)")
    print(f"Assignment:  {total_found_ass}/{total_fields_ass} ({100*total_found_ass/total_fields_ass:.1f}%)")
    diff = total_found_ass - total_found_trad
    if diff > 0:
        print(f"\n✅ Assignment layer improved by +{diff} fields")
    elif diff < 0:
        print(f"\n⚠️  Assignment layer decreased by {abs(diff)} fields")
    else:
        print(f"\n➡️  No difference")

    # Per-PDF comparison
    print("\nPer-PDF breakdown:")
    for i, trad in enumerate(results_traditional):
        ass = results_assignment[i]
        pdf = trad["pdf"]
        diff_pdf = ass["found"] - trad["found"]
        if diff_pdf != 0:
            print(f"  {pdf}: Traditional={trad['found']}/{trad['total']}, Assignment={ass['found']}/{ass['total']} (diff: {diff_pdf:+d})")


if __name__ == "__main__":
    main()
