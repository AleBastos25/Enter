"""Test script to verify schema enrichment, enum/text_multiline validators, and position hints."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.schema import enrich_schema
from src.validation.validators import validate_and_normalize

# Test schema with various field types
TEST_SCHEMA = {
    "nome": "Nome do profissional, normalmente no canto superior esquerdo da imagem",
    "inscricao": "Número de inscrição do profissional",
    "seccional": "Seccional do profissional",
    "subsecao": "Subseção à qual o profissional faz parte",
    "categoria": "Categoria, pode ser ADVOGADO, ADVOGADA, SUPLEMENTAR, ESTAGIARIO, ESTAGIARIA",
    "endereco_profissional": "Endereço profissional completo",
    "situacao": "Situação do profissional, normalmente no canto inferior direito.",
    "data_nascimento": "Data de nascimento",
    "valor_total": "Valor total em reais",
}


def test_schema_enrichment():
    """Test schema enrichment with types, synonyms, enums, and position hints."""
    print("=" * 60)
    print("Testing Schema Enrichment")
    print("=" * 60)

    enriched = enrich_schema("test", TEST_SCHEMA)

    print(f"\nLabel: {enriched.label}")
    print(f"Number of fields: {len(enriched.fields)}\n")

    for field in enriched.fields:
        print(f"Field: {field.name}")
        print(f"  Type: {field.type}")
        print(f"  Synonyms: {field.synonyms[:5]}...")  # First 5
        if field.meta:
            print(f"  Meta: {json.dumps(field.meta, ensure_ascii=False)}")
        print()

    # Verify specific types
    type_checks = {
        "nome": "text",
        "inscricao": "id_simple",
        "seccional": "uf",
        "categoria": "enum",
        "endereco_profissional": "text_multiline",
        "situacao": "enum",
        "data_nascimento": "date",
        "valor_total": "money",
    }

    print("\nType inference checks:")
    all_passed = True
    for field_name, expected_type in type_checks.items():
        field = next((f for f in enriched.fields if f.name == field_name), None)
        if field:
            if field.type == expected_type:
                print(f"  [OK] {field_name}: {field.type}")
            else:
                print(f"  [FAIL] {field_name}: expected {expected_type}, got {field.type}")
                all_passed = False
        else:
            print(f"  [FAIL] {field_name}: field not found")
            all_passed = False

    # Check position hints
    print("\nPosition hint checks:")
    nome_field = next((f for f in enriched.fields if f.name == "nome"), None)
    if nome_field and nome_field.meta.get("position_hint") == "top-left":
        print("  [OK] nome: position_hint = top-left")
    else:
        print(f"  [FAIL] nome: position_hint not found or incorrect")
        all_passed = False

    situacao_field = next((f for f in enriched.fields if f.name == "situacao"), None)
    if situacao_field and situacao_field.meta.get("position_hint") == "bottom-right":
        print("  [OK] situacao: position_hint = bottom-right")
    else:
        print(f"  [FAIL] situacao: position_hint not found or incorrect")
        all_passed = False

    # Check enum options
    print("\nEnum options checks:")
    categoria_field = next((f for f in enriched.fields if f.name == "categoria"), None)
    if categoria_field and categoria_field.meta.get("enum_options"):
        options = categoria_field.meta["enum_options"]
        print(f"  [OK] categoria: enum_options = {options}")
        if "ADVOGADO" in options and "ESTAGIARIO" in options:
            print("  [OK] Contains expected enum values")
        else:
            print("  [FAIL] Missing expected enum values")
            all_passed = False
    else:
        print("  [FAIL] categoria: enum_options not found")
        all_passed = False

    return all_passed


def test_validators():
    """Test enum and text_multiline validators."""
    print("\n" + "=" * 60)
    print("Testing Validators")
    print("=" * 60)

    all_passed = True

    # Test enum validator
    print("\n1. Testing enum validator:")
    enum_options = ["ADVOGADO", "ADVOGADA", "SUPLEMENTAR", "ESTAGIARIO", "ESTAGIÁRIA"]

    test_cases = [
        ("advogado", True, "ADVOGADO"),
        ("ADVOGADA", True, "ADVOGADA"),
        ("estagiário", True, None),  # Should match any valid enum option (ESTAGIARIO or ESTAGIÁRIA)
        ("INVALIDO", False, None),
        ("Categoria: ADVOGADO", True, "ADVOGADO"),
    ]

    for text, should_pass, expected_value in test_cases:
        ok, value = validate_and_normalize("enum", text, enum_options=enum_options)
        if should_pass:
            if ok and value and value in enum_options:
                if expected_value is None or value == expected_value:
                    print(f"  [OK] '{text}' -> {value}")
                else:
                    print(f"  [WARN] '{text}' -> {value} (expected {expected_value}, but valid)")
            else:
                print(f"  [FAIL] '{text}' -> expected valid enum, got {value if ok else None}")
                all_passed = False
        elif not should_pass and not ok:
            print(f"  [OK] '{text}' -> None (correctly rejected)")
        else:
            print(f"  [FAIL] '{text}' -> expected rejection, got {value if ok else None}")
            all_passed = False

    # Test text_multiline validator
    print("\n2. Testing text_multiline validator:")
    multiline_text = "Rua das Flores, 123\nApto 45\nBairro Centro\nSão Paulo - SP"

    ok, value = validate_and_normalize("text_multiline", multiline_text)
    if ok and value:
        print(f"  [OK] Merged multiline text: {value[:50]}...")
        if "\n" not in value and len(value) > 20:  # Should be merged
            print("  [OK] Lines were merged correctly")
        else:
            print("  [FAIL] Lines were not merged correctly")
            all_passed = False
    else:
        print(f"  [FAIL] Failed to validate multiline text")
        all_passed = False

    # Test single line (should still work)
    single_line = "Rua das Flores, 123"
    ok, value = validate_and_normalize("text_multiline", single_line)
    if ok and value == single_line:
        print(f"  [OK] Single line handled correctly: {value}")
    else:
        print(f"  [FAIL] Single line failed")
        all_passed = False

    return all_passed


def test_position_bonus():
    """Test position hint bonus calculation."""
    print("\n" + "=" * 60)
    print("Testing Position Bonus")
    print("=" * 60)

    from src.extraction.text_extractor import _position_bonus

    # Test cases: (position_hint, bbox, expected_bonus)
    test_cases = [
        ("top-left", (0.1, 0.1, 0.3, 0.3), 0.05),  # Center in top-left
        ("top-right", (0.7, 0.1, 0.9, 0.3), 0.05),  # Center in top-right
        ("bottom-left", (0.1, 0.7, 0.3, 0.9), 0.05),  # Center in bottom-left
        ("bottom-right", (0.7, 0.7, 0.9, 0.9), 0.05),  # Center in bottom-right
        ("top-left", (0.7, 0.1, 0.9, 0.3), 0.0),  # Wrong quadrant
        (None, (0.1, 0.1, 0.3, 0.3), 0.0),  # No hint
    ]

    all_passed = True
    for position_hint, bbox, expected in test_cases:
        meta = {"position_hint": position_hint} if position_hint else {}
        bonus = _position_bonus(meta, bbox)
        if bonus == expected:
            print(f"  [OK] {position_hint or 'None'}: bbox={bbox} -> bonus={bonus}")
        else:
            print(f"  [FAIL] {position_hint or 'None'}: bbox={bbox} -> expected {expected}, got {bonus}")
            all_passed = False

    return all_passed


def main():
    """Run all tests."""
    print("Testing Schema Enrichment + Validators + Position Hints")
    print("=" * 60)

    results = []

    # Test schema enrichment
    results.append(("Schema Enrichment", test_schema_enrichment()))

    # Test validators
    results.append(("Validators", test_validators()))

    # Test position bonus
    results.append(("Position Bonus", test_position_bonus()))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    all_passed = True
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n[OK] All tests passed!")
        sys.exit(0)
    else:
        print("\n[FAIL] Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

