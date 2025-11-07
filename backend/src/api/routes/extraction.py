"""Rotas de extração."""

import json
import sys
from pathlib import Path
from typing import List, Optional

# LOG IMEDIATO - ANTES DE QUALQUER IMPORT
print("[EXTRACTION_ROUTES] Módulo extraction.py sendo importado...", flush=True)
sys.stdout.flush()

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

print("[EXTRACTION_ROUTES] FastAPI importado", flush=True)
sys.stdout.flush()

# Adicionar raiz do projeto ao path
# backend/src/api/routes/extraction.py
# -> backend/src/api/routes (0 níveis - próprio)
# -> backend/src/api (1 nível - parent)
# -> backend/src (2 níveis - parent.parent)
# -> backend (3 níveis - parent.parent.parent)
# -> raiz do projeto (4 níveis - parent.parent.parent.parent)
backend_src = Path(__file__).parent.parent.parent  # backend/src
backend_dir = backend_src.parent                    # backend
project_root = backend_dir.parent                   # raiz do projeto

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

print("[EXTRACTION_ROUTES] Tentando importar extractor_service...", flush=True)
sys.stdout.flush()

try:
    from services.extractor_service import extractor_service
    print("[EXTRACTION_ROUTES] extractor_service importado com sucesso", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[EXTRACTION_ROUTES] ERRO ao importar extractor_service: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise

try:
    from services.graph_generator import graph_generator
    print("[EXTRACTION_ROUTES] graph_generator importado com sucesso", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[EXTRACTION_ROUTES] ERRO ao importar graph_generator: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise

try:
    from utils.file_handler import save_uploaded_files, cleanup_temp_dir
    print("[EXTRACTION_ROUTES] file_handler importado com sucesso", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[EXTRACTION_ROUTES] ERRO ao importar file_handler: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise

try:
    from api.models import RunResult, ExtractionResponse
    print("[EXTRACTION_ROUTES] models importado com sucesso", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[EXTRACTION_ROUTES] ERRO ao importar models: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise


print("[EXTRACTION_ROUTES] Criando router...", flush=True)
sys.stdout.flush()

router = APIRouter(prefix="/api", tags=["extraction"])

print("[EXTRACTION_ROUTES] Router criado com prefix=/api", flush=True)
sys.stdout.flush()


print("[EXTRACTION_ROUTES] Registrando rota POST /graph-extract...", flush=True)
sys.stdout.flush()

@router.post("/graph-extract")
async def extract_graph(
    request: Request,
    label: str = Form(...),
    schema: Optional[str] = Form(None),  # JSON string (opcional se schema_file fornecido)
    schema_file: Optional[UploadFile] = File(None),
    files: List[UploadFile] = File(...),
    dev_mode: bool = Form(False)
):
    """Extrai dados de múltiplos PDFs usando Graph Extractor.
    
    Args:
        label: Label do documento
        schema: Schema JSON como string (ou None se schema_file fornecido)
        schema_file: Arquivo JSON com schema (opcional)
        files: Lista de arquivos PDF (até 10)
        dev_mode: Se True, gera HTML do grafo e inclui metadados
        
    Returns:
        JSON array com resultados de cada PDF
    """
    # IMPORTANTE: Este print DEVE aparecer sempre que a requisição chegar
    # LOG IMEDIATO - ANTES DE QUALQUER PROCESSAMENTO
    import sys
    import time
    timestamp = time.time()
    
    # FORÇAR FLUSH IMEDIATO
    sys.stdout.flush()
    sys.stderr.flush()
    
    print("\n" + "=" * 80, flush=True)
    print(f"[API] ═══ ROTA /api/graph-extract CHAMADA ═══", flush=True)
    print(f"[API] Timestamp: {timestamp}", flush=True)
    print(f"[API] REQUISIÇÃO RECEBIDA: POST /api/graph-extract", flush=True)
    print(f"[API] Label: {label}", flush=True)
    print(f"[API] PDFs: {len(files)} arquivo(s)", flush=True)
    for i, f in enumerate(files, 1):
        print(f"[API]   PDF {i}: {f.filename} ({f.size if hasattr(f, 'size') else 'N/A'} bytes)", flush=True)
    print(f"[API] Dev mode: {dev_mode}", flush=True)
    print(f"[API] Schema: {schema[:100] if schema and len(schema) > 100 else schema}", flush=True)
    print("=" * 80 + "\n", flush=True)
    
    # FORÇAR FLUSH NOVAMENTE
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Validar número de arquivos
    print(f"[API] Validando arquivos...", flush=True)
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Máximo de 10 PDFs permitidos")
    
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Pelo menos 1 PDF é necessário")
    
    print(f"[API] Validação OK: {len(files)} arquivo(s)", flush=True)
    
    # Processar schema (schema_file tem prioridade)
    print(f"[API] Processando schema...", flush=True)
    schema_dict = None
    try:
        if schema_file:
            print(f"[API] Usando schema_file", flush=True)
            schema_content = await schema_file.read()
            schema_dict = json.loads(schema_content.decode("utf-8"))
        elif schema:
            print(f"[API] Usando schema string (tamanho: {len(schema) if schema else 0})", flush=True)
            print(f"[API] Schema raw (primeiros 200 chars): {schema[:200] if schema else 'None'}", flush=True)
            schema_dict = json.loads(schema)
        else:
            print(f"[API] ERRO: Schema não fornecido", flush=True)
            raise HTTPException(status_code=400, detail="Schema ou schema_file é obrigatório")
        
        # Validar que schema_dict é um dicionário
        print(f"[API] Tipo do schema após parse: {type(schema_dict)}", flush=True)
        if isinstance(schema_dict, list):
            print(f"[API] AVISO: Schema é uma lista, convertendo para dicionário...", flush=True)
            # Se for lista, tentar converter para dicionário
            # Pode ser uma lista de objetos [{key: value}, ...] ou lista de pares [[key, value], ...]
            if len(schema_dict) > 0 and isinstance(schema_dict[0], dict):
                # Lista de objetos: [{key: value}, ...]
                schema_dict = {k: v for item in schema_dict for k, v in item.items()}
            elif len(schema_dict) > 0 and isinstance(schema_dict[0], (list, tuple)) and len(schema_dict[0]) == 2:
                # Lista de pares: [[key, value], ...]
                schema_dict = dict(schema_dict)
            else:
                raise HTTPException(status_code=400, detail="Schema deve ser um objeto JSON (dicionário), não uma lista")
        
        if not isinstance(schema_dict, dict):
            raise HTTPException(status_code=400, detail=f"Schema deve ser um objeto JSON (dicionário), recebido: {type(schema_dict).__name__}")
        
        print(f"[API] Schema processado: {len(schema_dict)} campos", flush=True)
        print(f"[API] Schema keys: {list(schema_dict.keys())}", flush=True)
        sys.stdout.flush()
    except json.JSONDecodeError as e:
        print(f"[API] ERRO: Schema JSON inválido: {e}", flush=True)
        raise HTTPException(status_code=400, detail=f"Schema JSON inválido: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] ERRO ao processar schema: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        raise HTTPException(status_code=400, detail=f"Erro ao processar schema: {str(e)}")
    
    # Salvar arquivos temporariamente
    print(f"[API] Salvando arquivos PDF...", flush=True)
    try:
        pdf_files, temp_dir = await save_uploaded_files(files, max_files=10)
        print(f"[API] Arquivos salvos: {len(pdf_files)} arquivo(s) em {temp_dir}", flush=True)
        sys.stdout.flush()
    except ValueError as e:
        print(f"[API] ERRO ao salvar: {e}", flush=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[API] ERRO ao salvar arquivos: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivos: {str(e)}")
    
    try:
        # pdf_files já vem como lista de tuplas (Path, filename) do file_handler
        # Converter para lista de tuplas (str, str) para o serviço
        pdf_files_with_names = [(str(pdf_path), filename) for pdf_path, filename in pdf_files]
        
        print(f"[API] Arquivos convertidos: {len(pdf_files_with_names)}", flush=True)
        for pdf_path, filename in pdf_files_with_names:
            print(f"[API]   - {filename} -> {pdf_path}", flush=True)
        sys.stdout.flush()
        
        # Processar PDFs sequencialmente
        def progress_callback(step: str, current: int, total: int) -> None:
            # Para SSE, podemos enviar eventos aqui
            # Por enquanto, apenas log se dev_mode
            print(f"[API] PROGRESSO [{current}/{total}]: {step}", flush=True)
            sys.stdout.flush()
            if dev_mode:
                print(f"[{current}/{total}] {step}", flush=True)
        
        print(f"[API] Preparando processamento...", flush=True)
        print(f"[API] PDFs: {len(pdf_files_with_names)}, Campos: {len(schema_dict)}, Dev: {dev_mode}", flush=True)
        sys.stdout.flush()
        
        if dev_mode:
            print(f"[API] ===== MODO DEV ATIVADO - PRINTS DETALHADOS =====\n", flush=True)
        
        print(f"[API] Chamando extractor_service.process_multiple_pdfs...", flush=True)
        print(f"[API] Parâmetros:", flush=True)
        print(f"[API]   - label: {label}", flush=True)
        print(f"[API]   - schema keys: {list(schema_dict.keys())}", flush=True)
        print(f"[API]   - pdf_files: {len(pdf_files_with_names)} arquivo(s)", flush=True)
        print(f"[API]   - generate_graph: {dev_mode}", flush=True)
        print(f"[API]   - debug: {dev_mode}", flush=True)
        sys.stdout.flush()
        
        try:
            results = extractor_service.process_multiple_pdfs(
                pdf_files=pdf_files_with_names,
                label=label,
                schema=schema_dict,
                on_progress=progress_callback,
                generate_graph=dev_mode,
                debug=dev_mode  # Passar debug=dev_mode para ativar prints apenas no modo dev
            )
            
            print(f"[API] extractor_service.process_multiple_pdfs RETORNOU com {len(results)} resultado(s)", flush=True)
            sys.stdout.flush()
        except Exception as extract_error:
            print(f"[API] ERRO DURANTE process_multiple_pdfs:", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            raise
        
        if dev_mode:
            print(f"[API] Processamento concluído: {len(results)} resultado(s)", flush=True)
        
        # Converter para modelos Pydantic com validação
        run_results = []
        for i, r in enumerate(results):
            try:
                # Validar estrutura básica
                if not isinstance(r, dict):
                    raise ValueError(f"Resultado {i+1} não é um dicionário: {type(r)}")
                
                run_result = RunResult(
                    run_id=r.get("run_id", f"unknown_{i}"),
                    filename=r.get("filename", "unknown"),
                    status=r.get("status", "error"),
                    result=r.get("result"),
                    error_message=r.get("error_message"),
                    dev=r.get("dev") if dev_mode else None
                )
                run_results.append(run_result)
                
            except Exception as e:
                if dev_mode:
                    print(f"[API] ERRO ao validar resultado {i+1}: {e}")
                    import traceback
                    traceback.print_exc()
                # Criar resultado de erro
                run_results.append(RunResult(
                    run_id=r.get("run_id", f"error_{i}"),
                    filename=r.get("filename", "unknown"),
                    status="error",
                    result=None,
                    error_message=f"Erro ao processar resultado: {str(e)}",
                    dev=None
                ))
        
        response = ExtractionResponse(runs=run_results)
        
        # Tentar serializar para verificar se há problemas
        try:
            response_dict = response.dict()
            if dev_mode:
                print(f"[API] Resposta serializada: {len(run_results)} resultado(s)")
            return response_dict
        except Exception as e:
            if dev_mode:
                print(f"[API] ERRO ao serializar resposta: {e}")
                import traceback
                traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Erro ao serializar resposta: {str(e)}")
        
    except HTTPException:
        # Re-raise HTTP exceptions (já tratadas)
        raise
    except Exception as e:
        import traceback
        error_detail = f"Erro durante extração: {str(e)}\n{traceback.format_exc()}"
        print(f"[API] ===== ERRO CAPTURADO =====", flush=True)
        print(f"[API] Tipo do erro: {type(e).__name__}", flush=True)
        print(f"[API] Mensagem: {str(e)}", flush=True)
        print(f"[API] Traceback completo:", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        if dev_mode:
            print(f"[API] ERRO: {error_detail}", flush=True)
        raise HTTPException(status_code=500, detail=f"Erro durante extração: {str(e)}")
    finally:
        # Limpar arquivos temporários
        try:
            cleanup_temp_dir(temp_dir)
        except Exception as e:
            print(f"Erro ao limpar diretório temporário: {e}")

