"""Test script que processa apenas o primeiro PDF (oab_1.pdf) e compara com ground_truth.json.
Mostra erros um por um com detalhes.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def load_ground_truth(ground_truth_path: str) -> Dict[str, Dict[str, Any]]:
    """Load ground truth and index by PDF name."""
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    
    gt_by_pdf = {}
    for entry in gt_data:
        pdf_name = entry.get("pdf")
        if pdf_name:
            gt_by_pdf[pdf_name] = entry
    
    return gt_by_pdf


def load_dataset(dataset_path: str) -> Dict[str, Dict[str, Any]]:
    """Load dataset and index by PDF name."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    
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
    """Normalize value for comparison."""
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
    """Compare expected vs actual value for a field."""
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
    """Compare expected vs actual results and return list of errors."""
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


def main():
    """Main entry point - process only oab_1.pdf."""
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
    
    # Process ONLY oab_1.pdf
    pdf_name = "oab_1.pdf"
    
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"PROCESSANDO APENAS: {pdf_name}", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    
    expected = gt_by_pdf.get(pdf_name)
    if not expected:
        print(f"ERROR: {pdf_name} not found in ground_truth.json", file=sys.stderr)
        sys.exit(1)
    
    schema_info = schema_by_pdf.get(pdf_name)
    if not schema_info:
        print(f"ERROR: {pdf_name} not found in dataset.json", file=sys.stderr)
        sys.exit(1)
    
    label = schema_info["label"]
    schema_dict = schema_info["schema"]
    pdf_path = samples_dir / pdf_name
    
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)
    
    print(f"\nPDF: {pdf_name}", file=sys.stderr)
    print(f"Label: {label}", file=sys.stderr)
    print(f"Campos esperados: {list(expected['result'].keys())}", file=sys.stderr)
    print(f"Schema: {list(schema_dict.keys())}", file=sys.stderr)
    
    # Show expected values
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"VALORES ESPERADOS (GROUND TRUTH):", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    for field_name, expected_value in sorted(expected['result'].items()):
        print(f"  {field_name}: {repr(expected_value)}", file=sys.stderr)
    
    # Run pipeline
    print(f"\n{'='*80}", file=sys.stderr)
    print(f"EXECUTANDO PIPELINE...", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    
    try:
        actual = pipeline.run(label, schema_dict, str(pdf_path), debug=True)
        
        # Show actual values
        print(f"\n{'='*80}", file=sys.stderr)
        print(f"VALORES OBTIDOS (PIPELINE):", file=sys.stderr)
        print(f"{'='*80}", file=sys.stderr)
        actual_results = actual.get("results", {})
        for field_name in sorted(set(expected['result'].keys()) | set(actual_results.keys())):
            field_data = actual_results.get(field_name)
            if field_data is None:
                value = None
            elif isinstance(field_data, dict):
                value = field_data.get("value")
            else:
                value = field_data
            print(f"  {field_name}: {repr(value)}", file=sys.stderr)
        
        # Compare with ground truth
        print(f"\n{'='*80}", file=sys.stderr)
        print(f"COMPARANDO COM GROUND TRUTH...", file=sys.stderr)
        print(f"{'='*80}", file=sys.stderr)
        
        errors = compare_results(pdf_name, expected, actual)
        
        if errors:
            print(f"\n{'='*80}", file=sys.stderr)
            print(f"ERROS ENCONTRADOS: {len(errors)}", file=sys.stderr)
            print(f"{'='*80}", file=sys.stderr)
            
            for i, error in enumerate(errors, 1):
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"ERRO #{i}: {error['field']}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)
                print(f"Tipo: {error['error_type']}", file=sys.stderr)
                print(f"Esperado: {repr(error['expected'])}", file=sys.stderr)
                print(f"Obtido: {repr(error['actual'])}", file=sys.stderr)
                print(f"Mensagem: {error['message']}", file=sys.stderr)
                
                if error.get("trace"):
                    print(f"\nTrace completo:", file=sys.stderr)
                    print(json.dumps(error['trace'], indent=2, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"\n✓ Todos os campos coincidem com o ground truth!", file=sys.stderr)
        
        # Save output for inspection
        output_file = project_root / "out_oab_1_debug.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(actual, f, indent=2, ensure_ascii=False)
        print(f"\nOutput completo salvo em: {output_file}", file=sys.stderr)
        
    except Exception as e:
        import traceback
        print(f"\nERROR: Exceção durante processamento: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

