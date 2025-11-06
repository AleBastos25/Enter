"""Script para analisar resultados e identificar problemas."""

import json
from pathlib import Path
from typing import Dict, List, Any

# Resultados esperados
EXPECTED = [
    {
        "pdf": "oab_1.pdf",
        "label": "carteira_oab",
        "result": {
            "nome": "JOANA D'ARC",
            "inscricao": "101943",
            "seccional": "PR",
            "subsecao": "CONSELHO SECCIONAL - PARANÁ",
            "categoria": "SUPLEMENTAR",
            "endereco_profissional": "AVENIDA PAULISTA, Nº 2300 andar Pilotis, Bela Vista, SÃO PAULO - SP, 01310300",
            "telefone_profissional": None,
            "situacao": "SITUAÇÃO REGULAR"
        }
    },
    {
        "pdf": "oab_2.pdf",
        "label": "carteira_oab",
        "result": {
            "nome": "LUIS FILIPE ARAUJO AMARAL",
            "inscricao": "101943",
            "seccional": "PR",
            "subsecao": "CONSELHO SECCIONAL - PARANÁ",
            "categoria": "SUPLEMENTAR",
            "endereco_profissional": "AVENIDA PAULISTA, Nº 2300 andar Pilotis, Bela Vista, SÃO PAULO - SP, 01310300",
            "situacao": "SITUAÇÃO REGULAR"
        }
    },
    {
        "pdf": "oab_3.pdf",
        "label": "carteira_oab",
        "result": {
            "nome": "SON GOKU",
            "inscricao": "101943",
            "seccional": "PR",
            "subsecao": "CONSELHO SECCIONAL - PARANÁ",
            "categoria": "SUPLEMENTAR",
            "telefone_profissional": None,
            "situacao": "SITUAÇÃO REGULAR"
        }
    },
    {
        "pdf": "tela_sistema_1.pdf",
        "label": "tela_sistema",
        "result": {
            "data_base": "2025-09-05",
            "data_verncimento": "2025-10-12",
            "quantidade_parcelas": None,
            "produto": None,
            "sistema": "CONSIGNADO",
            "tipo_de_operacao": None,
            "tipo_de_sistema": None
        }
    },
    {
        "pdf": "tela_sistema_2.pdf",
        "label": "tela_sistema",
        "result": {
            "pesquisa_por": "CLIENTE",
            "pesquisa_tipo": "CPF",
            "sistema": "CONSIGNADO",
            "valor_parcela": "2372.64",
            "cidade": "Mozarlândia"
        }
    },
    {
        "pdf": "tela_sistema_3.pdf",
        "label": "tela_sistema",
        "result": {
            "data_referencia": "2021-02-04",
            "selecao_de_parcelas": None,
            "total_de_parcelas": None
        }
    }
]


