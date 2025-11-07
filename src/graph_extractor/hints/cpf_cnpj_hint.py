"""Hint para detectar CPF/CNPJ."""

import re
from typing import List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy


class CPFCNPJHint(BaseHint):
    """Hint para detectar CPF/CNPJ."""
    
    def __init__(self):
        """Inicializa CPFCNPJHint."""
        super().__init__(priority=1, aggregation_strategy=AggregationStrategy.NONE)
        # Regex para CPF (11 dígitos) e CNPJ (14 dígitos)
        # Aceita formatado (com pontos e traços) ou não formatado
        self._pattern = re.compile(
            r"(?:\d{3}[.-]?\d{3}[.-]?\d{3}[.-]?\d{2})|"  # CPF: XXX.XXX.XXX-XX
            r"(?:\d{2}[.-]?\d{3}[.-]?\d{3}[/-]?\d{4}[.-]?\d{2})|"  # CNPJ: XX.XXX.XXX/XXXX-XX
            r"(?:^\d{11}$)|"  # CPF sem formatação
            r"(?:^\d{14}$)"  # CNPJ sem formatação
        )
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "cpf_cnpj"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave relacionadas a CPF/CNPJ."""
        return [
            "cpf", "cnpj", "documento", "document", "identificacao", "identificação",
            "id", "inscricao", "inscrição", "registration", "registro",
            "cadastro", "cadastre", "numero", "número", "number"
        ]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é relacionado a CPF/CNPJ."""
        text = f"{field_name} {field_description}".lower()
        # Verificar palavras-chave específicas
        if any(keyword in text for keyword in ["cpf", "cnpj"]):
            return True
        # Verificar descrições que mencionam documento de identificação
        if any(keyword in text for keyword in ["documento", "identificação", "inscrição"]):
            # Mas não se for sobre outros tipos de documento (ex: "documento de identidade")
            if "identidade" not in text and "rg" not in text:
                return True
        return False
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto contém CPF ou CNPJ."""
        # Remover espaços e caracteres especiais para verificação
        cleaned = re.sub(r"[^\d]", "", text.strip())
        # Verificar se tem 11 dígitos (CPF) ou 14 dígitos (CNPJ)
        if len(cleaned) == 11 or len(cleaned) == 14:
            return bool(self._pattern.search(text.strip()))
        return False
    
    def get_regex(self) -> re.Pattern:
        """Retorna o regex pattern para CPF/CNPJ."""
        return self._pattern
    
    def normalize_value(self, text: str) -> str:
        """Normaliza o CPF/CNPJ extraído."""
        match = self._pattern.search(text.strip())
        if match:
            return match.group(0)
        return text.strip()
