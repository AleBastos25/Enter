"""Generic smoke test for system screen documents (tela_sistema_1, tela_sistema_2, tela_sistema_3)."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline

SCHEMA = {
    "data_referencia": "Data de referência",
    "total_geral": "Total geral (valor)",
    "uf": "UF do endereço",
}

PDFS = [
    "data/samples/tela_sistema_1.pdf",
    "data/samples/tela_sistema_2.pdf",
    "data/samples/tela_sistema_3.pdf",
]


def test_pdf(pdf_path: str) -> bool:
    """Test a single PDF and return True if it passes."""
    if not Path(pdf_path).exists():
        print(f"  ⚠ Skip: {pdf_path} not found")
        return True  # Don't fail if file doesn't exist

    pipe = Pipeline()
    out = pipe.run("tela_sistema", SCHEMA, pdf_path)

    # Generic checks (no hardcoded values)
    passed = True

    # Check data_referencia: should be date (YYYY-MM-DD) or null
    data = out["results"].get("data_referencia", {})
    if data.get("value") is not None:
        value = data["value"]
        # Should be ISO date format
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            print(f"  ❌ data_referencia value '{value}' doesn't look like ISO date")
            passed = False
        else:
            print(f"  ✓ data_referencia: {value} (confidence={data.get('confidence', 0):.2f})")
    else:
        print(f"  ⚠ data_referencia: null (no evidence found)")

    # Check total_geral: should be money (float with dot) or null
    total = out["results"].get("total_geral", {})
    if total.get("value") is not None:
        value = total["value"]
        # Should be numeric (float format)
        try:
            float(value)
            if "." not in value:
                print(f"  ⚠ total_geral value '{value}' is integer, expected float")
            else:
                print(f"  ✓ total_geral: {value} (confidence={total.get('confidence', 0):.2f})")
        except ValueError:
            print(f"  ❌ total_geral value '{value}' is not numeric")
            passed = False
    else:
        print(f"  ⚠ total_geral: null (no evidence found)")

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
        print(f"  ⚠ uf: null (no evidence found - this is OK)")

    return passed


if __name__ == "__main__":
    print("Running generic system screen smoke tests...\n")

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

