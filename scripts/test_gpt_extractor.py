"""Script de teste para o extrator GPT."""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gpt_extractor import GPTSafeExtractor, GPTExtractorConfig


def main():
    """Testa o extrator GPT com um PDF de exemplo."""
    # Iniciar contagem de tempo
    start_time = time.time()
    
    # Configuração
    config = GPTExtractorConfig(
        model="gpt-5-mini",
        temperature=0.0,
        max_ocr_chars=3000,
        timeout_seconds=30,
        case_sensitive_grounding=True,
        enable_type_gate=True,
        use_graph_extraction=True
    )
    
    # Criar extrator
    extractor = GPTSafeExtractor(config=config)
    
    # Schema de exemplo (OAB)
    schema = {
        "inscricao": "Número de inscrição na OAB",
        "nome": "Nome completo do profissional",
        "seccional": "Sigla da seccional (UF)",
        "situacao": "Situação do profissional",
        "categoria": "Categoria do profissional",
        "subsecao": "Subseção/cidade"
    }
    
    # PDF de exemplo
    pdf_path = "data/samples/oab_1.pdf"
    
    if not Path(pdf_path).exists():
        print(f"AVISO: {pdf_path} não encontrado. Use outro PDF.")
        return
    
    print("="*80)
    print("TESTE DO EXTRATOR GPT")
    print("="*80)
    print(f"\nPDF: {pdf_path}")
    print(f"Schema: {list(schema.keys())}")
    print(f"Modelo: {config.model}")
    print("\nExtraindo...\n")
    
    # Extrair
    result = extractor.extract(
        pdf_path=pdf_path,
        schema=schema,
        include_trace=True
    )
    
    # Mostrar resultado
    # Calcular tempo total
    total_time = time.time() - start_time
    
    # Mostrar apenas resultado
    print(json.dumps(result.result, indent=2, ensure_ascii=False))
    
    # Mostrar tempos e tokens
    if result.trace:
        print("\n" + "="*60)
        print("TEMPOS POR ETAPA:")
        print("="*60)
        print(f"Extraction OCR/Graph: {result.trace.t_ocr_ms/1000:.2f}s ({result.trace.t_ocr_ms:.0f}ms)")
        print(f"Construção do Prompt:  {result.trace.t_prompt_ms/1000:.2f}s ({result.trace.t_prompt_ms:.0f}ms)")
        print(f"Chamada GPT:           {result.trace.t_gpt_ms/1000:.2f}s ({result.trace.t_gpt_ms:.0f}ms)")
        print(f"Validação:             {result.trace.t_validate_ms/1000:.2f}s ({result.trace.t_validate_ms:.0f}ms)")
        
        # Mostrar informações de tokens
        if result.trace.token_info:
            print("\n" + "="*60)
            print("TOKENS:")
            print("="*60)
            ti = result.trace.token_info
            print(f"Prompt tokens:        {ti.get('prompt_tokens', 0)}")
            completion_tokens = ti.get('completion_tokens', 0)
            reasoning_tokens = ti.get('reasoning_tokens', 0)
            output_tokens = completion_tokens - reasoning_tokens
            print(f"Completion tokens:    {completion_tokens}")
            print(f"  - Reasoning tokens: {reasoning_tokens}")
            print(f"  - Output tokens:    {output_tokens}")
            print(f"Total tokens:         {ti.get('total_tokens', 0)}")
        
        print("\n" + "="*60)
        print(f"Tempo total: {total_time:.2f}s")
        print("="*60)


if __name__ == "__main__":
    main()

