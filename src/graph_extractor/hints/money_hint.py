"""Hint para detectar valores monetários."""

import re
from typing import List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy


class MoneyHint(BaseHint):
    """Hint para detectar valores monetários."""
    
    def __init__(self):
        """Inicializa MoneyHint."""
        super().__init__(priority=1, aggregation_strategy=AggregationStrategy.SUM)
        # Regex para valores monetários
        self._pattern = re.compile(
            r"(?:R\s*\$|US\s*\$|\$|€|£|BRL|USD|EUR|GBP)\s*"  # Símbolos monetários
            r"(?:\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+[.,]\d{2}|\d+)",  # Números
            re.IGNORECASE
        )
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "money"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave relacionadas a valores monetários."""
        return [
            "valor", "value", "preco", "preço", "price", "custo", "cost",
            "total", "subtotal", "desconto", "discount", "taxa", "fee",
            "pagamento", "payment", "pago", "paid", "parcela", "installment",
            "saldo", "balance", "montante", "amount", "dinheiro", "money",
            "receita", "revenue", "despesa", "expense", "lucro", "profit",
            "prejuizo", "prejuízo", "loss", "cifra", "cifrão"
        ]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é relacionado a valor monetário."""
        text = f"{field_name} {field_description}".lower()
        return any(keyword in text for keyword in self.keywords)
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto contém um valor monetário."""
        return bool(self._pattern.search(text.strip()))
    
    def get_regex(self) -> re.Pattern:
        """Retorna o regex pattern para valores monetários."""
        return self._pattern
    
    def normalize_value(self, text: str) -> str:
        """Normaliza o valor monetário extraído."""
        match = self._pattern.search(text.strip())
        if match:
            return match.group(0)
        return text.strip()
