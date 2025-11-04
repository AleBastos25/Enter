"""Smoke test for semantic embedding integration."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def main():
    """Test semantic embedding on a sample PDF."""
    pdf_path = "data/samples/oab_2.pdf"
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    # Schema with fields that might have non-obvious labels
    schema = {
    "nome": "Nome do profissional, normalmente no canto superior esquerdo da imagem",
    "inscricao": "Número de inscrição do profissional",
    "seccional": "Seccional do profissional",
    "subsecao": "Subseção à qual o profissional faz parte",
    "categoria": "Categoria, pode ser ADVOGADO, ADVOGADA, SUPLEMENTAR, ESTAGIARIO, ESTAGIARIA",
    "endereco_profissional": "Endereço profissional completo",
    "situacao": "Situação do profissional, normalmente no canto inferior direito."
}

    print(f"Testing semantic embedding on: {pdf_path}")
    print("\nNote: Embeddings are enabled by default in configs/embedding.yaml")
    print("      Set enabled: false to disable and test without embeddings\n")

    pipe = Pipeline()

    try:
        result = pipe.run("carteira_oab", schema, pdf_path)

        print("\nResults:")
        for field_name, field_result in result["results"].items():
            value = field_result.get("value")
            source = field_result.get("source", "none")
            confidence = field_result.get("confidence", 0.0)
            trace = field_result.get("trace", {})

            status = "[OK]" if value else "[NULL]"
            print(f"  {status} {field_name}:")
            print(f"    value: {value}")
            print(f"    source: {source}")
            print(f"    confidence: {confidence:.2f}")

            # Check if semantic scores are present
            if "scores" in trace or "semantic" in str(trace):
                print(f"    [SEMANTIC] trace contains semantic information")
                # Try to find semantic scores in candidates
                if "node_id" in trace:
                    print(f"      node_id: {trace.get('node_id')}")

        # Summary
        print("\nSummary:")
        sources = [r.get("source", "none") for r in result["results"].values()]
        source_counts = {}
        for s in sources:
            source_counts[s] = source_counts.get(s, 0) + 1

        for source, count in source_counts.items():
            print(f"  {source}: {count} fields")

        print("\n[INFO] Check trace for semantic scores if embeddings were used")
        print("       Embeddings help find labels that don't match by substring")

    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

