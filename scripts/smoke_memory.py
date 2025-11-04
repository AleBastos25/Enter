"""Smoke test for PatternMemory: run 2x and show learning gain."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline


def main():
    """Run pipeline twice on same PDF and show memory learning."""
    pdf_path = "data/samples/oab_1.pdf"
    schema = {
        "inscricao": "Número de inscrição na OAB",
        "seccional": "Sigla da seccional (UF)",
        "situacao": "Situação do profissional",
    }

    print("=" * 60)
    print("PatternMemory Smoke Test")
    print("=" * 60)

    pipe = Pipeline()

    # First run: learn from high-confidence extractions
    print("\n[Run 1] First pass - learning from extractions...")
    result1 = pipe.run("carteira_oab", schema, pdf_path)
    print("\nResults (Run 1):")
    for field_name, field_result in result1["results"].items():
        value = field_result.get("value")
        conf = field_result.get("confidence", 0.0)
        source = field_result.get("source", "none")
        trace = field_result.get("trace", {})
        memory_info = trace.get("memory", {})
        print(
            f"  {field_name}: {value} (conf={conf:.2f}, source={source}, "
            f"memory={bool(memory_info)})"
        )

    # Check if memory file was created
    memory_file = Path("data/artifacts/pattern_memory/carteira_oab.json")
    if memory_file.exists():
        print(f"\n[Memory] File created: {memory_file}")
        with open(memory_file, "r", encoding="utf-8") as f:
            memory_data = json.load(f)
            print(f"  Fields in memory: {list(memory_data.get('fields', {}).keys())}")
            for field_name, field_mem in memory_data.get("fields", {}).items():
                synonyms = field_mem.get("synonyms", [])
                offsets = field_mem.get("offsets", [])
                fingerprints = field_mem.get("fingerprints", [])
                print(f"    {field_name}:")
                print(f"      Synonyms: {len(synonyms)}")
                if synonyms:
                    print(f"        Examples: {[s['text'] for s in synonyms[:3]]}")
                print(f"      Offsets: {len(offsets)}")
                if offsets:
                    print(f"        Example: relation={offsets[0]['relation']}, dx={offsets[0]['dx']:.3f}, dy={offsets[0]['dy']:.3f}")
                print(f"      Fingerprints: {len(fingerprints)}")
    else:
        print("\n[Memory] File not created (memory disabled or no high-confidence extractions)")

    # Second run: should use learned patterns
    print("\n[Run 2] Second pass - using learned patterns...")
    result2 = pipe.run("carteira_oab", schema, pdf_path)

    print("\nResults (Run 2):")
    for field_name, field_result in result2["results"].items():
        value = field_result.get("value")
        conf = field_result.get("confidence", 0.0)
        source = field_result.get("source", "none")
        trace = field_result.get("trace", {})
        scores = trace.get("scores", {})
        memory_bonus = scores.get("memory", 0.0)
        print(
            f"  {field_name}: {value} (conf={conf:.2f}, source={source}, "
            f"memory_bonus={memory_bonus:.3f})"
        )

    # Compare results
    print("\n[Comparison]")
    for field_name in schema.keys():
        val1 = result1["results"].get(field_name, {}).get("value")
        conf1 = result1["results"].get(field_name, {}).get("confidence", 0.0)
        val2 = result2["results"].get(field_name, {}).get("value")
        conf2 = result2["results"].get(field_name, {}).get("confidence", 0.0)
        trace2 = result2["results"].get(field_name, {}).get("trace", {})
        memory_bonus = trace2.get("scores", {}).get("memory", 0.0)

        if val1 == val2:
            print(f"  {field_name}: Same value, conf {conf1:.2f} → {conf2:.2f} (memory bonus: {memory_bonus:.3f})")
        else:
            print(f"  {field_name}: Different values ({val1} vs {val2})")

    print("\n[Summary]")
    print("  ✓ PatternMemory should learn from Run 1")
    print("  ✓ Run 2 should show memory bonuses in trace")
    print("  ✓ Memory file should persist in data/artifacts/pattern_memory/")


if __name__ == "__main__":
    main()

