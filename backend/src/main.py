"""Aplicação FastAPI principal."""

import sys
from pathlib import Path

# FORÇAR FLUSH IMEDIATO
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("=" * 80, flush=True)
print("[MAIN] Iniciando aplicacao FastAPI...", flush=True)
print("=" * 80, flush=True)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import time

# Adicionar raiz do projeto ao path
# backend/src/main.py
# -> backend/src (1 nível acima - parent)
# -> backend (2 níveis acima - parent.parent)
# -> raiz do projeto (3 níveis acima - parent.parent.parent)
backend_src = Path(__file__).parent  # backend/src
backend_dir = backend_src.parent     # backend
project_root = backend_dir.parent    # raiz do projeto

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Adicionar backend/src ao path para imports relativos
backend_src = Path(__file__).parent
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

print("[MAIN] Paths configurados", flush=True)
print(f"[MAIN] Project root: {project_root}", flush=True)
print(f"[MAIN] Backend src: {backend_src}", flush=True)

# Agora importar usando caminhos relativos dentro de backend/src
print("[MAIN] Importando rotas...", flush=True)
print("[MAIN] Tentando importar extraction...", flush=True)
sys.stdout.flush()

try:
    from api.routes import extraction
    print("[MAIN] extraction importado com sucesso", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[MAIN] ERRO ao importar extraction: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise

print("[MAIN] Tentando importar graph...", flush=True)
sys.stdout.flush()

try:
    from api.routes import graph
    print("[MAIN] graph importado com sucesso", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"[MAIN] ERRO ao importar graph: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise

print("[MAIN] Rotas importadas com sucesso", flush=True)


print("[MAIN] Criando app FastAPI...", flush=True)
app = FastAPI(
    title="Graph Extractor API",
    description="API para extração de dados de PDFs usando Graph Extractor",
    version="1.0.0"
)
print("[MAIN] App FastAPI criado", flush=True)

# Configurar logging
logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)
print("[MAIN] Logging configurado", flush=True)

# Middleware para log de requisições
@app.middleware("http")
async def log_requests(request: Request, call_next):
    import sys
    start_time = time.time()
    # Log ANTES de qualquer coisa
    print("=" * 80, flush=True)
    print(f"[MIDDLEWARE] →→→ REQUISIÇÃO RECEBIDA ←←←", flush=True)
    print(f"[MIDDLEWARE] Método: {request.method}", flush=True)
    print(f"[MIDDLEWARE] URL: {request.url}", flush=True)
    print(f"[MIDDLEWARE] Path: {request.url.path}", flush=True)
    print(f"[MIDDLEWARE] Headers: {dict(request.headers)}", flush=True)
    print("=" * 80, flush=True)
    sys.stdout.flush()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        print(f"[MIDDLEWARE] ← {response.status_code} {request.url} ({process_time:.2f}s)", flush=True)
        sys.stdout.flush()
        return response
    except Exception as e:
        process_time = time.time() - start_time
        print(f"[MIDDLEWARE] ERRO: {e} ({process_time:.2f}s)", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        raise

# Exception handler para ValidationError (422) - erros de validação de Form/File
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import sys
    print("=" * 80, flush=True)
    print("[VALIDATION_ERROR] Erro de validação de requisição!", flush=True)
    print(f"[VALIDATION_ERROR] Path: {request.url.path}", flush=True)
    print(f"[VALIDATION_ERROR] Método: {request.method}", flush=True)
    print(f"[VALIDATION_ERROR] Erro: {exc}", flush=True)
    print(f"[VALIDATION_ERROR] Detalhes: {exc.errors()}", flush=True)
    print("=" * 80, flush=True)
    sys.stdout.flush()
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body}
    )

# Middleware de tratamento de erros
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import sys
    print("=" * 80, flush=True)
    print("[GLOBAL_ERROR] Erro não tratado capturado!", flush=True)
    print(f"[GLOBAL_ERROR] Tipo: {type(exc).__name__}", flush=True)
    print(f"[GLOBAL_ERROR] Mensagem: {str(exc)}", flush=True)
    import traceback
    traceback.print_exc()
    print("=" * 80, flush=True)
    sys.stdout.flush()
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Erro interno do servidor: {str(exc)}"}
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origens
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rotas
print("[MAIN] Registrando rotas...", flush=True)
print("[MAIN] Registrando router de extraction...", flush=True)
app.include_router(extraction.router)
print("[MAIN] Router de extraction registrado", flush=True)
print("[MAIN] Registrando router de graph...", flush=True)
app.include_router(graph.router)
print("[MAIN] Router de graph registrado", flush=True)

# Listar todas as rotas registradas
print("[MAIN] Rotas registradas:", flush=True)
for route in app.routes:
    if hasattr(route, 'methods') and hasattr(route, 'path'):
        print(f"[MAIN]   {list(route.methods)} {route.path}", flush=True)
