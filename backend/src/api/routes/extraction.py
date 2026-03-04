"""Rotas de extração."""

import json
import sys
from pathlib import Path
from typing import List, Optional

# Importar debug helper
try:
    from utils.debug import debug_print, error_print, set_debug_mode
except ImportError:
    # Fallback se não conseguir importar
    def debug_print(*args, **kwargs):
        pass
    def error_print(*args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)
    def set_debug_mode(enabled: bool):
        pass

# LOG IMEDIATO - ANTES DE QUALQUER IMPORT (apenas em debug)
debug_print("[EXTRACTION_ROUTES] Módulo extraction.py sendo importado...")

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

debug_print("[EXTRACTION_ROUTES] FastAPI importado")

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

debug_print("[EXTRACTION_ROUTES] Tentando importar extractor_service...")

try:
    from services.extractor_service import extractor_service
    debug_print("[EXTRACTION_ROUTES] extractor_service importado com sucesso")
except Exception as e:
    error_print(f"[EXTRACTION_ROUTES] ERRO ao importar extractor_service: {e}")
    import traceback
    traceback.print_exc()
    raise

try:
    from services.graph_generator import graph_generator
    debug_print("[EXTRACTION_ROUTES] graph_generator importado com sucesso")
except Exception as e:
    error_print(f"[EXTRACTION_ROUTES] ERRO ao importar graph_generator: {e}")
    import traceback
    traceback.print_exc()
    raise

try:
    from utils.file_handler import save_uploaded_files, cleanup_temp_dir
    debug_print("[EXTRACTION_ROUTES] file_handler importado com sucesso")
except Exception as e:
    error_print(f"[EXTRACTION_ROUTES] ERRO ao importar file_handler: {e}")
    import traceback
    traceback.print_exc()
    raise

try:
    from api.models import RunResult, ExtractionResponse
    debug_print("[EXTRACTION_ROUTES] models importado com sucesso")
except Exception as e:
    error_print(f"[EXTRACTION_ROUTES] ERRO ao importar models: {e}")
    import traceback
    traceback.print_exc()
    raise


debug_print("[EXTRACTION_ROUTES] Criando router...")

router = APIRouter(prefix="/api", tags=["extraction"])

debug_print("[EXTRACTION_ROUTES] Router criado com prefix=/api")


debug_print("[EXTRACTION_ROUTES] Registrando rota POST /graph-extract...")

