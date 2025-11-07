"""Modelos de dados para extração baseada em grafo."""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum
from src.graph_builder.models import Token


class MatchType(str, Enum):
    """Tipos de match possíveis."""
    PERFECT = "perfect"  # Match perfeito (regex ou pattern)
    PARTIAL = "partial"  # Match parcial
    EMBEDDING = "embedding"  # Match por similaridade semântica
    HEURISTIC = "heuristic"  # Match por heurísticas
    LLM = "llm"  # Match decidido por LLM


@dataclass
class MatchResult:
    """Resultado de um match entre campo e nó do grafo.
    
    Attributes:
        token: Token que corresponde ao campo
        score: Score de similaridade/match (0.0 a 1.0)
        match_type: Tipo de match usado
        reason: Explicação do motivo do match
        hint_name: Nome da hint que detectou (se aplicável)
        label_token: Token LABEL associado (se VALUE foi encontrado)
        extracted_value: Valor extraído do token (pode ser diferente do texto do token)
    """
    token: Token
    score: float
    match_type: MatchType
    reason: str
    hint_name: Optional[str] = None
    label_token: Optional[Token] = None
    extracted_value: Optional[str] = None
    
    def __post_init__(self):
        """Valida e normaliza após inicialização."""
        # Garantir que score está entre 0 e 1
        self.score = max(0.0, min(1.0, self.score))
        
    
    def get_value(self) -> str:
        """Retorna o valor extraído (com fallback para texto do token)."""
        return self.extracted_value or self.token.text.strip()


@dataclass
class FieldMatch:
    """Resultado da extração de um campo do schema.
    
    Attributes:
        field_name: Nome do campo extraído
        value: Valor extraído (None se não encontrado)
        match_result: Resultado do match (None se não encontrado)
        strategy_used: Estratégia usada para encontrar o valor
        metadata: Metadados adicionais (nós usados, scores, etc.)
    """
    field_name: str
    value: Optional[str]
    match_result: Optional[MatchResult] = None
    strategy_used: str = "none"
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Inicializa metadata se None."""
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "field_name": self.field_name,
            "value": self.value,
            "strategy_used": self.strategy_used,
            "metadata": self.metadata,
            "match_result": {
                "token_id": self.match_result.token.id if self.match_result else None,
                "score": self.match_result.score if self.match_result else None,
                "match_type": self.match_result.match_type.value if self.match_result else None,
                "reason": self.match_result.reason if self.match_result else None,
            } if self.match_result else None
        }


@dataclass
class ExtractionMetadata:
    """Metadados da extração completa.
    
    Attributes:
        label: Label do documento
        total_fields: Número total de campos no schema
        extracted_fields: Número de campos extraídos com sucesso
        nodes_used: Lista de IDs de nós usados
        extraction_time: Tempo de execução em segundos
        strategies_breakdown: Breakdown de estratégias usadas por campo
    """
    label: str
    total_fields: int
    extracted_fields: int
    nodes_used: List[int]
    extraction_time: float
    strategies_breakdown: Dict[str, str] = None
    
    def __post_init__(self):
        """Inicializa strategies_breakdown se None."""
        if self.strategies_breakdown is None:
            self.strategies_breakdown = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "label": self.label,
            "total_fields": self.total_fields,
            "extracted_fields": self.extracted_fields,
            "success_rate": self.extracted_fields / self.total_fields if self.total_fields > 0 else 0.0,
            "nodes_used": self.nodes_used,
            "nodes_used_count": len(self.nodes_used),
            "extraction_time": self.extraction_time,
            "strategies_breakdown": self.strategies_breakdown
        }


@dataclass
class ExtractionResult:
    """Resultado completo da extração de schema.
    
    Attributes:
        label: Label do documento
        fields: Dicionário com campos extraídos {campo: valor}
        field_matches: Lista de FieldMatch com detalhes de cada extração
        metadata: Metadados da extração
    """
    label: str
    fields: Dict[str, Optional[str]]
    field_matches: List[FieldMatch]
    metadata: ExtractionMetadata
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário no formato esperado."""
        return {
            "label": self.label,
            "fields": self.fields,
            "metadata": self.metadata.to_dict()
        }
    
    def to_dict_detailed(self) -> Dict[str, Any]:
        """Converte para dicionário com detalhes completos."""
        return {
            "label": self.label,
            "fields": self.fields,
            "field_matches": [fm.to_dict() for fm in self.field_matches],
            "metadata": self.metadata.to_dict()
        }
