"""Smoke test for the full pipeline."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline

if __name__ == "__main__":
    label = "carteira_oab"
    schema = {
        "inscricao": "Número de inscrição na OAB",
        "seccional": "Sigla da seccional (UF)",
    }

    pdf_path = "data/samples/oab_1.pdf"
    if not Path(pdf_path).exists():
        print(f"Warning: {pdf_path} not found. Please adjust the path.")
        sys.exit(1)

    pipe = Pipeline()
    out = pipe.run(label, schema, pdf_path)
    print(json.dumps(out, ensure_ascii=False, indent=2))

