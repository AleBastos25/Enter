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
    # Brazilian-specific types
    "cpf": ["cpf", "cadastro", "pessoa física"],
    "cnpj": ["cnpj", "empresa", "pessoa jurídica", "pj"],
    "email": ["email", "e-mail", "correio", "mail"],
    "phone_br": ["telefone", "phone", "celular", "fone", "whatsapp"],
    "placa_mercosul": ["placa", "veículo", "veiculo", "automóvel", "automovel"],
    "cnh": ["cnh", "carteira", "habilitação", "habilitacao"],
    "rg": ["rg", "identidade", "documento"],
    "chave_nf": ["chave", "nf", "nota fiscal", "nfe"],
}

# Common enum options (canonical uppercase, accent-tolerant matching)
ENUM_OPTIONS = {
    "categoria": ["ADVOGADO", "ADVOGADA", "SUPLEMENTAR", "ESTAGIARIO", "ESTAGIÁRIA", "ESTAGIÁRIO", "ESTAGIARIA"],
    "situacao": ["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"],
    "status": ["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"],
    "selecao_de_parcelas": ["VENCIDO", "PAGO", "PENDENTE"],
    "pesquisa_por": ["CLIENTE", "PARENTE", "PRESTADOR", "OUTRO"],
    "pesquisa_tipo": ["CPF", "CNPJ", "NOME", "EMAIL"],
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


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def _generate_synonyms(name: str, description: str, field_type: str) -> List[str]:
    """Generate synonyms from field name and description with Levenshtein tolerance for typos."""
    synonyms = [name.lower()]

    name_norm = _normalize_text(name)
    desc_norm = _normalize_text(description)

    # Type-specific synonyms
    if field_type == "id_simple":
        synonyms.extend(["nº", "no", "n.", "registro", "inscrição", "inscricao", "id"])
    elif field_type == "money":
        synonyms.extend(["valor", "total", "parcela", "parc."])
    elif field_type == "date":
        # Add common date synonyms with variations for typos
        date_synonyms = ["data", "vencimento", "emissão", "emissao", "vcto", "vcto.", "due", "venc"]
        synonyms.extend(date_synonyms)
        # Add Levenshtein variants for common typos (e.g., "verncimento" -> "vencimento")
        if "vencimento" in desc_norm or "vcto" in desc_norm:
            # Generate variants for common typos
            base_words = ["vencimento", "venc"]
            for base in base_words:
                # Generate variants with Levenshtein <= 2
                variants = []
                for i in range(len(base)):
                    # Single character changes
                    for c in "aeiou":
                        variant = base[:i] + c + base[i+1:]
                        if _levenshtein_distance(variant, base) <= 2:
                            variants.append(variant)
                synonyms.extend(variants[:3])  # Limit variants
    elif field_type == "uf":
        synonyms.extend(["uf", "seccional", "estado", "sigla"])
    elif field_type == "text_multiline":
        if "endereco" in name_norm or "endereço" in desc_norm:
            synonyms.extend(["endereço", "endereco"])
    elif name_norm == "nome":
        # Special handling for "nome" - avoid matching "profissional" in "Endereço Profissional"
        # Only use "nome" and "name" as synonyms, not "profissional"
        synonyms = ["nome", "name"]
    elif "nome" in name_norm:
        # For name fields, add common variations
        synonyms.extend(["nome", "name", "profissional"])
    
    # Extract tokens from description for additional synonyms
    # Look for short tokens (3-8 chars) that might be field labels
    import re
    desc_tokens = re.findall(r'\b\w{3,8}\b', description.lower())
    for token in desc_tokens[:3]:  # Top 3 tokens
        token_norm = _normalize_text(token)
        # Only add if it's not already in synonyms and Levenshtein distance is reasonable
        if token_norm not in synonyms and len(token_norm) >= 3:
            # Check if it's similar to name (Levenshtein <= 2)
            if _levenshtein_distance(token_norm, name_norm) <= 2:
                synonyms.append(token_norm)

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
        # Normalize name for checking
        name_norm = _normalize_text(name)

        # Infer type
        field_type = _infer_type(name, description)

        # Generate synonyms
        synonyms = _generate_synonyms(name, description, field_type)

        # Extract enum options if applicable
        enum_options = None
        if field_type == "enum":
            enum_options = _extract_enum_options(name, description)
            # Ensure common enum options for known fields
            if name_norm in ["situacao", "status"] and not enum_options:
                enum_options = ENUM_OPTIONS.get("situacao", ["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"])
            elif name_norm == "categoria" and not enum_options:
                enum_options = ENUM_OPTIONS.get("categoria", ["ADVOGADO", "ADVOGADA", "SUPLEMENTAR", "ESTAGIARIO", "ESTAGIÁRIA", "ESTAGIÁRIO"])
            elif name_norm in ["selecao_de_parcelas", "selecao de parcelas"] and not enum_options:
                enum_options = ENUM_OPTIONS.get("selecao_de_parcelas", ["VENCIDO", "PAGO", "PENDENTE"])
            elif name_norm in ["pesquisa_por", "pesquisa por"] and not enum_options:
                enum_options = ENUM_OPTIONS.get("pesquisa_por", ["CLIENTE", "PARENTE", "PRESTADOR", "OUTRO"])
            elif name_norm in ["pesquisa_tipo", "pesquisa tipo"] and not enum_options:
                enum_options = ENUM_OPTIONS.get("pesquisa_tipo", ["CPF", "CNPJ", "NOME", "EMAIL"])

        # Extract position hint
        position_hint = _extract_position_hint(description)

        # Build meta dict
        meta: Dict[str, object] = {}
        if enum_options:
            meta["enum_options"] = enum_options
        if position_hint:
            meta["position_hint"] = position_hint

        # Ensure situacao/status get enum options even if not explicitly mentioned
        if field_type == "enum" and name_norm in ["situacao", "status"] and not enum_options:
            enum_options = ENUM_OPTIONS.get("situacao", ["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"])
            if enum_options:
                meta["enum_options"] = enum_options

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

