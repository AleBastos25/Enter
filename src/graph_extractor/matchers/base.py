"""Interface abstrata para matchers."""

from abc import ABC, abstractmethod
from typing import List, Optional
from src.graph_builder.models import Token, Graph
from src.graph_extractor.models import MatchResult, MatchType


class BaseMatcher(ABC):
    """Interface abstrata para todos os matchers.
    
    Um matcher é responsável por encontrar nós do grafo que correspondem
    a um campo do schema de extração.
    """
    
    def __init__(self):
        """Inicializa o matcher."""
        pass
    
    @abstractmethod
    def match(
        self,
        field_name: str,
        field_description: str,
        candidates: List[Token],
        graph: Optional[Graph] = None
    ) -> List[MatchResult]:
        """Encontra nós candidatos que correspondem ao campo.
        
        Args:
            field_name: Nome do campo a ser extraído
            field_description: Descrição do campo
            candidates: Lista de nós candidatos para verificar
            graph: Grafo completo (opcional, para contexto adicional)
            
        Returns:
            Lista de MatchResult ordenada por score (maior primeiro)
        """
        pass
    
    def filter_available(self, candidates: List[Token], used_node_ids: set) -> List[Token]:
        """Filtra candidatos removendo nós já usados.
        
        Args:
            candidates: Lista de candidatos
            used_node_ids: Set de IDs de nós já usados
            
        Returns:
            Lista de candidatos disponíveis
        """
        return [token for token in candidates if token.id not in used_node_ids]
    
    def get_token_value(self, token: Token, graph: Optional[Graph] = None) -> str:
        """Obtém o valor de um token.
        
        Se o token é um LABEL, tenta encontrar o VALUE associado.
        Se é um VALUE, retorna o texto do token.
        Se é um HEADER isolado, retorna o texto do HEADER.
        
        Args:
            token: Token para obter valor
            graph: Grafo completo (opcional, para encontrar VALUE associado)
            
        Returns:
            Valor do token
        """
        # Se é VALUE, retornar texto
        if token.role == "VALUE":
            return token.text.strip()
        
        # Se é LABEL, tentar encontrar VALUE associado
        if token.role == "LABEL" and graph:
            # Procurar VALUE conectado ao LABEL
            edges = graph.get_edges_from(token.id)
            for edge in edges:
                if edge.relation in ("east", "south"):  # VALUE geralmente está à direita ou abaixo
                    value_token = graph.get_node(edge.to_id)
                    if value_token and value_token.role == "VALUE":
                        return value_token.text.strip()
        
        # Se é HEADER ou não tem VALUE associado, retornar texto do token
        return token.text.strip()
    
    def find_label_for_value(self, value_token: Token, graph: Optional[Graph] = None) -> Optional[Token]:
        """Encontra o LABEL associado a um VALUE.
        
        Args:
            value_token: Token VALUE
            graph: Grafo completo
            
        Returns:
            Token LABEL associado ou None
        """
        if not graph or value_token.role != "VALUE":
            return None
        
        # Procurar edges que chegam no VALUE
        edges = graph.get_edges_to(value_token.id)
        for edge in edges:
            if edge.relation in ("east", "south"):  # LABEL geralmente está à esquerda ou acima
                label_token = graph.get_node(edge.from_id)
                if label_token and label_token.role == "LABEL":
                    return label_token
        
        return None
    
    def combine_label_value(self, label_token: Token, value_token: Token) -> str:
        """Combina texto de LABEL e VALUE para matching semântico.
        
        Args:
            label_token: Token LABEL
            value_token: Token VALUE
            
        Returns:
            Texto combinado
        """
        label_text = label_token.text.strip()
        value_text = value_token.text.strip()
        
        # Remover ":" do final do label se houver
        if label_text.endswith(":"):
            label_text = label_text[:-1].strip()
        
        return f"{label_text} {value_text}"
    
    def sort_by_score(self, matches: List[MatchResult]) -> List[MatchResult]:
        """Ordena matches por score (maior primeiro).
        
        Args:
            matches: Lista de matches
            
        Returns:
            Lista ordenada por score
        """
        return sorted(matches, key=lambda m: m.score, reverse=True)
