"""Extrator principal de schema baseado em grafo."""

import sys
import time
from typing import Dict, Any, Optional, List, Callable

# Importar debug helper se disponível
try:
    # Tentar importar do backend
    import sys
    from pathlib import Path
    backend_src = Path(__file__).parent.parent.parent.parent / "backend" / "src"
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))
    from utils.debug import debug_print, error_print, get_debug_mode, set_debug_mode
except ImportError:
    # Fallback se não conseguir importar
    def debug_print(*args, **kwargs):
        pass
    def error_print(*args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)
    def get_debug_mode():
        return False
    def set_debug_mode(enabled: bool):
        pass

# Log de importação do módulo (apenas em debug)
debug_print("[EXTRACTOR_MODULE] Módulo extractor.py sendo importado...")

try:
    from src.graph_builder import TokenExtractor, GraphBuilder, RoleClassifier
    debug_print("[EXTRACTOR_MODULE] graph_builder importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar graph_builder: {e}")
    raise

try:
    from src.graph_builder.models import Graph, Token
    debug_print("[EXTRACTOR_MODULE] graph_builder.models importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar graph_builder.models: {e}")
    raise

try:
    from src.graph_extractor.models import (
        ExtractionResult, ExtractionMetadata, FieldMatch, MatchResult, MatchType
    )
    debug_print("[EXTRACTOR_MODULE] graph_extractor.models importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar graph_extractor.models: {e}")
    raise

try:
    from src.graph_extractor.node_manager import NodeUsageManager
    debug_print("[EXTRACTOR_MODULE] node_manager importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar node_manager: {e}")
    raise

try:
    from src.graph_extractor.matchers import PatternMatcher, RegexMatcher, EmbeddingMatcher
    debug_print("[EXTRACTOR_MODULE] matchers importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar matchers: {e}")
    raise

try:
    from src.graph_extractor.tiebreaker import HeuristicTieBreaker, LLMTieBreaker
    debug_print("[EXTRACTOR_MODULE] tiebreaker importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar tiebreaker: {e}")
    raise

try:
    from src.graph_extractor.learner import DocumentLearner
    debug_print("[EXTRACTOR_MODULE] learner importado")
except Exception as e:
    error_print(f"[EXTRACTOR_MODULE] ERRO ao importar learner: {e}")
    raise

debug_print("[EXTRACTOR_MODULE] Todas as dependências importadas com sucesso")
debug_print("[EXTRACTOR_MODULE] Definindo classe GraphSchemaExtractor...")