def load_actual_results(json_path: str) -> Dict[str, Any]:
    """Carrega resultados reais do JSON gerado."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_expected(pdf_name: str) -> Dict[str, Any]:
    """Encontra resultado esperado para um PDF."""
    for entry in EXPECTED:
        if entry["pdf"] == pdf_name:
            return entry
    return None


def analyze_field(pdf_name: str, field_name: str, expected_value: Any, actual_value: Any, actual_result: Dict) -> List[str]:
    """Analisa um campo específico e retorna problemas encontrados."""
    problems = []
    
    if expected_value is None and actual_value is None:
        return problems  # Ambos null, OK
    
    if expected_value is None and actual_value is not None:
        problems.append(f"  [ERROR] {field_name}: Esperado null, mas extraiu '{actual_value}'")
        return problems
    
    if expected_value is not None and actual_value is None:
        problems.append(f"  [ERROR] {field_name}: Esperado '{expected_value}', mas extraiu null")
        # Tentar entender por que não extraiu
        if "trace" in actual_result:
            trace = actual_result["trace"]
            reason = trace.get("reason", "unknown")
            problems.append(f"      Razão: {reason}")
        return problems
    
    # Ambos têm valores, comparar
    expected_str = str(expected_value).strip().upper()
    actual_str = str(actual_value).strip().upper()
    
    if expected_str != actual_str:
        problems.append(f"  [ERROR] {field_name}: Esperado '{expected_value}', mas extraiu '{actual_value}'")
        
        # Análise de diferenças
        if expected_str in actual_str:
            problems.append(f"      [WARN] Valor esperado esta contido no extraido (pode ser label incluido)")
        elif actual_str in expected_str:
            problems.append(f"      [WARN] Valor extraido esta contido no esperado (pode estar incompleto)")
        elif len(actual_str) > len(expected_str) * 1.5:
            problems.append(f"      [WARN] Valor extraido e muito maior (pode ter label ou texto extra)")
        elif len(actual_str) < len(expected_str) * 0.5:
            problems.append(f"      [WARN] Valor extraido e muito menor (pode estar incompleto)")
    else:
        problems.append(f"  [OK] {field_name}: OK")
    
    return problems


def main():
    """Analisa resultados e identifica problemas."""
    actual_file = Path("out_test3.json")
    if not actual_file.exists():
        actual_file = Path("out_test.json")
    if not actual_file.exists():
        print("[ERROR] Arquivo out_test.json nao encontrado. Execute primeiro:")
        print("   python scripts/batch_process.py --folder data/samples --out out_test.json")
        return
    
    actual_data = load_actual_results(str(actual_file))
    # Handle both list and dict formats
    if isinstance(actual_data, list):
        actual_results = actual_data
    else:
        actual_results = actual_data.get("results", [])
    
    print("=" * 80)
    print("ANÁLISE DE RESULTADOS")
    print("=" * 80)
    print()
    
    all_problems = []
    
    # Para cada PDF esperado
    for expected_entry in EXPECTED:
        pdf_name = expected_entry["pdf"]
        expected_result = expected_entry["result"]
        
        print(f"\n[PDF] {pdf_name}")
        print("-" * 80)
        
        # Encontrar resultado real
        actual_entry = None
        for entry in actual_results:
            # Handle both "pdf" and "pdf_name" keys
            entry_pdf = entry.get("pdf") or entry.get("pdf_name")
            if entry_pdf == pdf_name:
                actual_entry = entry
                break
        
        if not actual_entry:
            print(f"  [ERROR] PDF nao encontrado nos resultados reais!")
            continue
        
        actual_results_dict = actual_entry.get("results", {})
        
        # Analisar cada campo esperado
        pdf_problems = []
        for field_name, expected_value in expected_result.items():
            actual_field = actual_results_dict.get(field_name, {})
            actual_value = actual_field.get("value") if isinstance(actual_field, dict) else None
            
            field_problems = analyze_field(pdf_name, field_name, expected_value, actual_value, actual_field)
            pdf_problems.extend(field_problems)
            print("\n".join(field_problems))
        
        all_problems.extend(pdf_problems)
    
    # Resumo
    print("\n" + "=" * 80)
    print("RESUMO")
    print("=" * 80)
    
    total_expected = sum(len(entry["result"]) for entry in EXPECTED)
    total_correct = sum(1 for p in all_problems if "[OK]" in p)
    total_errors = sum(1 for p in all_problems if "[ERROR]" in p)
    
    print(f"Total de campos esperados: {total_expected}")
    print(f"Campos corretos: {total_correct}")
    print(f"Campos com erro: {total_errors}")
    print(f"Taxa de acerto: {total_correct / total_expected * 100:.1f}%")
    
    # Agrupar problemas por tipo
    print("\n" + "=" * 80)
    print("PROBLEMAS POR TIPO")
    print("=" * 80)
    
    # Problemas de formato
    format_issues = [p for p in all_problems if "label incluido" in p or "texto extra" in p or "incompleto" in p]
    if format_issues:
        print("\n[FORMATO] Problemas de Formato/Extracao:")
        for issue in format_issues[:10]:  # Limitar a 10
            print(f"  {issue}")
        if len(format_issues) > 10:
            print(f"  ... e mais {len(format_issues) - 10} problemas similares")
    
    # Problemas de null
    null_issues = [p for p in all_problems if "extraiu null" in p]
    if null_issues:
        print("\n[NULL] Campos Nao Extraidos (null):")
        for issue in null_issues:
            print(f"  {issue}")
    
    # Problemas de valor incorreto
    value_issues = [p for p in all_problems if "extraiu '" in p and "extraiu null" not in p]
    if value_issues:
        print("\n[VALOR] Valores Incorretos:")
        for issue in value_issues[:10]:  # Limitar a 10
            print(f"  {issue}")
        if len(value_issues) > 10:
            print(f"  ... e mais {len(value_issues) - 10} problemas similares")


if __name__ == "__main__":
    main()

