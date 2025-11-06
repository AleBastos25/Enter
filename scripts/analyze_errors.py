"""Compare current output with ground truth and analyze errors."""

import json
from pathlib import Path
from typing import Dict, List, Any

def load_json(file_path: str) -> Any:
    """Load JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def compare_results(ground_truth: List[Dict], current_output: List[Dict]) -> Dict[str, Any]:
    """Compare ground truth with current output and identify errors."""
    
    # Build lookup by PDF name
    gt_by_pdf = {item["pdf"]: item["result"] for item in ground_truth}
    current_by_pdf = {item["pdf"]: item["result"] for item in current_output}
    
    errors = []
    all_fields = set()
    
    for pdf_name in sorted(set(gt_by_pdf.keys()) | set(current_by_pdf.keys())):
        gt_result = gt_by_pdf.get(pdf_name, {})
        current_result = current_by_pdf.get(pdf_name, {})
        
        all_fields.update(gt_result.keys())
        all_fields.update(current_result.keys())
        
        pdf_errors = []
        for field_name in sorted(all_fields):
            gt_value = gt_result.get(field_name)
            current_value = current_result.get(field_name)
            
            # Check for errors
            if gt_value != current_value:
                error_type = "unknown"
                if gt_value is None and current_value is not None:
                    error_type = "extra_extraction"  # Extraiu valor quando deveria ser null
                elif gt_value is not None and current_value is None:
                    error_type = "missing_extraction"  # Não extraiu quando deveria
                elif gt_value != current_value:
                    error_type = "wrong_value"  # Extraiu valor errado
                
                pdf_errors.append({
                    "field": field_name,
                    "expected": gt_value,
                    "got": current_value,
                    "error_type": error_type
                })
        
        if pdf_errors:
            errors.append({
                "pdf": pdf_name,
                "errors": pdf_errors
            })
    
    return {
        "total_pdfs": len(set(gt_by_pdf.keys()) | set(current_by_pdf.keys())),
        "pdfs_with_errors": len(errors),
        "errors": errors,
        "summary_by_type": {
            "missing_extraction": sum(1 for e in errors for err in e["errors"] if err["error_type"] == "missing_extraction"),
            "extra_extraction": sum(1 for e in errors for err in e["errors"] if err["error_type"] == "extra_extraction"),
            "wrong_value": sum(1 for e in errors for err in e["errors"] if err["error_type"] == "wrong_value"),
        }
    }

def main():
    """Main function."""
    ground_truth_path = Path("ground_truth.json")
    current_output_path = Path("output_current.json")
    
    if not ground_truth_path.exists():
        print(f"ERROR: {ground_truth_path} not found")
        return
    
    if not current_output_path.exists():
        print(f"ERROR: {current_output_path} not found")
        return
    
    ground_truth = load_json(str(ground_truth_path))
    current_output = load_json(str(current_output_path))
    
    analysis = compare_results(ground_truth, current_output)
    
    print("=" * 80)
    print("ANÁLISE DE ERROS - Ground Truth vs Output Atual")
    print("=" * 80)
    print(f"\nTotal de PDFs: {analysis['total_pdfs']}")
    print(f"PDFs com erros: {analysis['pdfs_with_errors']}")
    print(f"\nResumo por tipo de erro:")
    print(f"  - Extrações faltando (missing_extraction): {analysis['summary_by_type']['missing_extraction']}")
    print(f"  - Extrações extras (extra_extraction): {analysis['summary_by_type']['extra_extraction']}")
    print(f"  - Valores errados (wrong_value): {analysis['summary_by_type']['wrong_value']}")
    
    print("\n" + "=" * 80)
    print("DETALHES DOS ERROS POR PDF")
    print("=" * 80)
    
    for pdf_error in analysis["errors"]:
        pdf_name = pdf_error["pdf"]
        print(f"\nPDF: {pdf_name}")
        print("-" * 80)
        
        for err in pdf_error["errors"]:
            field = err["field"]
            error_type = err["error_type"]
            expected = err["expected"]
            got = err["got"]
            
            print(f"\n  Campo: {field}")
            print(f"    Tipo: {error_type}")
            print(f"    Esperado: {repr(expected)}")
            print(f"    Obtido: {repr(got)}")
            
            # Análise específica
            if error_type == "missing_extraction":
                print(f"    PROBLEMA: Campo nao foi extraido")
            elif error_type == "extra_extraction":
                print(f"    PROBLEMA: Campo foi extraido quando deveria ser null")
            elif error_type == "wrong_value":
                print(f"    PROBLEMA: Valor extraido esta incorreto")
    
    # Salvar análise detalhada
    output_path = Path("error_analysis.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    print(f"\n\nAnálise detalhada salva em: {output_path}")

if __name__ == "__main__":
    main()

