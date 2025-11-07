"""Interface abstrata para tiebreakers."""

from abc import ABC, abstractmethod
from typing import List
from src.graph_builder.models import Graph
from src.graph_extractor.models import MatchResult


class BaseTieBreaker(ABC):
    """Interface abstrata para tiebreakers.
    
    Um tiebreaker é usado para desempatar entre múltiplos candidatos
    quando os scores são muito próximos.
    """
    
    def __init__(self):
        """Inicializa o tiebreaker."""
        pass
    
    @abstractmethod
    def break_tie(
        self,
        candidates: List[MatchResult],
        graph: Graph,
        field_description: str
    ) -> MatchResult:
        """Desempata entre candidatos.
        
        Args:
            candidates: Lista de MatchResult candidatos (já ordenados por score)
            graph: Grafo completo (para contexto adicional)
            field_description: Descrição do campo (para contexto)
            
        Returns:
            MatchResult escolhido como vencedor
        """
        pass
    
    def should_break_tie(self, candidates: List[MatchResult], threshold: float = 0.05) -> bool:
        """Verifica se é necessário fazer desempate.
        
        Args:
            candidates: Lista de candidatos
            threshold: Diferença mínima de score para considerar empate (default: 0.05)
            
        Returns:
            True se há empate (diferença de score < threshold)
        """
        if len(candidates) < 2:
            return False
        
        # Verificar se os top candidatos têm scores muito próximos
        top_score = candidates[0].score
        for candidate in candidates[1:]:
            if top_score - candidate.score < threshold:
                return True
        
        return False
