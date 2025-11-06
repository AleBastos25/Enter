"""Debug profundo de cada diferença entre output e ground truth."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline
from src.core.models import Document
from src.io.pdf_loader import load_document, extract_blocks
from src.core.schema import enrich_schema
from src.layout.builder import build_layout
from src.tables.detector import detect_tables
from src.matching.matcher import match_fields
from src.memory.pattern_memory import PatternMemory
from src.core.doc_profile import DocProfile
from src.core.policy import load_runtime_config


def load_json(file_path: str) -> Any:
    """Load JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def debug_single_pdf(pdf_name: str, label: str, schema_dict: Dict[str, str], pdf_path: str):
    """Debug um único PDF para entender de onde vem cada erro."""
    
    print(f"\n{'='*80}")
    print(f"DEBUG: {pdf_name}")
    print(f"{'='*80}\n")
    
    # Load document
    print("1. Loading document...")
    doc = load_document(pdf_path, label=label)
    print(f"   - Page count: {doc.meta.get('page_count', 1)}")
    
    # Enrich schema
    print("\n2. Enriching schema...")
    extraction_schema = enrich_schema(label, schema_dict)
    schema_fields = extraction_schema.fields
    print(f"   - Fields: {[f.name for f in schema_fields]}")
    for field in schema_fields:
        print(f"     - {field.name}: type={field.type}, synonyms={field.synonyms[:3] if field.synonyms else []}")
        if field.meta and field.meta.get("enum_options"):
            print(f"       enum_options={field.meta.get('enum_options')}")
    
    # Extract blocks
    print("\n3. Extracting blocks...")
    blocks = extract_blocks(doc)
    print(f"   - Total blocks: {len(blocks)}")
    print(f"   - Sample blocks (first 5):")
    for i, block in enumerate(blocks[:5]):
        print(f"     [{i}] {block.text[:50] if block.text else '(empty)'}")
    
    # Build layout
    print("\n4. Building layout...")
    layout = build_layout(doc, blocks)
    print(f"   - Layout built successfully")
    
    # Detect tables
    print("\n5. Detecting tables...")
    pdf_lines = getattr(layout, "pdf_lines", None)
    tables = detect_tables(layout, cfg=None, pdf_lines=pdf_lines)
    object.__setattr__(layout, "tables", tables)
    print(f"   - Tables found: {len(tables)}")
    
    # Build profile
    print("\n6. Building document profile...")
    profile = DocProfile.build(blocks, layout)
    print(f"   - Profile built")
    
    # Load pattern memory
    print("\n7. Loading pattern memory...")
    try:
        memory = PatternMemory()
        memory_cfg = {"use": {"max_synonyms_injection": 6}}
    except Exception as e:
        print(f"   - Memory not available: {e}")
        memory = None
        memory_cfg = None
    
    # Match fields
    print("\n8. Matching fields...")
    candidates_map = match_fields(
        schema_fields,
        layout,
        top_k=3,
        pattern_memory=memory,
        memory_cfg=memory_cfg,
    )
    
    print(f"\n9. Analyzing candidates for each field:")
    print("-" * 80)
    
    for field in schema_fields:
        field_name = field.name
        candidates = candidates_map.get(field_name, [])
        
        print(f"\nField: {field_name}")
        print(f"  Type: {field.type}")
        print(f"  Synonyms: {field.synonyms[:5] if field.synonyms else []}")
        print(f"  Candidates found: {len(candidates)}")
        
        if not candidates:
            print("  ❌ PROBLEMA: Nenhum candidato encontrado!")
            print("     Possíveis causas:")
            print("     - Labels não foram encontrados no documento")
            print("     - Neighborhood não está funcionando")
            print("     - Type gate rejeitou todos os candidatos")
            continue
        
        # Analisar cada candidato
        for i, cand in enumerate(candidates[:3]):
            print(f"\n  Candidate #{i+1}:")
            
            if isinstance(cand, dict):
                # v2 Candidate
                block_id = cand.get("block_id")
                relation = cand.get("relation")
                text_window = cand.get("text_window", "")
                score_tuple = cand.get("score_tuple", ())
                roi_info = cand.get("roi_info", {})
                
                print(f"    Block ID: {block_id}")
                print(f"    Relation: {relation}")
                print(f"    Text window: {repr(text_window[:100])}")
                print(f"    Score tuple: {score_tuple}")
                
                # Get block text
                block = next((b for b in layout.blocks if b.id == block_id), None)
                if block:
                    print(f"    Block text: {repr(block.text[:100] if block.text else '')}")
                
                # Try extraction
                from src.extraction.text_extractor import extract_from_candidate
                value, confidence, trace = extract_from_candidate(field, cand, layout)
                
                print(f"    Extraction result:")
                print(f"      Value: {repr(value)}")
                print(f"      Confidence: {confidence}")
                print(f"      Trace reason: {trace.get('reason', 'success')}")
                
                if value is None:
                    print(f"    ❌ REJEITADO: {trace.get('reason', 'unknown')}")
                    if 'label_only' in str(trace.get('reason', '')):
                        print(f"      ⚠️  Texto é apenas label, não valor!")
            else:
                # Legacy FieldCandidate
                print(f"    Node ID: {cand.node_id}")
                print(f"    Relation: {cand.relation}")
    
    # Run full pipeline to get final results
    print(f"\n10. Running full pipeline...")
    pipeline = Pipeline()
    result = pipeline.run(label, schema_dict, pdf_path, debug=False)
    
    print(f"\n11. Final results:")
    results = result.get("results", {})
    for field_name in schema_dict.keys():
        field_result = results.get(field_name, {})
        value = field_result.get("value") if isinstance(field_result, dict) else field_result
        source = field_result.get("source", "unknown") if isinstance(field_result, dict) else "unknown"
        print(f"   {field_name}: {repr(value)} (source: {source})")
    
    return result


