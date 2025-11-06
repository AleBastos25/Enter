"""Script para verificar se o bbox do PyMuPDF está correto comparado ao texto real."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF

def check_bbox_accuracy():
    """Verifica a precisão do bbox comparando com o texto real."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    print("="*80)
    print("VERIFICAÇÃO DE PRECISÃO DO BBOX")
    print("="*80)
    
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    text_dict = page.get_text("dict")
    
    # Encontrar spans de interesse
    spans_to_check = []
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if "JOANA" in span_text and "ARC" in span_text:
                    spans_to_check.append(("JOANA D'ARC", span))
                if "SITUAÇÃO" in span_text and "REGULAR" in span_text:
                    spans_to_check.append(("SITUAÇÃO REGULAR", span))
                if "Inscrição" in span_text:
                    spans_to_check.append(("Inscrição", span))
    
    print(f"\nEncontrados {len(spans_to_check)} spans para verificar\n")
    
    for name, span in spans_to_check:
        span_text = span.get("text", "").strip()
        span_bbox = span.get("bbox")
        font_size = span.get("size", 0)
        
        span_width = span_bbox[2] - span_bbox[0]
        span_height = span_bbox[3] - span_bbox[1]
        
        # Estimar largura do texto baseado no tamanho da fonte
        # Aproximação: largura média de caractere = font_size * 0.6 (para Helvetica)
        avg_char_width = font_size * 0.6
        estimated_width = len(span_text) * avg_char_width
        
        # Calcular diferença
        width_diff = span_width - estimated_width
        width_diff_percent = (width_diff / span_width) * 100 if span_width > 0 else 0
        
        print(f"{name}:")
        print(f"  Text: '{span_text}'")
        print(f"  Font Size: {font_size}")
        print(f"  Text Length: {len(span_text)} caracteres")
        print(f"  BBox Width: {span_width:.4f} pontos")
        print(f"  Estimated Width (font_size * 0.6 * chars): {estimated_width:.4f} pontos")
        print(f"  Diferença: {width_diff:.4f} pontos ({width_diff_percent:.2f}%)")
        
        if width_diff > 0:
            print(f"  [INFO] O bbox é {width_diff:.4f} pontos MAIOR que o texto estimado")
            print(f"         Isso indica espaço vazio no bbox")
        elif width_diff < 0:
            print(f"  [AVISO] O bbox é {abs(width_diff):.4f} pontos MENOR que o texto estimado")
            print(f"         Isso indica que o texto pode estar cortado")
        else:
            print(f"  [OK] O bbox parece estar correto")
        
        print()
    
    # Verificar se há espaços no início/fim do texto
    print("="*80)
    print("VERIFICAÇÃO DE ESPAÇOS NO TEXTO")
    print("="*80)
    
    for name, span in spans_to_check:
        span_text = span.get("text", "")
        span_text_stripped = span_text.strip()
        
        leading_spaces = len(span_text) - len(span_text.lstrip())
        trailing_spaces = len(span_text) - len(span_text.rstrip())
        
        print(f"\n{name}:")
        print(f"  Text original: {repr(span_text)}")
        print(f"  Text stripped: {repr(span_text_stripped)}")
        print(f"  Espaços no início: {leading_spaces}")
        print(f"  Espaços no fim: {trailing_spaces}")
        
        if leading_spaces > 0 or trailing_spaces > 0:
            print(f"  [AVISO] O texto tem espaços que podem afetar o bbox")
    
    doc.close()

if __name__ == "__main__":
    check_bbox_accuracy()

