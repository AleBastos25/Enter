"""Value generators for synthetic documents (BR and general types)."""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional

try:
    from faker import Faker
    from faker.providers import BaseProvider
except ImportError:
    Faker = None
    BaseProvider = None

# Fallback if Faker not available
if Faker is None:
    # Minimal fallback generators
    _fake = None
else:
    _fake = Faker("pt_BR")
    _fake_en = Faker()


class BRProvider(BaseProvider if BaseProvider else object):
    """Brazilian-specific value generators."""

    def cpf(self) -> str:
        """Generate valid CPF (without formatting)."""
        if _fake:
            return _fake.cpf().replace(".", "").replace("-", "")
        # Fallback: simple 11-digit
        return "".join(str(random.randint(0, 9)) for _ in range(11))

    def cnpj(self) -> str:
        """Generate valid CNPJ (without formatting)."""
        if _fake:
            return _fake.cnpj().replace(".", "").replace("/", "").replace("-", "")
        # Fallback: simple 14-digit
        return "".join(str(random.randint(0, 9)) for _ in range(14))

    def cep(self) -> str:
        """Generate CEP (without formatting)."""
        if _fake:
            return _fake.postcode().replace("-", "")
        return f"{random.randint(10000, 99999)}{random.randint(100, 999)}"

    def uf(self) -> str:
        """Generate Brazilian state code."""
        ufs = [
            "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
            "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
            "RS", "RO", "RR", "SC", "SP", "SE", "TO"
        ]
        return random.choice(ufs)


# Initialize Faker with BR provider if available
if _fake and BaseProvider:
    _fake.add_provider(BRProvider)
    _fake_br = _fake
else:
    _fake_br = BRProvider()


# Type generators mapping
TYPE_GENERATORS: Dict[str, callable] = {}


def _register_generators():
    """Register generators for each type."""
    if _fake:
        TYPE_GENERATORS["name"] = lambda: _fake.name()
        TYPE_GENERATORS["email"] = lambda: _fake.email()
        TYPE_GENERATORS["phone_br"] = lambda: _fake.phone_number()
        TYPE_GENERATORS["address"] = lambda: _fake.address()
        TYPE_GENERATORS["city"] = lambda: _fake.city()
        TYPE_GENERATORS["date"] = lambda: _fake.date(pattern="%d/%m/%Y")
        TYPE_GENERATORS["money"] = lambda: f"R$ {random.uniform(10.0, 99999.99):.2f}".replace(".", ",")
    else:
        TYPE_GENERATORS["name"] = lambda: f"Nome {random.randint(1, 1000)}"
        TYPE_GENERATORS["email"] = lambda: f"email{random.randint(1, 1000)}@example.com"
        TYPE_GENERATORS["phone_br"] = lambda: f"({random.randint(11, 99)}) {random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
        TYPE_GENERATORS["address"] = lambda: f"Rua {random.randint(1, 999)}, Bairro Centro"
        TYPE_GENERATORS["city"] = lambda: random.choice(["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba"])
        TYPE_GENERATORS["date"] = lambda: f"{random.randint(1, 28):02d}/{random.randint(1, 12):02d}/{random.randint(2020, 2024)}"
        TYPE_GENERATORS["money"] = lambda: f"R$ {random.uniform(10.0, 99999.99):.2f}".replace(".", ",")

    TYPE_GENERATORS["cpf"] = lambda: _fake_br.cpf() if hasattr(_fake_br, "cpf") else "".join(str(random.randint(0, 9)) for _ in range(11))
    TYPE_GENERATORS["cnpj"] = lambda: _fake_br.cnpj() if hasattr(_fake_br, "cnpj") else "".join(str(random.randint(0, 9)) for _ in range(14))
    TYPE_GENERATORS["cep"] = lambda: _fake_br.cep() if hasattr(_fake_br, "cep") else f"{random.randint(10000, 99999)}{random.randint(100, 999)}"
    TYPE_GENERATORS["uf"] = lambda: _fake_br.uf() if hasattr(_fake_br, "uf") else random.choice(["SP", "RJ", "MG", "RS", "PR"])
    TYPE_GENERATORS["id_simple"] = lambda: f"{random.randint(1000, 999999)}"
    TYPE_GENERATORS["text"] = lambda: _fake.text(max_nb_chars=50) if _fake else f"Texto exemplo {random.randint(1, 1000)}"
    TYPE_GENERATORS["text_multiline"] = lambda: (_fake.address() + "\n" + _fake.city() + ", " + _fake_br.uf()) if _fake else "Endereço exemplo\nCidade, UF"
    TYPE_GENERATORS["alphanum_code"] = lambda: "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))


_register_generators()