class GraphSchemaExtractor:
    """Extrator principal que usa grafo hierárquico para extrair schemas de PDFs.
    
    Executa uma cascata de estratégias de matching para encontrar valores
    correspondentes a cada campo do schema:
    1. Pattern Matching (hints)
    2. Regex Matching
    3. Embedding Matching (FastEmbed)
    4. Tiebreaking (heurísticas → LLM)
    """
    
    def __init__(
        self,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        min_embedding_similarity: float = 0.3,
        tiebreak_threshold: float = 0.05,
        llm_model: str = "gpt-5-mini",
        use_llm_tiebreaker: bool = True,
        debug: bool = False,
        use_learning: bool = True
    ):
        """Inicializa o extrator.
        
        Args:
            embedding_model: Nome do modelo FastEmbed
            min_embedding_similarity: Similaridade mínima para embeddings (0.0 a 1.0)
            tiebreak_threshold: Threshold para considerar empate (diferença de score)
            llm_model: Modelo LLM para tiebreaker (se use_llm_tiebreaker=True)
            use_llm_tiebreaker: Se True, usa LLM quando heurísticas não resolvem
            debug: Se True, imprime informações de debug durante a extração
            use_learning: Se True, usa aprendizado incremental de documentos anteriores
        """
        # Componentes de construção de grafo
        self.token_extractor = TokenExtractor()
        self.graph_builder = GraphBuilder()
        self.role_classifier = RoleClassifier()
        
        # Matchers
        self.pattern_matcher = PatternMatcher()
        self.regex_matcher = RegexMatcher()
        self.embedding_matcher = EmbeddingMatcher(
            model_name=embedding_model,
            min_similarity=min_embedding_similarity
        )
        
        # Tiebreakers
        self.heuristic_tiebreaker = HeuristicTieBreaker()
        self.llm_tiebreaker = LLMTieBreaker(model=llm_model) if use_llm_tiebreaker else None
        if self.llm_tiebreaker:
            self.llm_tiebreaker.debug = debug  # Passar debug flag para LLM tiebreaker
        
        # Configurações
        self.tiebreak_threshold = tiebreak_threshold
        self.debug = debug
        self.use_learning = use_learning
        
        # Configurar modo debug global baseado no parâmetro
        set_debug_mode(debug)
        
        # Helper para prints condicionais (usa debug global ou self.debug como fallback)
        def _debug_print(*args, **kwargs):
            if get_debug_mode() or self.debug:
                debug_print(*args, **kwargs)
        self._debug_print = _debug_print
        
        # Sistema de aprendizado incremental (singleton compartilhado)
        # Usa arquivo persistente para compartilhar entre UI e CLI
        if use_learning:
            self.learner = DocumentLearner.get_instance()
        else:
            # Usar NoOpLearner quando aprendizado está desabilitado
            from src.graph_extractor.learner import NoOpLearner
            self.learner = NoOpLearner()
        
        # Log de inicialização (apenas em debug)
        debug_print(f"[GraphSchemaExtractor.__init__] Extrator inicializado com sucesso")
        debug_print(f"[GraphSchemaExtractor.__init__]   - embedding_model: {embedding_model}")
        debug_print(f"[GraphSchemaExtractor.__init__]   - llm_model: {llm_model}")
        debug_print(f"[GraphSchemaExtractor.__init__]   - debug: {debug}")
        debug_print(f"[GraphSchemaExtractor.__init__]   - use_learning: {use_learning}")
    
    def extract(
        self,
        label: str,
        extraction_schema: Dict[str, str],
        pdf_path: str,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """Extrai informações do PDF conforme o schema fornecido.
        
        Args:
            label: Tipo/identificação do documento
            extraction_schema: Dicionário com campos e descrições
            pdf_path: Caminho para o arquivo PDF
            on_progress: Callback opcional chamado nas etapas de progresso.
                        Recebe (step: str) onde step pode ser:
                        "building_graph", "regex_matching", "embedding_matching",
                        "tiebreaking", "post_processing", "done"
            
        Returns:
            Dicionário com resultado da extração no formato:
            {
                "label": str,
                "fields": {campo: valor, ...},
                "metadata": {...}
            }
        """
        start_time = time.time()
        
        # Log inicial (apenas em debug)
        debug_print(f"[EXTRACT] Iniciando extração")
        debug_print(f"[EXTRACT]   - label: {label}")
        debug_print(f"[EXTRACT]   - pdf_path: {pdf_path}")
        debug_print(f"[EXTRACT]   - campos: {list(extraction_schema.keys())}")
        
        try:
            # 1. Construir grafo
            if on_progress:
                on_progress("building_graph")
            debug_print(f"[EXTRACT] Construindo grafo...")
            graph = self._build_graph(pdf_path, label)
            debug_print(f"[EXTRACT] Grafo construído: {len(graph.nodes) if graph else 0} nós")
            
            if not graph or not graph.nodes:
                return self._create_empty_result(label, extraction_schema, start_time, "PDF vazio ou sem texto")
            
            # 2. Inicializar gerenciador de nós
            node_manager = NodeUsageManager()
            
            # 3. FASE 1: Processar TODOS os regex de uma vez (mais rápido)
            if on_progress:
                on_progress("regex_matching")
            debug_print(f"[EXTRACT] Iniciando fase de regex matching...")
            # Dicionário para armazenar resultados: {field_name: FieldMatch}
            field_matches_dict = {}
            remaining_fields = {}  # Campos que não tiveram match de regex
            
            for field_name, field_description in extraction_schema.items():
                # PULAR regex para campos de nome - eles usam embedding obrigatório
                is_name_field = self._is_name_field(field_name, field_description)
                if is_name_field:
                    # Campos de nome não devem passar por regex - pular direto para pattern/embedding
                    field_matches_dict[field_name] = FieldMatch(
                        field_name=field_name,
                        value=None,
                        strategy_used="Early name recognition",
                        metadata={"reason": "Campo de nome: pulando regex, usando embedding obrigatório"}
                    )
                    remaining_fields[field_name] = field_description
                else:
                    # Tentar regex apenas para campos que NÃO são nome
                    field_match = self._try_regex_matching(
                        field_name, field_description, graph, node_manager
                    )
                    field_matches_dict[field_name] = field_match
                    
                    # Aprender do resultado da extração (mesmo que seja None)
                    self._learn_from_field_match(
                        label, field_name, field_description, field_match, graph
                    )
                    
                    # Se regex não encontrou match válido, adicionar à lista de campos restantes
                    if field_match.strategy_used == "none" and field_match.value is None:
                        remaining_fields[field_name] = field_description
            
            # 4. FASE 2: Para campos restantes, usar pattern + embedding/LLM
            if on_progress:
                on_progress("embedding_matching")
            debug_print(f"[EXTRACT] Iniciando fase de embedding matching ({len(remaining_fields)} campos restantes)...")
            needs_tiebreak = False
            for field_name, field_description in remaining_fields.items():
                field_match = self._extract_field_with_pattern_embedding(
                    field_name, field_description, graph, node_manager, label
                )
                field_matches_dict[field_name] = field_match
                # Verificar se houve tiebreak
                if "tiebreak" in field_match.strategy_used:
                    needs_tiebreak = True
                
                # Aprender do resultado da extração
                self._learn_from_field_match(
                    label, field_name, field_description, field_match, graph
                )
            
            if needs_tiebreak and on_progress:
                on_progress("tiebreaking")
            
            # 5. Pós-processamento
            if on_progress:
                on_progress("post_processing")
            
            # 6. Converter dicionário para lista (manter ordem original)
            field_matches = [field_matches_dict[field_name] for field_name in extraction_schema.keys()]
            
            # 7. Montar resultado
            fields = {fm.field_name: fm.value for fm in field_matches}
            extracted_count = sum(1 for fm in field_matches if fm.value is not None)
            
            metadata = ExtractionMetadata(
                label=label,
                total_fields=len(extraction_schema),
                extracted_fields=extracted_count,
                nodes_used=list(node_manager.get_used_nodes()),
                extraction_time=round(time.time() - start_time, 2),
                strategies_breakdown={fm.field_name: fm.strategy_used for fm in field_matches}
            )
            
            result = ExtractionResult(
                label=label,
                fields=fields,
                field_matches=field_matches,
                metadata=metadata
            )
            
            if on_progress:
                on_progress("done")
            
            result_dict = result.to_dict()
            elapsed_time = time.time() - start_time
            debug_print(f"[EXTRACT] Extração concluída com sucesso em {elapsed_time:.2f}s")
            debug_print(f"[EXTRACT] Campos extraídos: {extracted_count}/{len(extraction_schema)}")
            
            return result_dict
            
        except Exception as e:
            import traceback
            elapsed_time = time.time() - start_time
            error_print(f"[EXTRACT] ERRO durante extração (após {elapsed_time:.2f}s):")
            error_print(f"[EXTRACT] Tipo: {type(e).__name__}")
            error_print(f"[EXTRACT] Mensagem: {str(e)}")
            if get_debug_mode() or self.debug:
                traceback.print_exc()
            return self._create_empty_result(
                label, extraction_schema, start_time, f"Erro: {str(e)}"
            )
    
    def _build_graph(self, pdf_path: str, label: str) -> Optional[Graph]:
        """Constrói o grafo a partir do PDF.
        
        Args:
            pdf_path: Caminho para o PDF
            label: Label do documento
            
        Returns:
            Grafo construído ou None se falhar
        """
        try:
            # Extrair tokens
            tokens = self.token_extractor.extract(pdf_path)
            if not tokens:
                return None
            
            # Construir grafo
            graph = self.graph_builder.build(tokens)
            
            # Classificar roles
            roles, tables = self.role_classifier.classify(tokens, graph, label=label)
            
            # Aplicar roles aos tokens
            for token in tokens:
                if token.id in roles:
                    token.role = roles[token.id]
            
            # Verificar e corrigir padrão específico de tabelas verticais
            # onde há labels sem values correspondentes (values "apagados")
            self._fix_missing_table_values(tokens, graph, tables)
            
            return graph
            
        except Exception as e:
            print(f"Erro ao construir grafo: {e}")
            return None
    
    def _try_regex_matching(
        self,
        field_name: str,
        field_description: str,
        graph: Graph,
        node_manager: NodeUsageManager
    ) -> FieldMatch:
        """Tenta extrair campo usando regex (fase rápida).
        
        Para cada nó, verifica se há palavras em comum com o schema.
        - Se não tiver nenhuma palavra igual: pula o nó
        - Se tiver pelo menos 30% das palavras iguais: aplica regras de regex
        
        IMPORTANTE: A validação LLM (se necessário) será aplicada apenas para campos
        com hints específicas que requerem validação (endereço, telefone).
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            graph: Grafo completo
            node_manager: Gerenciador de nós usados
            
        Returns:
            FieldMatch com resultado da extração (ou None se não encontrou)
        """
        # Debug: mostrar hints encontradas para este campo
        if self.debug or get_debug_mode():
            from src.graph_extractor.hints.base import hint_registry
            relevant_hints = hint_registry.find_relevant(field_name, field_description)
            hint_names = [h.name for h in relevant_hints]
            has_specific_hints = self._has_specific_hints(field_name, field_description)
            expected_type = self._get_expected_type_name(field_name, field_description)
            debug_print(f"\n[Regex Phase] Campo: '{field_name}'")
            debug_print(f"  Hints encontradas: {hint_names}")
            debug_print(f"  Tem hints específicas: {has_specific_hints}")
            debug_print(f"  Tipo esperado: {expected_type}")
            if expected_type:
                llm_required = expected_type in ["endereço", "telefone"]
                debug_print(f"  Requer validação LLM: {llm_required}")
        
        # Obter nós disponíveis
        available_nodes = self._get_available_nodes(graph, node_manager)
        
        if not available_nodes:
            return FieldMatch(
                field_name=field_name,
                value=None,
                strategy_used="none",
                metadata={"reason": "Nenhum nó disponível"}
            )
        
        # Filtrar nós que têm pelo menos 30% de palavras em comum
        candidate_nodes = self._filter_nodes_by_word_similarity(
            field_name, field_description, available_nodes, threshold=0.3
        )
        
        if not candidate_nodes:
            # Não há nós com palavras suficientes em comum
            return FieldMatch(
                field_name=field_name,
                value=None,
                strategy_used="none",
                metadata={"reason": "Nenhum nó com palavras em comum suficiente (30%)"}
            )
        
        # Para cada candidato, verificar match de regex
        regex_matches = []
        for token in candidate_nodes:
            match_result = self._check_regex_match_for_node(
                field_name, field_description, token, graph
            )
            if match_result:
                regex_matches.append(match_result)
        
        if not regex_matches:
            return FieldMatch(
                field_name=field_name,
                value=None,
                strategy_used="none",
                metadata={"reason": "Nenhum match de regex encontrado"}
            )
        
        # Separar matches perfeitos (regex idêntico) de parciais
        perfect_matches = [m for m in regex_matches if m.match_type == MatchType.PERFECT]
        partial_matches = [m for m in regex_matches if m.match_type == MatchType.PARTIAL]
        
        # Processar matches perfeitos primeiro
        if perfect_matches:
            return self._process_perfect_regex_matches(
                field_name, perfect_matches, field_description, graph, node_manager
            )
        
        # Se não há matches perfeitos, processar parciais
        if partial_matches:
            return self._process_partial_regex_matches(
                field_name, partial_matches, field_description, graph, node_manager
            )
        
        return FieldMatch(
            field_name=field_name,
            value=None,
            strategy_used="none",
            metadata={"reason": "Regex matches não puderam ser processados"}
        )
    
    def _extract_field_with_pattern_embedding(
        self,
        field_name: str,
        field_description: str,
        graph: Graph,
        node_manager: NodeUsageManager,
        label_type: Optional[str] = None
    ) -> FieldMatch:
        """Extrai um campo usando cascata de matching.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            graph: Grafo completo
            node_manager: Gerenciador de nós usados
            
        Returns:
            FieldMatch com resultado da extração
        """
        # Obter nós disponíveis
        available_nodes = self._get_available_nodes(graph, node_manager)
        
        if not available_nodes:
            return FieldMatch(
                field_name=field_name,
                value=None,
                strategy_used="none",
                metadata={"reason": "Nenhum nó disponível"}
            )
        
        # Verificar se o campo é identificado como "nome" (requer validação por embedding)
        is_name_field = self._is_name_field(field_name, field_description)
        
        # Se é campo de nome, usar embedding como primeira etapa (antes de pattern/regex)
        if is_name_field:
            # Filtrar candidatos que podem ser nomes (sem símbolos, números, não siglas)
            name_candidates = self._filter_name_candidates(available_nodes, graph)
            
            if not name_candidates:
                return FieldMatch(
                    field_name=field_name,
                    value=None,
                    strategy_used="none",
                    metadata={"reason": "Campo de nome: nenhum candidato válido encontrado após filtro inicial"}
                )
            
            # Extrair textos dos candidatos
            candidate_texts = []
            for token in name_candidates:
                token_value = self.pattern_matcher.get_token_value(token, graph)
                if token_value:
                    candidate_texts.append(token_value)
            
            if not candidate_texts:
                return FieldMatch(
                    field_name=field_name,
                    value=None,
                    strategy_used="none",
                    metadata={"reason": "Campo de nome: nenhum candidato com valor válido"}
                )
            
            # Usar heurística para identificar qual candidato é um nome
            if self.debug or get_debug_mode():
                debug_print(f"  [Nome] Avaliando {len(candidate_texts)} candidatos com heurística: {[t[:30] for t in candidate_texts]}")
            
            # Heurística: escolher candidato que parece mais com nome
            # Sistema de pontuação:
            # - 2+ palavras: +10 pontos (nomes geralmente têm 2+ palavras)
            # - 1 palavra: +5 pontos
            # - Sem números: +5 pontos
            # - Sem símbolos estranhos (exceto apóstrofes e hífens): +3 pontos
            # - Primeira letra maiúscula em cada palavra: +2 pontos
            # - Threshold mínimo: 10 pontos
            best_index = None
            best_score = -1
            
            import re
            for i, text in enumerate(candidate_texts):
                score = 0
                words = text.split()
                
                # Mais palavras = melhor (nomes geralmente têm 2+ palavras)
                if len(words) >= 2:
                    score += 10
                elif len(words) == 1:
                    score += 5
                
                # Sem números = melhor
                if not any(c.isdigit() for c in text):
                    score += 5
                
                # Sem símbolos estranhos (exceto apóstrofes e hífens)
                if not re.search(r'[^\w\s\'-]', text):
                    score += 3
                
                # Primeira letra maiúscula em cada palavra = melhor
                if all(word[0].isupper() if word else False for word in words):
                    score += 2
                
                if self.debug or get_debug_mode():
                    debug_print(f"    Candidato {i+1}: '{text[:50]}' -> score: {score}")
                
                if score > best_score:
                    best_score = score
                    best_index = i
            
            if best_index is not None and best_score >= 10:  # Threshold mínimo
                selected_token = name_candidates[best_index]
                selected_value = candidate_texts[best_index]
                
                if self.debug or get_debug_mode():
                    debug_print(f"  [Nome] Heurística escolheu candidato {best_index + 1} (score: {best_score}): '{selected_value[:50]}'")
                
                # Criar MatchResult para o token selecionado
                match_result = MatchResult(
                    token=selected_token,
                    score=0.95,  # Alta confiança quando heurística identifica
                    match_type=MatchType.PERFECT,
                    reason=f"Nome identificado por heurística (candidato {best_index + 1} de {len(candidate_texts)}, score: {best_score})",
                    extracted_value=selected_value
                )
                
                return self._create_field_match(field_name, match_result, "name_heuristic", node_manager)
            else:
                # Nenhum candidato foi identificado
                if self.debug or get_debug_mode():
                    debug_print(f"  [Nome] Nenhum candidato válido identificado (melhor score: {best_score}, threshold: 10)")
                
                return FieldMatch(
                    field_name=field_name,
                    value=None,
                    strategy_used="none",
                    metadata={"reason": f"Campo de nome: nenhum candidato válido identificado (melhor score: {best_score}, threshold: 10)"}
                )
        
        # Para campos que NÃO são nome, usar cascata normal
        # FASE 1: Regex Matching (vem antes de Pattern)
        regex_matches = self.regex_matcher.match(
            field_name, field_description, available_nodes, graph
        )
        
        if regex_matches:
            # Separar matches perfeitos de parciais
            # Filtrar matches que retornam string vazia (não queremos retornar o input exato)
            # String vazia em extracted_value significa "não retornar input, retornar null"
            perfect_regex = [m for m in regex_matches if m.match_type == MatchType.PERFECT and m.extracted_value != ""]
            partial_regex = [m for m in regex_matches if m.match_type == MatchType.PARTIAL and m.extracted_value != ""]
            
            # Match perfeito tem prioridade (apenas os que têm valor)
            if perfect_regex:
                if len(perfect_regex) == 1:
                    # Validar qualidade do match antes de retornar
                    if not self._validate_match_quality(perfect_regex[0], field_name, field_description, graph, label_type):
                        # Match não faz sentido, não retornar
                        pass  # Continuar para próxima fase
                    else:
                        return self._create_field_match(field_name, perfect_regex[0], "regex_perfect", node_manager)
                else:
                    # Múltiplos matches perfeitos, desempate
                    selected = self._resolve_tie(perfect_regex, field_description, graph, field_name)
                    # Validar qualidade do match após tiebreak
                    if not self._validate_match_quality(selected, field_name, field_description, graph, label_type):
                        # Match não faz sentido, não retornar
                        pass  # Continuar para próxima fase
                    else:
                        return self._create_field_match(field_name, selected, "regex_perfect_tiebreak", node_manager)
            
            # Se não há match perfeito válido, usar parcial (mas precisa de desempate se houver múltiplos)
            if partial_regex:
                if len(partial_regex) == 1:
                    # Validar qualidade e tipo antes de retornar
                    if not self._validate_match_quality(partial_regex[0], field_name, field_description, graph, label_type):
                        # Match não faz sentido, não retornar
                        pass  # Continuar para próxima fase
                    elif self._has_specific_hints(field_name, field_description):
                        if not self._validate_value_type(partial_regex[0].extracted_value, field_name, field_description):
                            # Tipo não corresponde, não retornar este match
                            pass  # Continuar para próxima fase
                        else:
                            return self._create_field_match(field_name, partial_regex[0], "regex_partial", node_manager)
                    else:
                        return self._create_field_match(field_name, partial_regex[0], "regex_partial", node_manager)
                else:
                    # Múltiplos matches parciais, desempate
                    selected = self._resolve_tie(partial_regex, field_description, graph, field_name)
                    # Validar qualidade e tipo após tiebreak
                    if not self._validate_match_quality(selected, field_name, field_description, graph, label_type):
                        # Match não faz sentido, não retornar
                        pass  # Continuar para próxima fase
                    elif self._has_specific_hints(field_name, field_description):
                        if not self._validate_value_type(selected.extracted_value, field_name, field_description):
                            # Tipo não corresponde, não retornar este match
                            pass  # Continuar para próxima fase
                        else:
                            return self._create_field_match(field_name, selected, "regex_partial_tiebreak", node_manager)
                    else:
                        return self._create_field_match(field_name, selected, "regex_partial_tiebreak", node_manager)
        
        # FASE 2: Pattern Matching (hints) - só se regex não encontrou
        pattern_matches = self.pattern_matcher.match(
            field_name, field_description, available_nodes, graph
        )
        
        if pattern_matches:
            perfect_matches = [m for m in pattern_matches if m.score >= 0.9]
            if len(perfect_matches) == 1:
                # Validar qualidade e tipo antes de retornar
                if not self._validate_match_quality(perfect_matches[0], field_name, field_description, graph, label_type):
                    # Match não faz sentido, não retornar
                    pass  # Continuar para próxima fase
                elif self._has_specific_hints(field_name, field_description):
                    if not self._validate_value_type(perfect_matches[0].extracted_value, field_name, field_description):
                        # Tipo não corresponde, não retornar este match
                        pass  # Continuar para próxima fase
                    else:
                        return self._create_field_match(field_name, perfect_matches[0], "pattern_perfect", node_manager)
                else:
                    return self._create_field_match(field_name, perfect_matches[0], "pattern_perfect", node_manager)
            elif perfect_matches:
                # Múltiplos matches perfeitos - usar embedding com sinônimos para desempatar
                # Isso é especialmente importante para campos de data que têm sinônimos (ex: "vcto" para "vencimento")
                try:
                    embedding_matches = self.embedding_matcher.match(
                        field_name, field_description,
                        [m.token for m in perfect_matches], graph
                    )
                    
                    if embedding_matches:
                        # Encontrar o match perfeito correspondente ao melhor embedding
                        best_embedding_token_id = embedding_matches[0].token.id
                        for perfect_match in perfect_matches:
                            if perfect_match.token.id == best_embedding_token_id:
                                # Validar qualidade e tipo antes de retornar
                                if not self._validate_match_quality(perfect_match, field_name, field_description, graph, label_type):
                                    continue  # Tentar próximo match
                                elif self._has_specific_hints(field_name, field_description):
                                    if not self._validate_value_type(perfect_match.extracted_value, field_name, field_description):
                                        continue  # Tentar próximo match
                                return self._create_field_match(
                                    field_name, perfect_match, "pattern_perfect_embedding_tiebreak", node_manager
                                )
                except Exception as e:
                    if self.debug or get_debug_mode():
                        debug_print(f"  [Pattern Tiebreak] Erro ao usar embedding: {e}")
                
                # Fallback: usar tiebreaker normal
                selected = self._resolve_tie(perfect_matches, field_description, graph, field_name)
                # Validar qualidade e tipo após tiebreak
                if not self._validate_match_quality(selected, field_name, field_description, graph, label_type):
                    # Match não faz sentido, não retornar
                    pass  # Continuar para próxima fase
                elif self._has_specific_hints(field_name, field_description):
                    if not self._validate_value_type(selected.extracted_value, field_name, field_description):
                        # Tipo não corresponde, não retornar este match
                        pass  # Continuar para próxima fase
                    else:
                        return self._create_field_match(field_name, selected, "pattern_perfect_tiebreak", node_manager)
                else:
                    return self._create_field_match(field_name, selected, "pattern_perfect_tiebreak", node_manager)
            
            # Verificar matches parciais de pattern
            if pattern_matches[0].score >= 0.7:
                # Validar se o match faz sentido antes de retornar
                if not self._validate_match_quality(pattern_matches[0], field_name, field_description, graph, label_type):
                    # Match não faz sentido, não retornar
                    pass  # Continuar para próxima fase
                # Validar tipo antes de retornar
                elif self._has_specific_hints(field_name, field_description):
                    if not self._validate_value_type(pattern_matches[0].extracted_value, field_name, field_description):
                        # Tipo não corresponde, não retornar este match
                        pass  # Continuar para próxima fase
                    else:
                        return self._create_field_match(field_name, pattern_matches[0], "pattern_partial", node_manager)
                else:
                    return self._create_field_match(field_name, pattern_matches[0], "pattern_partial", node_manager)
        
        # FASE 3: Embedding Matching (para campos que não são nome)
        embedding_matches = self.embedding_matcher.match(
            field_name, field_description, available_nodes, graph
        )
        
        if embedding_matches:
            # Verificar se há empate
            if self.heuristic_tiebreaker.should_break_tie(embedding_matches, self.tiebreak_threshold):
                selected = self._resolve_tie(embedding_matches, field_description, graph, field_name)
                # Validar qualidade do match antes de retornar
                if not self._validate_match_quality(selected, field_name, field_description, graph, label_type):
                    # Match não faz sentido, não retornar
                    pass  # Continuar para retornar None
                # Validar tipo após tiebreak
                elif self._has_specific_hints(field_name, field_description):
                    if not self._validate_value_type(selected.extracted_value, field_name, field_description):
                        # Tipo não corresponde, não retornar este match
                        pass  # Continuar para retornar None
                    else:
                        return self._create_field_match(field_name, selected, "embedding_tiebreak", node_manager)
                else:
                    return self._create_field_match(field_name, selected, "embedding_tiebreak", node_manager)
            else:
                # Melhor match único - validar qualidade e tipo
                best_match = embedding_matches[0]
                if not self._validate_match_quality(best_match, field_name, field_description, graph, label_type):
                    # Match não faz sentido, não retornar
                    pass  # Continuar para retornar None
                elif self._has_specific_hints(field_name, field_description):
                    if not self._validate_value_type(best_match.extracted_value, field_name, field_description):
                        # Tipo não corresponde, não retornar este match
                        pass  # Continuar para retornar None
                    else:
                        return self._create_field_match(field_name, best_match, "embedding", node_manager)
                else:
                    return self._create_field_match(field_name, best_match, "embedding", node_manager)
        
        # Nenhum match encontrado
        return FieldMatch(
            field_name=field_name,
            value=None,
            strategy_used="none",
            metadata={"reason": "Nenhum match encontrado em nenhuma fase"}
        )
    
    def _is_name_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é identificado como 'nome'.
        
        Verifica se NameHint está presente E não há outras hints mais específicas
        (com prioridade menor que NameHint) que impedem ser considerado nome.
        Ex: se houver AddressHint (priority=1) e NameHint (priority=2), não é nome.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            True se é campo de nome (e não há hints mais específicas)
        """
        from src.graph_extractor.hints.base import hint_registry
        
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        
        # Verificar se NameHint está na lista
        name_hint_found = False
        name_hint_priority = None
        
        # Verificar se há hints mais específicas (priority < NameHint priority)
        for hint in relevant_hints:
            if hint.name == "name":
                name_hint_found = True
                name_hint_priority = hint.priority
                break
        
        if not name_hint_found:
            return False
        
        # Verificar se há outras hints mais específicas (prioridade menor = mais específica)
        # Hints mais específicas que NameHint impedem que seja considerado nome
        for hint in relevant_hints:
            if hint.name != "name" and hint.priority < name_hint_priority:
                # Há hint mais específica, não é campo de nome
                return False
        
        # NameHint está presente e não há hints mais específicas
        return True
    
    def _filter_name_candidates(
        self,
        candidates: List[Token],
        graph: Optional[Graph] = None
    ) -> List[Token]:
        """Filtra candidatos que podem ser nomes de pessoas.
        
        Filtra nós que:
        - Não têm muitos símbolos ou números
        - Não são siglas conhecidas (PR, SP, etc.)
        - Têm formato similar a nomes (pelo menos 3 caracteres, preferencialmente 2+ palavras)
        - NÃO são endereços (ex: "avenida paulistano")
        
        Args:
            candidates: Lista de tokens candidatos
            graph: Grafo completo (para obter valores associados)
            
        Returns:
            Lista de tokens filtrados que podem ser nomes
        """
        from src.graph_extractor.hints.name_hint import NameHint
        from src.graph_extractor.hints.address_hint import AddressHint
        
        name_hint = NameHint()
        address_hint = AddressHint()
        name_candidates = []
        
        # Usar o pattern_matcher para obter valores dos tokens (já tem o método get_token_value)
        for token in candidates:
            token_value = self.pattern_matcher.get_token_value(token, graph)
            
            # EXCLUIR endereços - se detectar como endereço, não é nome
            if address_hint.detect(token_value):
                continue
            
            # Verificar se pode ser nome usando critérios da NameHint
            # Isso filtra: siglas, strings com muitos números/símbolos, etc.
            if name_hint.detect(token_value):
                name_candidates.append(token)
        
        return name_candidates
    
    def _get_available_nodes(self, graph: Graph, node_manager: NodeUsageManager) -> List[Token]:
        """Obtém nós disponíveis (não usados).
        
        Args:
            graph: Grafo completo
            node_manager: Gerenciador de nós usados
            
        Returns:
            Lista de tokens disponíveis
        """
        used_node_ids = node_manager.get_used_nodes()
        return [node for node in graph.nodes if node.id not in used_node_ids]
    
    def _filter_nodes_by_word_similarity(
        self,
        field_name: str,
        field_description: str,
        candidates: List[Token],
        threshold: float = 0.3
    ) -> List[Token]:
        """Filtra nós que têm pelo menos threshold% de palavras em comum com o schema.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            candidates: Lista de nós candidatos
            threshold: Percentual mínimo de palavras em comum (0.0 a 1.0)
            
        Returns:
            Lista de nós que têm pelo menos threshold% de palavras em comum
        """
        import unicodedata
        import re
        
        def normalize_and_extract_words(text: str) -> set:
            """Normaliza texto e extrai palavras-chave."""
            if not text:
                return set()
            
            # Converter underscore para espaço
            text = text.replace('_', ' ')
            
            # Normalizar: lowercase, remover acentos
            text = text.lower().strip()
            text = unicodedata.normalize('NFD', text)
            text = text.encode('ascii', 'ignore').decode('ascii')
            
            # Remover caracteres especiais, manter apenas alfanuméricos e espaços
            text = re.sub(r'[^\w\s]', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            
            # Extrair palavras
            words = text.split()
            
            # Filtrar stop words e palavras muito curtas
            stop_words = {
                'o', 'a', 'de', 'do', 'da', 'em', 'no', 'na', 'para', 'com', 'por', 'e', 'ou', 'um', 'uma',
                'profissional', 'normalmente', 'canto', 'superior', 'inferior', 'esquerdo', 'direito', 
                'imagem', 'pode', 'ser', 'que', 'qual', 'faz', 'parte'
            }
            keywords = {w for w in words if len(w) > 2 and w not in stop_words}
            
            return keywords
        
        # Extrair palavras-chave do schema
        schema_text = f"{field_name} {field_description}"
        schema_words = normalize_and_extract_words(schema_text)
        
        if not schema_words:
            return []
        
        # Filtrar nós que têm pelo menos threshold% de palavras em comum
        filtered_nodes = []
        for token in candidates:
            token_text = token.text.strip()
            token_words = normalize_and_extract_words(token_text)
            
            if not token_words:
                continue
            
            # Calcular percentual de palavras em comum
            common_words = schema_words.intersection(token_words)
            similarity = len(common_words) / len(schema_words) if schema_words else 0.0
            
            # Se tem pelo menos threshold% de palavras em comum, incluir
            if similarity >= threshold:
                filtered_nodes.append(token)
        
        return filtered_nodes
    
    def _check_regex_match_for_node(
        self,
        field_name: str,
        field_description: str,
        token: Token,
        graph: Graph
    ) -> Optional[MatchResult]:
        """Verifica match de regex para um nó específico.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            token: Token a verificar
            graph: Grafo completo
            
        Returns:
            MatchResult se houver match, None caso contrário
        """
        # Usar o regex_matcher existente, mas apenas para um nó
        matches = self.regex_matcher.match(
            field_name, field_description, [token], graph
        )
        
        if matches:
            return matches[0]  # Retornar o primeiro match (deveria ser apenas um)
        
        return None
    
    def _process_perfect_regex_matches(
        self,
        field_name: str,
        perfect_matches: List[MatchResult],
        field_description: str,
        graph: Graph,
        node_manager: NodeUsageManager
    ) -> FieldMatch:
        """Processa matches perfeitos (regex idêntico).
        
        Se um nó tem exatamente o mesmo regex que chave/descrição:
        - Se tiver filho VALUE → retorna VALUE
        - Se não tiver filho → retorna null
        - Se tiver filho LABEL → desempata entre devolver LABEL ou LABEL + seu filho (VALUE)
        
        Args:
            field_name: Nome do campo
            perfect_matches: Lista de matches perfeitos
            field_description: Descrição do campo
            graph: Grafo completo
            node_manager: Gerenciador de nós usados
            
        Returns:
            FieldMatch com resultado processado
        """
        if len(perfect_matches) == 1:
            # Match perfeito único - processar regras
            match = perfect_matches[0]
            return self._resolve_perfect_regex_match(
                field_name, match, graph, node_manager, field_description
            )
        
        # Múltiplos matches perfeitos - desempata com embedding ou LLM
        selected = self._resolve_tie(perfect_matches, field_description, graph, field_name)
        return self._resolve_perfect_regex_match(
            field_name, selected, graph, node_manager, field_description, strategy_suffix="_tiebreak"
        )
    
    def _validate_match_quality(
        self,
        match_result: MatchResult,
        field_name: str,
        field_description: str,
        graph: Graph,
        label_type: Optional[str] = None
    ) -> bool:
        """Valida se um match faz sentido baseado no contexto do grafo e semântica.
        
        Rejeita matches que claramente não fazem sentido, como:
        - Tokens com poucas conexões no grafo
        - Valores de interface (botões, links, etc.)
        - Valores conectados apenas a dados irrelevantes
        
        Args:
            match_result: Resultado do match a validar
            field_name: Nome do campo
            field_description: Descrição do campo
            graph: Grafo completo
            
        Returns:
            True se o match faz sentido, False caso contrário
        """
        token = match_result.token
        value = match_result.extracted_value
        
        if not value:
            return False
        
        value_lower = value.strip().lower()
        
        # 1. Rejeitar valores claramente de interface/UI
        ui_keywords = [
            "esconder filtros", "mostrar filtros", "ocultar filtros",
            "atualizar", "buscar", "pesquisar", "filtrar",
            "limpar", "resetar", "voltar", "avançar", "próximo",
            "anterior", "cancelar", "confirmar", "salvar",
            "<<", ">>", "<", ">", "..."
        ]
        
        for keyword in ui_keywords:
            if keyword in value_lower:
                if self.debug or get_debug_mode():
                    debug_print(f"  [Match Quality] Rejeitado: valor de interface '{value}' para campo '{field_name}'")
                return False
        
        # 2. Verificar conexões do grafo
        edges_from = graph.get_edges_from(token.id)
        edges_to = graph.get_edges_to(token.id)
        total_edges = len(edges_from) + len(edges_to)
        
        # Se tem muito poucas conexões (menos de 2), pode ser um token isolado/irrelevante
        if total_edges < 2:
            # Verificar se as conexões fazem sentido
            relevant_connections = 0
            
            # Verificar conexões de saída (token -> outros)
            for edge in edges_from:
                connected_token = graph.get_node(edge.to_id)
                if connected_token:
                    # Verificar se a conexão faz sentido para o campo
                    connected_text = connected_token.text.strip().lower()
                    # Rejeitar se conectado apenas a datas para campos não relacionados a data
                    if connected_token.is_date():
                        expected_type = self._get_expected_type_name(field_name, field_description)
                        if expected_type != "data":
                            if self.debug or get_debug_mode():
                                debug_print(f"  [Match Quality] Rejeitado: token '{value}' conectado apenas a data para campo '{field_name}' (tipo esperado: {expected_type})")
                            return False
                    relevant_connections += 1
            
            # Verificar conexões de entrada (outros -> token)
            for edge in edges_to:
                connected_token = graph.get_node(edge.from_id)
                if connected_token:
                    relevant_connections += 1
            
            # Se tem menos de 2 conexões relevantes, rejeitar
            if relevant_connections < 2:
                if self.debug or get_debug_mode():
                    debug_print(f"  [Match Quality] Rejeitado: token '{value}' tem poucas conexões ({relevant_connections}) para campo '{field_name}'")
                return False
        
        # 3. Verificar se o valor faz sentido semântico para o campo
        # Rejeitar apenas valores claramente de interface/UI, não valores genéricos
        # (valores genéricos podem ser válidos em alguns contextos)
        ui_values = ["esconder filtros", "atualizar", "buscar", "pesquisar", "esconder", "filtros", "<<"]
        if any(ui_val in value_lower for ui_val in ui_values):
            if self.debug or get_debug_mode():
                debug_print(f"  [Match Quality] Rejeitado: valor '{value}' é valor de interface para campo '{field_name}'")
            return False
        
        # Rejeitar valores que começam com números seguidos de texto (ex: "0 CONSIGNADO")
        # Isso geralmente indica valores de dropdown/select que não foram preenchidos corretamente
        import re
        if re.match(r'^\d+\s+[A-Z]', value.strip()):
            if self.debug or get_debug_mode():
                debug_print(f"  [Match Quality] Rejeitado: valor '{value}' parece ser valor de dropdown não preenchido para campo '{field_name}'")
            return False
        
        # 4. Verificar aprendizado incremental (se disponível)
        if label_type:
            # Obter posição do token
            x = token.bbox.x0 if hasattr(token, 'bbox') and token.bbox else None
            y = token.bbox.y0 if hasattr(token, 'bbox') and token.bbox else None
            
            # Obter tipo de dado esperado
            expected_type = self._get_expected_type_name(field_name, field_description)
            
            # Verificar se deve rejeitar baseado no aprendizado
            should_reject, reason = self.learner.should_reject_match(
                label_type=label_type,
                field_name=field_name,
                x=x,
                y=y,
                role=token.role,
                data_type=expected_type,
                connections=total_edges
            )
            
            if should_reject:
                if self.debug or get_debug_mode():
                    debug_print(f"  [Match Quality] Rejeitado por aprendizado: {reason}")
                return False
        
        return True
    
    def _validate_value_type(
        self,
        value: str,
        field_name: str,
        field_description: str
    ) -> bool:
        """Valida se o valor corresponde ao tipo esperado do schema.
        
        Usa classificação por embedding primeiro (mais inteligente), depois fallback para hints.
        
        Args:
            value: Valor extraído a validar
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            True se o valor corresponde ao tipo esperado, False caso contrário
        """
        from src.graph_extractor.hints.base import hint_registry
        import re
        
        if not value:
            return False
        
        # 1. Tentar classificação por embedding primeiro (mais inteligente)
        expected_type = self._get_expected_type_name(field_name, field_description)
        
        if expected_type:
            # Validar baseado no tipo classificado
            value_lower = value.strip().lower()
            
            if expected_type == "data":
                # Validar formato de data
                date_pattern = re.compile(
                    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"  # DD/MM/YYYY
                    r"\d{4}-\d{2}-\d{2}"  # YYYY-MM-DD
                )
                return bool(date_pattern.search(value))
            
            elif expected_type == "valor monetário" or expected_type == "dinheiro":
                # Aceitar valores monetários ou números simples
                money_pattern = re.compile(
                    r"(?:R\s*\$|US\s*\$|\$|€|£|BRL|USD|EUR|GBP)?\s*"
                    r"(?:\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+[.,]\d{2}|\d+)",
                    re.IGNORECASE
                )
                # Também aceitar números simples (sem símbolo monetário)
                if money_pattern.search(value) or re.match(r'^\d+(?:[.,]\d+)?$', value.strip()):
                    return True
                return False
            
            elif expected_type == "telefone":
                # Validar formato de telefone
                phone_pattern = re.compile(
                    r"[\d\s\(\)\-\+]{8,}"  # Números, espaços, parênteses, hífens, +
                )
                return bool(phone_pattern.search(value)) and len(re.findall(r'\d', value)) >= 8
            
            elif expected_type == "endereço":
                # Endereços são mais complexos, usar hint específica
                address_hint = None
                for hint in hint_registry.find_relevant(field_name, field_description):
                    if hint.name == "address":
                        address_hint = hint
                        break
                if address_hint:
                    return address_hint.detect(value)
                # Se não tem hint, aceitar (endereços são difíceis de validar)
                return True
            
            elif expected_type == "email":
                email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
                return bool(email_pattern.search(value))
            
            elif expected_type == "CPF ou CNPJ":
                # Validar CPF ou CNPJ
                cpf_cnpj_pattern = re.compile(r'\d{11}|\d{14}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}')
                return bool(cpf_cnpj_pattern.search(value))
            
            elif expected_type == "número":
                # Aceitar números simples
                return bool(re.match(r'^\d+(?:[.,]\d+)?$', value.strip()))
            
            # Para outros tipos, aceitar (não temos validação específica)
            return True
        
        # 2. Fallback: usar hints tradicionais
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        
        # Se não há hints específicas, aceitar qualquer valor
        if not relevant_hints:
            return True
        
        # Verificar se pelo menos uma hint relevante detecta o valor
        for hint in relevant_hints:
            # Pular TextHint e NameHint - são muito genéricas
            if hint.name in ("text", "name"):
                continue
            
            # Verificar se o valor corresponde ao padrão da hint
            if hint.detect(value):
                return True
        
        # Nenhuma hint específica detectou o valor
        # Se há hints específicas mas nenhuma detectou, verificar casos especiais
        
        has_specific_hints = any(h.name not in ("text", "name") for h in relevant_hints)
        if has_specific_hints:
            # Caso especial: se hint é "money" mas o valor é um número válido, aceitar
            has_money_hint = any(h.name == "money" for h in relevant_hints)
            if has_money_hint:
                # Verificar se é um número válido (inteiro ou decimal)
                if re.match(r'^\d+(?:[.,]\d+)?$', value.strip()):
                    return True
            
            # Para outros tipos específicos (date, phone, address), rejeitar se não detectou
            return False
        
        # Apenas hints genéricas (text/name) - aceitar
        return True
    
    def _classify_field_type_with_embedding(
        self,
        field_name: str,
        field_description: str
    ) -> Optional[str]:
        """Classifica o tipo esperado do campo usando embedding semântico.
        
        Compara a descrição do campo com descrições típicas de cada tipo usando embedding.
        Mais inteligente que apenas palavras-chave, pois entende semântica.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            Nome do tipo esperado (ex: "data", "dinheiro", "telefone") ou None
        """
        # Tipos clássicos com descrições típicas (mais específicas e representativas)
        type_descriptions = {
            "data": [
                "data de vencimento", "data de nascimento", "data de emissão",
                "data base", "data de referência", "data inicial", "data final",
                "data de criação", "data de atualização", "data de expiração",
                "vencimento", "expiração", "prazo", "período", "dia mês ano",
                "calendário", "timestamp", "formato de data"
            ],
            "dinheiro": [
                "valor monetário", "preço em reais", "custo em dinheiro", "total em reais",
                "subtotal monetário", "saldo bancário", "montante financeiro",
                "valor da parcela em reais", "quantia em dinheiro", "dinheiro real",
                "R$", "valor pago", "receita financeira", "despesa monetária"
            ],
            "telefone": [
                "telefone celular", "número de telefone", "contato telefônico",
                "telefone fixo", "celular", "whatsapp", "número para ligar",
                "contato por telefone", "telefone de contato"
            ],
            "endereço": [
                "endereço completo", "rua e número", "avenida com número",
                "logradouro completo", "localização física", "endereço residencial",
                "cidade estado CEP", "bairro cidade", "endereço postal"
            ],
            "email": [
                "email eletrônico", "endereço de email", "correio eletrônico",
                "e-mail para contato", "email profissional", "conta de email"
            ],
            "nome": [
                "nome completo da pessoa", "nome do profissional", "nome pessoal",
                "identificação por nome", "razão social", "nome de identificação"
            ],
            "CPF_CNPJ": [
                "CPF cadastro pessoa física", "CNPJ cadastro nacional",
                "documento de identificação", "número de CPF", "número de CNPJ",
                "identificação fiscal", "documento fiscal"
            ],
            "hora": [
                "hora do dia", "horário específico", "tempo do dia",
                "hora minutos", "horário de funcionamento", "momento do dia"
            ],
            "número": [
                "quantidade numérica", "contagem de itens", "número total",
                "quantidade de elementos", "contagem simples", "número inteiro",
                "quantidade sem unidade", "número puro"
            ],
            "sigla": [
                "sigla abreviada", "código identificador", "código curto",
                "abreviação de texto", "identificador curto", "código alfanumérico"
            ]
        }
        
        # Criar query combinando nome e descrição
        query_text = f"{field_name} {field_description}".lower()
        
        # Gerar embedding da query
        query_embedding = self.embedding_matcher._get_embedding(query_text)
        if query_embedding is None:
            return None
        
        # Comparar com cada tipo
        best_type = None
        best_score = 0.0
        
        for type_name, descriptions in type_descriptions.items():
            # Criar texto representativo do tipo (todas as descrições combinadas)
            type_text = " ".join(descriptions)
            
            # Gerar embedding do tipo
            type_embedding = self.embedding_matcher._get_embedding(type_text)
            if type_embedding is None:
                continue
            
            # Calcular similaridade
            similarity = self.embedding_matcher._calculate_similarity(query_embedding, type_text)
            
            if similarity > best_score:
                best_score = similarity
                best_type = type_name
        
        # Retornar tipo apenas se similaridade for alta o suficiente
        # Threshold mais baixo (0.45) para capturar mais casos, mas ainda manter qualidade
        if best_score >= 0.45:
            # Se há múltiplos tipos com score similar, preferir tipos mais específicos
            # Ordem de preferência: data > dinheiro > telefone > endereço > outros
            type_priority = {
                "data": 10,
                "dinheiro": 9,
                "telefone": 8,
                "endereço": 7,
                "email": 6,
                "CPF_CNPJ": 5,
                "nome": 4,
                "hora": 3,
                "número": 2,
                "sigla": 1
            }
            
            # Se o melhor tipo tem prioridade alta e score bom, retornar
            priority = type_priority.get(best_type, 0)
            if priority >= 5 or best_score >= 0.55:
                return best_type
        
        return None
    
    def _get_expected_type_name(self, field_name: str, field_description: str) -> Optional[str]:
        """Obtém o nome do tipo esperado para um campo.
        
        Tenta primeiro classificação por embedding (mais inteligente), depois fallback para hints.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            Nome do tipo esperado (ex: "endereço", "telefone", "data") ou None
        """
        # Primeiro tentar classificação por embedding (mais inteligente)
        embedding_type = self._classify_field_type_with_embedding(field_name, field_description)
        if embedding_type:
            # Mapear para nomes consistentes
            type_mapping = {
                "data": "data",
                "dinheiro": "valor monetário",
                "telefone": "telefone",
                "endereço": "endereço",
                "email": "email",
                "nome": "nome",
                "CPF_CNPJ": "CPF ou CNPJ",
                "hora": "hora",
                "número": "número",
                "sigla": "sigla"
            }
            return type_mapping.get(embedding_type, embedding_type)
        
        # Fallback: usar hints tradicionais
        from src.graph_extractor.hints.base import hint_registry
        
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        
        # Mapeamento de nomes de hints para nomes de tipos
        type_mapping = {
            "address": "endereço",
            "phone": "telefone",
            "date": "data",
            "money": "valor monetário",
            "cpf_cnpj": "CPF ou CNPJ"
        }
        
        # Encontrar primeira hint específica (não genérica)
        for hint in relevant_hints:
            if hint.name not in ("text", "name") and hint.name in type_mapping:
                return type_mapping[hint.name]
        
        return None
    
    def _fix_missing_table_values(
        self,
        tokens: List[Token],
        graph: Graph,
        tables: List
    ) -> None:
        """Corrige padrão específico em tabelas verticais onde há labels sem values.
        
        Detecta casos onde uma tabela vertical tem múltiplas colunas de labels
        intercaladas com colunas de values, mas alguns labels não têm values associados
        (values "apagados").
        
        Padrão típico:
        - Coluna 0: Labels
        - Coluna 1: Values
        - Coluna 2: Labels (mas seus values estão "apagados")
        
        Nesse caso, os labels da coluna 2 devem ter seus values associados
        aos values da coluna 1 (mesma linha), compartilhando os mesmos values.
        
        Args:
            tokens: Lista de tokens
            graph: Grafo completo
            tables: Lista de tabelas detectadas
        """
        from src.graph_builder.table_detector import TableOrientation
        from src.graph_builder.adjacency import AdjacencyMatrix
        
        adjacency = AdjacencyMatrix(graph)
        
        for table in tables:
            # Só processar tabelas verticais
            if table.orientation != TableOrientation.VERTICAL:
                continue
            
            max_col = max(cell.col for cell in table.cells)
            if max_col < 1:
                continue
            
            # Para cada coluna par (0, 2, 4, ...) que contém labels
            # Verificar se a coluna seguinte (ímpar) contém values
            # E se os labels não têm values associados, associá-los aos values da coluna anterior
            for label_col in range(0, max_col + 1, 2):  # Colunas pares (0, 2, 4, ...)
                value_col = label_col + 1
                
                if value_col > max_col:
                    continue
                
                label_cells = table.get_col(label_col)
                value_cells = table.get_col(value_col)
                
                if not label_cells or not value_cells:
                    continue
                
                # Verificar se são realmente labels e values
                are_labels = all(
                    cell.token.role == "LABEL" for cell in label_cells
                )
                are_values = all(
                    cell.token.role == "VALUE" for cell in value_cells
                )
                
                if not (are_labels and are_values):
                    continue
                
                # Para cada label, verificar se tem value associado
                # Se não tem, procurar value na coluna anterior (se houver) ou na coluna seguinte
                for label_cell in label_cells:
                    label_token = label_cell.token
                    label_row = label_cell.row
                    
                    # Verificar se este label já tem um value associado
                    has_value = False
                    for edge in graph.get_edges_from(label_token.id):
                        child = graph.get_node(edge.to_id)
                        if child and child.role == "VALUE":
                            has_value = True
                            break
                    
                    # Se não tem value, procurar value na mesma linha
                    if not has_value:
                        # Primeiro tentar coluna seguinte (value_col)
                        value_cell = table.get_cell(label_row, value_col)
                        if value_cell:
                            value_token = value_cell.token
                            
                            # Criar associação: label -> value
                            from src.graph_builder.models import Edge
                            
                            # Verificar se já existe edge
                            has_edge = False
                            for edge in graph.get_edges_from(label_token.id):
                                if edge.to_id == value_token.id:
                                    has_edge = True
                                    break
                            
                            if not has_edge:
                                # Adicionar edge east (label -> value à direita)
                                edge = Edge(
                                    from_id=label_token.id,
                                    to_id=value_token.id,
                                    relation="east"
                                )
                                graph.add_edge(edge)
                                adjacency.add_edge(edge)
                                
                                # Atualizar role do token se necessário
                                if label_token.role != "LABEL":
                                    label_token.role = "LABEL"
                        else:
                            # Se não há value na coluna seguinte, tentar coluna anterior
                            if label_col > 0:
                                prev_value_col = label_col - 1
                                prev_value_cell = table.get_cell(label_row, prev_value_col)
                                if prev_value_cell and prev_value_cell.token.role == "VALUE":
                                    value_token = prev_value_cell.token
                                    
                                    from src.graph_builder.models import Edge
                                    
                                    # Verificar se já existe edge
                                    has_edge = False
                                    for edge in graph.get_edges_from(label_token.id):
                                        if edge.to_id == value_token.id:
                                            has_edge = True
                                            break
                                    
                                    if not has_edge:
                                        # Adicionar edge west (label -> value à esquerda)
                                        edge = Edge(
                                            from_id=label_token.id,
                                            to_id=value_token.id,
                                            relation="west"
                                        )
                                        graph.add_edge(edge)
                                        adjacency.add_edge(edge)
                                        
                                        # Atualizar role do token se necessário
                                        if label_token.role != "LABEL":
                                            label_token.role = "LABEL"
    
    def _collect_all_descendants(self, token: Token, graph: Graph) -> List[Token]:
        """Coleta todos os descendentes de um token (recursivo).
        
        Args:
            token: Token raiz
            graph: Grafo completo
            
        Returns:
            Lista de todos os tokens descendentes (filhos, netos, etc.)
        """
        descendants = []
        visited = set()
        
        def collect_recursive(node_id: int):
            if node_id in visited:
                return
            visited.add(node_id)
            
            edges = graph.get_edges_from(node_id)
            for edge in edges:
                child = graph.get_node(edge.to_id)
                if child and child.id != token.id:  # Não incluir o próprio token
                    descendants.append(child)
                    collect_recursive(child.id)
        
        collect_recursive(token.id)
        return descendants
    
    def _build_aggregation_candidates(
        self, 
        token: Token, 
        descendants: List[Token]
    ) -> List[str]:
        """Constrói candidatos de agregação (do mais completo ao mais simples).
        
        Algoritmo:
        1. Se tem descendentes, começar com token + todos os descendentes
        2. Reduzir um descendente por vez até ter apenas o token
        3. Último candidato: apenas o token
        
        Args:
            token: Token raiz
            descendants: Lista de descendentes
            
        Returns:
            Lista de strings candidatas (do mais completo ao mais simples)
        """
        candidates = []
        
        if not descendants:
            # Sem descendentes, retornar apenas o token
            candidates.append(token.text.strip())
            return candidates
        
        # Ordenar descendentes por ordem espacial (Y primeiro, depois X)
        sorted_descendants = sorted(
            descendants, 
            key=lambda t: (t.bbox.center_y(), t.bbox.center_x())
        )
        
        # Candidato mais completo: token + todos os descendentes
        all_texts = [token.text.strip()] + [d.text.strip() for d in sorted_descendants]
        all_text = " ".join([t for t in all_texts if t])  # Filtrar vazios
        if all_text:
            candidates.append(all_text)
        
        # Reduzir um por um (do mais completo ao mais simples)
        # Começar removendo o último descendente, depois o penúltimo, etc.
        for i in range(len(sorted_descendants) - 1, 0, -1):
            subset = sorted_descendants[:i]
            subset_texts = [token.text.strip()] + [d.text.strip() for d in subset]
            candidate_text = " ".join([t for t in subset_texts if t])
            if candidate_text and candidate_text not in candidates:
                candidates.append(candidate_text)
        
        # Último candidato: apenas o token (se ainda não estiver na lista)
        token_only = token.text.strip()
        if token_only and token_only not in candidates:
            candidates.append(token_only)
        
        return candidates
    
    def _validate_with_llm_type_check(
        self,
        token: Token,
        field_name: str,
        field_description: str,
        graph: Graph
    ) -> Optional[str]:
        """Valida tipo usando LLM com abordagem de agregação progressiva.
        
        IMPORTANTE: A validação LLM só é aplicada para tipos que realmente precisam:
        - endereço (address)
        - telefone (phone)
        
        Outros tipos (data, money, cpf_cnpj) usam validação com hints padrão, não LLM.
        
        Algoritmo:
        1. Identificar tipo esperado (endereço, telefone, etc.)
        2. Verificar se é um tipo que requer validação LLM (apenas endereço/telefone)
        3. Coletar todos os descendentes do token (recursivo)
        4. Construir candidatos: todos os filhos concatenados → reduzindo até o token
        5. Para cada candidato, perguntar ao LLM se é do tipo esperado
        6. Retornar o primeiro candidato validado, ou None se nenhum passar
        
        Args:
            token: Token a validar
            field_name: Nome do campo
            field_description: Descrição do campo
            graph: Grafo completo
            
        Returns:
            Primeiro candidato validado pelo LLM, ou None se nenhum passar
        """
        # 1. Identificar tipo esperado
        expected_type = self._get_expected_type_name(field_name, field_description)
        
        # 2. Verificar se é um tipo que requer validação LLM (apenas endereço e telefone)
        llm_required_types = ["endereço", "telefone"]
        
        if not expected_type or expected_type not in llm_required_types:
            if self.debug or get_debug_mode():
                debug_print(f"  [LLM Validation] Pulando validação LLM - tipo '{expected_type}' não requer LLM (apenas endereço/telefone)")
            return None  # Não é um tipo que requer validação LLM
        
        if not self.llm_tiebreaker:
            if self.debug or get_debug_mode():
                debug_print(f"  [LLM Validation] LLM não disponível")
            return None  # LLM não disponível
        
        if self.debug or get_debug_mode():
            debug_print(f"  [LLM Validation] APLICANDO validação LLM para tipo: {expected_type}")
            debug_print(f"  [LLM Validation] Campo: '{field_name}' | Descrição: '{field_description}'")
            debug_print(f"  [LLM Validation] Token: '{token.text}' (role: {token.role})")
        
        # 3. Coletar todos os descendentes (recursivo)
        all_descendants = self._collect_all_descendants(token, graph)
        
        if self.debug or get_debug_mode():
            debug_print(f"  [LLM Validation] Descendentes encontrados: {len(all_descendants)}")
            if all_descendants:
                debug_print(f"  [LLM Validation] Descendentes: {[d.text for d in all_descendants[:5]]}")
        
        # 4. Construir candidatos (do mais completo ao mais simples)
        candidates = self._build_aggregation_candidates(token, all_descendants)
        
        if self.debug or get_debug_mode():
            debug_print(f"  [LLM Validation] Candidatos gerados: {len(candidates)}")
        
        # 5. Validar cada candidato com LLM (parar no primeiro positivo)
        # Limitar tentativas para evitar muitas chamadas ao LLM
        max_attempts = min(7, len(candidates))  # Máximo 7 tentativas
        
        for i, candidate_text in enumerate(candidates[:max_attempts]):
            if self.debug or get_debug_mode():
                debug_print(f"  [LLM Validation] Tentativa {i+1}/{max_attempts}: Validando '{candidate_text[:50]}...'")
            
            try:
                is_valid = self.llm_tiebreaker.validate_type(candidate_text, expected_type)
                
                if self.debug or get_debug_mode():
                    debug_print(f"  [LLM Validation] Resultado: {'SIM' if is_valid else 'NÃO'}")
                
                if is_valid:
                    # Primeiro candidato validado → retornar
                    return candidate_text
            except Exception as e:
                if self.debug or get_debug_mode():
                    debug_print(f"  [LLM Validation] Erro ao validar: {e}")
                continue
        
        # 6. Nenhum candidato passou → retornar None
        if self.debug or get_debug_mode():
            debug_print(f"  [LLM Validation] Nenhum candidato foi validado como {expected_type}")
        
        return None
    
    def _resolve_perfect_regex_match(
        self,
        field_name: str,
        match: MatchResult,
        graph: Graph,
        node_manager: NodeUsageManager,
        field_description: str = "",
        strategy_suffix: str = ""
    ) -> FieldMatch:
        """Resolve um match perfeito de regex aplicando as regras.
        
        Se um nó tem exatamente o mesmo regex que chave/descrição:
        - Se o token é LABEL → busca VALUE filho, retorna VALUE (ou null se não tiver)
        - Se o token é HEADER → verifica se é tipo esperado, se não for null
        - Se o token é VALUE → retorna VALUE (após validar tipo)
        
        Args:
            field_name: Nome do campo
            match: MatchResult do match perfeito
            graph: Grafo completo
            node_manager: Gerenciador de nós usados
            field_description: Descrição do campo
            strategy_suffix: Sufixo para estratégia (ex: "_tiebreak")
            
        Returns:
            FieldMatch com valor resolvido
        """
        token = match.token
        extracted_value = None
        strategy = f"regex_perfect{strategy_suffix}"
        
        # Debug: campos problemáticos
        if field_name in ("endereco_profissional", "telefone_profissional") and (self.debug or get_debug_mode()):
            debug_print(f"\n[DEBUG] _resolve_perfect_regex_match para '{field_name}':")
            debug_print(f"  Token: '{token.text}' (role: {token.role})")
            debug_print(f"  match.extracted_value: '{match.extracted_value}'")
            debug_print(f"  _has_specific_hints: {self._has_specific_hints(field_name, field_description)}")
        
        # PRIORIDADE 1: Se o MatchResult já tem extracted_value definido (do regex_matcher)
        # Isso acontece quando o regex_matcher já encontrou o VALUE filho de uma LABEL
        if match.extracted_value and match.extracted_value != "":
            candidate_value = match.extracted_value
            
            # Se o token é LABEL e tem VALUE filho, sempre retornar o VALUE (não validar tipo)
            # Isso garante que "Inscrição" → VALUE seja sempre retornado
            if token.role == "LABEL":
                # LABEL com VALUE filho já extraído → retornar diretamente
                extracted_value = candidate_value
                strategy = f"regex_perfect_value{strategy_suffix}"
            elif token.role == "HEADER":
                # HEADER sem VALUE filho (o extracted_value é o próprio HEADER)
                # Se o campo espera tipo específico (endereço, telefone), validar usando LLM com agregação progressiva
                
                extracted_value = candidate_value
                strategy = f"regex_perfect_header{strategy_suffix}"
            else:
                # Para outros roles (VALUE, etc.), validar tipo se necessário
                if self._has_specific_hints(field_name, field_description):
                    if self._validate_value_type(candidate_value, field_name, field_description):
                        extracted_value = candidate_value
                        strategy = f"regex_perfect_value{strategy_suffix}"
                    else:
                        extracted_value = None
                        strategy = f"regex_perfect_value_type_mismatch{strategy_suffix}"
                else:
                    extracted_value = candidate_value
                    strategy = f"regex_perfect_value{strategy_suffix}"
        
        # Se não tem extracted_value do match, verificar baseado no role do token
        elif token.role == "LABEL":
            # LABEL → buscar VALUE filho
            value_token = self.regex_matcher._find_value_for_label(token, graph)
            if value_token:
                extracted_value = value_token.text.strip()
                strategy = f"regex_perfect_label_value{strategy_suffix}"
            else:
                # LABEL sem VALUE → verificar se é tipo esperado (endereço, telefone, etc.)
                # Se for tipo específico esperado, usar LLM para validar com agregação progressiva
                if self._has_specific_hints(field_name, field_description):
                    # Usar validação LLM com agregação progressiva
                    validated_value = self._validate_with_llm_type_check(
                        token, field_name, field_description, graph
                    )
                    
                    if validated_value:
                        # LLM validou algum candidato → retornar
                        extracted_value = validated_value
                        strategy = f"regex_perfect_label_llm_validated{strategy_suffix}"
                    else:
                        # Nenhum candidato foi validado pelo LLM → retornar null
                        extracted_value = None
                        strategy = f"regex_perfect_label_no_value{strategy_suffix}"
                else:
                    # Tipo genérico, retornar null
                    extracted_value = None
                    strategy = f"regex_perfect_label_no_value{strategy_suffix}"
        
        elif token.role == "HEADER":
            # Verificar se o token foi convertido de HEADER para LABEL pela regra AdjacentHeadersToLabelValueRule
            # (o role pode ter sido atualizado diretamente no token, mas o MatchResult ainda tem o role antigo)
            current_role = token.role  # Pode ter sido atualizado pela regra
            
            # Se foi convertido para LABEL, tratar como LABEL
            if current_role == "LABEL":
                # LABEL → buscar VALUE filho
                value_token = self.regex_matcher._find_value_for_label(token, graph)
                if value_token:
                    extracted_value = value_token.text.strip()
                    strategy = f"regex_perfect_label_value_converted{strategy_suffix}"
                else:
                    extracted_value = None
                    strategy = f"regex_perfect_label_no_value_converted{strategy_suffix}"
            else:
                # HEADER → verificar se tem VALUE filho primeiro
                # Se o campo espera tipo específico (endereço, telefone), verificar se HEADER tem VALUE filho
                edges = graph.get_edges_from(token.id)
                header_value_children = []
                for edge in edges:
                    child = graph.get_node(edge.to_id)
                    if child and child.role == "VALUE":
                        header_value_children.append(child)
                
                # Verificar se há HEADERs adjacentes que foram convertidos em VALUE pela regra AdjacentHeadersToLabelValueRule
                # Procurar por HEADERs próximos (south ou east) que podem ter sido convertidos em VALUE
                adjacent_value = None
                if not header_value_children:
                    # Procurar HEADERs adjacentes que podem ter sido convertidos em VALUE
                    for edge in edges:
                        neighbor = graph.get_node(edge.to_id)
                        if neighbor and neighbor.role == "VALUE":
                            # Verificar se está próximo (south ou east)
                            if edge.relation in ("south", "east"):
                                # Verificar se o neighbor era originalmente um HEADER (pode ter sido convertido)
                                # Se está próximo e é VALUE, pode ser o resultado da conversão
                                neighbor_bbox = neighbor.bbox
                                token_bbox = token.bbox
                                
                                # Verificar proximidade
                                is_below = neighbor_bbox.y0 > token_bbox.y1
                                is_right = neighbor_bbox.x0 > token_bbox.x1
                                
                                if (is_below and edge.relation == "south") or (is_right and edge.relation == "east"):
                                    # Verificar distância (não muito longe)
                                    if is_below:
                                        distance = neighbor_bbox.y0 - token_bbox.y1
                                        if distance < (token_bbox.y1 - token_bbox.y0) * 3:
                                            adjacent_value = neighbor
                                            break
                                    elif is_right:
                                        distance = neighbor_bbox.x0 - token_bbox.x1
                                        if distance < (token_bbox.x1 - token_bbox.x0) * 3:
                                            adjacent_value = neighbor
                                            break
                
                if adjacent_value:
                    # HEADER tem VALUE adjacente (convertido pela regra) → retornar VALUE
                    candidate_value = adjacent_value.text.strip()
                    if self._has_specific_hints(field_name, field_description):
                        if self._validate_value_type(candidate_value, field_name, field_description):
                            extracted_value = candidate_value
                            strategy = f"regex_perfect_header_converted_to_label_value{strategy_suffix}"
                        else:
                            extracted_value = None
                            strategy = f"regex_perfect_header_converted_type_mismatch{strategy_suffix}"
                    else:
                        extracted_value = candidate_value
                        strategy = f"regex_perfect_header_converted_to_label_value{strategy_suffix}"
                elif header_value_children:
                    # HEADER tem VALUE filho → retornar VALUE após validar tipo
                    candidate_value = header_value_children[0].text.strip()
                    if self._has_specific_hints(field_name, field_description):
                        if self._validate_value_type(candidate_value, field_name, field_description):
                            extracted_value = candidate_value
                            strategy = f"regex_perfect_header_value{strategy_suffix}"
                        else:
                            # HEADER tem VALUE mas tipo não corresponde → retornar null
                            extracted_value = None
                            strategy = f"regex_perfect_header_value_type_mismatch{strategy_suffix}"
                    else:
                        # Sem hints específicas, aceitar VALUE do HEADER
                        extracted_value = candidate_value
                        strategy = f"regex_perfect_header_value{strategy_suffix}"
                else:
                    # HEADER sem VALUE filho
                    # Se regex é perfeito e não tem filho VALUE, sempre retornar null
                    # (não importa se é tipo específico ou genérico)
                    extracted_value = None
                    strategy = f"regex_perfect_header_no_value{strategy_suffix}"
                
                if self.debug and field_name in ("endereco_profissional", "telefone_profissional"):
                    print(f"  HEADER sem VALUE filho: '{token.text.strip()}'")
                    print(f"  Regex perfeito sem filho -> retornando null")
                    print(f"  extracted_value final: {extracted_value}")
        
        elif token.role == "VALUE":
            # VALUE → retornar após validar tipo
            candidate_value = token.text.strip()
            if self._validate_value_type(candidate_value, field_name, field_description):
                extracted_value = candidate_value
                strategy = f"regex_perfect_token_value{strategy_suffix}"
            else:
                # Para VALUE, mesmo que tipo não corresponda, retornar o valor
                # (pode ser um caso especial)
                extracted_value = candidate_value
                strategy = f"regex_perfect_token_value{strategy_suffix}"
        
        else:
            # Outros roles → retornar null
            extracted_value = None
            strategy = f"regex_perfect_no_value{strategy_suffix}"
        
        # Verificar filhos do token (nós conectados por edges que saem deste token)
        # Isso é usado como fallback se ainda não tivermos um valor
        if extracted_value is None:
            edges = graph.get_edges_from(token.id)
            value_children = []
            label_children = []
            
            for edge in edges:
                child = graph.get_node(edge.to_id)
                if child:
                    if child.role == "VALUE":
                        value_children.append(child)
                    elif child.role == "LABEL":
                        label_children.append(child)
            
            # Se tiver filho VALUE → retornar VALUE
            if value_children:
                extracted_value = value_children[0].text.strip()
                strategy = f"regex_perfect_value{strategy_suffix}"
            
            # Se tiver filho LABEL → buscar VALUE do LABEL filho
            elif label_children:
                for label_child in label_children:
                    label_edges = graph.get_edges_from(label_child.id)
                    for label_edge in label_edges:
                        if label_edge.relation in ("east", "south"):
                            value_child = graph.get_node(label_edge.to_id)
                            if value_child and value_child.role == "VALUE":
                                extracted_value = value_child.text.strip()
                                strategy = f"regex_perfect_label_value{strategy_suffix}"
                                break
                    if extracted_value:
                        break
                
                if not extracted_value:
                    # LABEL filho sem VALUE → retornar null
                    extracted_value = None
                    strategy = f"regex_perfect_label_no_value{strategy_suffix}"
        
        # Criar MatchResult atualizado
        updated_match = MatchResult(
            token=match.token,
            score=match.score,
            match_type=match.match_type,
            reason=match.reason,
            hint_name=match.hint_name,
            label_token=match.label_token,
            extracted_value=extracted_value
        )
        
        return self._create_field_match(field_name, updated_match, strategy, node_manager)
    
    def _has_specific_hints(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo tem hints específicas (não genéricas como text/name).
        
        Usa classificação por embedding primeiro (mais inteligente), depois fallback para hints.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            True se há hints específicas ou tipo classificado por embedding
        """
        # Primeiro verificar se embedding classificou um tipo específico
        expected_type = self._get_expected_type_name(field_name, field_description)
        if expected_type:
            # Tipos genéricos que não requerem validação rigorosa
            generic_types = {"nome", "texto", "sigla"}
            if expected_type.lower() not in generic_types:
                return True
        
        # Fallback: usar hints tradicionais
        from src.graph_extractor.hints.base import hint_registry
        
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        
        # Verificar se há hints específicas (não text/name)
        for hint in relevant_hints:
            if hint.name not in ("text", "name"):
                return True
        
        return False
    
    def _process_partial_regex_matches(
        self,
        field_name: str,
        partial_matches: List[MatchResult],
        field_description: str,
        graph: Graph,
        node_manager: NodeUsageManager
    ) -> FieldMatch:
        """Processa matches parciais (regex na mesma faixa).
        
        Se tiver mais que um com regex na mesma faixa, desempata com embedding ou LLM.
        
        Args:
            field_name: Nome do campo
            partial_matches: Lista de matches parciais
            field_description: Descrição do campo
            graph: Grafo completo
            node_manager: Gerenciador de nós usados
            
        Returns:
            FieldMatch com resultado processado
        """
        if len(partial_matches) == 1:
            # Match parcial único
            match = partial_matches[0]
            if match.extracted_value and match.extracted_value != "":
                # Validar tipo antes de retornar
                if self._validate_value_type(match.extracted_value, field_name, field_description):
                    return self._create_field_match(field_name, match, "regex_partial", node_manager)
                else:
                    return FieldMatch(
                        field_name=field_name,
                        value=None,
                        strategy_used="none",
                        metadata={"reason": "Match parcial mas tipo não corresponde ao esperado"}
                    )
            else:
                return FieldMatch(
                    field_name=field_name,
                    value=None,
                    strategy_used="none",
                    metadata={"reason": "Match parcial mas sem valor extraído"}
                )
        
        # Múltiplos matches parciais na mesma faixa - desempata com embedding ou LLM
        # Primeiro tentar embedding
        try:
            embedding_matches = self.embedding_matcher.match(
                field_name, field_description,
                [m.token for m in partial_matches], graph
            )
            
            if embedding_matches:
                # Usar embedding para desempatar
                selected_match = partial_matches[0]  # Pegar match correspondente ao melhor embedding
                # Encontrar o match parcial correspondente ao melhor embedding
                for partial_match in partial_matches:
                    if partial_match.token.id == embedding_matches[0].token.id:
                        selected_match = partial_match
                        break
                
                if selected_match.extracted_value and selected_match.extracted_value != "":
                    # Validar tipo antes de retornar
                    if self._validate_value_type(selected_match.extracted_value, field_name, field_description):
                        return self._create_field_match(
                            field_name, selected_match, "regex_partial_embedding_tiebreak", node_manager
                        )
                    else:
                        return FieldMatch(
                            field_name=field_name,
                            value=None,
                            strategy_used="none",
                            metadata={"reason": "Match parcial (embedding tiebreak) mas tipo não corresponde"}
                        )
        except Exception as e:
            print(f"Erro ao usar embedding para desempate: {e}")
        
        # Se embedding não funcionou, usar LLM ou heurísticas
        selected = self._resolve_tie(partial_matches, field_description, graph, field_name)
        if selected.extracted_value and selected.extracted_value != "":
            # Validar tipo antes de retornar
            if self._validate_value_type(selected.extracted_value, field_name, field_description):
                return self._create_field_match(
                    field_name, selected, "regex_partial_llm_tiebreak", node_manager
                )
            else:
                return FieldMatch(
                    field_name=field_name,
                    value=None,
                    strategy_used="none",
                    metadata={"reason": "Match parcial (LLM tiebreak) mas tipo não corresponde"}
                )
        
        return FieldMatch(
            field_name=field_name,
            value=None,
            strategy_used="none",
            metadata={"reason": "Matches parciais não puderam ser desempatados"}
        )
    
    def _resolve_tie(
        self,
        candidates: List[MatchResult],
        field_description: str,
        graph: Graph,
        field_name: Optional[str] = None
    ) -> MatchResult:
        """Resolve empate entre candidatos (método geral).
        
        Ordem de tentativas:
        1. Embedding com sinônimos (mais geral e inteligente)
        2. Heurísticas
        3. LLM (se disponível)
        
        Args:
            candidates: Lista de candidatos empatados
            field_description: Descrição do campo
            graph: Grafo completo
            field_name: Nome do campo (opcional, para melhor embedding)
            
        Returns:
            MatchResult escolhido
        """
        if len(candidates) == 1:
            return candidates[0]
        
        # 1. Tentar embedding primeiro (mais geral e inteligente)
        if field_name:
            try:
                embedding_matches = self.embedding_matcher.match(
                    field_name, field_description,
                    [c.token for c in candidates], graph
                )
                
                if embedding_matches:
                    # Encontrar o candidato correspondente ao melhor embedding
                    best_embedding_token_id = embedding_matches[0].token.id
                    for candidate in candidates:
                        if candidate.token.id == best_embedding_token_id:
                            if self.debug or get_debug_mode():
                                debug_print(f"  [Tiebreak] Embedding escolheu candidato com label: {candidate.label_token.text if candidate.label_token else 'N/A'}")
                            return candidate
            except Exception as e:
                if self.debug or get_debug_mode():
                    debug_print(f"  [Tiebreak] Erro ao usar embedding: {e}")
        
        # 2. Tentar heurísticas
        try:
            selected = self.heuristic_tiebreaker.break_tie(candidates, graph, field_description)
            
            # 3. Se heurísticas não conseguiram desempatar bem, usar LLM
            if self.llm_tiebreaker and self.heuristic_tiebreaker.should_break_tie(candidates, 0.01):
                try:
                    selected = self.llm_tiebreaker.break_tie(candidates, graph, field_description)
                except Exception as e:
                    # Se LLM falhar, usar resultado das heurísticas
                    if self.debug or get_debug_mode():
                        debug_print(f"  [Tiebreak] Erro ao usar LLM: {e}")
            
            return selected
            
        except Exception as e:
            if self.debug or get_debug_mode():
                debug_print(f"  [Tiebreak] Erro ao resolver empate: {e}")
            # Fallback: retornar primeiro candidato (maior score)
            return candidates[0]
    
    def _create_field_match(
        self,
        field_name: str,
        match_result: MatchResult,
        strategy: str,
        node_manager: NodeUsageManager
    ) -> FieldMatch:
        """Cria FieldMatch e marca nó como usado apenas se houver alta certeza.
        
        Alta certeza é considerada quando:
        - Score >= 0.9
        - Match type é PERFECT
        - Estratégia é "pattern_perfect" ou "regex_perfect"
        
        Args:
            field_name: Nome do campo
            match_result: Resultado do match
            strategy: Estratégia usada
            node_manager: Gerenciador de nós usados
            
        Returns:
            FieldMatch criado
        """
        # Obter valor: se extracted_value é string vazia ou None, significa null
        # IMPORTANTE: Não usar get_value() aqui porque ele tem fallback para token.text
        # Queremos retornar None quando explicitamente definido como None ou ""
        if match_result.extracted_value == "" or match_result.extracted_value is None:
            value = None
        else:
            # Usar extracted_value diretamente (sem fallback)
            value = match_result.extracted_value
        
        # Determinar se há alta certeza
        high_confidence = self._has_high_confidence(match_result, strategy)
        
        # Marcar nó como usado apenas se houver alta certeza
        if high_confidence:
            node_manager.mark_as_used(
                match_result.token.id,
                field_name,
                value
            )
        
        return FieldMatch(
            field_name=field_name,
            value=value,
            match_result=match_result,
            strategy_used=strategy,
            metadata={
                "score": match_result.score,
                "match_type": match_result.match_type.value,
                "reason": match_result.reason,
                "token_id": match_result.token.id,
                "hint_name": match_result.hint_name,
                "node_marked_as_used": high_confidence  # Indicar se nó foi marcado
            }
        )
    
    def _learn_from_field_match(
        self,
        label_type: str,
        field_name: str,
        field_description: str,
        field_match: FieldMatch,
        graph: Graph
    ) -> None:
        """Aprende de um resultado de extração de campo.
        
        Args:
            label_type: Tipo do documento (label)
            field_name: Nome do campo
            field_description: Descrição do campo
            field_match: Resultado da extração
            graph: Grafo completo
        """
        found = field_match.value is not None
        
        # Obter informações do token se houver match
        x = None
        y = None
        role = None
        data_type = None
        strategy = field_match.strategy_used
        connections = None
        
        if field_match.match_result:
            token = field_match.match_result.token
            if hasattr(token, 'bbox') and token.bbox:
                x = token.bbox.x0
                y = token.bbox.y0
            role = token.role
            data_type = self._get_expected_type_name(field_name, field_description)
            
            # Contar conexões
            edges_from = graph.get_edges_from(token.id)
            edges_to = graph.get_edges_to(token.id)
            connections = len(edges_from) + len(edges_to)
        
        # Aprender
        self.learner.learn_from_extraction(
            label_type=label_type,
            field_name=field_name,
            found=found,
            x=x,
            y=y,
            role=role,
            data_type=data_type,
            strategy=strategy,
            connections=connections
        )
        
        if (self.debug or get_debug_mode()) and found:
            info = self.learner.get_field_info(label_type, field_name)
            if info:
                debug_print(f"  [Learning] Campo '{field_name}': rigidez={info['rigidity']:.2f}, taxa_sucesso={info['found_rate']:.2f}, ocorrências={info['occurrence_count']}")
    
    def _has_high_confidence(self, match_result: MatchResult, strategy: str) -> bool:
        """Verifica se há alta certeza no match.
        
        Args:
            match_result: Resultado do match
            strategy: Estratégia usada
            
        Returns:
            True se há alta certeza (deve marcar nó como usado)
        """
        # Estratégias com alta certeza
        high_confidence_strategies = [
            "pattern_perfect",
            "regex_perfect",
            "pattern_perfect_tiebreak",  # Após desempate de matches perfeitos
            "regex_perfect_tiebreak",  # Após desempate de matches perfeitos
            "regex_partial_tiebreak",  # Regex parcial após desempate (múltiplos parciais)
            "name_gpt",  # Nome identificado por GPT
            "regex_perfect_header_llm_validated",  # Regex perfeito HEADER validado por LLM
            "regex_perfect_label_llm_validated"  # Regex perfeito LABEL validado por LLM
        ]
        
        # Verificar estratégia
        if strategy in high_confidence_strategies:
            return True
        
        # Verificar score alto
        if match_result.score >= 0.9:
            return True
        
        # Verificar se é match PERFECT
        if match_result.match_type == MatchType.PERFECT:
            return True
        
        # Para embeddings, só marcar se score muito alto (>= 0.85) E sem empate
        if strategy == "embedding" and match_result.score >= 0.85:
            return True
        
        # Para embedding com tiebreak (desempate), só marcar se score muito alto (>= 0.9)
        # porque já passou por desempate, então há mais confiança
        if strategy == "embedding_tiebreak" and match_result.score >= 0.9:
            return True
        
        # Para name_embedding, já passou por filtro de NameHint + embedding, então é alta confiança
        if strategy in ("name_embedding", "name_embedding_tiebreak"):
            return match_result.score >= 0.7  # Threshold mais baixo porque já foi filtrado
        
        # Para outros casos, não marcar como usado (baixa certeza)
        return False
    
    def _create_empty_result(
        self,
        label: str,
        extraction_schema: Dict[str, str],
        start_time: float,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cria resultado vazio em caso de erro.
        
        Args:
            label: Label do documento
            extraction_schema: Schema de extração
            start_time: Tempo de início
            error: Mensagem de erro (opcional)
            
        Returns:
            Dicionário com resultado vazio
        """
        fields = {field: None for field in extraction_schema.keys()}
        metadata = ExtractionMetadata(
            label=label,
            total_fields=len(extraction_schema),
            extracted_fields=0,
            nodes_used=[],
            extraction_time=round(time.time() - start_time, 2),
            strategies_breakdown={field: "none" for field in extraction_schema.keys()}
        )
        
        result = ExtractionResult(
            label=label,
            fields=fields,
            field_matches=[],
            metadata=metadata
        )
        
        result_dict = result.to_dict()
        if error:
            result_dict["metadata"]["error"] = error
        
        return result_dict
