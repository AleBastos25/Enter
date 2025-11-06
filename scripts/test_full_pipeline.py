"""Script para testar todas as etapas do pipeline até o HTML final."""

import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page

def test_full_pipeline():
    """Testa todas as etapas do pipeline."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    html_path = project_root / "token_graph_overlay.html"
    
    print("="*80)
    print("TESTE COMPLETO DO PIPELINE")
    print("="*80)
    
    # ETAPA 1: Extração do PDF
    print("\n" + "="*80)
    print("ETAPA 1: EXTRAÇÃO DO PDF")
    print("="*80)
    
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    print(f"PDF Original: {pdf_original_width:.2f} x {pdf_original_height:.2f}")
    
    # Obter bbox RAW do PyMuPDF
    text_dict = page.get_text("dict")
    span_bbox_raw = None
    span_text_raw = None
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if "JOANA" in span_text and "ARC" in span_text:
                    span_bbox_raw = span.get("bbox")
                    span_text_raw = span_text
                    break
    
    if not span_bbox_raw:
        print("[ERRO] Span não encontrado!")
        return
    
    print(f"\n[OK] Span encontrado: '{span_text_raw}'")
    print(f"BBox RAW: {span_bbox_raw}")
    print(f"  x0: {span_bbox_raw[0]:.4f}")
    print(f"  y0: {span_bbox_raw[1]:.4f}")
    print(f"  x1: {span_bbox_raw[2]:.4f}")
    print(f"  y1: {span_bbox_raw[3]:.4f}")
    print(f"  Width: {span_bbox_raw[2] - span_bbox_raw[0]:.4f}")
    print(f"  Height: {span_bbox_raw[3] - span_bbox_raw[1]:.4f}")
    
    # ETAPA 2: Normalização e Padding
    print("\n" + "="*80)
    print("ETAPA 2: NORMALIZAÇÃO E PADDING")
    print("="*80)
    
    tokens = extract_tokens_from_page(str(pdf_path))
    joanadarc_token = None
    for token in tokens:
        if "JOANA" in token["text"] and "ARC" in token["text"]:
            joanadarc_token = token
            break
    
    if not joanadarc_token:
        print("[ERRO] Token não encontrado!")
        return
    
    bbox_norm = joanadarc_token["bbox"]
    print(f"\n[OK] Token normalizado: '{joanadarc_token['text']}'")
    print(f"BBox Normalizado: {bbox_norm}")
    print(f"  x0: {bbox_norm[0]:.8f}")
    print(f"  y0: {bbox_norm[1]:.8f}")
    print(f"  x1: {bbox_norm[2]:.8f}")
    print(f"  y1: {bbox_norm[3]:.8f}")
    
    # Verificar padding aplicado
    span_width = span_bbox_raw[2] - span_bbox_raw[0]
    padding_factor_right = 0.10
    min_padding_right = 15.0
    padding_right = max(span_width * padding_factor_right, min_padding_right)
    
    x1_expected = (span_bbox_raw[2] + padding_right) / pdf_original_width
    print(f"\n[VERIFICAÇÃO] Padding aplicado:")
    print(f"  padding_right: {padding_right:.4f} pontos")
    print(f"  x1 esperado (com padding): {x1_expected:.8f}")
    print(f"  x1 obtido: {bbox_norm[2]:.8f}")
    print(f"  Diferença: {abs(bbox_norm[2] - x1_expected):.8f}")
    
    # ETAPA 3: Renderização da Imagem
    print("\n" + "="*80)
    print("ETAPA 3: RENDERIZAÇÃO DA IMAGEM")
    print("="*80)
    
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pdf_rendered_width = pix.width
    pdf_rendered_height = pix.height
    
    print(f"Zoom: {zoom}x")
    print(f"Dimensões renderizadas: {pdf_rendered_width} x {pdf_rendered_height}")
    print(f"Esperado: {pdf_original_width * zoom:.2f} x {pdf_original_height * zoom:.2f}")
    
    # ETAPA 4: Conversão para Coordenadas Renderizadas
    print("\n" + "="*80)
    print("ETAPA 4: CONVERSÃO PARA COORDENADAS RENDERIZADAS")
    print("="*80)
    
    x0_render = bbox_norm[0] * pdf_rendered_width
    y0_render = bbox_norm[1] * pdf_rendered_height
    x1_render = bbox_norm[2] * pdf_rendered_width
    y1_render = bbox_norm[3] * pdf_rendered_height
    
    print(f"Coordenadas renderizadas:")
    print(f"  x0: {x0_render:.4f} pixels")
    print(f"  y0: {y0_render:.4f} pixels")
    print(f"  x1: {x1_render:.4f} pixels")
    print(f"  y1: {y1_render:.4f} pixels")
    print(f"  Width: {x1_render - x0_render:.4f} pixels")
    print(f"  Height: {y1_render - y0_render:.4f} pixels")
    
    # ETAPA 5: Verificar HTML Gerado
    print("\n" + "="*80)
    print("ETAPA 5: VERIFICAR HTML GERADO")
    print("="*80)
    
    if not html_path.exists():
        print("[ERRO] HTML não encontrado!")
        return
    
    html_content = html_path.read_text(encoding='utf-8')
    
    # Verificar se as dimensões renderizadas estão no JavaScript
    match = re.search(r'const pdfRenderedWidth = (\d+);', html_content)
    if match:
        html_rendered_width = int(match.group(1))
        print(f"\n[OK] pdfRenderedWidth no HTML: {html_rendered_width}")
        print(f"  Esperado: {pdf_rendered_width}")
        print(f"  Diferença: {abs(html_rendered_width - pdf_rendered_width)}")
    else:
        print("\n[ERRO] pdfRenderedWidth não encontrado no HTML!")
    
    match = re.search(r'const pdfRenderedHeight = (\d+);', html_content)
    if match:
        html_rendered_height = int(match.group(1))
        print(f"[OK] pdfRenderedHeight no HTML: {html_rendered_height}")
        print(f"  Esperado: {pdf_rendered_height}")
        print(f"  Diferença: {abs(html_rendered_height - pdf_rendered_height)}")
    
    # Verificar tokensData no HTML
    match = re.search(r'const tokensData = (\[.*?\]);', html_content, re.DOTALL)
    if match:
        try:
            tokens_data_str = match.group(1)
            tokens_data = json.loads(tokens_data_str)
            joana_token_html = None
            for token in tokens_data:
                if "JOANA" in token.get("text", "") and "ARC" in token.get("text", ""):
                    joana_token_html = token
                    break
            
            if joana_token_html:
                print(f"\n[OK] Token encontrado no HTML:")
                print(f"  ID: {joana_token_html['id']}")
                print(f"  Text: '{joana_token_html['text']}'")
                print(f"  BBox: {joana_token_html['bbox']}")
                print(f"  Comparação:")
                print(f"    x0: {joana_token_html['bbox'][0]:.8f} vs {bbox_norm[0]:.8f}")
                print(f"    x1: {joana_token_html['bbox'][2]:.8f} vs {bbox_norm[2]:.8f}")
        except Exception as e:
            print(f"\n[ERRO] Erro ao parsear tokensData: {e}")
    
    # Verificar cálculo no JavaScript
    print("\n" + "="*80)
    print("ETAPA 6: VERIFICAR CÁLCULO NO JAVASCRIPT")
    print("="*80)
    
    # Simular o que o JavaScript faz
    js_imgWidth = pdf_rendered_width
    js_bbox = bbox_norm
    js_x0 = js_bbox[0] * js_imgWidth
    js_x1 = js_bbox[2] * js_imgWidth
    js_width = js_x1 - js_x0
    
    print(f"JavaScript calcula (simulado):")
    print(f"  imgWidth = {js_imgWidth}")
    print(f"  x0 = {js_bbox[0]:.8f} * {js_imgWidth} = {js_x0:.4f}")
    print(f"  x1 = {js_bbox[2]:.8f} * {js_imgWidth} = {js_x1:.4f}")
    print(f"  width = {js_width:.4f}")
    
    # Com stroke adjustment
    stroke_width = 2
    stroke_half = stroke_width / 2
    js_adjusted_x0 = js_x0 - stroke_half
    js_adjusted_x1 = js_x1 + stroke_half
    js_adjusted_width = js_adjusted_x1 - js_adjusted_x0
    
    print(f"\nCom stroke adjustment:")
    print(f"  adjusted_x0 = {js_adjusted_x0:.4f}")
    print(f"  adjusted_x1 = {js_adjusted_x1:.4f}")
    print(f"  adjusted_width = {js_adjusted_width:.4f}")
    
    # HIPÓTESE: Verificar se há problema no SVG viewBox
    print("\n" + "="*80)
    print("ETAPA 7: VERIFICAR SVG VIEWBOX")
    print("="*80)
    
    # Procurar viewBox no HTML
    match = re.search(r"svg\.setAttribute\('viewBox', `0 0 (\d+) (\d+)`\);", html_content)
    if match:
        viewbox_width = int(match.group(1))
        viewbox_height = int(match.group(2))
        print(f"\n[OK] SVG viewBox encontrado:")
        print(f"  viewBox: 0 0 {viewbox_width} {viewbox_height}")
        print(f"  Esperado: 0 0 {pdf_rendered_width} {pdf_rendered_height}")
        print(f"  Diferença: {abs(viewbox_width - pdf_rendered_width)} x {abs(viewbox_height - pdf_rendered_height)}")
    
    # HIPÓTESE: Verificar se o problema está na renderização do retângulo
    print("\n" + "="*80)
    print("ETAPA 8: VERIFICAR RENDERIZAÇÃO DO RETÂNGULO")
    print("="*80)
    
    # Procurar criação do retângulo no JavaScript
    rect_pattern = r"rect\.setAttribute\('x', (.*?)\.toString\(\)\)"
    matches = re.findall(rect_pattern, html_content)
    if matches:
        print(f"[OK] Encontrados {len(matches)} retângulos no código")
    
    # Verificar se há problema com o cálculo do width
    width_pattern = r"rect\.setAttribute\('width', (.*?)\.toString\(\)\)"
    matches = re.findall(width_pattern, html_content)
    if matches:
        print(f"[OK] Encontrados {len(matches)} cálculos de width")
        # Verificar se o cálculo está correto
        if "x1 - x0" in matches[0] or "rectWidth" in matches[0]:
            print(f"  Cálculo parece correto: {matches[0]}")
    
    # HIPÓTESE FINAL: Verificar se há problema de precisão
    print("\n" + "="*80)
    print("ETAPA 9: ANÁLISE DE PRECISÃO")
    print("="*80)
    
    # Calcular bbox esperado do "RC" baseado no texto
    # Se "D'ARC" tem width de ~75 pontos, e "RC" está no final
    # O "C" deve estar aproximadamente em x1 - (largura_do_C)
    
    # Obter bbox de "D'ARC" separadamente
    words = page.get_text("words")
    darc_word = None
    for word in words:
        if "D'ARC" in word[4] or "D'ARC" in word[4]:
            darc_word = word
            break
    
    if darc_word:
        print(f"\n[OK] Palavra 'D'ARC' encontrada:")
        print(f"  BBox: {darc_word[0]:.2f}, {darc_word[1]:.2f}, {darc_word[2]:.2f}, {darc_word[3]:.2f}")
        print(f"  Width: {darc_word[2] - darc_word[0]:.2f}")
        print(f"  x1 da palavra: {darc_word[2]:.2f}")
        print(f"  x1 do span completo: {span_bbox_raw[2]:.4f}")
        print(f"  Diferença: {span_bbox_raw[2] - darc_word[2]:.4f}")
        print(f"  O span termina {span_bbox_raw[2] - darc_word[2]:.4f} pontos DEPOIS da palavra 'D'ARC'")
    
    doc.close()
    
    print("\n" + "="*80)
    print("RESUMO")
    print("="*80)
    print(f"\nPadding aplicado: {padding_right:.4f} pontos ({padding_right * 2:.4f} pixels)")
    print(f"x1 final renderizado: {js_adjusted_x1:.4f} pixels")
    print(f"Se o 'C' ainda está cortado, pode ser que o padding de {padding_right:.4f} pontos não seja suficiente.")

if __name__ == "__main__":
    test_full_pipeline()

