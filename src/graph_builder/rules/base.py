"""Classe base para regras de classificação."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass
from src.graph_builder.models import Token, Graph
from src.graph_builder.adjacency import AdjacencyMatrix


@dataclass
class RuleContext:
    """Contexto passado entre regras."""
    tokens: List[Token]
    graph: Graph
    roles: Dict[int, str]
    adjacency: AdjacencyMatrix
    label_candidates: List[int]
    label_to_value: Dict[int, int]
    value_to_label: Dict[int, int]
    label: Optional[str] = None
    role_sources: Optional[Dict[int, str]] = None  # Rastreamento: qual regra definiu cada role
    
    def __post_init__(self):
        """Inicializa campos opcionais."""
        if self.role_sources is None:
            object.__setattr__(self, 'role_sources', {})
    
    def get_node_by_id(self, token_id: int) -> Optional[Token]:
        """Obtém um nó por ID."""
        return self.graph.get_node(token_id)
    
    def set_role(self, token_id: int, role: str, source_rule: Optional[str] = None) -> None:
        """Define o role de um token e registra qual regra definiu.
        
        Args:
            token_id: ID do token.
            role: Role a ser definido.
            source_rule: Nome da regra que está definindo este role (opcional).
        """
        self.roles[token_id] = role
        if source_rule:
            self.role_sources[token_id] = source_rule
    
    def get_role(self, token_id: int) -> Optional[str]:
        """Obtém o role de um token."""
        return self.roles.get(token_id)
    
    def get_role_source(self, token_id: int) -> Optional[str]:
        """Obtém qual regra definiu o role de um token."""
        return self.role_sources.get(token_id)


class BaseRule(ABC):
    """Classe abstrata base para todas as regras de classificação."""
    
    def __init__(
        self,
        name: str,
        priority: int,
        dependencies: Optional[List[str]] = None
    ):
        """Inicializa a regra.
        
        Args:
            name: Nome da regra (usado para dependências).
            priority: Prioridade da regra (menor = executa primeiro).
            dependencies: Lista de nomes de regras que devem executar antes.
        """
        self.name = name
        self.priority = priority
        self.dependencies = dependencies or []
    
    @abstractmethod
    def apply(self, context: RuleContext) -> None:
        """Aplica a regra ao contexto.
        
        Args:
            context: Contexto com tokens, grafo, roles, etc.
        """
        pass
    
    def can_apply(self, executed_rules: List[str]) -> bool:
        """Verifica se a regra pode ser aplicada (dependências satisfeitas).
        
        Args:
            executed_rules: Lista de nomes de regras já executadas.
        
        Returns:
            True se todas as dependências foram executadas.
        """
        return all(dep in executed_rules for dep in self.dependencies)
    
    def get_dependencies(self) -> List[str]:
        """Retorna lista de dependências."""
        return self.dependencies.copy()
    
    def __repr__(self) -> str:
        """Representação da regra."""
        return f"{self.__class__.__name__}(name={self.name}, priority={self.priority})"

