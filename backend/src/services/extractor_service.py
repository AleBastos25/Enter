"""Serviço de extração que envolve o GraphSchemaExtractor."""

import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Tuple

# Adicionar raiz do projeto ao path
# backend/src/services/extractor_service.py
# -> backend/src/services (0 níveis acima - é o próprio)
# -> backend/src (1 nível acima - parent)
# -> backend (2 níveis acima - parent.parent)
# -> raiz do projeto (3 níveis acima - parent.parent.parent)
backend_src = Path(__file__).parent.parent  # backend/src
backend_dir = backend_src.parent            # backend
project_root = backend_dir.parent           # raiz do projeto (correto!)

print(f"[EXTRACTOR_SERVICE] backend_src: {backend_src}", flush=True)
print(f"[EXTRACTOR_SERVICE] project_root: {project_root}", flush=True)

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    print(f"[EXTRACTOR_SERVICE] Adicionado project_root ao path: {project_root}", flush=True)

if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))
    print(f"[EXTRACTOR_SERVICE] Adicionado backend_src ao path: {backend_src}", flush=True)

# Verificar se o módulo existe
graph_extractor_path = project_root / "src" / "graph_extractor"
print(f"[EXTRACTOR_SERVICE] Verificando graph_extractor em: {graph_extractor_path}", flush=True)
if not graph_extractor_path.exists():
    raise ImportError(f"graph_extractor não encontrado em: {graph_extractor_path}")

# Verificar se __init__.py existe
init_file = graph_extractor_path / "__init__.py"
print(f"[EXTRACTOR_SERVICE] Verificando __init__.py: {init_file} (existe: {init_file.exists()})", flush=True)

# Verificar se extractor.py existe
extractor_file = graph_extractor_path / "extractor.py"
print(f"[EXTRACTOR_SERVICE] Verificando extractor.py: {extractor_file} (existe: {extractor_file.exists()})", flush=True)

try:
    print(f"[EXTRACTOR_SERVICE] Tentando importar módulo src.graph_extractor...", flush=True)
    import src.graph_extractor as graph_extractor_module
    print(f"[EXTRACTOR_SERVICE] Módulo src.graph_extractor importado: {graph_extractor_module}", flush=True)
    print(f"[EXTRACTOR_SERVICE] Diretório do módulo: {graph_extractor_module.__file__ if hasattr(graph_extractor_module, '__file__') else 'N/A'}", flush=True)
    
    print(f"[EXTRACTOR_SERVICE] Tentando importar GraphSchemaExtractor...", flush=True)
    from src.graph_extractor import GraphSchemaExtractor
    print(f"[EXTRACTOR_SERVICE] GraphSchemaExtractor importado com sucesso: {GraphSchemaExtractor}", flush=True)
    print(f"[EXTRACTOR_SERVICE] Tipo: {type(GraphSchemaExtractor)}", flush=True)
