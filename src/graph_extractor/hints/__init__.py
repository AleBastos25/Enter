"""Módulo de hints (dicas) para identificar padrões em campos."""

from src.graph_extractor.hints.base import BaseHint, HintRegistry, AggregationStrategy, hint_registry
from src.graph_extractor.hints.date_hint import DateHint
from src.graph_extractor.hints.money_hint import MoneyHint
from src.graph_extractor.hints.address_hint import AddressHint
from src.graph_extractor.hints.cpf_cnpj_hint import CPFCNPJHint
from src.graph_extractor.hints.phone_hint import PhoneHint
from src.graph_extractor.hints.name_hint import NameHint
from src.graph_extractor.hints.text_hint import TextHint

# Registrar todas as hints no registry global (ordenadas por prioridade)
hint_registry.register(DateHint())
hint_registry.register(MoneyHint())
hint_registry.register(CPFCNPJHint())
hint_registry.register(PhoneHint())
hint_registry.register(NameHint())  # Nome antes de Address para priorizar
hint_registry.register(AddressHint())
hint_registry.register(TextHint())  # TextHint deve ser o último (fallback)

__all__ = [
    "BaseHint",
    "HintRegistry",
    "AggregationStrategy",
    "hint_registry",
    "DateHint",
    "MoneyHint",
    "AddressHint",
    "CPFCNPJHint",
    "PhoneHint",
    "NameHint",
    "TextHint",
]

