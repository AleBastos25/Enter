"""Test the pipeline with the provided dataset.json file."""

import json
import sys
import time
from pathlib import Path

# Fix Windows encoding issues
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def main():
    """Run pipeline on all entries in dataset.json."""
    dataset_path = Path("data/samples/dataset.json")
    samples_dir = Path("data/samples")

    if not dataset_path.exists():
        print(f"Error: {dataset_path} not found", file=sys.stderr)
        sys.exit(1)

    # Load dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Loaded {len(dataset)} entries from dataset.json\n")
    print("=" * 80)

    pipeline = Pipeline()
    results_summary = []

    for i, entry in enumerate(dataset, 1):
        label = entry["label"]
        schema = entry["extraction_schema"]
        pdf_name = entry["pdf_path"]
        pdf_path = samples_dir / pdf_name

        print(f"\n[{i}/{len(dataset)}] Testing: {pdf_name} (label: {label})")
        print("-" * 80)

        if not pdf_path.exists():
            print(f"  [WARN] PDF not found: {pdf_path}", file=sys.stderr)
            results_summary.append({"pdf": pdf_name, "status": "error", "error": "PDF not found"})
            continue

        try:
            # Run pipeline with timing
            start_time = time.time()
            result = pipeline.run(label, schema, str(pdf_path))
            elapsed_time = time.time() - start_time

            # Print results
            print(f"  Results:")
            found_count = 0
            total_confidence = 0.0
            field_count = 0

            for field_name, field_result in result["results"].items():
                value = field_result.get("value")
                confidence = field_result.get("confidence", 0.0)
                source = field_result.get("source", "none")
                page_index = field_result.get("trace", {}).get("page_index", 0)

                field_count += 1
                if value is not None:
                    found_count += 1
                    total_confidence += confidence
                    status = "[OK]"
                    value_preview = str(value)[:50] + ("..." if len(str(value)) > 50 else "")
                    print(f"    {status} {field_name:25s} = {value_preview:50s} (conf: {confidence:.2f}, src: {source}, page: {page_index})")
                else:
                    status = "[--]"
                    print(f"    {status} {field_name:25s} = <null> (conf: {confidence:.2f}, src: {source})")

            avg_confidence = total_confidence / found_count if found_count > 0 else 0.0
            print(f"\n  Summary: {found_count}/{field_count} fields found, avg confidence: {avg_confidence:.2f}, time: {elapsed_time:.2f}s")

            results_summary.append({
                "pdf": pdf_name,
                "status": "success",
                "found": found_count,
                "total": field_count,
                "avg_confidence": avg_confidence,
                "time": elapsed_time,
            })

        except Exception as e:
            print(f"  [ERROR] Error processing {pdf_name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            results_summary.append({"pdf": pdf_name, "status": "error", "error": str(e)})

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    successful = [r for r in results_summary if r["status"] == "success"]
    errors = [r for r in results_summary if r["status"] == "error"]

    print(f"\nSuccessful: {len(successful)}/{len(results_summary)}")
    if successful:
        total_found = sum(r["found"] for r in successful)
        total_fields = sum(r["total"] for r in successful)
        overall_avg_conf = sum(r["avg_confidence"] for r in successful) / len(successful) if successful else 0.0
        times = [r["time"] for r in successful]
        avg_time = sum(times) / len(times) if times else 0.0
        max_time = max(times) if times else 0.0
        print(f"  Total fields found: {total_found}/{total_fields}")
        print(f"  Average confidence: {overall_avg_conf:.2f}")
        print(f"  Average time per PDF: {avg_time:.2f}s")
        print(f"  Maximum time per PDF: {max_time:.2f}s")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for err in errors:
            print(f"  - {err['pdf']}: {err.get('error', 'Unknown error')}")

    print()


if __name__ == "__main__":
    main()

