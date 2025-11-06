"""Script para testar hipóteses sobre a renderização do SVG."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page
import json

def test_svg_rendering():
    """Testa diferentes hipóteses sobre a renderização do SVG."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    # Abrir PDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    print("="*80)
    print("TESTE DE HIPOTESES: RENDERIZACAO SVG")
    print("="*80)
    
    # Renderizar com zoom
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pdf_rendered_width = pix.width
    pdf_rendered_height = pix.height
    
    print(f"\nPDF Original: {pdf_original_width:.2f} x {pdf_original_height:.2f}")
    print(f"PDF Renderizado (zoom {zoom}x): {pdf_rendered_width} x {pdf_rendered_height}")
    print(f"Fator de escala: {pdf_rendered_width/pdf_original_width:.4f}x")
    
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
    bbox_norm = joanadarc_token["bbox"]
    print(f"BBox Normalizado: {bbox_norm}")
    
    # HIPÓTESE 1: Verificar se o bbox normalizado está correto
    print("\n" + "="*80)
    print("HIPOTESE 1: Conversão de coordenadas")
    print("="*80)
    
    # Converter bbox normalizado para coordenadas originais
    x0_orig = bbox_norm[0] * pdf_original_width
    y0_orig = bbox_norm[1] * pdf_original_height
    x1_orig = bbox_norm[2] * pdf_original_width
    y1_orig = bbox_norm[3] * pdf_original_height
    
    print(f"\nBBox em coordenadas originais (points):")
    print(f"  x0: {x0_orig:.4f}")
    print(f"  y0: {y0_orig:.4f}")
    print(f"  x1: {x1_orig:.4f}")
    print(f"  y1: {y1_orig:.4f}")
    print(f"  Width: {x1_orig - x0_orig:.4f}")
    print(f"  Height: {y1_orig - y0_orig:.4f}")
    
    # Converter para coordenadas renderizadas
    x0_render = bbox_norm[0] * pdf_rendered_width
    y0_render = bbox_norm[1] * pdf_rendered_height
    x1_render = bbox_norm[2] * pdf_rendered_width
    y1_render = bbox_norm[3] * pdf_rendered_height
    
    print(f"\nBBox em coordenadas renderizadas (pixels):")
    print(f"  x0: {x0_render:.4f}")
    print(f"  y0: {y0_render:.4f}")
    print(f"  x1: {x1_render:.4f}")
    print(f"  y1: {y1_render:.4f}")
    print(f"  Width: {x1_render - x0_render:.4f}")
    print(f"  Height: {y1_render - y0_render:.4f}")
    
    # Verificar se a conversão está correta
    expected_width_render = (x1_orig - x0_orig) * zoom
    actual_width_render = x1_render - x0_render
    print(f"\nVerificação:")
    print(f"  Largura esperada (original * zoom): {expected_width_render:.4f}")
    print(f"  Largura calculada (normalizado * renderizado): {actual_width_render:.4f}")
    print(f"  Diferença: {abs(actual_width_render - expected_width_render):.4f}")
    
    # HIPÓTESE 2: Verificar o que o JavaScript está fazendo
    print("\n" + "="*80)
    print("HIPOTESE 2: Cálculo no JavaScript")
    print("="*80)
    
    # Simular o que o JavaScript faz
    imgWidth = pdf_rendered_width
    imgHeight = pdf_rendered_height
    
    # O que o JavaScript faz (do código HTML)
    js_x0 = bbox_norm[0] * imgWidth
    js_y0 = bbox_norm[1] * imgHeight
    js_x1 = bbox_norm[2] * imgWidth
    js_y1 = bbox_norm[3] * imgHeight
    
    print(f"\nJavaScript calcula:")
    print(f"  x0 = bbox[0] * imgWidth = {bbox_norm[0]:.8f} * {imgWidth} = {js_x0:.4f}")
    print(f"  x1 = bbox[2] * imgWidth = {bbox_norm[2]:.8f} * {imgWidth} = {js_x1:.4f}")
    print(f"  width = x1 - x0 = {js_x1 - js_x0:.4f}")
    
    # Com stroke adjustment
    stroke_width = 2
    stroke_half = stroke_width / 2
    js_adjusted_x0 = js_x0 - stroke_half
    js_adjusted_x1 = js_x1 + stroke_half
    js_adjusted_width = js_adjusted_x1 - js_adjusted_x0
    
    print(f"\nCom stroke adjustment (stroke_width={stroke_width}):")
    print(f"  adjusted_x0 = x0 - {stroke_half} = {js_adjusted_x0:.4f}")
    print(f"  adjusted_x1 = x1 + {stroke_half} = {js_adjusted_x1:.4f}")
    print(f"  adjusted_width = {js_adjusted_width:.4f}")
    
    # HIPÓTESE 3: Verificar se o SVG viewBox está correto
    print("\n" + "="*80)
    print("HIPOTESE 3: SVG viewBox e dimensões")
    print("="*80)
    
    print(f"\nSVG viewBox configurado como: '0 0 {imgWidth} {imgHeight}'")
    print(f"SVG width/height: '100%'")
    print(f"SVG preserveAspectRatio: 'none'")
    
    # HIPÓTESE 4: Verificar bbox RAW do PyMuPDF
    print("\n" + "="*80)
    print("HIPOTESE 4: Bbox RAW do PyMuPDF vs Normalizado")
    print("="*80)
    
    text_dict = page.get_text("dict")
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if "JOANA" in span_text and "ARC" in span_text:
                    span_bbox = span.get("bbox")
                    
                    print(f"\nBBox RAW do PyMuPDF:")
                    print(f"  {span_bbox}")
                    
                    # Normalizar manualmente
                    x0_norm_manual = span_bbox[0] / pdf_original_width
                    y0_norm_manual = span_bbox[1] / pdf_original_height
                    x1_norm_manual = span_bbox[2] / pdf_original_width
                    y1_norm_manual = span_bbox[3] / pdf_original_height
                    
                    print(f"\nNormalização manual (sem padding):")
                    print(f"  x0_norm = {span_bbox[0]:.4f} / {pdf_original_width:.2f} = {x0_norm_manual:.8f}")
                    print(f"  x1_norm = {span_bbox[2]:.4f} / {pdf_original_width:.2f} = {x1_norm_manual:.8f}")
                    
                    print(f"\nBBox normalizado do token (com padding):")
                    print(f"  {bbox_norm}")
                    
                    print(f"\nDiferença:")
                    print(f"  x0: {bbox_norm[0]:.8f} vs {x0_norm_manual:.8f} (diff: {bbox_norm[0] - x0_norm_manual:.8f})")
                    print(f"  x1: {bbox_norm[2]:.8f} vs {x1_norm_manual:.8f} (diff: {bbox_norm[2] - x1_norm_manual:.8f})")
                    
                    # Calcular padding aplicado
                    padding_right = (bbox_norm[2] - x1_norm_manual) * pdf_original_width
                    print(f"\nPadding à direita aplicado: {padding_right:.4f} pontos")
                    
                    break
    
    # HIPÓTESE 5: Verificar se há problema na renderização da imagem
    print("\n" + "="*80)
    print("HIPOTESE 5: Verificar renderização da imagem")
    print("="*80)
    
    # Verificar se a imagem está sendo redimensionada pelo CSS
    print(f"\nA imagem tem width='100%' no HTML, o que pode redimensionar ela.")
    print(f"Mas o SVG usa viewBox com dimensões fixas: {imgWidth} x {imgHeight}")
    print(f"\nPROBLEMA POTENCIAL: Se a imagem for redimensionada pelo CSS,")
    print(f"o SVG pode não estar alinhado corretamente!")
    
    doc.close()

if __name__ == "__main__":
    test_svg_rendering()

