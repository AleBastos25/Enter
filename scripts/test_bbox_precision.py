"""Script para testar a precisão do cálculo do bbox."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page

def test_bbox_precision():
    """Testa se o cálculo do bbox está correto."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    # Extrair tokens
    tokens = extract_tokens_from_page(str(pdf_path))
    
    # Abrir PDF para obter dimensões
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    # Renderizar com zoom
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pdf_rendered_width = pix.width
    pdf_rendered_height = pix.height
    doc.close()
    
    print("="*80)
    print("TESTE DE PRECISÃO DO BBOX")
    print("="*80)
    print(f"\nPDF Original: {pdf_original_width:.2f} x {pdf_original_height:.2f}")
    print(f"PDF Renderizado (zoom {zoom}x): {pdf_rendered_width} x {pdf_rendered_height}")
    print(f"Fator de escala: {pdf_rendered_width/pdf_original_width:.2f}x")
    
    # Verificar alguns tokens
    print("\n" + "="*80)
    print("ANÁLISE DE TOKENS (primeiros 10)")
    print("="*80)
    
    for i, token in enumerate(tokens[:10]):
        bbox_norm = token["bbox"]
        text = token["text"]
        
        # Converter para coordenadas renderizadas
        x0_render = bbox_norm[0] * pdf_rendered_width
        y0_render = bbox_norm[1] * pdf_rendered_height
        x1_render = bbox_norm[2] * pdf_rendered_width
        y1_render = bbox_norm[3] * pdf_rendered_height
        
        width_render = x1_render - x0_render
        height_render = y1_render - y0_render
        
        # Converter para coordenadas originais (para verificação)
        x0_orig = bbox_norm[0] * pdf_original_width
        y0_orig = bbox_norm[1] * pdf_original_height
        x1_orig = bbox_norm[2] * pdf_original_width
        y1_orig = bbox_norm[3] * pdf_original_height
        
        width_orig = x1_orig - x0_orig
        height_orig = y1_orig - y0_orig
        
        print(f"\nToken {token['id']}: '{text[:30]}'")
        print(f"  BBox normalizado: [{bbox_norm[0]:.6f}, {bbox_norm[1]:.6f}, {bbox_norm[2]:.6f}, {bbox_norm[3]:.6f}]")
        print(f"  Original (points): ({x0_orig:.2f}, {y0_orig:.2f}) -> ({x1_orig:.2f}, {y1_orig:.2f})")
        print(f"  Original size: {width_orig:.2f} x {height_orig:.2f}")
        print(f"  Renderizado (pixels): ({x0_render:.2f}, {y0_render:.2f}) -> ({x1_render:.2f}, {y1_render:.2f})")
        print(f"  Renderizado size: {width_render:.2f} x {height_render:.2f}")
        
        # Verificar se o tamanho renderizado está correto (deve ser 2x o original)
        expected_width = width_orig * zoom
        expected_height = height_orig * zoom
        width_diff = abs(width_render - expected_width)
        height_diff = abs(height_render - expected_height)
        
        if width_diff > 0.1 or height_diff > 0.1:
            print(f"  ⚠️  AVISO: Diferença no tamanho - width: {width_diff:.2f}, height: {height_diff:.2f}")
    
    # Verificar se há tokens com "joanadarc"
    print("\n" + "="*80)
    print("BUSCANDO TOKEN 'joanadarc'")
    print("="*80)
    
    joanadarc_tokens = [t for t in tokens if "joanadarc" in t["text"].lower()]
    
    if joanadarc_tokens:
        for token in joanadarc_tokens:
            print(f"\nToken encontrado: '{token['text']}'")
            print(f"  ID: {token['id']}")
            print(f"  BBox: {token['bbox']}")
    else:
        print("\nNenhum token com 'joanadarc' encontrado")
        print("Tokens que contêm 'joan':")
        for token in tokens:
            if "joan" in token["text"].lower():
                print(f"  Token {token['id']}: '{token['text']}'")

if __name__ == "__main__":
    test_bbox_precision()

