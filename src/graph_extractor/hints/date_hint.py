"""Hint para detectar e extrair datas."""

import re
from typing import List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy


class DateHint(BaseHint):
    """Hint para detectar datas em vários formatos."""
    
    def __init__(self):
        """Inicializa DateHint."""
        super().__init__(priority=1, aggregation_strategy=AggregationStrategy.NONE)
        # Regex para datas em vários formatos
        self._pattern = re.compile(
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"  # DD/MM/YYYY, DD-MM-YY, etc.
            r"\d{4}-\d{2}-\d{2}|"  # YYYY-MM-DD (ISO)
            r"\d{1,2}\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|january|february|march|april|may|june|july|august|september|october|november|december)[a-z]*\s+\d{2,4}"  # DD MMM YYYY
        )
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "date"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave relacionadas a datas."""
        return [
            "data", "date", "vencimento", "venc", "expira", "expiration",
            "emissao", "emissão", "emission", "inicio", "início", "start",
            "fim", "end", "final", "termino", "término", "termination",
            "periodo", "período", "period", "prazo", "deadline",
            "aniversario", "aniversário", "birthday", "nascimento"
        ]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é relacionado a data."""
        text = f"{field_name} {field_description}".lower()
        return any(keyword in text for keyword in self.keywords)
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto contém uma data."""
        return bool(self._pattern.search(text.strip()))
    
    def get_regex(self) -> re.Pattern:
        """Retorna o regex pattern para datas."""
        return self._pattern
    
    def normalize_value(self, text: str) -> str:
        """Normaliza o valor da data extraído."""
        match = self._pattern.search(text.strip())
        if match:
            return match.group(0)
        return text.strip()
