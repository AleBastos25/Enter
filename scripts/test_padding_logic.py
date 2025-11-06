"""Script para testar a lógica de padding."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page
import fitz

def test_padding_logic():
    """Testa a lógica de padding."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    print("="*80)
    print("TESTE DA LÓGICA DE PADDING")
    print("="*80)
    
    # Extrair tokens
    tokens = extract_tokens_from_page(str(pdf_path))
    
    # Abrir PDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    
    # Encontrar tokens de interesse
    situacao_token = None
    joana_token = None
    
    for token in tokens:
        if "SITUAÇÃO" in token["text"] and "REGULAR" in token["text"]:
            situacao_token = token
        if "JOANA" in token["text"] and "ARC" in token["text"]:
            joana_token = token
    
    # Obter spans RAW
    text_dict = page.get_text("dict")
    situacao_span_raw = None
    joana_span_raw = None
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if "SITUAÇÃO" in span_text and "REGULAR" in span_text:
                    situacao_span_raw = span
                if "JOANA" in span_text and "ARC" in span_text:
                    joana_span_raw = span
    
    def check_padding_logic(span, token, name):
        """Verifica a lógica de padding para um span."""
        span_text = span.get("text", "").strip()
        span_bbox = span.get("bbox")
        font_size = span.get("size", 0)
        
        span_width = span_bbox[2] - span_bbox[0]
        avg_char_width = font_size * 0.6 if font_size > 0 else span_width / max(len(span_text), 1)
        estimated_text_width = len(span_text) * avg_char_width
        bbox_has_extra_space = span_width > estimated_text_width * 1.02
        
        # NOVA LÓGICA SIMPLIFICADA: sempre adicionar padding
        padding_factor_right = 0.08  # 8% de padding na largura
        min_padding_right = 12.0  # Mínimo de 12 pontos à direita
        padding_right = max(span_width * padding_factor_right, min_padding_right)
        
        x1_with_padding = span_bbox[2] + padding_right
        x1_norm_expected = x1_with_padding / pdf_original_width
        x1_norm_actual = token["bbox"][2]
        
        print(f"\n{name}:")
        print(f"  Text: '{span_text}'")
        print(f"  Font Size: {font_size}")
        print(f"  Span Width: {span_width:.4f}")
        print(f"  Estimated Text Width: {estimated_text_width:.4f}")
        print(f"  Bbox has extra space: {bbox_has_extra_space}")
        print(f"  Padding aplicado: {padding_right:.4f}")
        print(f"  x1 original: {span_bbox[2]:.4f}")
        print(f"  x1 com padding: {x1_with_padding:.4f}")
        print(f"  x1 normalizado esperado: {x1_norm_expected:.8f}")
        print(f"  x1 normalizado obtido: {x1_norm_actual:.8f}")
        print(f"  Diferença: {abs(x1_norm_actual - x1_norm_expected):.8f}")
        
        return padding_right
    
    if joana_token and joana_span_raw:
        joana_padding = check_padding_logic(joana_span_raw, joana_token, "JOANA D'ARC")
    
    if situacao_token and situacao_span_raw:
        situacao_padding = check_padding_logic(situacao_span_raw, situacao_token, "SITUAÇÃO REGULAR")
    
    doc.close()
    
    print("\n" + "="*80)
    print("RESUMO")
    print("="*80)
    if joana_token and situacao_token:
        print(f"\nJOANA D'ARC recebeu padding: {joana_padding:.4f} pontos")
        print(f"SITUAÇÃO REGULAR recebeu padding: {situacao_padding:.4f} pontos")
        print(f"\nDiferença: {abs(joana_padding - situacao_padding):.4f} pontos")

if __name__ == "__main__":
    test_padding_logic()

