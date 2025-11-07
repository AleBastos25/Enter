"""Hint genérico para texto."""

import re
from typing import List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy


class TextHint(BaseHint):
    """Hint genérico para texto (fallback).
    
    Esta hint é usada como fallback quando nenhuma outra hint específica
    se aplica. Ela aceita qualquer texto não numérico.
    """
    
    def __init__(self):
        """Inicializa TextHint."""
        super().__init__(priority=3, aggregation_strategy=AggregationStrategy.NONE)
        # Regex genérico que aceita qualquer texto com letras
        self._pattern = re.compile(r".+", re.DOTALL)
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "text"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave genéricas."""
        return [
            "nome", "name", "texto", "text", "descricao", "descrição", "description",
            "observacao", "observação", "observation", "comentario", "comentário",
            "comment", "nota", "note", "informacao", "informação", "information"
        ]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Sempre retorna True (fallback).
        
        Esta hint é usada como última opção quando nenhuma outra hint
        se aplica. O PatternMatcher deve verificar outras hints primeiro.
        """
        # Esta hint é aplicada apenas quando outras não se aplicam
        return True
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto contém pelo menos uma letra.
        
        Exclui valores puramente numéricos, datas e valores monetários,
        que devem ser capturados por outras hints.
        """
        text_clean = text.strip()
        if not text_clean:
            return False
        
        # Verificar se tem pelo menos uma letra (incluindo acentos)
        has_letter = bool(re.search(r"[A-Za-zÀ-ÿ]", text_clean))
        
        # Se não tem letras, não é texto genérico
        if not has_letter:
            return False
        
        # Verificar se não é principalmente numérico (com alguns caracteres)
        # Ex: "123abc" é texto, mas "123" não é
        digit_ratio = sum(1 for c in text_clean if c.isdigit()) / len(text_clean)
        
        # Se mais de 80% são dígitos, provavelmente não é texto genérico
        if digit_ratio > 0.8:
            return False
        
        return True
    
    def get_regex(self) -> re.Pattern:
        """Retorna o regex pattern genérico."""
        return self._pattern
    
    def normalize_value(self, text: str) -> str:
        """Normaliza o texto extraído."""
        return text.strip()
