"""Classe abstrata base para hints."""

from abc import ABC, abstractmethod
from typing import Optional, List, Pattern
import re
from enum import Enum


class AggregationStrategy(str, Enum):
    """Estratégias de agregação para hints."""
    NONE = "none"  # Não agrega (valor único)
    CONCATENATE = "concatenate"  # Concatena múltiplos valores (ex: endereço)
    SUM = "sum"  # Soma valores (ex: valores monetários)
    LIST = "list"  # Lista de valores


class BaseHint(ABC):
    """Classe abstrata base para todas as hints (dicas de padrões).
    
    Uma hint identifica padrões específicos em campos do schema e ajuda
    a encontrar nós correspondentes no grafo.
    """
    
    def __init__(self, priority: int = 5, aggregation_strategy: AggregationStrategy = AggregationStrategy.NONE):
        """Inicializa a hint.
        
        Args:
            priority: Prioridade da hint (menor = maior prioridade, default: 5)
            aggregation_strategy: Estratégia de agregação quando múltiplos valores são encontrados
        """
        self.priority = priority
        self.aggregation_strategy = aggregation_strategy
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nome único da hint.
        
        Returns:
            Nome da hint (ex: "date", "money", "address")
        """
        pass
    
    @property
    @abstractmethod
    def keywords(self) -> List[str]:
        """Palavras-chave que indicam que esta hint é relevante.
        
        Returns:
            Lista de palavras-chave (ex: ["data", "date", "vencimento"])
        """
        pass
    
    @abstractmethod
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se esta hint é relevante para um campo.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            True se a hint é relevante para este campo
        """
        pass
    
    @abstractmethod
    def detect(self, text: str) -> bool:
        """Detecta se um texto corresponde ao padrão desta hint.
        
        Args:
            text: Texto a verificar
            
        Returns:
            True se o texto corresponde ao padrão
        """
        pass
    
    @abstractmethod
    def get_regex(self) -> Pattern:
        """Retorna o regex pattern para esta hint.
        
        Returns:
            Regex pattern compilado
        """
        pass
    
    def extract_pattern(self, text: str) -> Optional[str]:
        """Extrai o padrão do texto (normalizado).
        
        Args:
            text: Texto de onde extrair o padrão
            
        Returns:
            Padrão extraído ou None se não encontrado
        """
        match = self.get_regex().search(text)
        if match:
            return match.group(0)
        return None
    
    def normalize_value(self, text: str) -> str:
        """Normaliza um valor extraído.
        
        Args:
            text: Texto a normalizar
            
        Returns:
            Texto normalizado
        """
        return text.strip()
    
    def should_aggregate(self) -> bool:
        """Verifica se esta hint requer agregação de múltiplos valores.
        
        Returns:
            True se requer agregação
        """
        return self.aggregation_strategy != AggregationStrategy.NONE
    
    def aggregate_values(self, values: List[str]) -> str:
        """Agrega múltiplos valores em um único valor.
        
        Args:
            values: Lista de valores a agregar
            
        Returns:
            Valor agregado
        """
        if not values:
            return ""
        
        if self.aggregation_strategy == AggregationStrategy.CONCATENATE:
            # Concatenar com espaço
            return " ".join(v.strip() for v in values if v.strip())
        elif self.aggregation_strategy == AggregationStrategy.LIST:
            # Lista separada por vírgula
            return ", ".join(v.strip() for v in values if v.strip())
        elif self.aggregation_strategy == AggregationStrategy.SUM:
            # Tentar somar valores numéricos
            try:
                total = sum(float(v.replace(",", ".").replace("R$", "").strip()) for v in values)
                return str(total)
            except (ValueError, AttributeError):
                # Se não conseguir somar, concatenar
                return " + ".join(v.strip() for v in values if v.strip())
        else:
            # NONE ou desconhecido: retornar primeiro valor
            return values[0] if values else ""
    
    def __repr__(self) -> str:
        """Representação da hint."""
        return f"{self.__class__.__name__}(priority={self.priority}, name={self.name})"


class HintRegistry:
    """Registry global de hints disponíveis."""
    
    _instance = None
    _hints: List[BaseHint] = []
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, hint: BaseHint) -> None:
        """Registra uma hint.
        
        Args:
            hint: Hint a registrar
        """
        # Verificar se já existe
        for existing in self._hints:
            if existing.name == hint.name:
                # Atualizar hint existente
                self._hints.remove(existing)
                break
        
        self._hints.append(hint)
        # Ordenar por prioridade (menor = maior prioridade)
        self._hints.sort(key=lambda h: h.priority)
    
    def get_all(self) -> List[BaseHint]:
        """Retorna todas as hints registradas.
        
        Returns:
            Lista de hints ordenadas por prioridade
        """
        return self._hints.copy()
    
    def get_by_name(self, name: str) -> Optional[BaseHint]:
        """Retorna uma hint por nome.
        
        Args:
            name: Nome da hint
            
        Returns:
            Hint encontrada ou None
        """
        for hint in self._hints:
            if hint.name == name:
                return hint
        return None
    
    def find_relevant(self, field_name: str, field_description: str) -> List[BaseHint]:
        """Encontra hints relevantes para um campo.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            Lista de hints relevantes ordenadas por prioridade
        """
        relevant = []
        field_text = f"{field_name} {field_description}".lower()
        
        for hint in self._hints:
            if hint.matches_field(field_name, field_description):
                relevant.append(hint)
        
        return relevant
    
    def reset(self) -> None:
        """Reseta o registry (útil para testes)."""
        self._hints.clear()


# Registry global
hint_registry = HintRegistry()
