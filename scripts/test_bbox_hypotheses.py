"""Script para testar hipóteses sobre o problema do bbox."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page

def test_hypotheses():
    """Testa diferentes hipóteses sobre o problema do bbox."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    # Abrir PDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    print("="*80)
    print("TESTE DE HIPOTESES: PROBLEMA DO BBOX")
    print("="*80)
    
    # Extrair tokens
    tokens = extract_tokens_from_page(str(pdf_path))
    
    # Encontrar token JOANA D'ARC
    joanadarc_token = None
    for token in tokens:
        if "JOANA" in token["text"] and "ARC" in token["text"]:
            joanadarc_token = token
            break
    
    if not joanadarc_token:
        print("\n[ERRO] Token não encontrado!")
        return
    
    print(f"\n[OK] Token: '{joanadarc_token['text']}'")
    print(f"   Tamanho do texto: {len(joanadarc_token['text'])} caracteres")
    
    # HIPÓTESE 1: Verificar caracteres especiais e espaçamento
    print("\n" + "="*80)
    print("HIPOTESE 1: Caracteres especiais e espaçamento")
    print("="*80)
    
    text = joanadarc_token['text']
    print(f"\nTexto: '{text}'")
    print(f"Repr: {repr(text)}")
    print(f"\nAnálise de caracteres:")
    for i, char in enumerate(text):
        code = ord(char)
        print(f"  [{i}] '{char}' (U+{code:04X}) - {code}")
    
    # Verificar se há espaços ou caracteres especiais
    has_space = ' ' in text
    has_apostrophe = "'" in text or "'" in text
    print(f"\nTem espaço: {has_space}")
    print(f"Tem apóstrofo: {has_apostrophe}")
    
    # HIPÓTESE 2: Obter bbox RAW e verificar se há caracteres individuais
    print("\n" + "="*80)
    print("HIPOTESE 2: Bbox RAW do PyMuPDF e caracteres individuais")
    print("="*80)
    
    text_dict = page.get_text("dict")
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            spans = line_dict.get("spans", [])
            
            # Verificar se o texto está em um único span ou múltiplos
            matching_spans = [s for s in spans if "JOANA" in s.get("text", "").strip() and "ARC" in s.get("text", "").strip()]
            
            if matching_spans:
                print(f"\n[SPAN] Encontrado {len(matching_spans)} span(s) contendo 'JOANA D'ARC'")
                
                for idx, span in enumerate(matching_spans):
                    span_text = span.get("text", "").strip()
                    span_bbox = span.get("bbox")
                    font_size = span.get("size", 0)
                    font_name = span.get("font", "")
                    
                    print(f"\n  Span {idx}:")
                    print(f"    Texto: '{span_text}'")
                    print(f"    Font: {font_name}")
                    print(f"    Font Size: {font_size}")
                    print(f"    BBox: {span_bbox}")
                    print(f"    Width: {span_bbox[2] - span_bbox[0]:.4f}")
                    print(f"    Height: {span_bbox[3] - span_bbox[1]:.4f}")
                    
                    # HIPÓTESE 3: Verificar se podemos obter bbox de caracteres individuais
                    print(f"\n  [HIPOTESE 3] Tentando obter bbox de caracteres individuais...")
                    
                    # Tentar obter bbox de cada caractere usando get_text("words") ou "chars"
                    try:
                        # Obter palavras
                        words = page.get_text("words")
                        matching_words = [w for w in words if "JOANA" in w[4] or "ARC" in w[4]]
                        if matching_words:
                            print(f"    Encontradas {len(matching_words)} palavras relacionadas:")
                            for w in matching_words[:5]:  # Primeiras 5
                                print(f"      '{w[4]}' bbox: {w[0]:.2f}, {w[1]:.2f}, {w[2]:.2f}, {w[3]:.2f}")
                        
                        # Obter caracteres individuais
                        chars = page.get_text("rawdict")
                        # Tentar encontrar caracteres do texto
                        print(f"    Método get_text('rawdict') retornou: {type(chars)}")
                        
                    except Exception as e:
                        print(f"    Erro ao obter caracteres: {e}")
                    
                    # HIPÓTESE 4: Verificar se o problema é kerning (espaçamento entre letras)
                    print(f"\n  [HIPOTESE 4] Verificando espaçamento entre letras...")
                    span_width = span_bbox[2] - span_bbox[0]
                    char_count = len(span_text.replace(' ', ''))  # Contar sem espaços
                    avg_char_width = span_width / char_count if char_count > 0 else 0
                    print(f"    Largura total: {span_width:.4f}")
                    print(f"    Caracteres (sem espaços): {char_count}")
                    print(f"    Largura média por caractere: {avg_char_width:.4f}")
                    
                    # Verificar se "RC" pode ter mais espaçamento
                    if "RC" in span_text:
                        r_pos = span_text.find("RC")
                        print(f"    Posição de 'RC' no texto: {r_pos}")
                        print(f"    'RC' pode ter kerning especial (espaçamento entre R e C)")
    
    # HIPÓTESE 5: Testar diferentes valores de padding
    print("\n" + "="*80)
    print("HIPOTESE 5: Testar diferentes valores de padding")
    print("="*80)
    
    span_bbox_raw = (5.0, 6.0, 170.9, 40.35)  # Do debug anterior
    span_width = span_bbox_raw[2] - span_bbox_raw[0]
    span_height = span_bbox_raw[3] - span_bbox_raw[1]
    
    print(f"\nBBox RAW: {span_bbox_raw}")
    print(f"Width: {span_width:.4f}, Height: {span_height:.4f}")
    
    padding_values = [
        (0.01, 2.0, "Atual (1% + 2pt mínimo)"),
        (0.02, 3.0, "2% + 3pt mínimo"),
        (0.03, 4.0, "3% + 4pt mínimo"),
        (0.05, 5.0, "5% + 5pt mínimo"),
    ]
    
    zoom = 2.0
    for padding_factor, min_padding, desc in padding_values:
        padding_x = max(span_width * padding_factor, min_padding)
        padding_y = max(span_height * padding_factor, min_padding)
        
        x1_with_padding = span_bbox_raw[2] + padding_x
        x1_render = (x1_with_padding / pdf_original_width) * (pdf_original_width * zoom)
        
        # Com stroke adjustment
        stroke_half = 1.0
        x1_final = x1_render + stroke_half
        
        print(f"\n{desc}:")
        print(f"  padding_x: {padding_x:.4f} pontos")
        print(f"  x1 com padding: {x1_with_padding:.4f} pontos")
        print(f"  x1 renderizado: {x1_render:.4f} pixels")
        print(f"  x1 final (com stroke): {x1_final:.4f} pixels")
        print(f"  Expansão total: {x1_final - (span_bbox_raw[2] * zoom):.4f} pixels")
    
    # HIPÓTESE 6: Verificar se há algum problema na renderização da imagem vs SVG
    print("\n" + "="*80)
    print("HIPOTESE 6: Verificar renderização")
    print("="*80)
    
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    rendered_width = pix.width
    rendered_height = pix.height
    
    print(f"\nDimensões renderizadas: {rendered_width} x {rendered_height}")
    print(f"Zoom aplicado: {zoom}x")
    print(f"Esperado: {pdf_original_width * zoom} x {pdf_original_height * zoom}")
    
    # Verificar se há diferença
    expected_width = pdf_original_width * zoom
    expected_height = pdf_original_height * zoom
    if abs(rendered_width - expected_width) > 0.1:
        print(f"  [AVISO] Largura renderizada diferente do esperado!")
        print(f"    Esperado: {expected_width:.2f}")
        print(f"    Obtido: {rendered_width}")
    
    doc.close()

if __name__ == "__main__":
    test_hypotheses()

