"""Matcher baseado em regex."""

import re
import unicodedata
from typing import List, Optional, Pattern
from src.graph_builder.models import Token, Graph
from src.graph_extractor.models import MatchResult, MatchType
from src.graph_extractor.matchers.base import BaseMatcher
from src.graph_extractor.hints.base import hint_registry


class RegexMatcher(BaseMatcher):
    """Matcher que usa regex para encontrar correspondências exatas.
    
    Este matcher normaliza texto e aplica regex baseado em hints ou
    no nome/descrição do campo para encontrar matches perfeitos ou parciais.
    """
    
    def __init__(self):
        """Inicializa RegexMatcher."""
        super().__init__()
    
    def match(
        self,
        field_name: str,
        field_description: str,
        candidates: List[Token],
        graph: Optional[Graph] = None
    ) -> List[MatchResult]:
        """Encontra candidatos usando regex.
        
        Lógica:
        - Match perfeito: regex do campo (chave OU descrição) é idêntico a um nó
        - Se match perfeito com LABEL → retorna VALUE associado (se tiver) ou null
        - Se match perfeito com múltiplos nós → desempate necessário
        - Match parcial: perde para match perfeito, mas diferentes parciais precisam desempate
        - Regex com LABEL → devolve VALUE (se tiver) ou null
        - Regex com HEADER → devolve HEADER inteiro
        - Regex com VALUE → devolve VALUE inteiro
        - Se regex perfeito para algo sem VALUE → retorna null
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            candidates: Lista de nós candidatos
            graph: Grafo completo (para encontrar VALUEs associados)
            
        Returns:
            Lista de MatchResult ordenada por score (perfeitos primeiro, depois parciais)
        """
        if not candidates or not graph:
            return []
        
        # Normalizar nome do campo e descrição
        normalized_field_name = self._normalize_text(field_name)
        normalized_field_description = self._normalize_text(field_description)
        
        # Criar regex patterns do campo (chave e descrição)
        field_regex = self._create_field_regex(field_name, field_description)
        description_regex = self._create_field_regex(field_description, "")
        
        matches = []
        
        # Verificar cada candidato
        for token in candidates:
            # Verificar match perfeito: regex idêntico ao texto do nó
            perfect_match = self._check_perfect_regex_match(
                field_name, field_description,
                normalized_field_name, normalized_field_description,
                field_regex, description_regex,
                token, graph
            )
            if perfect_match:
                matches.append(perfect_match)
                continue
            
            # Verificar match parcial (só se não encontrou perfeito)
            partial_match = self._check_partial_regex_match(
                normalized_field_name, normalized_field_description,
                field_regex, description_regex,
                token, graph
            )
            if partial_match:
                matches.append(partial_match)
        
        # Separar perfeitos de parciais e ordenar
        perfect_matches = [m for m in matches if m.match_type == MatchType.PERFECT]
        partial_matches = [m for m in matches if m.match_type == MatchType.PARTIAL]
        
        # Retornar perfeitos primeiro, depois parciais
        return perfect_matches + partial_matches
    
    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para comparação.
        
        Remove acentos, converte para lowercase, remove espaços extras.
        
        Args:
            text: Texto a normalizar
            
        Returns:
            Texto normalizado
        """
        if not text:
            return ""
        
        # Converter underscore para espaço
        text = text.replace('_', ' ')
        
        # Converter para lowercase
        text = text.lower().strip()
        
        # Remover acentos
        text = unicodedata.normalize('NFD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        
        # Remover espaços extras e caracteres especiais (manter apenas alfanuméricos e espaços)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _check_perfect_regex_match(
        self,
        field_name: str,
        field_description: str,
        normalized_field_name: str,
        normalized_field_description: str,
        field_regex: Optional[Pattern],
        description_regex: Optional[Pattern],
        token: Token,
        graph: Graph
    ) -> Optional[MatchResult]:
        """Verifica match perfeito: regex do campo é idêntico ao nó.
        
        Match perfeito significa que o regex (da chave OU descrição) corresponde
        exatamente ao texto do nó (normalizado).
        
        Args:
            field_name: Nome do campo (não normalizado)
            field_description: Descrição do campo (não normalizado)
            normalized_field_name: Nome do campo normalizado
            normalized_field_description: Descrição do campo normalizada
            field_regex: Regex pattern do campo
            description_regex: Regex pattern da descrição
            token: Token candidato
            graph: Grafo completo
            
        Returns:
            MatchResult se houver match perfeito, None caso contrário
        """
        # Obter texto do token (usar texto original, não VALUE, para comparar com regex)
        token_text = token.text.strip()
        normalized_token_text = self._normalize_text(token_text)
        
        # Verificar match perfeito: regex do campo OU descrição corresponde exatamente ao token
        is_perfect_match = False
        matched_field = None
        
        # Testar match perfeito: nome do campo idêntico ao token (normalizado)
        if normalized_field_name and normalized_field_name == normalized_token_text:
            is_perfect_match = True
            matched_field = "field_name"
        # Testar match perfeito: descrição do campo idêntica ao token (normalizado)
        elif normalized_field_description and normalized_field_description == normalized_token_text:
            is_perfect_match = True
            matched_field = "field_description"
        # Testar regex patterns (fullmatch = match exato)
        if not is_perfect_match and field_regex:
            match = field_regex.fullmatch(normalized_token_text)
            if match:
                is_perfect_match = True
                matched_field = "field_regex"
        if not is_perfect_match and description_regex:
            match = description_regex.fullmatch(normalized_token_text)
            if match:
                is_perfect_match = True
                matched_field = "description_regex"
        
        if not is_perfect_match:
            return None
        
        # Match perfeito encontrado - determinar valor a retornar baseado no role do token
        extracted_value = None
        
        if token.role == "LABEL":
            # Regex com LABEL → devolve VALUE se tiver, ou null
            value_token = self._find_value_for_label(token, graph)
            if value_token:
                extracted_value = value_token.text.strip()
            else:
                extracted_value = None  # Não tem VALUE, retorna null
        elif token.role == "HEADER":
            # Match perfeito com HEADER → coletar filhos e testar quais encaixam nas hints específicas
            # Testa cada filho contra as hints específicas do campo
            best_child_value = self._find_best_child_for_header(
                token, graph, field_name, field_description
            )
            if best_child_value:
                extracted_value = best_child_value
            else:
                # Nenhum filho encaixou nas hints ou HEADER não tem filhos
                extracted_value = None
        elif token.role == "VALUE":
            # Regex com VALUE → devolve VALUE inteiro
            extracted_value = token.text.strip()
        else:
            # Se não tem VALUE (outros roles sem VALUE) → retorna null
            extracted_value = None
        
        # Se match perfeito mas não tem VALUE para retornar → null
        # Usar string vazia como marcador (será convertido para None depois)
        if extracted_value is None:
            # Não queremos retornar o input exato, então retorna MatchResult com valor vazio
            # O extractor vai verificar e retornar None
            return MatchResult(
                token=token,
                score=0.95,
                match_type=MatchType.PERFECT,
                reason=f"Perfect regex match with {matched_field}, but no VALUE to return",
                extracted_value=""  # String vazia = não retornar input
            )
        
        # Match perfeito com valor válido
        label_token = None
        if token.role == "VALUE":
            label_token = self.find_label_for_value(token, graph)
        
        reason = f"Perfect regex match: {matched_field} matches token '{token_text}'"
        if token.role == "LABEL":
            reason += f" (LABEL → VALUE)"
        elif token.role == "HEADER":
            if extracted_value:
                reason += f" (HEADER → filho que encaixa nas hints: '{extracted_value}')"
            else:
                reason += f" (HEADER → nenhum filho encaixa nas hints)"
        elif label_token:
            reason += f" (VALUE, LABEL: '{label_token.text}')"
        
        return MatchResult(
            token=token,
            score=0.95,
            match_type=MatchType.PERFECT,
            reason=reason,
            label_token=label_token,
            extracted_value=extracted_value
        )
    
    def _find_value_for_label(self, label_token: Token, graph: Graph) -> Optional[Token]:
        """Encontra VALUE associado a um LABEL.
        
        Args:
            label_token: Token LABEL
            graph: Grafo completo
            
        Returns:
            Token VALUE associado ou None
        """
        edges = graph.get_edges_from(label_token.id)
        for edge in edges:
            if edge.relation in ("east", "south"):
                value_token = graph.get_node(edge.to_id)
                if value_token and value_token.role == "VALUE":
                    return value_token
        return None
    
    def _collect_path_from_token(self, token: Token, graph: Graph, visited: Optional[set] = None) -> List[Token]:
        """Coleta caminho completo de descendentes de um token (recursivo).
        
        Coleta todos os tokens do caminho desde o token até não ter mais filhos.
        Exemplo: LABEL1 → LABEL2 → VALUE1 → VALUE2
        
        Args:
            token: Token raiz
            graph: Grafo completo
            visited: Set de IDs visitados (para evitar loops)
            
        Returns:
            Lista de tokens no caminho (do mais próximo ao mais distante)
        """
        if visited is None:
            visited = set()
        
        if token.id in visited:
            return []
        
        visited.add(token.id)
        path = [token]
        
        # Coletar filhos ordenados espacialmente (Y primeiro, depois X)
        edges = graph.get_edges_from(token.id)
        children = []
        for edge in edges:
            child = graph.get_node(edge.to_id)
            if child:
                children.append(child)
        
        # Ordenar filhos por posição espacial
        sorted_children = sorted(
            children,
            key=lambda t: (t.bbox.center_y(), t.bbox.center_x())
        )
        
        # Para cada filho, coletar seu caminho recursivamente
        for child in sorted_children:
            child_path = self._collect_path_from_token(child, graph, visited)
            if child_path:
                path.extend(child_path)
        
        return path
    
    def _build_candidate_strings_from_path(self, path: List[Token]) -> List[str]:
        """Constrói strings candidatas a partir de um caminho de tokens.
        
        Testa do caminho mais completo ao mais simples:
        - Caminho completo: todos os tokens concatenados
        - Reduzindo um token por vez até ter apenas o primeiro token
        
        Args:
            path: Lista de tokens no caminho
            
        Returns:
            Lista de strings candidatas (do mais completo ao mais simples)
        """
        if not path:
            return []
        
        candidates = []
        
        # Candidato mais completo: todos os tokens do caminho
        all_texts = [t.text.strip() for t in path if t.text.strip()]
        if all_texts:
            candidates.append(" ".join(all_texts))
        
        # Reduzir um token por vez (do final para o início)
        for i in range(len(path) - 1, 0, -1):
            subset = path[:i]
            subset_texts = [t.text.strip() for t in subset if t.text.strip()]
            if subset_texts:
                candidate = " ".join(subset_texts)
                if candidate not in candidates:
                    candidates.append(candidate)
        
        return candidates
    
    def _find_best_child_for_header(
        self,
        header_token: Token,
        graph: Graph,
        field_name: str,
        field_description: str
    ) -> Optional[str]:
        """Encontra o melhor filho de um HEADER que encaixa nas hints específicas.
        
        Para match perfeito com HEADER:
        - Para cada filho direto, coleta o caminho completo até não ter mais filhos
        - Testa cada caminho do mais completo ao mais simples
        - Retorna o primeiro valor que encaixa nas hints, ou None
        
        Algoritmo:
        1. Coletar filhos diretos do HEADER
        2. Para cada filho, coletar caminho completo (recursivo)
        3. Construir candidatos do caminho (do mais completo ao mais simples)
        4. Testar cada candidato contra as hints específicas
        5. Retornar o primeiro que encaixa
        
        Args:
            header_token: Token HEADER
            graph: Grafo completo
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            Valor do melhor caminho ou None se nenhum encaixar
        """
        # Debug para telefone
        is_phone_debug = field_name == "telefone_profissional"
        
        if is_phone_debug:
            print(f"\n[DEBUG] _find_best_child_for_header para '{field_name}':")
            print(f"  HEADER: '{header_token.text}' (role: {header_token.role})")
        
        # Coletar filhos diretos do HEADER
        edges = graph.get_edges_from(header_token.id)
        direct_children = []
        for edge in edges:
            child = graph.get_node(edge.to_id)
            if child:
                direct_children.append(child)
        
        if not direct_children:
            # HEADER sem filhos → retornar None
            if is_phone_debug:
                print(f"  [RESULTADO] None (sem filhos)")
            return None
        
        # Obter hints relevantes para o campo
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        
        # Filtrar apenas hints específicas (não genéricas como text/name)
        specific_hints = [h for h in relevant_hints if h.name not in ("text", "name")]
        
        if is_phone_debug:
            print(f"  Hints específicas: {[h.name for h in specific_hints]}")
        
        # Se não há hints específicas, retornar None (não sabemos qual filho escolher)
        if not specific_hints:
            # Sem hints específicas, não podemos escolher entre filhos
            # Deixar o extractor tratar isso (retornar null)
            if is_phone_debug:
                print(f"  [RESULTADO] None (sem hints específicas)")
            return None
        
        # Ordenar filhos diretos por posição espacial
        sorted_children = sorted(
            direct_children,
            key=lambda t: (t.bbox.center_y(), t.bbox.center_x())
        )
        
        # Para cada filho direto, coletar caminho completo e testar
        for child_idx, child in enumerate(sorted_children):
            if is_phone_debug:
                print(f"\n  Processando filho [{child_idx}]: '{child.text}' (role: {child.role})")
            
            # Coletar caminho completo a partir deste filho
            path = self._collect_path_from_token(child, graph, visited=set())
            
            if not path:
                if is_phone_debug:
                    print(f"    Sem caminho (sem descendentes)")
                continue
            
            if is_phone_debug:
                print(f"    Caminho coletado ({len(path)} tokens): {[t.text for t in path[:5]]}")
            
            # Construir candidatos do caminho (do mais completo ao mais simples)
            candidates = self._build_candidate_strings_from_path(path)
            
            if is_phone_debug:
                print(f"    Candidatos gerados ({len(candidates)}):")
                for i, cand in enumerate(candidates[:5]):
                    print(f"      [{i}] '{cand}'")
            
            # Testar cada candidato contra as hints (do mais completo ao mais simples)
            for cand_idx, candidate_text in enumerate(candidates):
                for hint in specific_hints:
                    detect_result = hint.detect(candidate_text)
                    if is_phone_debug:
                        print(f"      Candidato [{cand_idx}] '{candidate_text}' vs hint '{hint.name}': {detect_result}")
                    
                    if detect_result:
                        # Candidato encaixa na hint → retornar
                        if is_phone_debug:
                            print(f"  [RESULTADO] '{candidate_text}' (hint '{hint.name}' detectou)")
                        return candidate_text
        
        # Nenhum caminho encaixou nas hints → retornar None
        if is_phone_debug:
            print(f"  [RESULTADO] None (nenhum candidato passou nas hints)")
        return None
    
    
    def _check_partial_regex_match(
        self,
        normalized_field_name: str,
        normalized_field_description: str,
        field_regex: Optional[Pattern],
        description_regex: Optional[Pattern],
        token: Token,
        graph: Graph
    ) -> Optional[MatchResult]:
        """Verifica match parcial usando regex.
        
        Match parcial: regex corresponde parcialmente ao token.
        
        Args:
            normalized_field_name: Nome do campo normalizado
            normalized_field_description: Descrição do campo normalizada
            field_regex: Regex pattern do campo
            description_regex: Regex pattern da descrição
            token: Token candidato
            graph: Grafo completo
            
        Returns:
            MatchResult se houver match parcial, None caso contrário
        """
        token_text = token.text.strip()
        normalized_token_text = self._normalize_text(token_text)
        
        # Verificar match parcial com regex
        is_partial_match = False
        match_score = 0.0
        
        # Testar match parcial com nome do campo (substring)
        if normalized_field_name and normalized_field_name in normalized_token_text:
            match_ratio = len(normalized_field_name) / len(normalized_token_text) if normalized_token_text else 0.0
            match_score = max(match_score, match_ratio * 0.8)  # Score parcial
            is_partial_match = True
        
        # Testar match parcial com descrição
        if normalized_field_description and normalized_field_description in normalized_token_text:
            match_ratio = len(normalized_field_description) / len(normalized_token_text) if normalized_token_text else 0.0
            match_score = max(match_score, match_ratio * 0.8)
            is_partial_match = True
        
        # Testar regex patterns (search em vez de fullmatch)
        if field_regex:
            match = field_regex.search(normalized_token_text)
            if match:
                match_ratio = len(match.group(0)) / len(normalized_token_text) if normalized_token_text else 0.0
                match_score = max(match_score, match_ratio * 0.8)
                is_partial_match = True
        
        if description_regex:
            match = description_regex.search(normalized_token_text)
            if match:
                match_ratio = len(match.group(0)) / len(normalized_token_text) if normalized_token_text else 0.0
                match_score = max(match_score, match_ratio * 0.8)
                is_partial_match = True
        
        if not is_partial_match or match_score < 0.3:
            return None
        
        # Match parcial encontrado - determinar valor a retornar
        extracted_value = None
        
        if token.role == "LABEL":
            # Regex com LABEL → devolve VALUE se tiver, ou string vazia (null)
            value_token = self._find_value_for_label(token, graph)
            if value_token:
                extracted_value = value_token.text.strip()
            else:
                extracted_value = ""  # String vazia = não retornar input
        elif token.role == "HEADER":
            # Regex com HEADER → devolve HEADER inteiro
            extracted_value = token.text.strip()
        elif token.role == "VALUE":
            # Regex com VALUE → devolve VALUE inteiro
            extracted_value = token.text.strip()
        else:
            extracted_value = ""  # String vazia = não retornar input
        
        label_token = None
        if token.role == "VALUE":
            label_token = self.find_label_for_value(token, graph)
        
        reason = f"Partial regex match: score {match_score:.3f}"
        if token.role == "LABEL":
            reason += f" (LABEL → VALUE)"
        elif label_token:
            reason += f" (VALUE, LABEL: '{label_token.text}')"
        
        return MatchResult(
            token=token,
            score=match_score,
            match_type=MatchType.PARTIAL,
            reason=reason,
            label_token=label_token,
            extracted_value=extracted_value
        )
    
    def _create_field_regex(self, field_name: str, field_description: str) -> Optional[Pattern]:
        """Cria regex pattern a partir do nome/descrição do campo.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            Regex pattern compilado ou None
        """
        # Normalizar e extrair palavras-chave
        normalized_field = self._normalize_text(f"{field_name} {field_description}")
        words = normalized_field.split()
        
        # Filtrar stop words
        stop_words = {'o', 'a', 'de', 'do', 'da', 'em', 'no', 'na', 'para', 'com', 'por', 'e', 'ou'}
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        if not keywords:
            return None
        
        # Criar regex que busca qualquer uma das palavras-chave
        pattern = '|'.join(re.escape(keyword) for keyword in keywords)
        return re.compile(pattern, re.IGNORECASE)
