"""Matcher baseado em hints/pattern matching."""

from typing import List, Optional
from src.graph_builder.models import Token, Graph
from src.graph_extractor.models import MatchResult, MatchType
from src.graph_extractor.matchers.base import BaseMatcher
from src.graph_extractor.hints.base import hint_registry


class PatternMatcher(BaseMatcher):
    """Matcher que usa hints para identificar padrões e encontrar candidatos.
    
    Este matcher aplica hints relevantes ao campo para encontrar nós
    que correspondem aos padrões esperados (data, dinheiro, endereço, etc.).
    """
    
    def __init__(self):
        """Inicializa PatternMatcher."""
        super().__init__()
    
    def match(
        self,
        field_name: str,
        field_description: str,
        candidates: List[Token],
        graph: Optional[Graph] = None
    ) -> List[MatchResult]:
        """Encontra candidatos usando hints.
        
        Separa hints específicas de fallback (TextHint). Se uma hint específica
        rejeita um valor, o fallback não é usado.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            candidates: Lista de nós candidatos
            graph: Grafo completo (para encontrar VALUEs associados)
            
        Returns:
            Lista de MatchResult ordenada por score
        """
        if not candidates:
            return []
        
        # Encontrar hints relevantes para este campo
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        
        if not relevant_hints:
            # Nenhuma hint relevante encontrada
            return []
        
        # Separar hints específicas de fallback baseado na prioridade
        # Hints com menor prioridade (mais específicas) têm preferência
        # Se uma hint específica (prioridade menor) rejeita, hints de maior prioridade (fallback) não devem ser usadas
        if len(relevant_hints) > 1:
            # Ordenar por prioridade (menor = mais específica)
            sorted_hints = sorted(relevant_hints, key=lambda h: h.priority)
            # A maior prioridade na lista é a do fallback
            max_priority = max(h.priority for h in relevant_hints)
            # Hints específicas: prioridade menor que a máxima
            specific_hints = [h for h in sorted_hints if h.priority < max_priority]
            # Fallback: hints com prioridade máxima (geralmente TextHint)
            fallback_hints = [h for h in sorted_hints if h.priority == max_priority]
        else:
            # Se há apenas uma hint, tratar como específica
            specific_hints = relevant_hints
            fallback_hints = []
        
        matches = []
        
        # Para cada candidato, verificar se alguma hint detecta o padrão
        for token in candidates:
            # Obter valor do token (VALUE se for VALUE, ou texto se for HEADER/LABEL)
            token_value = self.get_token_value(token, graph)
            
            # Primeiro, testar hints específicas (prioridade menor = mais específica)
            specific_rejected = False
            match_result = None
            
            if specific_hints:
                # Testar todas as hints específicas
                for hint in specific_hints:
                    # Verificar se a hint detecta (pode aceitar ou rejeitar)
                    if hint.detect(token_value):
                        # Hint específica ACEITOU - criar match
                        match_result = self._check_hint_match(
                            hint, token, token_value, field_name, field_description, graph
                        )
                        if match_result:
                            matches.append(match_result)
                            break  # Usar esta hint específica
                    else:
                        # Hint específica REJEITOU explicitamente
                        # Se é uma hint específica e rejeitou, não usar fallback
                        specific_rejected = True
                        # Continuar testando outras específicas (pode haver múltiplas)
                
                # Se alguma hint específica rejeitou E nenhuma aceitou, não usar fallback
                if specific_rejected and not match_result:
                    # Hint específica rejeitou, não usar fallback
                    continue
            
            # Se não há hints específicas OU nenhuma específica rejeitou, usar fallback
            if not match_result and not specific_rejected:
                # Usar fallback (hints com maior prioridade)
                for hint in fallback_hints:
                    match_result = self._check_hint_match(
                        hint, token, token_value, field_name, field_description, graph
                    )
                    if match_result:
                        matches.append(match_result)
                        break  # Usar apenas a primeira hint fallback que faz match
        
        # Ordenar por score
        return self.sort_by_score(matches)
    
    def _check_hint_match(
        self,
        hint,
        token: Token,
        token_value: str,
        field_name: str,
        field_description: str,
        graph: Optional[Graph] = None
    ) -> Optional[MatchResult]:
        """Verifica se uma hint faz match com o token.
        
        Args:
            hint: Hint a verificar
            token: Token candidato
            token_value: Valor do token (já processado)
            field_name: Nome do campo
            field_description: Descrição do campo
            graph: Grafo completo
            
        Returns:
            MatchResult se houver match, None caso contrário
        """
        # Verificar se a hint detecta o padrão no valor do token
        if not hint.detect(token_value):
            return None
        
        # Extrair padrão normalizado
        extracted_pattern = hint.extract_pattern(token_value)
        if not extracted_pattern:
            return None
        
        # Determinar score baseado no tipo de match
        score = self._calculate_match_score(hint, token, token_value, extracted_pattern)
        
        # Determinar tipo de match
        match_type = MatchType.PERFECT if score >= 0.9 else MatchType.PARTIAL
        
        # Encontrar LABEL associado se token for VALUE
        label_token = None
        if token.role == "VALUE" and graph:
            label_token = self.find_label_for_value(token, graph)
        
        # Criar razão do match
        reason = f"Pattern match: {hint.name} detected '{extracted_pattern}' in token text"
        if token.role == "VALUE" and label_token:
            reason += f" (LABEL: '{label_token.text}')"
        
        # Normalizar valor extraído usando a hint
        normalized_value = hint.normalize_value(extracted_pattern)
        
        return MatchResult(
            token=token,
            score=score,
            match_type=match_type,
            reason=reason,
            hint_name=hint.name,
            label_token=label_token,
            extracted_value=normalized_value
        )
    
    def _calculate_match_score(
        self,
        hint,
        token: Token,
        token_value: str,
        extracted_pattern: str
    ) -> float:
        """Calcula score de match baseado em vários fatores.
        
        Args:
            hint: Hint que detectou o padrão
            token: Token candidato
            token_value: Valor do token
            extracted_pattern: Padrão extraído
            
        Returns:
            Score entre 0.0 e 1.0
        """
        score = 0.5  # Base score
        
        # Fator 1: Tipo de token (VALUE > HEADER > LABEL)
        if token.role == "VALUE":
            score += 0.3
        elif token.role == "HEADER":
            score += 0.2
        elif token.role == "LABEL":
            score += 0.1
        
        
        # Fator 2: Prioridade da hint (hints mais específicas têm maior prioridade)
        # Prioridade menor = mais específica = maior score
        priority_bonus = max(0.0, (11 - hint.priority) / 10.0) * 0.1
        score += priority_bonus
        
        # Garantir que score está entre 0.0 e 1.0
        return min(1.0, max(0.0, score))
    
    def match_with_label_value(
        self,
        field_name: str,
        field_description: str,
        candidates: List[Token],
        graph: Optional[Graph] = None
    ) -> List[MatchResult]:
        """Versão alternativa que também verifica LABEL+VALUE combinado.
        
        Útil quando queremos verificar se o LABEL também corresponde ao campo.
        Usa a mesma lógica de separação entre hints específicas e fallback.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            candidates: Lista de nós candidatos
            graph: Grafo completo
            
        Returns:
            Lista de MatchResult ordenada por score
        """
        if not candidates or not graph:
            return self.match(field_name, field_description, candidates, graph)
        
        # Encontrar hints relevantes
        relevant_hints = hint_registry.find_relevant(field_name, field_description)
        if not relevant_hints:
            return []
        
        # Separar hints específicas de fallback baseado na prioridade (mesma lógica do match)
        if len(relevant_hints) > 1:
            sorted_hints = sorted(relevant_hints, key=lambda h: h.priority)
            max_priority = max(h.priority for h in relevant_hints)
            specific_hints = [h for h in sorted_hints if h.priority < max_priority]
            fallback_hints = [h for h in sorted_hints if h.priority == max_priority]
        else:
            specific_hints = relevant_hints
            fallback_hints = []
        
        matches = []
        
        for token in candidates:
            token_value = self.get_token_value(token, graph)
            
            # Primeiro, testar hints específicas no valor do token
            specific_rejected = False
            match_result = None
            
            if specific_hints:
                for hint in specific_hints:
                    if hint.detect(token_value):
                        match_result = self._check_hint_match(
                            hint, token, token_value, field_name, field_description, graph
                        )
                        if match_result:
                            matches.append(match_result)
                            break
                    else:
                        specific_rejected = True
            
            # Se não há hints específicas OU nenhuma específica rejeitou, usar fallback
            if not match_result and not specific_rejected:
                for hint in fallback_hints:
                    if hint.detect(token_value):
                        match_result = self._check_hint_match(
                            hint, token, token_value, field_name, field_description, graph
                        )
                        if match_result:
                            matches.append(match_result)
                            break
            
            # Se token é VALUE, também verificar LABEL+VALUE combinado
            if token.role == "VALUE" and not match_result:
                label_token = self.find_label_for_value(token, graph)
                if label_token:
                    combined_text = self.combine_label_value(label_token, token)
                    
                    # Testar hints específicas no texto combinado
                    combined_specific_rejected = False
                    
                    if specific_hints:
                        for hint in specific_hints:
                            if hint.detect(combined_text):
                                match_result = self._check_hint_match(
                                    hint, token, token_value, field_name, field_description, graph
                                )
                                if match_result:
                                    match_result.score = min(1.0, match_result.score + 0.1)
                                    match_result.reason += f" (LABEL '{label_token.text}' also matches)"
                                    matches.append(match_result)
                                    break
                            else:
                                combined_specific_rejected = True
                    
                    # Se não há hints específicas OU nenhuma específica rejeitou, usar fallback
                    if not match_result and not combined_specific_rejected:
                        for hint in fallback_hints:
                            if hint.detect(combined_text):
                                match_result = self._check_hint_match(
                                    hint, token, token_value, field_name, field_description, graph
                                )
                                if match_result:
                                    match_result.score = min(1.0, match_result.score + 0.1)
                                    match_result.reason += f" (LABEL '{label_token.text}' also matches)"
                                    matches.append(match_result)
                                    break
        
        return self.sort_by_score(matches)
