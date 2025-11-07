"""Tiebreaker baseado em heurísticas."""

from typing import List
from src.graph_builder.models import Graph, Token
from src.graph_extractor.models import MatchResult
from src.graph_extractor.tiebreaker.base import BaseTieBreaker


class HeuristicTieBreaker(BaseTieBreaker):
    """Tiebreaker que usa heurísticas para desempatar entre candidatos.
    
    Heurísticas aplicadas (em ordem de prioridade):
    1. Tipo de token (VALUE > HEADER > LABEL)
    2. HEADER isolado vs HEADER com filhos correlacionados
    3. Ordem no documento (top-down, left-right) - preferir primeiro
    4. Tamanho do texto (preferir valores mais específicos)
    5. Distância do LABEL (se VALUE tem LABEL próximo, melhor)
    """
    
    def __init__(self):
        """Inicializa HeuristicTieBreaker."""
        super().__init__()
    
    def break_tie(
        self,
        candidates: List[MatchResult],
        graph: Graph,
        field_description: str
    ) -> MatchResult:
        """Desempata entre candidatos usando heurísticas.
        
        Args:
            candidates: Lista de MatchResult candidatos
            graph: Grafo completo
            field_description: Descrição do campo
            
        Returns:
            MatchResult escolhido como vencedor
        """
        if not candidates:
            raise ValueError("Lista de candidatos vazia")
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Ordenar candidatos por heurísticas
        scored_candidates = []
        for candidate in candidates:
            score = self._calculate_heuristic_score(candidate, graph, field_description)
            scored_candidates.append((score, candidate))
        
        # Ordenar por score heurístico (maior primeiro)
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Retornar o melhor
        return scored_candidates[0][1]
    
    def _calculate_heuristic_score(
        self,
        candidate: MatchResult,
        graph: Graph,
        field_description: str
    ) -> float:
        """Calcula score heurístico para um candidato.
        
        Args:
            candidate: Candidato a avaliar
            graph: Grafo completo
            field_description: Descrição do campo
            
        Returns:
            Score heurístico (maior = melhor)
        """
        score = 0.0
        token = candidate.token
        
        # Heurística 1: Tipo de token (peso: 0.4)
        role_score = self._get_role_score(token.role)
        score += role_score * 0.4
        
        # Heurística 2: HEADER isolado vs com filhos (peso: 0.2)
        if token.role == "HEADER":
            header_score = self._get_header_isolation_score(token, graph)
            score += header_score * 0.2
        
        # Heurística 3: Ordem no documento (peso: 0.2)
        # Preferir tokens que aparecem primeiro (top-down, left-right)
        order_score = self._get_document_order_score(token)
        score += order_score * 0.2
        
        # Heurística 4: Tamanho do texto (peso: 0.1)
        # Preferir valores mais específicos (nem muito curtos, nem muito longos)
        length_score = self._get_text_length_score(token)
        score += length_score * 0.1
        
        # Heurística 5: Relação LABEL-VALUE (peso: 0.1)
        # Se VALUE tem LABEL associado, melhor
        label_score = self._get_label_relation_score(candidate, graph)
        score += label_score * 0.1
        
        return score
    
    def _get_role_score(self, role: str) -> float:
        """Retorna score baseado no role do token.
        
        VALUE > HEADER > LABEL > None
        
        Args:
            role: Role do token
            
        Returns:
            Score entre 0.0 e 1.0
        """
        role_scores = {
            "VALUE": 1.0,
            "HEADER": 0.7,
            "LABEL": 0.3,
        }
        return role_scores.get(role, 0.0)
    
    def _get_header_isolation_score(self, token: Token, graph: Graph) -> float:
        """Calcula score baseado se HEADER é isolado ou tem filhos correlacionados.
        
        HEADER isolado = melhor (retorna ele mesmo)
        HEADER com filhos correlacionados = pior (prefere VALUE filho)
        
        Args:
            token: Token HEADER
            graph: Grafo completo
            
        Returns:
            Score entre 0.0 e 1.0
        """
        # Verificar edges que saem do HEADER
        edges_from = graph.get_edges_from(token.id)
        
        # Se não tem edges, é isolado (melhor)
        if not edges_from:
            return 1.0
        
        # Contar VALUEs conectados
        value_count = 0
        for edge in edges_from:
            if edge.relation in ("south", "east"):  # Abaixo ou à direita
                connected_token = graph.get_node(edge.to_id)
                if connected_token and connected_token.role == "VALUE":
                    value_count += 1
        
        # Se tem VALUEs filhos, preferir não usar o HEADER diretamente
        if value_count > 0:
            return 0.3  # Baixo score, preferir VALUE filho
        
        # HEADER isolado sem VALUEs
        return 1.0
    
    def _get_document_order_score(self, token: Token) -> float:
        """Calcula score baseado na ordem do token no documento.
        
        Tokens que aparecem primeiro (top-down, left-right) têm score maior.
        
        Args:
            token: Token a avaliar
            
        Returns:
            Score entre 0.0 e 1.0 (normalizado)
        """
        # Usar posição Y (top-down) e X (left-right)
        # Valores menores = mais acima/à esquerda = melhor
        
        # Normalizar: assumir que Y e X estão entre 0 e 1
        # Score = 1 - ((Y + X) / 2)
        y_pos = token.bbox.center_y()
        x_pos = token.bbox.center_x()
        
        # Score baseado em posição (quanto menor Y e X, maior o score)
        position_score = 1.0 - ((y_pos + x_pos) / 2.0)
        
        # Garantir que está entre 0 e 1
        return max(0.0, min(1.0, position_score))
    
    def _get_text_length_score(self, token: Token) -> float:
        """Calcula score baseado no tamanho do texto.
        
        Prefere valores com tamanho médio (nem muito curtos, nem muito longos).
        
        Args:
            token: Token a avaliar
            
        Returns:
            Score entre 0.0 e 1.0
        """
        text_length = len(token.text.strip())
        
        # Valores ideais: entre 3 e 50 caracteres
        if 3 <= text_length <= 50:
            return 1.0
        elif text_length < 3:
            # Muito curto (pode ser abreviação ou código)
            return 0.7
        elif text_length <= 100:
            # Médio-longo (pode ser endereço ou descrição)
            return 0.8
        else:
            # Muito longo (provavelmente não é o valor específico)
            return 0.5
    
    def _get_label_relation_score(self, candidate: MatchResult, graph: Graph) -> float:
        """Calcula score baseado na relação LABEL-VALUE.
        
        Se VALUE tem LABEL associado e próximo, melhor.
        
        Args:
            candidate: Candidato a avaliar
            graph: Grafo completo
            
        Returns:
            Score entre 0.0 e 1.0
        """
        token = candidate.token
        
        # Se não é VALUE, score neutro
        if token.role != "VALUE":
            return 0.5
        
        # Se já tem label_token no candidate, score alto
        if candidate.label_token:
            # Calcular distância entre LABEL e VALUE
            label = candidate.label_token
            distance = self._calculate_distance(label.bbox, token.bbox)
            
            # Distância menor = score maior
            # Normalizar: distância < 0.1 = score 1.0, distância > 0.5 = score 0.5
            if distance < 0.1:
                return 1.0
            elif distance < 0.3:
                return 0.9
            elif distance < 0.5:
                return 0.7
            else:
                return 0.5
        
        # Tentar encontrar LABEL associado
        edges = graph.get_edges_to(token.id)
        for edge in edges:
            if edge.relation in ("west", "north"):  # LABEL à esquerda ou acima
                label_token = graph.get_node(edge.from_id)
                if label_token and label_token.role == "LABEL":
                    # LABEL encontrado
                    distance = self._calculate_distance(label_token.bbox, token.bbox)
                    if distance < 0.2:
                        return 0.8
                    else:
                        return 0.6
        
        # Sem LABEL associado
        return 0.4
    
    def _calculate_distance(self, bbox1, bbox2) -> float:
        """Calcula distância euclidiana entre dois bboxes.
        
        Args:
            bbox1: Primeiro bbox
            bbox2: Segundo bbox
            
        Returns:
            Distância normalizada (0-1)
        """
        center_x1 = bbox1.center_x()
        center_y1 = bbox1.center_y()
        center_x2 = bbox2.center_x()
        center_y2 = bbox2.center_y()
        
        # Distância euclidiana
        distance = ((center_x2 - center_x1) ** 2 + (center_y2 - center_y1) ** 2) ** 0.5
        
        # Normalizar: distância máxima possível é diagonal (sqrt(2))
        normalized = distance / (2 ** 0.5)
        
        return min(1.0, normalized)
