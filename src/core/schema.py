"""Schema enrichment: convert simple schema dict to rich ExtractionSchema."""

from __future__ import annotations

import unicodedata
from typing import Dict, List

from .models import ExtractionSchema, SchemaField

# Type inference triggers (case-insensitive, accent-insensitive)
TYPE_TRIGGERS = {
    "date": ["data", "date", "emissao", "venc", "vcto", "issued", "due", "nascimento"],
    "money": ["valor", "preço", "preco", "total", "montante", "amount", "value", "saldo"],
    "id_simple": ["inscri", "registro", "nº", "no ", "n. ", "id", "code", "codigo", "código"],
    "uf": ["uf", "estado", "seccional", "sigla", "state"],
    "cep": ["cep", "zip", "postal"],
    "enum": ["categoria", "situacao", "status", "classe", "tipo"],
}

# Common enum options (canonical uppercase, accent-tolerant matching)
ENUM_OPTIONS = {
    "categoria": ["ADVOGADO", "ADVOGADA", "SUPLEMENTAR", "ESTAGIARIO", "ESTAGIÁRIA", "ESTAGIÁRIO"],
    "situacao": ["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"],
    "status": ["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"],
}


def _normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove accents."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower()


def _infer_type(name: str, description: str) -> str:
    """Infer field type from name and description."""
    name_norm = _normalize_text(name)
    desc_norm = _normalize_text(description)

    # Check for text_multiline (address-like) - priority
    if any(word in name_norm or word in desc_norm for word in ["endereco", "endereço", "address"]):
        return "text_multiline"

    # Check enum first (before id_simple to avoid conflicts)
    if any(word in name_norm or word in desc_norm for word in TYPE_TRIGGERS["enum"]):
        return "enum"

    # Check other types (avoid matching "nome" as id_simple)
    for ftype, triggers in TYPE_TRIGGERS.items():
        if ftype == "enum":  # Already checked
            continue
        # For id_simple, avoid matching "nome" (which contains "no")
        if ftype == "id_simple":
            # Check if it's actually "nome" (name field)
            if "nome" in name_norm and len(name_norm) <= 5:  # "nome" is short
                continue
            # Check if description suggests it's a name field
            if "nome" in desc_norm or "name" in desc_norm:
                continue
        if any(trigger in name_norm or trigger in desc_norm for trigger in triggers):
            return ftype

    return "text"


def _generate_synonyms(name: str, description: str, field_type: str) -> List[str]:
    """Generate synonyms from field name and description."""
    synonyms = [name.lower()]

    name_norm = _normalize_text(name)
    desc_norm = _normalize_text(description)

    # Type-specific synonyms
    if field_type == "id_simple":
        synonyms.extend(["nº", "no", "n.", "registro", "inscrição", "inscricao", "id"])
    elif field_type == "money":
        synonyms.extend(["valor", "total"])
    elif field_type == "date":
        synonyms.extend(["data", "vencimento", "emissão", "emissao"])
    elif field_type == "uf":
        synonyms.extend(["uf", "seccional", "estado", "sigla"])
    elif field_type == "text_multiline":
        if "endereco" in name_norm or "endereço" in desc_norm:
            synonyms.extend(["endereço", "endereco"])

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for syn in synonyms:
        syn_norm = syn.lower().strip()
        if syn_norm and syn_norm not in seen:
            seen.add(syn_norm)
            unique.append(syn_norm)

    # Keep 2-6 items
    return unique[:6]


def _extract_enum_options(name: str, description: str) -> List[str] | None:
    """Extract enum options from description if available."""
    name_norm = _normalize_text(name)
    desc_norm = _normalize_text(description)

    # Check if we have predefined options for this field
    for key, options in ENUM_OPTIONS.items():
        if key in name_norm or key in desc_norm:
            return options

    # Try to extract from description (e.g., "pode ser A, B, C")
    # Simple heuristic: look for "pode ser" or "são" followed by uppercase words
    if "pode ser" in desc_norm or "são" in desc_norm:
        # Look for comma-separated uppercase words
        import re

        matches = re.findall(r"\b([A-Z][A-Z\sÁÉÍÓÚÂÊÔÃÕÇ]+?)(?:\s*[,.]|$)", description)
        if matches:
            # Normalize to uppercase, remove extra spaces
            options = [m.strip().upper() for m in matches if len(m.strip()) > 2]
            if options:
                return options

    return None


def _extract_position_hint(description: str) -> str | None:
    """Extract position hint from description."""
    desc_norm = _normalize_text(description)

    if "canto superior esquerdo" in desc_norm or "superior esquerdo" in desc_norm:
        return "top-left"
    if "canto superior direito" in desc_norm or "superior direito" in desc_norm:
        return "top-right"
    if "canto inferior esquerdo" in desc_norm or "inferior esquerdo" in desc_norm:
        return "bottom-left"
    if "canto inferior direito" in desc_norm or "inferior direito" in desc_norm:
        return "bottom-right"

    return None


def enrich_schema(label: str, schema_dict: Dict[str, str]) -> ExtractionSchema:
    """Convert {name: description} into ExtractionSchema with types, synonyms, enums, and position hints.

    Args:
        label: Document label/type.
        schema_dict: Mapping field_name -> description.

    Returns:
        ExtractionSchema with enriched SchemaField objects.
    """
    fields: List[SchemaField] = []

    for name, description in schema_dict.items():
        # Infer type
        field_type = _infer_type(name, description)

        # Generate synonyms
        synonyms = _generate_synonyms(name, description, field_type)

        # Extract enum options if applicable
        enum_options = None
        if field_type == "enum":
            enum_options = _extract_enum_options(name, description)

        # Extract position hint
        position_hint = _extract_position_hint(description)

        # Build meta dict
        meta: Dict[str, object] = {}
        if enum_options:
            meta["enum_options"] = enum_options
        if position_hint:
            meta["position_hint"] = position_hint

        fields.append(
            SchemaField(
                name=name,
                description=description,
                type=field_type,
                synonyms=synonyms,
                meta=meta,
            )
        )

    return ExtractionSchema(label=label, fields=fields)