print("[MAIN] Rotas registradas com sucesso", flush=True)

# Servir arquivos estáticos (HTMLs do grafo)
# NOTA: A rota do router /graph/{run_id}.html tem prioridade sobre o mount do StaticFiles
# O mount do StaticFiles serve como fallback para arquivos que não são servidos pela rota
graphs_dir = project_root / "backend" / "static" / "graphs"
graphs_dir.mkdir(parents=True, exist_ok=True)
# Montar StaticFiles APÓS as rotas do router para que a rota tenha prioridade
app.mount("/graph", StaticFiles(directory=str(graphs_dir)), name="graph_static")
print(f"[MAIN] Diretorio de graficos: {graphs_dir}", flush=True)
print(f"[MAIN] StaticFiles montado em /graph (fallback)", flush=True)


@app.get("/")
async def root():
    """Endpoint raiz."""
    print("[ROOT] Requisicao recebida em /", flush=True)
    return {"message": "Graph Extractor API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Endpoint de health check."""
    print("[HEALTH] Health check recebido", flush=True)
    return {"status": "ok"}


@app.get("/test")
async def test():
    """Endpoint de teste para verificar se o backend está respondendo."""
    import sys
    print("=" * 80, flush=True)
    print("[TEST] Endpoint de teste chamado", flush=True)
    print(f"[TEST] Timestamp: {time.time()}", flush=True)
    print("=" * 80, flush=True)
    sys.stdout.flush()
    return {
        "status": "ok",
        "message": "Backend está respondendo!",
        "timestamp": time.time()
    }

@app.post("/test-post")
async def test_post(request: Request):
    """Endpoint de teste POST para verificar se requisições POST chegam."""
    import sys
    print("=" * 80, flush=True)
    print("[TEST_POST] Endpoint de teste POST chamado", flush=True)
    print(f"[TEST_POST] Método: {request.method}", flush=True)
    print(f"[TEST_POST] URL: {request.url}", flush=True)
    print(f"[TEST_POST] Headers: {dict(request.headers)}", flush=True)
    try:
        body = await request.body()
        print(f"[TEST_POST] Body size: {len(body)} bytes", flush=True)
    except Exception as e:
        print(f"[TEST_POST] Erro ao ler body: {e}", flush=True)
    print("=" * 80, flush=True)
    sys.stdout.flush()
    return {
        "status": "ok",
        "message": "POST funcionando!",
        "timestamp": time.time()
    }

@app.get("/test-import")
async def test_import():
    """Endpoint para testar se o módulo GraphSchemaExtractor pode ser importado."""
    import sys
    from pathlib import Path
    
    print("=" * 80, flush=True)
    print("[TEST_IMPORT] Testando importação do GraphSchemaExtractor...", flush=True)
    sys.stdout.flush()
    
    backend_src = Path(__file__).parent
    backend_dir = backend_src.parent
    project_root = backend_dir.parent
    
    result = {
        "status": "ok",
        "project_root": str(project_root),
        "import_success": False,
        "error": None
    }
    
    try:
        print(f"[TEST_IMPORT] Project root: {project_root}", flush=True)
        print(f"[TEST_IMPORT] Tentando importar...", flush=True)
        sys.stdout.flush()
        
        # Tentar importar
        from src.graph_extractor import GraphSchemaExtractor
        print(f"[TEST_IMPORT] GraphSchemaExtractor importado com sucesso!", flush=True)
        print(f"[TEST_IMPORT] Tipo: {type(GraphSchemaExtractor)}", flush=True)
        sys.stdout.flush()
        
        result["import_success"] = True
        result["extractor_type"] = str(type(GraphSchemaExtractor))
        
        # Tentar criar uma instância
        try:
            print(f"[TEST_IMPORT] Tentando criar instância...", flush=True)
            sys.stdout.flush()
            extractor = GraphSchemaExtractor(
                embedding_model="BAAI/bge-small-en-v1.5",
                llm_model="gpt-4o-mini",
                debug=False
            )
            print(f"[TEST_IMPORT] Instância criada com sucesso!", flush=True)
            sys.stdout.flush()
            result["instance_created"] = True
        except Exception as inst_error:
            print(f"[TEST_IMPORT] ERRO ao criar instância: {inst_error}", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            result["instance_created"] = False
            result["instance_error"] = str(inst_error)
            
    except Exception as e:
        print(f"[TEST_IMPORT] ERRO ao importar: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        result["status"] = "error"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
    
    print("=" * 80, flush=True)
    sys.stdout.flush()
    return result

print("[MAIN] Aplicacao configurada com sucesso!", flush=True)
print("=" * 80, flush=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
