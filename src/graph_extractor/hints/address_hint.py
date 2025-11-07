"""Hint para detectar e agregar endereços."""

import re
from typing import List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy


class AddressHint(BaseHint):
    """Hint para detectar endereços e agregar múltiplos VALUEs."""
    
    def __init__(self):
        """Inicializa AddressHint."""
        super().__init__(priority=1, aggregation_strategy=AggregationStrategy.CONCATENATE)
        # Regex para componentes de endereço
        # Endereços geralmente contêm: rua, número, bairro, cidade, estado, CEP
        self._pattern = re.compile(
            r"(?:rua|av|avenida|rod|rodovia|estrada|travessa|praça|alameda|via)[\s.]*[^\s,]+|"  # Rua/Avenida
            r"\d{5}[-.]?\d{3}|"  # CEP
            r"(?:cep|zip|postal)[\s:]*\d{5}[-.]?\d{3}",  # CEP com prefixo
            re.IGNORECASE
        )
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "address"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave relacionadas a endereço."""
        return [
            "endereco", "endereço", "address", "rua", "street", "avenida", "avenue",
            "bairro", "neighborhood", "cidade", "city", "estado", "state",
            "uf", "cep", "zip", "postal", "code", "local", "location",
            "logradouro", "numero", "número", "number", "complemento", "complement"
        ]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é relacionado a endereço."""
        text = f"{field_name} {field_description}".lower()
        return any(keyword in text for keyword in self.keywords)
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto contém componentes de endereço."""
        # Endereços geralmente têm múltiplas palavras e podem conter números
        text_lower = text.strip().lower()
        text_original = text.strip()
        
        # Verificar se contém componentes típicos de endereço (palavras-chave de endereço)
        address_keywords = [
            "rua", "av", "avenida", "rod", "rodovia", "estrada", "travessa", 
            "praça", "alameda", "via", "boulevard", "blvd", "avenue", "street"
        ]
        
        # Verificar se alguma palavra do texto começa com ou contém palavra-chave de endereço
        words = text_lower.split()
        for word in words:
            # Verificar se a palavra é uma palavra-chave de endereço
            if word in address_keywords:
                return True
            # Verificar se a palavra começa com palavra-chave de endereço (ex: "avenida" em "avenidapaulistano")
            for keyword in address_keywords:
                if word.startswith(keyword) and len(word) > len(keyword):
                    return True
        
        # Verificar padrões de CEP
        if re.search(r"\b\d{5}[-.]?\d{3}\b", text_original):
            return True
        
        # Verificar palavras-chave relacionadas a CEP
        if re.search(r"\b(cep|zip|postal)\b", text_lower):
            return True
        
        # Endereços geralmente têm pelo menos 2 palavras
        words = text_original.split()
        if len(words) >= 2:
            # Verificar se tem mix de palavras e números (típico de endereços)
            has_numbers = any(re.search(r'\d', word) for word in words)
            has_letters = any(re.search(r'[a-zA-ZÀ-ÿ]', word) for word in words)
            if has_numbers and has_letters:
                return True
            
            # Se tem 3+ palavras e não parece ser um nome (começa com palavra-chave de endereço)
            if len(words) >= 3:
                first_word_lower = words[0].lower()
                if any(first_word_lower.startswith(kw) for kw in address_keywords):
                    return True
        
        return False
    
    def get_regex(self) -> re.Pattern:
        """Retorna o regex pattern para endereços."""
        return self._pattern
    
    def normalize_value(self, text: str) -> str:
        """Normaliza o endereço extraído."""
        # Para endereços, manter o texto completo
        return text.strip()
    
    def aggregate_values(self, values: List[str]) -> str:
        """Agrega múltiplos valores de endereço.
        
        Endereços são concatenados com vírgula e espaço.
        """
        if not values:
            return ""
        
        # Filtrar valores vazios e normalizar
        cleaned_values = [v.strip() for v in values if v.strip()]
        
        # Concatenar com vírgula e espaço
        return ", ".join(cleaned_values)
