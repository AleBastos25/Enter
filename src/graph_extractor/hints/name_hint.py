"""Hint para detectar nomes de pessoas."""

import re
from typing import Optional, Pattern, List
from src.graph_extractor.hints.base import BaseHint, AggregationStrategy, hint_registry


class NameHint(BaseHint):
    """Hint para detectar e extrair nomes de pessoas."""
    
    def __init__(self):
        """Inicializa NameHint."""
        super().__init__(priority=2, aggregation_strategy=AggregationStrategy.CONCATENATE)
    
    @property
    def name(self) -> str:
        """Nome da hint."""
        return "name"
    
    @property
    def keywords(self) -> List[str]:
        """Palavras-chave relacionadas a nomes."""
        return ["nome", "name", "pessoa", "person", "profissional", "cliente"]
    
    @property
    def description_keywords(self) -> List[str]:
        """Palavras-chave na descrição do campo."""
        return ["nome completo", "nome da pessoa", "nome do profissional"]
    
    def matches_field(self, field_name: str, field_description: str) -> bool:
        """Verifica se o campo é relacionado a nome de pessoa."""
        text = f"{field_name} {field_description}".lower()
        # Verificar keywords no nome do campo
        if any(keyword in field_name.lower() for keyword in self.keywords):
            return True
        # Verificar keywords na descrição
        if any(keyword in field_description.lower() for keyword in self.description_keywords):
            return True
        return False
    
    # Siglas comuns a excluir (estados brasileiros, abreviações)
    _excluded_siglas = {
        "PR", "SP", "RJ", "MG", "RS", "BA", "SC", "GO", "PE", "CE",
        "DF", "ES", "MT", "MS", "PA", "PB", "AM", "RN", "AL", "PI",
        "TO", "MA", "SE", "RO", "AC", "AP", "RR", "BR", "US", "EUA",
        "CNPJ", "CPF", "RG", "IE", "UF", "OAB", "CRC", "CREA"
    }
    
    def detect(self, text: str) -> bool:
        """Detecta se o texto parece ser um nome de pessoa.
        
        Critérios:
        - Tem pelo menos 3 caracteres
        - Tem pelo menos 2 palavras (nomes completos) OU uma palavra com 4+ caracteres
        - Não é sigla conhecida (PR, SP, etc.)
        - Palavras começam com maiúscula (nomes próprios) ou são todas maiúsculas
        - Não é principalmente numérico
        """
        text_clean = text.strip()
        
        # Muito curto para ser nome completo
        if len(text_clean) < 3:
            return False
        
        # É sigla conhecida?
        text_upper = text_clean.upper().strip()
        if text_upper in self._excluded_siglas:
            return False
        
        # Se tem apenas 1 palavra e é muito curta, provavelmente não é nome completo
        words = text_clean.split()
        if len(words) == 1 and len(words[0]) <= 3:
            return False
        
        # Verificar se tem letras
        if not re.search(r"[A-Za-zÀ-ÿ]", text_clean):
            return False
        
        # Verificar se não é principalmente numérico
        digit_ratio = sum(1 for c in text_clean if c.isdigit()) / len(text_clean)
        if digit_ratio > 0.3:  # Mais de 30% dígitos = provavelmente não é nome
            return False
        
        # Se tem 2+ palavras, maior chance de ser nome completo
        if len(words) >= 2:
            # Verificar se palavras têm tamanho razoável (pelo menos uma com 3+ caracteres)
            has_long_word = any(len(w) >= 3 for w in words)
            if has_long_word:
                return True
        
        # Se tem apenas 1 palavra, precisa ser mais longa (mínimo 4 caracteres)
        if len(words) == 1:
            return len(words[0]) >= 4
        
        return False
    
    def extract_pattern(self, text: str) -> Optional[str]:
        """Extrai o nome do texto."""
        text_clean = text.strip()
        
        # Remover pontuação final
        text_clean = re.sub(r'[^\w\sÀ-ÿ-]+$', '', text_clean).strip()
        
        # Validar novamente antes de retornar
        if self.detect(text_clean):
            return text_clean
        
        return None
    
    def get_regex(self) -> Optional[Pattern]:
        """Regex para nomes: palavras começando com maiúscula, 2+ palavras, 3+ caracteres cada."""
        # Padrão: 2+ palavras, cada uma com pelo menos 3 caracteres, começando com maiúscula
        pattern = re.compile(
            r"\b[A-ZÀ-Ÿ][a-zà-ÿ]{2,}(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]{2,})+\b"
        )
        return pattern
    
    def calculate_score(self, text: str, field_name: str, field_description: str) -> float:
        """Calcula score para nomes.
        
        Score maior se:
        - Tem mais palavras (nome completo)
        - Palavras começam com maiúscula
        - Não é sigla
        """
        score = 0.6  # Base score
        
        words = text.strip().split()
        
        # Bônus por número de palavras (nome completo)
        if len(words) >= 3:
            score += 0.2  # Nome completo (nome + sobrenomes)
        elif len(words) == 2:
            score += 0.1  # Nome + sobrenome
        
        # Bônus se palavras começam com maiúscula (padrão de nome próprio)
        # Ou se é tudo maiúsculo (nomes em documentos oficiais)
        all_upper = all(w.isupper() for w in words if w)
        proper_case = all(w and w[0].isupper() for w in words if w)
        
        if all_upper or proper_case:
            score += 0.1
        
        # Penalizar se é muito curto
        if len(text.strip()) < 5:
            score -= 0.2
        
        return min(1.0, max(0.0, score))