def infer_type_from_field(field_name: str, description: str) -> str:
    """Infer field type from name and description (same logic as core/schema.py)."""
    import unicodedata

    def _normalize(text: str) -> str:
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return text.lower()

    name_norm = _normalize(field_name)
    desc_norm = _normalize(description)

    # Check for text_multiline (address-like)
    if any(word in name_norm or word in desc_norm for word in ["endereco", "endereço", "address"]):
        return "text_multiline"

    # Check enum
    if any(word in name_norm or word in desc_norm for word in ["categoria", "situacao", "status", "classe", "tipo"]):
        return "enum"

    # Check other types
    triggers = {
        "date": ["data", "date", "emissao", "venc", "vcto", "issued", "due", "nascimento"],
        "money": ["valor", "preço", "preco", "total", "montante", "amount", "value", "saldo"],
        "id_simple": ["inscri", "registro", "nº", "no ", "n. ", "id", "code", "codigo", "código"],
        "cpf": ["cpf", "cadastro", "pessoa física"],
        "cnpj": ["cnpj", "empresa", "pessoa jurídica", "pj"],
        "email": ["email", "e-mail", "correio", "mail"],
        "phone_br": ["telefone", "phone", "celular", "fone", "whatsapp"],
        "cep": ["cep", "zip", "postal"],
        "uf": ["uf", "estado", "seccional", "sigla", "state"],
    }

    for ftype, trigger_list in triggers.items():
        if ftype == "id_simple":
            # Avoid matching "nome" as id_simple
            if "nome" in name_norm and len(name_norm) <= 5:
                continue
            if "nome" in desc_norm or "name" in desc_norm:
                continue
        if any(trigger in name_norm or trigger in desc_norm for trigger in trigger_list):
            return ftype

    return "text"


def extract_enum_options(description: str) -> Optional[List[str]]:
    """Extract enum options from description if mentioned."""
    # Look for patterns like "pode ser X, Y, Z" or "X, Y ou Z"
    desc_lower = description.lower()
    # Common patterns
    patterns = [
        r"pode ser ([A-Z][A-Z\s,]+)",
        r"pode ser ([A-ZÁÉÍÓÚ][a-záéíóú\s,]+)",
        r"([A-Z][A-Z\s,]+) ou ([A-Z][A-Z\s,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            options_str = match.group(1) if match.groups() else match.group(0)
            # Split by comma or "ou"
            options = [opt.strip().upper() for opt in re.split(r"[,\s]ou\s|,", options_str) if opt.strip()]
            if options:
                return options
    return None


def generate_value(field_name: str, description: str, field_type: Optional[str] = None, enum_options: Optional[List[str]] = None) -> str:
    """Generate a value for a field based on its type.

    Args:
        field_name: Field name.
        description: Field description.
        field_type: Optional explicit type (if None, will infer).
        enum_options: Optional enum options.

    Returns:
        Generated value string.
    """
    if field_type is None:
        field_type = infer_type_from_field(field_name, description)

    # Handle enum
    if field_type == "enum":
        if enum_options:
            return random.choice(enum_options)
        # Fallback: common enums
        if "situacao" in field_name.lower() or "status" in field_name.lower():
            return random.choice(["REGULAR", "SUSPENSO", "CANCELADO", "ATIVO", "INATIVO"])
        if "categoria" in field_name.lower():
            return random.choice(["ADVOGADO", "ADVOGADA", "SUPLEMENTAR", "ESTAGIARIO", "ESTAGIÁRIA"])
        if "selecao" in field_name.lower() or "seleção" in field_name.lower():
            return random.choice(["VENCIDO", "PAGO", "PENDENTE"])
        # Generic enum
        return random.choice(["OPÇÃO A", "OPÇÃO B", "OPÇÃO C"])

    # Use registered generator
    generator = TYPE_GENERATORS.get(field_type)
    if generator:
        return generator()

    # Fallback
    return f"Valor {field_name} {random.randint(1, 1000)}"


def generate_pairs_for_schema(schema: Dict[str, str], coverage: float = 0.8) -> List[tuple[str, str, str]]:
    """Generate key-value pairs from a schema.

    Args:
        schema: {field_name: description}
        coverage: Fraction of fields to include (0.0-1.0).

    Returns:
        List of (field_name, label, value) tuples.
    """
    all_fields = list(schema.items())
    random.shuffle(all_fields)
    n_fields = max(1, int(len(all_fields) * coverage))
    selected = all_fields[:n_fields]

    pairs = []
    for field_name, description in selected:
        # Generate label (use synonym or field name)
        label = field_name.replace("_", " ").title()
        # Generate value
        value = generate_value(field_name, description)
        pairs.append((field_name, label, value))

    return pairs

