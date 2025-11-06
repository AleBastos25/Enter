"""Debug um campo específico de um PDF para entender o problema."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def debug_field(pdf_name: str, field_name: str):
    """Debug um campo específico."""
    
    # Load dataset
    dataset = json.loads(Path("data/samples/dataset.json").read_text(encoding="utf-8"))
    pdf_to_schema = {}
    for entry in dataset:
        pdf_name_entry = Path(entry.get("pdf_path", "")).name
        label = entry.get("label")
        schema_dict = entry.get("extraction_schema", {})
        if label and schema_dict:
            pdf_to_schema[pdf_name_entry] = (label, schema_dict)
    
    if pdf_name not in pdf_to_schema:
        print(f"PDF {pdf_name} não encontrado no dataset")
        return
    
    label, schema_dict = pdf_to_schema[pdf_name]
    pdf_path = f"data/samples/{pdf_name}"
    
    # Load ground truth
    gt = json.loads(Path("ground_truth.json").read_text(encoding="utf-8"))
    gt_result = None
    for item in gt:
        if item["pdf"] == pdf_name:
            gt_result = item["result"]
            break
    
    expected = gt_result.get(field_name) if gt_result else None
    
    print(f"\n{'='*80}")
    print(f"DEBUG: {pdf_name} -> {field_name}")
    print(f"{'='*80}")
    print(f"Expected: {repr(expected)}")
    
    # Run pipeline with debug
    pipeline = Pipeline()
    result = pipeline.run(label, schema_dict, pdf_path, debug=True)
    
    field_result = result.get("results", {}).get(field_name, {})
    value = field_result.get("value") if isinstance(field_result, dict) else field_result
    
    print(f"Got: {repr(value)}")
    
    # Show debug info
    if isinstance(field_result, dict):
        trace = field_result.get("trace", {})
        print(f"\nTrace:")
        print(f"  Source: {field_result.get('source')}")
        print(f"  Confidence: {field_result.get('confidence')}")
        print(f"  Reason: {trace.get('reason')}")
        if "debug" in result:
            field_debug = result["debug"].get(field_name)
            if field_debug:
                print(f"\nDebug info:")
                print(json.dumps(field_debug, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python debug_single_field.py <pdf_name> <field_name>")
        print("Example: python debug_single_field.py oab_1.pdf nome")
        sys.exit(1)
    
    debug_field(sys.argv[1], sys.argv[2])