@router.post("/graph-extract")
async def extract_graph(
    request: Request,
    label: str = Form(...),
    schema: Optional[str] = Form(None),  # JSON string (opcional se schema_file fornecido)
    schema_file: Optional[UploadFile] = File(None),
    files: List[UploadFile] = File(...),
    dev_mode: bool = Form(False),
    use_learning: bool = Form(True)
):
    """Extrai dados de múltiplos PDFs usando Graph Extractor.
    
    Args:
        label: Label do documento
        schema: Schema JSON como string (ou None se schema_file fornecido)
        schema_file: Arquivo JSON com schema (opcional)
        files: Lista de arquivos PDF (até 10)
        dev_mode: Se True, gera HTML do grafo e inclui metadados
        use_learning: Se True, usa aprendizado incremental de documentos anteriores
        
    Returns:
        JSON array com resultados de cada PDF
    """
    # Configurar modo debug baseado em dev_mode
    set_debug_mode(dev_mode)
    
    import time
    timestamp = time.time()
    
    debug_print("\n" + "=" * 80)
    debug_print(f"[API] === ROTA /api/graph-extract CHAMADA ===")
    debug_print(f"[API] Timestamp: {timestamp}")
    debug_print(f"[API] REQUISIÇÃO RECEBIDA: POST /api/graph-extract")
    debug_print(f"[API] Label: {label}")
    debug_print(f"[API] PDFs: {len(files)} arquivo(s)")
    for i, f in enumerate(files, 1):
        debug_print(f"[API]   PDF {i}: {f.filename} ({f.size if hasattr(f, 'size') else 'N/A'} bytes)")
    debug_print(f"[API] Dev mode: {dev_mode}")
    debug_print(f"[API] Schema: {schema[:100] if schema and len(schema) > 100 else schema}")
    debug_print("=" * 80 + "\n")
    
    # Validar número de arquivos
    debug_print(f"[API] Validando arquivos...")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Máximo de 10 PDFs permitidos")
    
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Pelo menos 1 PDF é necessário")
    
    debug_print(f"[API] Validação OK: {len(files)} arquivo(s)")
    
    # Processar schema (schema_file tem prioridade)
    debug_print(f"[API] Processando schema...")
    schema_dict = None
    try:
        if schema_file:
            debug_print(f"[API] Usando schema_file")
            schema_content = await schema_file.read()
            schema_dict = json.loads(schema_content.decode("utf-8"))
        elif schema:
            debug_print(f"[API] Usando schema string (tamanho: {len(schema) if schema else 0})")
            debug_print(f"[API] Schema raw (primeiros 200 chars): {schema[:200] if schema else 'None'}")
            schema_dict = json.loads(schema)
        else:
            error_print(f"[API] ERRO: Schema não fornecido")
            raise HTTPException(status_code=400, detail="Schema ou schema_file é obrigatório")
        
        # Validar que schema_dict é um dicionário
        debug_print(f"[API] Tipo do schema após parse: {type(schema_dict)}")
        if isinstance(schema_dict, list):
            debug_print(f"[API] AVISO: Schema é uma lista, convertendo para dicionário...")
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
        
        debug_print(f"[API] Schema processado: {len(schema_dict)} campos")
        debug_print(f"[API] Schema keys: {list(schema_dict.keys())}")
    except json.JSONDecodeError as e:
        error_print(f"[API] ERRO: Schema JSON inválido: {e}")
        raise HTTPException(status_code=400, detail=f"Schema JSON inválido: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        error_print(f"[API] ERRO ao processar schema: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Erro ao processar schema: {str(e)}")
    
    # Salvar arquivos temporariamente
    debug_print(f"[API] Salvando arquivos PDF...")
    try:
        pdf_files, temp_dir = await save_uploaded_files(files, max_files=10)
        debug_print(f"[API] Arquivos salvos: {len(pdf_files)} arquivo(s) em {temp_dir}")
    except ValueError as e:
        error_print(f"[API] ERRO ao salvar: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_print(f"[API] ERRO ao salvar arquivos: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivos: {str(e)}")
    
    try:
        # pdf_files já vem como lista de tuplas (Path, filename) do file_handler
        # Converter para lista de tuplas (str, str) para o serviço
        pdf_files_with_names = [(str(pdf_path), filename) for pdf_path, filename in pdf_files]
        
        debug_print(f"[API] Arquivos convertidos: {len(pdf_files_with_names)}")
        for pdf_path, filename in pdf_files_with_names:
            debug_print(f"[API]   - {filename} -> {pdf_path}")
        
        # Processar PDFs sequencialmente
        def progress_callback(step: str, current: int, total: int) -> None:
            # Para SSE, podemos enviar eventos aqui
            # Por enquanto, apenas log se dev_mode
            debug_print(f"[API] PROGRESSO [{current}/{total}]: {step}")
        
        debug_print(f"[API] Preparando processamento...")
        debug_print(f"[API] PDFs: {len(pdf_files_with_names)}, Campos: {len(schema_dict)}, Dev: {dev_mode}")
        
        if dev_mode:
            debug_print(f"[API] ===== MODO DEV ATIVADO - PRINTS DETALHADOS =====\n")
        
        debug_print(f"[API] Chamando extractor_service.process_multiple_pdfs...")
        debug_print(f"[API] Parâmetros:")
        debug_print(f"[API]   - label: {label}")
        debug_print(f"[API]   - schema keys: {list(schema_dict.keys())}")
        debug_print(f"[API]   - pdf_files: {len(pdf_files_with_names)} arquivo(s)")
        debug_print(f"[API]   - generate_graph: {dev_mode}")
        debug_print(f"[API]   - debug: {dev_mode}")
        
        try:
            results = extractor_service.process_multiple_pdfs(
                pdf_files=pdf_files_with_names,
                label=label,
                schema=schema_dict,
                on_progress=progress_callback,
                generate_graph=dev_mode,
                debug=dev_mode,  # Passar debug=dev_mode para ativar prints apenas no modo dev
                use_learning=use_learning
            )
            
            debug_print(f"[API] extractor_service.process_multiple_pdfs RETORNOU com {len(results)} resultado(s)")
        except Exception as extract_error:
            error_print(f"[API] ERRO DURANTE process_multiple_pdfs:")
            import traceback
            traceback.print_exc()
            raise
        
        if dev_mode:
            debug_print(f"[API] Processamento concluído: {len(results)} resultado(s)")
        
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
                    debug_print(f"[API] ERRO ao validar resultado {i+1}: {e}")
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
            response_dict = response.model_dump()
            debug_print(f"[API] Resposta serializada: {len(run_results)} resultado(s)")
            return response_dict
        except Exception as e:
            error_print(f"[API] ERRO ao serializar resposta: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Erro ao serializar resposta: {str(e)}")
        
    except HTTPException:
        # Re-raise HTTP exceptions (já tratadas)
        raise
    except Exception as e:
        import traceback
        error_detail = f"Erro durante extração: {str(e)}\n{traceback.format_exc()}"
        error_print(f"[API] ===== ERRO CAPTURADO =====")
        error_print(f"[API] Tipo do erro: {type(e).__name__}")
        error_print(f"[API] Mensagem: {str(e)}")
        error_print(f"[API] Traceback completo:")
        traceback.print_exc()
        if dev_mode:
            debug_print(f"[API] ERRO: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Erro durante extração: {str(e)}")
    finally:
        # Limpar arquivos temporários
        try:
            cleanup_temp_dir(temp_dir)
        except Exception as e:
            debug_print(f"Erro ao limpar diretório temporário: {e}")

