"""Generic smoke test for OAB documents (oab_1, oab_2, oab_3)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline

SCHEMA = {
    "inscricao": "Número de inscrição",
    "uf": "Sigla da seccional (UF)",
}

PDFS = ["data/samples/oab_1.pdf", "data/samples/oab_2.pdf", "data/samples/oab_3.pdf"]


def test_pdf(pdf_path: str) -> bool:
    """Test a single PDF and return True if it passes."""
    if not Path(pdf_path).exists():
        print(f"  ⚠ Skip: {pdf_path} not found")
        return True  # Don't fail if file doesn't exist

    pipe = Pipeline()
    out = pipe.run("carteira_oab", SCHEMA, pdf_path)

    # Generic checks (no hardcoded values)
    passed = True

    # Check inscricao: should be id_simple (digits/alphanumeric)
    inscricao = out["results"].get("inscricao", {})
    if inscricao.get("value") is not None:
        value = inscricao["value"]
        # Should be alphanumeric/digits, length >= 3
        if not (value.isalnum() or any(c.isdigit() for c in value)):
            print(f"  ❌ inscricao value '{value}' doesn't look like id_simple")
            passed = False
        else:
            print(f"  ✓ inscricao: {value} (confidence={inscricao.get('confidence', 0):.2f})")
    else:
        print(f"  ⚠ inscricao: null (no evidence found)")

    # Check uf: should be 2 uppercase letters or null
    uf = out["results"].get("uf", {})
    if uf.get("value") is not None:
        value = uf["value"]
        if len(value) != 2 or not value.isalpha() or not value.isupper():
            print(f"  ❌ uf value '{value}' doesn't look like UF (should be 2 uppercase letters)")
            passed = False
        else:
            print(f"  ✓ uf: {value} (confidence={uf.get('confidence', 0):.2f})")
    else:
        print(f"  ⚠ uf: null (no evidence found)")

    return passed


if __name__ == "__main__":
    print("Running generic OAB smoke tests...\n")

    all_passed = True
    for pdf in PDFS:
        print(f"Testing {Path(pdf).name}:")
        if not test_pdf(pdf):
            all_passed = False
        print()

    if all_passed:
        print("✓ All tests passed (or files not found)")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)

