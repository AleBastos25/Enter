"""Script para comparar o token 'SITUAÇÃO REGULAR' com outros tokens."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page

def compare_tokens():
    """Compara o token 'SITUAÇÃO REGULAR' com outros tokens."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    print("="*80)
    print("COMPARAÇÃO: SITUAÇÃO REGULAR vs OUTROS TOKENS")
    print("="*80)
    
    # Extrair tokens
    tokens = extract_tokens_from_page(str(pdf_path))
    
    # Encontrar tokens de interesse
    situacao_token = None
    joana_token = None
    
    for token in tokens:
        if "SITUAÇÃO" in token["text"] and "REGULAR" in token["text"]:
            situacao_token = token
        if "JOANA" in token["text"] and "ARC" in token["text"]:
            joana_token = token
    
    if not situacao_token:
        print("\n[ERRO] Token 'SITUAÇÃO REGULAR' não encontrado!")
        return
    
    if not joana_token:
        print("\n[ERRO] Token 'JOANA D'ARC' não encontrado!")
        return
    
    # Abrir PDF para obter bbox RAW
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    text_dict = page.get_text("dict")
    
    # Obter spans RAW
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
    
    if not situacao_span_raw or not joana_span_raw:
        print("\n[ERRO] Spans não encontrados!")
        doc.close()
        return
    
    print("\n" + "="*80)
    print("COMPARAÇÃO: JOANA D'ARC")
    print("="*80)
    
    print(f"\nToken normalizado:")
    print(f"  Text: '{joana_token['text']}'")
    print(f"  BBox: {joana_token['bbox']}")
    
    print(f"\nSpan RAW do PyMuPDF:")
    joana_bbox_raw = joana_span_raw.get("bbox")
    print(f"  Text: '{joana_span_raw.get('text', '').strip()}'")
    print(f"  BBox RAW: {joana_bbox_raw}")
    print(f"  Font: {joana_span_raw.get('font', 'N/A')}")
    print(f"  Font Size: {joana_span_raw.get('size', 'N/A')}")
    print(f"  Width: {joana_bbox_raw[2] - joana_bbox_raw[0]:.4f}")
    
    # Calcular padding aplicado
    joana_width = joana_bbox_raw[2] - joana_bbox_raw[0]
    padding_factor = 0.10
    min_padding = 15.0
    joana_padding = max(joana_width * padding_factor, min_padding)
    joana_x1_expected = joana_bbox_raw[2] + joana_padding
    
    print(f"\nPadding aplicado:")
    print(f"  Width: {joana_width:.4f}")
    print(f"  Padding: {joana_padding:.4f} pontos")
    print(f"  x1 original: {joana_bbox_raw[2]:.4f}")
    print(f"  x1 com padding: {joana_x1_expected:.4f}")
    print(f"  x1 normalizado: {joana_token['bbox'][2]:.8f}")
    print(f"  x1 esperado (normalizado): {joana_x1_expected / pdf_original_width:.8f}")
    
    print("\n" + "="*80)
    print("COMPARAÇÃO: SITUAÇÃO REGULAR")
    print("="*80)
    
    print(f"\nToken normalizado:")
    print(f"  Text: '{situacao_token['text']}'")
    print(f"  BBox: {situacao_token['bbox']}")
    
    print(f"\nSpan RAW do PyMuPDF:")
    situacao_bbox_raw = situacao_span_raw.get("bbox")
    print(f"  Text: '{situacao_span_raw.get('text', '').strip()}'")
    print(f"  BBox RAW: {situacao_bbox_raw}")
    print(f"  Font: {situacao_span_raw.get('font', 'N/A')}")
    print(f"  Font Size: {situacao_span_raw.get('size', 'N/A')}")
    print(f"  Width: {situacao_bbox_raw[2] - situacao_bbox_raw[0]:.4f}")
    
    # Calcular padding aplicado
    situacao_width = situacao_bbox_raw[2] - situacao_bbox_raw[0]
    situacao_padding = max(situacao_width * padding_factor, min_padding)
    situacao_x1_expected = situacao_bbox_raw[2] + situacao_padding
    
    print(f"\nPadding aplicado:")
    print(f"  Width: {situacao_width:.4f}")
    print(f"  Padding: {situacao_padding:.4f} pontos")
    print(f"  x1 original: {situacao_bbox_raw[2]:.4f}")
    print(f"  x1 com padding: {situacao_x1_expected:.4f}")
    print(f"  x1 normalizado: {situacao_token['bbox'][2]:.8f}")
    print(f"  x1 esperado (normalizado): {situacao_x1_expected / pdf_original_width:.8f}")
    
    print("\n" + "="*80)
    print("ANÁLISE DE DIFERENÇAS")
    print("="*80)
    
    # Comparar
    print(f"\nDiferenças:")
    print(f"  JOANA - Width: {joana_width:.4f}, Padding: {joana_padding:.4f}")
    print(f"  SITUAÇÃO - Width: {situacao_width:.4f}, Padding: {situacao_padding:.4f}")
    
    # Verificar se há diferença no texto RAW vs normalizado
    joana_text_raw = joana_span_raw.get("text", "").strip()
    joana_text_token = joana_token['text']
    situacao_text_raw = situacao_span_raw.get("text", "").strip()
    situacao_text_token = situacao_token['text']
    
    print(f"\nComparação de texto:")
    print(f"  JOANA RAW: '{joana_text_raw}'")
    print(f"  JOANA Token: '{joana_text_token}'")
    print(f"  São iguais: {joana_text_raw == joana_text_token}")
    
    print(f"  SITUAÇÃO RAW: '{situacao_text_raw}'")
    print(f"  SITUAÇÃO Token: '{situacao_text_token}'")
    print(f"  São iguais: {situacao_text_raw == situacao_text_token}")
    
    # Verificar se há múltiplos spans
    print(f"\nVerificando se há múltiplos spans...")
    
    # Verificar se o texto está em múltiplos spans
    joana_spans = []
    situacao_spans = []
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if "JOANA" in span_text and "ARC" in span_text:
                    joana_spans.append(span)
                if "SITUAÇÃO" in span_text and "REGULAR" in span_text:
                    situacao_spans.append(span)
    
    print(f"  JOANA spans encontrados: {len(joana_spans)}")
    print(f"  SITUAÇÃO spans encontrados: {len(situacao_spans)}")
    
    if len(situacao_spans) > 1:
        print(f"\n[PROBLEMA POTENCIAL] 'SITUAÇÃO REGULAR' está em {len(situacao_spans)} spans!")
        for i, span in enumerate(situacao_spans):
            print(f"    Span {i}: '{span.get('text', '').strip()}' bbox: {span.get('bbox')}")
    
    # Verificar se há espaços ou caracteres especiais
    print(f"\nAnálise de caracteres:")
    print(f"  JOANA tem espaço: {' ' in joana_text_raw}")
    print(f"  SITUAÇÃO tem espaço: {' ' in situacao_text_raw}")
    
    # Verificar se o bbox normalizado está correto
    print(f"\nVerificação de bbox normalizado:")
    joana_x1_norm_expected = (joana_bbox_raw[2] + joana_padding) / pdf_original_width
    situacao_x1_norm_expected = (situacao_bbox_raw[2] + situacao_padding) / pdf_original_width
    
    print(f"  JOANA x1 normalizado obtido: {joana_token['bbox'][2]:.8f}")
    print(f"  JOANA x1 normalizado esperado: {joana_x1_norm_expected:.8f}")
    print(f"  Diferença: {abs(joana_token['bbox'][2] - joana_x1_norm_expected):.8f}")
    
    print(f"  SITUAÇÃO x1 normalizado obtido: {situacao_token['bbox'][2]:.8f}")
    print(f"  SITUAÇÃO x1 normalizado esperado: {situacao_x1_norm_expected:.8f}")
    print(f"  Diferença: {abs(situacao_token['bbox'][2] - situacao_x1_norm_expected):.8f}")
    
    doc.close()

if __name__ == "__main__":
    compare_tokens()