except ImportError as e:
    print(f"[EXTRACTOR_SERVICE] ERRO ao importar GraphSchemaExtractor: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise
except Exception as e:
    print(f"[EXTRACTOR_SERVICE] ERRO INESPERADO ao importar: {type(e).__name__}: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    raise

from services.graph_generator import graph_generator


class ExtractorService:
    """Serviço que gerencia extrações usando GraphSchemaExtractor."""
    
    def __init__(self):
        """Inicializa o serviço de extração."""
        self._extractor: Optional[GraphSchemaExtractor] = None
        self._debug_extractor: Optional[GraphSchemaExtractor] = None
    
    def get_extractor(self, debug: bool = False) -> GraphSchemaExtractor:
        """Obtém instância do extrator (singleton ou debug).
        
        Args:
            debug: Se True, usa extractor com debug ativado (separado)
            
        Returns:
            Instância do GraphSchemaExtractor
        """
        import sys
        
        if debug:
            # Extrator com debug (separado para não afetar o normal)
            if self._debug_extractor is None:
                print(f"[GET_EXTRACTOR] Inicializando extractor DEBUG...", flush=True)
                sys.stdout.flush()
                try:
                    # Usar EXATAMENTE os mesmos parâmetros do teste
                    print(f"[GET_EXTRACTOR] Parâmetros: embedding_model=BAAI/bge-small-en-v1.5, llm_model=gpt-4o-mini, debug=True", flush=True)
                    self._debug_extractor = GraphSchemaExtractor(
                        embedding_model="BAAI/bge-small-en-v1.5",
                        min_embedding_similarity=0.3,
                        tiebreak_threshold=0.05,
                        llm_model="gpt-4o-mini",  # Teste usa "gpt-5-mini" mas esse não existe, usar gpt-4o-mini
                        use_llm_tiebreaker=True,
                        debug=True  # Debug ativado
                    )
                    print(f"[GET_EXTRACTOR] Extrator DEBUG inicializado com sucesso", flush=True)
                    print(f"[GET_EXTRACTOR] Tipo do extractor: {type(self._debug_extractor)}", flush=True)
                    sys.stdout.flush()
                except Exception as e:
                    print(f"[GET_EXTRACTOR] ERRO ao inicializar GraphSchemaExtractor (debug): {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    sys.stdout.flush()
                    raise
            else:
                print(f"[GET_EXTRACTOR] Reutilizando extractor DEBUG existente", flush=True)
            return self._debug_extractor
        else:
            # Extrator normal (sem debug)
            if self._extractor is None:
                print(f"[GET_EXTRACTOR] Inicializando extractor NORMAL...", flush=True)
                sys.stdout.flush()
                try:
                    # Usar EXATAMENTE os mesmos parâmetros do teste
                    print(f"[GET_EXTRACTOR] Parâmetros: embedding_model=BAAI/bge-small-en-v1.5, llm_model=gpt-4o-mini, debug=False", flush=True)
                    self._extractor = GraphSchemaExtractor(
                        embedding_model="BAAI/bge-small-en-v1.5",
                        min_embedding_similarity=0.3,
                        tiebreak_threshold=0.05,
                        llm_model="gpt-4o-mini",
                        use_llm_tiebreaker=True,
                        debug=False  # Sem debug
                    )
                    print(f"[GET_EXTRACTOR] Extrator NORMAL inicializado com sucesso", flush=True)
                    print(f"[GET_EXTRACTOR] Tipo do extractor: {type(self._extractor)}", flush=True)
                    sys.stdout.flush()
                except Exception as e:
                    print(f"[GET_EXTRACTOR] ERRO ao inicializar GraphSchemaExtractor: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    sys.stdout.flush()
                    raise
            else:
                print(f"[GET_EXTRACTOR] Reutilizando extractor NORMAL existente", flush=True)
            return self._extractor
    
    def generate_run_id(self, filename: str) -> str:
        """Gera ID único para uma execução.
        
        Args:
            filename: Nome do arquivo PDF
            
        Returns:
            Run ID no formato: {YYYY-MM-DDTHH-MM-SS}_{filename_stem}
        """
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        filename_stem = Path(filename).stem
        return f"{timestamp}_{filename_stem}"
    
    def extract_rules_used(self, strategies_breakdown: Dict[str, str]) -> List[str]:
        """Extrai lista única de regras/estratégias usadas.
        
        Args:
            strategies_breakdown: Dicionário {field_name: strategy}
            
        Returns:
            Lista única de estratégias (sem duplicatas)
        """
        rules = set(strategies_breakdown.values())
        # Remover "none" da lista
        rules.discard("none")
        return sorted(list(rules))
    
    def process_pdf(
        self,
        pdf_path: str,
        label: str,
        schema: Dict[str, str],
        filename: str,
        on_progress: Optional[Callable[[str], None]] = None,
        generate_graph: bool = False,
        debug: bool = False
    ) -> Dict[str, Any]:
        """Processa um único PDF.
        
        Args:
            pdf_path: Caminho para o arquivo PDF
            label: Label do documento
            schema: Schema de extração
            filename: Nome do arquivo (para run_id)
            on_progress: Callback de progresso (opcional)
            generate_graph: Se True, gera HTML do grafo
            
        Returns:
            Dicionário com resultado no formato:
            {
                "run_id": str,
                "filename": str,
                "status": "ok" | "error",
                "result": {...} ou None,
                "error_message": str ou None,
                "dev": {
                    "elapsed_ms": int,
                    "rules_used": List[str],
                    "graph_url": str ou None
                }
            }
        """
        run_id = self.generate_run_id(filename)
        start_time = time.time()
        
        # Callback wrapper para progresso
        def progress_callback(step: str) -> None:
            if on_progress:
                on_progress(step)
        
        import sys
        
        try:
            print(f"[PROCESS_PDF] Iniciando processamento de {filename}", flush=True)
            sys.stdout.flush()
            
            if debug:
                print(f"\n{'='*80}")
                print(f"INICIANDO EXTRAÇÃO (MODO DEV)")
                print(f"  PDF: {filename} ({pdf_path})")
                print(f"  Label: {label}")
                print(f"  Schema: {list(schema.keys())}")
                print(f"{'='*80}\n")
                sys.stdout.flush()
            
            pdf_path_obj = Path(pdf_path)
            print(f"[PROCESS_PDF] Verificando PDF: {pdf_path}", flush=True)
            if not pdf_path_obj.exists():
                print(f"[PROCESS_PDF] ERRO: PDF não encontrado!", flush=True)
                raise FileNotFoundError(f"PDF não encontrado: {pdf_path}")
            print(f"[PROCESS_PDF] PDF existe: OK", flush=True)
            sys.stdout.flush()
            
            # Obter extractor apropriado (com ou sem debug)
            print(f"[PROCESS_PDF] Obtendo extractor (debug={debug})...", flush=True)
            extractor = self.get_extractor(debug=debug)
            print(f"[PROCESS_PDF] Extractor obtido", flush=True)
            sys.stdout.flush()
            
            # Executar extração (igual ao teste, mas com on_progress opcional)
            print(f"[PROCESS_PDF] Chamando extractor.extract()...", flush=True)
            print(f"[PROCESS_PDF] Parâmetros do extract:", flush=True)
            print(f"[PROCESS_PDF]   - label: {label}", flush=True)
            print(f"[PROCESS_PDF]   - pdf_path: {pdf_path}", flush=True)
            print(f"[PROCESS_PDF]   - schema keys: {list(schema.keys())}", flush=True)
            print(f"[PROCESS_PDF]   - on_progress: {on_progress is not None}", flush=True)
            sys.stdout.flush()
            
            try:
                result = extractor.extract(
                    label=label,
                    extraction_schema=schema,
                    pdf_path=str(pdf_path),  # Garantir que é string
                    on_progress=progress_callback if on_progress else None
                )
                
                print(f"[PROCESS_PDF] extractor.extract() RETORNOU", flush=True)
                print(f"[PROCESS_PDF] Tipo do resultado: {type(result)}", flush=True)
                if isinstance(result, dict):
                    print(f"[PROCESS_PDF] Keys do resultado: {list(result.keys())}", flush=True)
                sys.stdout.flush()
            except Exception as extract_exception:
                print(f"[PROCESS_PDF] ERRO durante extractor.extract():", flush=True)
                print(f"[PROCESS_PDF] Tipo: {type(extract_exception).__name__}", flush=True)
                print(f"[PROCESS_PDF] Mensagem: {str(extract_exception)}", flush=True)
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
                raise
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            if debug:
                print(f"\n{'='*80}")
                print(f"EXTRAÇÃO CONCLUÍDA (MODO DEV)")
                print(f"  Status: OK")
                print(f"  Tempo: {elapsed_ms}ms")
                print(f"{'='*80}\n")
                sys.stdout.flush()
            
            if debug:
                print(f"  Resultado tipo: {type(result)}")
                print(f"  Keys do resultado: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
            
            # Verificar se result é um dict válido
            if not isinstance(result, dict):
                raise ValueError(f"Resultado da extração não é um dicionário: {type(result)}")
            
            # Extrair campos
            fields = result.get("fields", {})
            if not isinstance(fields, dict):
                if debug:
                    print(f"AVISO: 'fields' não é um dict: {type(fields)}")
                fields = {}
            
            # Extrair regras usadas
            metadata = result.get("metadata", {})
            if not isinstance(metadata, dict):
                if debug:
                    print(f"AVISO: 'metadata' não é um dict: {type(metadata)}")
                metadata = {}
            
            strategies_breakdown = metadata.get("strategies_breakdown", {})
            rules_used = self.extract_rules_used(strategies_breakdown)
            
            # Garantir que fields é serializável (sem valores None ou tipos complexos)
            serializable_fields = {}
            for key, value in fields.items():
                if value is None:
                    serializable_fields[key] = None
                elif isinstance(value, (str, int, float, bool)):
                    serializable_fields[key] = value
                else:
                    # Converter para string se não for tipo básico
                    serializable_fields[key] = str(value)
                    if debug:
                        print(f"AVISO: Campo '{key}' convertido para string: {type(value)}")
            
            # Gerar HTML do grafo se solicitado
            graph_url = None
            if generate_graph:
                try:
                    if debug:
                        print(f"Gerando HTML do grafo para {filename}...")
                    graph_url = graph_generator.generate_graph_html(
                        pdf_path=pdf_path,
                        run_id=run_id,
                        label=label
                    )
                    if debug:
                        print(f"HTML do grafo gerado: {graph_url}")
                except Exception as e:
                    # Não falhar a extração se o HTML não puder ser gerado
                    if debug:
                        print(f"Aviso: Erro ao gerar HTML do grafo: {e}")
            
            response_dict = {
                "run_id": run_id,
                "filename": filename,
                "status": "ok",
                "result": serializable_fields,
                "error_message": None,
                "dev": {
                    "elapsed_ms": elapsed_ms,
                    "rules_used": rules_used,
                    "graph_url": graph_url
                }
            }
            
            if debug:
                print(f"Resposta preparada: status=ok, campos={len(serializable_fields)}, tempo={elapsed_ms}ms")
            
            return response_dict
            
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            if debug:
                print(f"\n{'='*80}")
                print(f"ERRO NA EXTRAÇÃO (MODO DEV)")
                print(f"  Erro: {error_msg}")
                print(f"  Tempo até erro: {elapsed_ms}ms")
                print(f"{'='*80}\n")
                import traceback
                traceback.print_exc()
            
            # Tentar obter regras usadas mesmo em erro (se disponível)
            rules_used = []
            
            return {
                "run_id": run_id,
                "filename": filename,
                "status": "error",
                "result": None,
                "error_message": error_msg,
                "dev": {
                    "elapsed_ms": elapsed_ms,
                    "rules_used": rules_used,
                    "graph_url": None
                }
            }
    
    def process_multiple_pdfs(
        self,
        pdf_files: List[tuple[str, str]],  # Lista de (pdf_path, filename)
        label: str,
        schema: Dict[str, str],
        on_progress: Optional[Callable[[str, int, int], None]] = None,  # (step, current, total)
        generate_graph: bool = False,
        debug: bool = False
    ) -> List[Dict[str, Any]]:
        """Processa múltiplos PDFs sequencialmente.
        
        Args:
            pdf_files: Lista de tuplas (pdf_path, filename)
            label: Label do documento
            schema: Schema de extração
            on_progress: Callback de progresso global (step, current_index, total)
            generate_graph: Se True, gera HTML do grafo para cada PDF
            
        Returns:
            Lista de resultados na ordem de processamento
        """
        import sys
        sys.stdout.flush()
        print(f"[SERVICE] process_multiple_pdfs INICIADO", flush=True)
        print(f"[SERVICE] Total de PDFs: {len(pdf_files)}, Debug: {debug}", flush=True)
        sys.stdout.flush()
        
        results = []
        total = len(pdf_files)
        
        for idx, (pdf_path, filename) in enumerate(pdf_files, 1):
            print(f"[SERVICE] ===== PDF {idx}/{total}: {filename} =====", flush=True)
            sys.stdout.flush()
            
            if debug:
                print(f"\n{'#'*80}")
                print(f"# PROCESSANDO PDF {idx}/{total}: {filename}")
                print(f"{'#'*80}\n")
                sys.stdout.flush()
            
            # Callback de progresso por PDF
            def pdf_progress(step: str) -> None:
                print(f"[SERVICE] [{idx}/{total}] Progresso: {step}", flush=True)
                if debug:
                    print(f"  [PROGRESSO] [{idx}/{total}] {step}", flush=True)
                if on_progress:
                    on_progress(step, idx, total)
                sys.stdout.flush()
            
            try:
                print(f"[SERVICE] Chamando process_pdf para {filename}...", flush=True)
                sys.stdout.flush()
                
                result = self.process_pdf(
                    pdf_path=pdf_path,
                    label=label,
                    schema=schema,
                    filename=filename,
                    on_progress=pdf_progress,
                    generate_graph=generate_graph,
                    debug=debug
                )
                
                print(f"[SERVICE] process_pdf RETORNOU para {filename}", flush=True)
                results.append(result)
                
                if debug:
                    print(f"\n{'#'*80}")
                    print(f"# PDF {idx}/{total} ({filename}) CONCLUÍDO: {result['status']}")
                    print(f"{'#'*80}\n")
                sys.stdout.flush()
                
            except Exception as e:
                print(f"[SERVICE] ERRO ao processar {filename}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
                
                if debug:
                    print(f"\n{'#'*80}")
                    print(f"# ERRO ao processar PDF {idx}/{total} ({filename})")
                    print(f"# Erro: {e}")
                    print(f"{'#'*80}\n")
                    sys.stdout.flush()
                
                # Adicionar resultado de erro
                results.append({
                    "run_id": self.generate_run_id(filename),
                    "filename": filename,
                    "status": "error",
                    "result": None,
                    "error_message": str(e),
                    "dev": {
                        "elapsed_ms": 0,
                        "rules_used": [],
                        "graph_url": None
                    }
                })
        
        print(f"[SERVICE] process_multiple_pdfs CONCLUÍDO: {len(results)} resultados", flush=True)
        sys.stdout.flush()
        return results


# Instância singleton
extractor_service = ExtractorService()

