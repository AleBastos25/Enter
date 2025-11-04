"""Smoke test for LLM fallback integration."""

import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline
from src.llm.client import create_client, NoopClient


def main():
    """Test LLM fallback on a sample PDF."""
    pdf_path = "data/samples/oab_1.pdf"
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    # Simple schema with potentially ambiguous field
    schema = {
        "inscricao": "Número de inscrição na OAB",
        "seccional": "Sigla da seccional (UF)",
        "nome": "Nome completo do profissional",
    }

    print(f"Testing LLM fallback on: {pdf_path}")
    print("\nChecking LLM client...")

    # Check if LLM is available
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("  [OK] OPENAI_API_KEY found (from environment)")
    else:
        # Check secrets.yaml
        secrets_path = Path("configs/secrets.yaml")
        if secrets_path.exists():
            try:
                if yaml:
                    with open(secrets_path, "r", encoding="utf-8") as f:
                        secrets = yaml.safe_load(f) or {}
                        api_key = secrets.get("openai_api_key", "")
                        if api_key:
                            print("  [OK] OPENAI_API_KEY found (from configs/secrets.yaml)")
                        else:
                            print("  [INFO] OPENAI_API_KEY not set - will use NoopClient")
                            print("         Hint: Set in configs/secrets.yaml or environment variable")
                else:
                    print("  [INFO] PyYAML not installed - cannot read secrets.yaml")
            except Exception:
                print("  [INFO] OPENAI_API_KEY not set - will use NoopClient")
        else:
            print("  [INFO] OPENAI_API_KEY not set - will use NoopClient")
            print("         Hint: Create configs/secrets.yaml or set environment variable")

    # Create client to check type
    try:
        client = create_client("openai", "gpt-4o-mini", 0.0)
        client_type = "OpenAI" if not isinstance(client, NoopClient) else "Noop"
        print(f"  Client type: {client_type}")
    except Exception as e:
        print(f"  [WARN] Client creation failed: {e}")
        client_type = "Noop"

    print("\nRunning pipeline...")
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

            # Check if LLM was used
            if "llm" in trace:
                llm_info = trace["llm"]
                print(f"    [LLM] used={llm_info.get('used')}, context={llm_info.get('chars_context', 0)} chars")

        # Summary
        print("\nSummary:")
        sources = [r.get("source", "none") for r in result["results"].values()]
        source_counts = {}
        for s in sources:
            source_counts[s] = source_counts.get(s, 0) + 1

        for source, count in source_counts.items():
            print(f"  {source}: {count} fields")

        if "llm" in source_counts:
            print(f"\n[OK] LLM fallback used for {source_counts['llm']} field(s)")
        else:
            print("\n[INFO] LLM fallback not used (heuristics/tables sufficient)")

    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

