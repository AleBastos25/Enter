"""Script para analisar a largura real dos caracteres."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF

def analyze_char_width():
    """Analisa a largura real dos caracteres."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    print("="*80)
    print("ANÁLISE DE LARGURA REAL DOS CARACTERES")
    print("="*80)
    
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    
    text_dict = page.get_text("dict")
    
    # Analisar vários spans para calcular o fator real
    spans_data = []
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if len(span_text) > 3 and not span_text.startswith(' '):  # Ignorar spans muito pequenos ou com espaço inicial
                    span_bbox = span.get("bbox")
                    font_size = span.get("size", 0)
                    
                    if font_size > 0:
                        span_width = span_bbox[2] - span_bbox[0]
                        char_count = len(span_text)
                        avg_char_width_real = span_width / char_count if char_count > 0 else 0
                        factor = avg_char_width_real / font_size if font_size > 0 else 0
                        
                        spans_data.append({
                            'text': span_text[:30],
                            'font_size': font_size,
                            'width': span_width,
                            'chars': char_count,
                            'avg_char_width': avg_char_width_real,
                            'factor': factor
                        })
    
    # Calcular fator médio
    if spans_data:
        factors = [s['factor'] for s in spans_data if s['factor'] > 0]
        avg_factor = sum(factors) / len(factors) if factors else 0
        
        print(f"\nAnalisados {len(spans_data)} spans")
        print(f"Fator médio (largura_char / font_size): {avg_factor:.4f}")
        print(f"Fator atual usado: 0.6")
        print(f"Diferença: {abs(avg_factor - 0.6):.4f}")
        
        # Mostrar alguns exemplos
        print(f"\nPrimeiros 10 exemplos:")
        for i, s in enumerate(spans_data[:10]):
            print(f"  {i+1}. '{s['text'][:20]}' | font={s['font_size']:.1f} | width={s['width']:.2f} | chars={s['chars']} | factor={s['factor']:.4f}")
        
        # Verificar spans específicos
        print(f"\n" + "="*80)
        print("SPANS ESPECÍFICOS")
        print("="*80)
        
        for name_match in ["Telefone Profissional", "JOANA D'ARC", "SITUAÇÃO REGULAR"]:
            for s in spans_data:
                if name_match.split()[0] in s['text'] and name_match.split()[-1] in s['text']:
                    print(f"\n{name_match}:")
                    print(f"  Text: '{s['text']}'")
                    print(f"  Font Size: {s['font_size']}")
                    print(f"  Width: {s['width']:.4f}")
                    print(f"  Chars: {s['chars']}")
                    print(f"  Avg Char Width Real: {s['avg_char_width']:.4f}")
                    print(f"  Factor Real: {s['factor']:.4f}")
                    print(f"  Estimated com 0.6: {s['font_size'] * 0.6 * s['chars']:.4f}")
                    print(f"  Estimated com {avg_factor:.4f}: {s['font_size'] * avg_factor * s['chars']:.4f}")
                    break
    
    doc.close()

if __name__ == "__main__":
    analyze_char_width()

