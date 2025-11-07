"""Hint para detectar telefones."""

import re
from typing import List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy


class PhoneHint(BaseHint):
    """Hint para detectar números de telefone."""
    
    def __init__(self):
        """Inicializa PhoneHint."""
        super().__init__(priority=1, aggregation_strategy=AggregationStrategy.NONE)
        # Regex para telefones brasileiros e internacionais
        # Aceita formatado (com parênteses, traços) ou não formatado
        self._pattern = re.compile(
            r"(?:\(?\d{2}\)?\s?)?\d{4,5}[.-]?\d{4}|"  # Brasileiro: (XX) XXXX-XXXX ou (XX) XXXXX-XXXX
            r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,3}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}|"  # Internacional
            r"(?:^\d{10,11}$)"  # Sem formatação (10 ou 11 dígitos)
        )
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "phone"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave relacionadas a telefone."""
        return [
            "telefone", "phone", "fone", "celular", "mobile", "cel",
            "whatsapp", "whats", "contato", "contact", "tel", "ddd"
        ]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é relacionado a telefone."""
        text = f"{field_name} {field_description}".lower()
        return any(keyword in text for keyword in self.keywords)
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto contém um número de telefone."""
        if not text:
            return False
        
        text_stripped = text.strip()
        
        # Remover espaços e caracteres especiais para verificação
        cleaned = re.sub(r"[^\d]", "", text_stripped)
        
        # Telefone deve ter entre 10 e 15 dígitos
        if 10 <= len(cleaned) <= 15:
            return bool(self._pattern.search(text_stripped))
        
        return False
    
    def get_regex(self) -> re.Pattern:
        """Retorna o regex pattern para telefones."""
        return self._pattern
    
    def normalize_value(self, text: str) -> str:
        """Normaliza o telefone extraído."""
        match = self._pattern.search(text.strip())
        if match:
            return match.group(0)
        return text.strip()
