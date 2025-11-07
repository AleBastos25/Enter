#!/usr/bin/env python3
"""Script CLI para processar múltiplos PDFs de uma pasta e gerar JSON de resposta oficial.

Uso:
    python scripts/batch_extract.py --input data/samples --output results.json
    python scripts/batch_extract.py --input data/samples --output results.json --label carteira_oab
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

# Adicionar raiz do projeto ao path
script_dir = Path(__file__).parent
project_root = script_dir.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

backend_src = project_root / "backend" / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

# Importar serviço de extração e debug helper
try:
    from services.extractor_service import extractor_service
    from utils.debug import set_debug_mode, debug_print, error_print
except ImportError as e:
    print(f"ERRO: Não foi possível importar módulos necessários: {e}", file=sys.stderr)
    print(f"Certifique-se de que está executando do diretório raiz do projeto", file=sys.stderr)
    sys.exit(1)


def load_dataset(dataset_path: Path) -> List[Dict[str, Any]]:
    """Carrega dataset.json com schemas e labels.
    
    Args:
        dataset_path: Caminho para dataset.json
        
    Returns:
        Lista de entradas do dataset
    """
    if not dataset_path.exists():
        debug_print(f"AVISO: dataset.json não encontrado em {dataset_path}")
        return []
    
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as e:
        error_print(f"ERRO: dataset.json inválido: {e}")
        return []


def find_pdfs_in_folder(folder_path: Path) -> List[Path]:
    """Encontra todos os PDFs em uma pasta.
    
    Args:
        folder_path: Caminho da pasta
        
    Returns:
        Lista de caminhos de PDFs
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return []
    
    pdfs = list(folder_path.glob("*.pdf"))
    return sorted(pdfs)


