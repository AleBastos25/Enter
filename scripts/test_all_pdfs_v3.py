"""Testa pipeline v3.0 com todos os PDFs de data/samples/."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def main():
    project_root = Path(__file__).parent.parent
    samples_dir = project_root / "data" / "samples"
    ground_truth_path = project_root / "ground_truth.json"
    dataset_path = project_root / "data" / "samples" / "dataset.json"
    
    # Carregar ground truth e dataset
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    gt_by_pdf = {entry["pdf"]: entry for entry in gt_data}
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    schema_by_pdf = {entry["pdf_path"]: entry for entry in dataset}
    
    # Pipeline
    pipeline = Pipeline()
    
    # Processar cada PDF
    results = []
    total_fields = 0
    correct_fields = 0
    
    for pdf_name in sorted(gt_by_pdf.keys()):
        pdf_path = samples_dir / pdf_name
        if not pdf_path.exists():
            print(f"  WARNING: {pdf_path} not found, skipping")
            continue
        
        schema_info = schema_by_pdf.get(pdf_name)
        if not schema_info:
            print(f"  WARNING: {pdf_name} not found in dataset.json, skipping")
            continue
        
        label = schema_info["label"]
        schema_dict = schema_info["extraction_schema"]
        
        print(f"\n{'='*80}")
        print(f"Processando: {pdf_name} (label: {label})")
        print(f"{'='*80}")
        
        try:
            result = pipeline.run(label, schema_dict, str(pdf_path), debug=False)
            results.append({
                "pdf": pdf_name,
                "result": result
            })
            
            # Comparar com ground truth
            expected = gt_by_pdf[pdf_name]["result"]
            actual = result["results"]
            
            print(f"\nComparação para {pdf_name}:")
            for field_name, expected_value in expected.items():
                total_fields += 1
                actual_value = actual.get(field_name, {}).get("value")
                
                # Normalizar comparação (strings)
                expected_str = str(expected_value) if expected_value is not None else None
                actual_str = str(actual_value) if actual_value is not None else None
                
                match = expected_str == actual_str
                if match:
                    correct_fields += 1
                
                status = "[OK]" if match else "[ERRO]"
                print(f"  {status} {field_name}: esperado={expected_value}, obtido={actual_value}")
        
        except Exception as e:
            print(f"  ERRO: {e}")
            import traceback
            traceback.print_exc()
    
    # Salvar resultados
    output_path = project_root / "test_results_v3.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em: {output_path}")
    
    # Estatísticas finais
    print(f"\n{'='*80}")
    print(f"RESUMO FINAL")
    print(f"{'='*80}")
    print(f"Total de campos: {total_fields}")
    print(f"Campos corretos: {correct_fields}")
    if total_fields > 0:
        accuracy = (correct_fields / total_fields) * 100
        print(f"Precisão: {accuracy:.1f}%")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()