def main():
    """Main function."""
    # Load ground truth and current output
    ground_truth = load_json("ground_truth.json")
    current_output = load_json("output_debug.json")
    
    # Load dataset to get schemas
    dataset = load_json("data/samples/dataset.json")
    pdf_to_schema = {}
    for entry in dataset:
        pdf_name = Path(entry.get("pdf_path", "")).name
        label = entry.get("label")
        schema_dict = entry.get("extraction_schema", {})
        if label and schema_dict:
            pdf_to_schema[pdf_name] = (label, schema_dict)
    
    # Build comparison
    gt_by_pdf = {item["pdf"]: item["result"] for item in ground_truth}
    current_by_pdf = {item["pdf"]: item["result"] for item in current_output}
    
    # Find all differences
    all_pdfs = sorted(set(gt_by_pdf.keys()) | set(current_by_pdf.keys()))
    
    print("="*80)
    print("DEBUG PROFUNDO - ANALISANDO CADA DIFERENCA")
    print("="*80)
    
    for pdf_name in all_pdfs:
        if pdf_name not in pdf_to_schema:
            print(f"\n⚠️  {pdf_name}: Schema não encontrado no dataset.json")
            continue
        
        gt_result = gt_by_pdf.get(pdf_name, {})
        current_result = current_by_pdf.get(pdf_name, {})
        
        # Check if there are differences
        has_differences = False
        for field_name in set(list(gt_result.keys()) + list(current_result.keys())):
            gt_value = gt_result.get(field_name)
            current_value = current_result.get(field_name)
            if gt_value != current_value:
                has_differences = True
                break
        
        if not has_differences:
            print(f"\n✓ {pdf_name}: Sem diferenças")
            continue
        
        # Debug this PDF
        label, schema_dict = pdf_to_schema[pdf_name]
        pdf_path = f"data/samples/{pdf_name}"
        
        if not Path(pdf_path).exists():
            print(f"\n⚠️  {pdf_name}: Arquivo não encontrado")
            continue
        
        try:
            debug_single_pdf(pdf_name, label, schema_dict, pdf_path)
        except Exception as e:
            print(f"\nERRO ao processar {pdf_name}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()