def get_schema_for_pdf(pdf_filename: str, dataset: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Obtém schema e label para um PDF do dataset.
    
    Args:
        pdf_filename: Nome do arquivo PDF
        dataset: Lista de entradas do dataset
        
    Returns:
        Dicionário com 'label' e 'schema', ou None se não encontrado
    """
    for entry in dataset:
        if entry.get("pdf_path") == pdf_filename:
            return {
                "label": entry.get("label", "unknown"),
                "schema": entry.get("extraction_schema", {})
            }
    return None


def process_folder(
    input_folder: Path,
    output_path: Path,
    label_filter: Optional[str] = None,
    verbose: bool = True,
    use_learning: bool = True
) -> None:
    """Processa todos os PDFs de uma pasta e gera JSON de resposta.
    
    Args:
        input_folder: Caminho da pasta com PDFs
        output_path: Caminho do arquivo JSON de saída
        label_filter: Se fornecido, processa apenas PDFs com este label
        verbose: Se True, imprime progresso no terminal
    """
    # Configurar modo debug: True se verbose, False se quiet
    set_debug_mode(verbose)
    
    if verbose:
        print("=" * 80)
        print("BATCH EXTRACTION - Processamento em Lote")
        print("=" * 80)
        print(f"Pasta de entrada: {input_folder}")
        print(f"Arquivo de saída: {output_path}")
        if label_filter:
            print(f"Filtro de label: {label_filter}")
        print("=" * 80)
        print()
    
    # Carregar dataset.json se existir
    dataset_path = input_folder / "dataset.json"
    dataset = load_dataset(dataset_path)
    
    if verbose and dataset:
        print(f"Dataset carregado: {len(dataset)} entradas encontradas")
        print()
    
    # Encontrar PDFs
    pdfs = find_pdfs_in_folder(input_folder)
    
    if not pdfs:
        error_print(f"ERRO: Nenhum PDF encontrado em {input_folder}")
        sys.exit(1)
    
    if verbose:
        print(f"PDFs encontrados: {len(pdfs)}")
        for pdf in pdfs:
            print(f"  - {pdf.name}")
        print()
    
    # Processar cada PDF
    all_results = []
    total = len(pdfs)
    processing_times = []  # Lista para armazenar tempos de processamento
    start_total_time = time.time()  # Tempo total de início
    
    for idx, pdf_path in enumerate(pdfs, 1):
        pdf_filename = pdf_path.name
        
        if verbose:
            print("=" * 80)
            print(f"PROCESSANDO [{idx}/{total}]: {pdf_filename}")
            print("=" * 80)
        
        # Obter schema do dataset ou usar padrão
        schema_info = get_schema_for_pdf(pdf_filename, dataset)
        
        if schema_info:
            label = schema_info["label"]
            schema = schema_info["schema"]
            
            if label_filter and label != label_filter:
                if verbose:
                    print(f"  Pulando: label '{label}' não corresponde ao filtro '{label_filter}'")
                    print()
                continue
            
            if verbose:
                print(f"  Label: {label}")
                print(f"  Campos do schema: {list(schema.keys())}")
        else:
            if label_filter:
                # Se há filtro mas não encontrou no dataset, pular
                if verbose:
                    print(f"  Pulando: PDF não encontrado no dataset e há filtro de label")
                    print()
                continue
            
            # Usar schema padrão genérico
            label = "unknown"
            schema = {
                "texto": "Extrair todo o texto do documento"
            }
            
            if verbose:
                print(f"  AVISO: PDF não encontrado no dataset.json, usando schema genérico")
                print(f"  Label: {label}")
        
        if verbose:
            print(f"  Iniciando extração...")
            print()
        
        # Processar PDF
        start_time = time.time()  # Tempo de início deste PDF
        try:
            result = extractor_service.process_pdf(
                pdf_path=str(pdf_path),
                label=label,
                schema=schema,
                filename=pdf_filename,
                on_progress=None,  # Sem callback de progresso para CLI
                generate_graph=False,  # Não gerar gráficos no modo batch
                debug=verbose,  # Debug baseado em verbose (quiet=False significa debug=True)
                use_learning=use_learning
            )
            
            elapsed_time = time.time() - start_time
            processing_times.append(elapsed_time)
            
            # Extrair apenas os dados extraídos (result.result) ou None se erro
            if result["status"] == "ok" and result.get("result"):
                # Resultado é um dicionário simples com chaves do schema -> valores extraídos
                extracted_data = result["result"]
                all_results.append(extracted_data)
                
                # Sempre imprimir o dicionário assim que processar (modo quiet ou verbose)
                print(json.dumps(extracted_data, ensure_ascii=False, indent=2))
                
                if verbose:
                    print(f"  ✓ Extração concluída com sucesso")
                    print(f"    Campos extraídos: {len(extracted_data)}")
                    print()
            else:
                # Em caso de erro, adicionar None ou dicionário vazio
                all_results.append(None)
                
                # Sempre imprimir null para erro
                print("null")
                
                if verbose:
                    error_msg = result.get('error_message', 'Erro desconhecido')
                    print(f"  ✗ Erro na extração: {error_msg}")
                    print()
        
        except Exception as e:
            elapsed_time = time.time() - start_time
            processing_times.append(elapsed_time)
            
            # Sempre imprimir null para erro
            print("null")
            
            if verbose:
                print(f"  ✗ ERRO ao processar: {e}")
                print()
            
            # Adicionar None em caso de erro
            all_results.append(None)
    
    # Preparar resposta final: lista de dicionários na mesma ordem da entrada
    # Se for apenas um PDF, retornar o dicionário diretamente; se múltiplos, retornar lista
    # Manter None (será serializado como null no JSON) em caso de erro
    if len(all_results) == 1:
        # Um único PDF: retornar dicionário diretamente ou null se erro
        response = all_results[0] if all_results[0] is not None else None
    else:
        # Múltiplos PDFs: retornar lista (None será null no JSON)
        response = all_results
    
    # Salvar JSON de saída
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    total_time = time.time() - start_total_time
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(response, f, indent=2, ensure_ascii=False)
        
        if verbose:
            print("=" * 80)
            print("PROCESSAMENTO CONCLUÍDO")
            print("=" * 80)
            print(f"Total processado: {len(all_results)} PDF(s)")
            print(f"Sucessos: {sum(1 for r in all_results if r is not None)}")
            print(f"Erros: {sum(1 for r in all_results if r is None)}")
            print(f"Resultado salvo em: {output_path}")
            print("=" * 80)
        else:
            # Modo quiet: printar apenas tempo total e médio
            avg_time = total_time / len(processing_times) if processing_times else 0
            print(f"Tempo total: {total_time:.2f}s")
            print(f"Tempo médio: {avg_time:.2f}s")
    
    except Exception as e:
        error_print(f"ERRO ao salvar arquivo de saída: {e}")
        sys.exit(1)


def main():
    """Função principal do CLI."""
    parser = argparse.ArgumentParser(
        description="Processa múltiplos PDFs de uma pasta e gera JSON de resposta oficial",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Processar todos os PDFs da pasta samples
  python scripts/batch_extract.py --input data/samples --output results.json
  
  # Processar apenas PDFs com label específico
  python scripts/batch_extract.py --input data/samples --output results.json --label carteira_oab
  
  # Processar pasta customizada
  python scripts/batch_extract.py --input /caminho/para/pdfs --output /caminho/para/saida.json
        """
    )
    
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Caminho da pasta contendo os PDFs (e opcionalmente dataset.json)"
    )
    
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="Caminho do arquivo JSON de saída"
    )
    
    parser.add_argument(
        "--label",
        "-l",
        type=str,
        default=None,
        help="Filtrar apenas PDFs com este label (opcional)"
    )
    
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Modo silencioso (não imprime progresso)"
    )
    
    parser.add_argument(
        "--no-learning",
        action="store_true",
        help="Desabilitar aprendizado incremental"
    )
    
    args = parser.parse_args()
    
    # Converter para Path
    input_folder = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    
    # Validar pasta de entrada
    if not input_folder.exists():
        error_print(f"ERRO: Pasta não encontrada: {input_folder}")
        sys.exit(1)
    
    if not input_folder.is_dir():
        error_print(f"ERRO: Caminho não é uma pasta: {input_folder}")
        sys.exit(1)
    
    # Processar
    try:
        process_folder(
            input_folder=input_folder,
            output_path=output_path,
            label_filter=args.label,
            verbose=not args.quiet,
            use_learning=not args.no_learning
        )
    except KeyboardInterrupt:
        error_print("\n\nProcessamento interrompido pelo usuário")
        sys.exit(130)
    except Exception as e:
        error_print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

