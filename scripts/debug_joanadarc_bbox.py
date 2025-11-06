"""Script para debugar o bbox do token JOANA D'ARC."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page

def debug_joanadarc():
    """Debuga o bbox do token JOANA D'ARC."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    # Abrir PDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    print("="*80)
    print("DEBUG: BBOX DO TOKEN JOANA D'ARC")
    print("="*80)
    print(f"\nPDF Original: {pdf_original_width:.2f} x {pdf_original_height:.2f}")
    
    # Extrair tokens
    tokens = extract_tokens_from_page(str(pdf_path))
    
    # Encontrar token JOANA D'ARC
    joanadarc_token = None
    for token in tokens:
        if "JOANA" in token["text"] and "ARC" in token["text"]:
            joanadarc_token = token
            break
    
    if not joanadarc_token:
        print("\n[ERRO] Token JOANA D'ARC não encontrado!")
        return
    
    print(f"\n[OK] Token encontrado: '{joanadarc_token['text']}'")
    print(f"   ID: {joanadarc_token['id']}")
    
    # Verificar bbox normalizado
    bbox_norm = joanadarc_token["bbox"]
    print(f"\n[BBOX] BBox Normalizado: [{bbox_norm[0]:.8f}, {bbox_norm[1]:.8f}, {bbox_norm[2]:.8f}, {bbox_norm[3]:.8f}]")
    
    # Converter para coordenadas originais
    x0_orig = bbox_norm[0] * pdf_original_width
    y0_orig = bbox_norm[1] * pdf_original_height
    x1_orig = bbox_norm[2] * pdf_original_width
    y1_orig = bbox_norm[3] * pdf_original_height
    
    print(f"\n[COORD] Coordenadas Originais (points):")
    print(f"   x0: {x0_orig:.4f}")
    print(f"   y0: {y0_orig:.4f}")
    print(f"   x1: {x1_orig:.4f}")
    print(f"   y1: {y1_orig:.4f}")
    print(f"   Width: {x1_orig - x0_orig:.4f}")
    print(f"   Height: {y1_orig - y0_orig:.4f}")
    
    # Verificar bbox RAW do PyMuPDF (antes da normalização e padding)
    print("\n" + "="*80)
    print("DEBUG: BBOX RAW DO PyMuPDF (ANTES DE NORMALIZAÇÃO)")
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
                    print(f"\n[SPAN] Span Text: '{span_text}'")
                    print(f"   BBox RAW: {span_bbox}")
                    print(f"   x0: {span_bbox[0]:.4f}")
                    print(f"   y0: {span_bbox[1]:.4f}")
                    print(f"   x1: {span_bbox[2]:.4f}")
                    print(f"   y1: {span_bbox[3]:.4f}")
                    print(f"   Width: {span_bbox[2] - span_bbox[0]:.4f}")
                    print(f"   Height: {span_bbox[3] - span_bbox[1]:.4f}")
                    
                    # Calcular padding aplicado (APENAS À DIREITA)
                    padding_factor_right = 0.08  # 8% de padding na largura
                    min_padding_right = 10.0  # Mínimo de 10 pontos à direita
                    span_width = span_bbox[2] - span_bbox[0]
                    padding_right = max(span_width * padding_factor_right, min_padding_right)
                    
                    print(f"\n[PADDING] Padding aplicado (APENAS À DIREITA):")
                    print(f"   padding_right: {padding_right:.6f} ({padding_right/pdf_original_width*100:.4f}% da largura)")
                    print(f"   NÃO há padding à esquerda, topo ou base")
                    
                    # Bbox após padding (apenas à direita)
                    x0_with_padding = span_bbox[0]  # Sem padding à esquerda
                    x1_with_padding = span_bbox[2] + padding_right  # Padding apenas à direita
                    y0_with_padding = span_bbox[1]  # Sem padding no topo
                    y1_with_padding = span_bbox[3]  # Sem padding embaixo
                    
                    print(f"\n[BBOX] BBox após padding:")
                    print(f"   x0: {x0_with_padding:.4f} (original: {span_bbox[0]:.4f}, diff: {x0_with_padding - span_bbox[0]:.4f}) [SEM MUDANÇA]")
                    print(f"   x1: {x1_with_padding:.4f} (original: {span_bbox[2]:.4f}, diff: {x1_with_padding - span_bbox[2]:.4f}) [EXPANDIDO]")
                    print(f"   y0: {y0_with_padding:.4f} (original: {span_bbox[1]:.4f}, diff: {y0_with_padding - span_bbox[1]:.4f}) [SEM MUDANÇA]")
                    print(f"   y1: {y1_with_padding:.4f} (original: {span_bbox[3]:.4f}, diff: {y1_with_padding - span_bbox[3]:.4f}) [SEM MUDANÇA]")
                    print(f"   Width: {x1_with_padding - x0_with_padding:.4f} (original: {span_width:.4f}, diff: {(x1_with_padding - x0_with_padding) - span_width:.4f})")
                    print(f"   Height: {y1_with_padding - y0_with_padding:.4f} (original: {span_bbox[3] - span_bbox[1]:.4f}, diff: 0.0) [SEM MUDANÇA]")
                    
                    # Verificar se o padding é suficiente
                    padding_right_pixels = padding_right * 2.0  # Converter para pixels renderizados (zoom 2x)
                    print(f"\n[INFO] Padding à direita em pixels renderizados: {padding_right_pixels:.4f}")
    
    # Verificar coordenadas renderizadas
    zoom = 2.0
    pdf_rendered_width = pdf_original_width * zoom
    pdf_rendered_height = pdf_original_height * zoom
    
    x0_render = bbox_norm[0] * pdf_rendered_width
    y0_render = bbox_norm[1] * pdf_rendered_height
    x1_render = bbox_norm[2] * pdf_rendered_width
    y1_render = bbox_norm[3] * pdf_rendered_height
    
    print("\n" + "="*80)
    print("DEBUG: COORDENADAS RENDERIZADAS (zoom 2.0x)")
    print("="*80)
    print(f"\n[COORD] Coordenadas Renderizadas (pixels):")
    print(f"   x0: {x0_render:.4f}")
    print(f"   y0: {y0_render:.4f}")
    print(f"   x1: {x1_render:.4f}")
    print(f"   y1: {y1_render:.4f}")
    print(f"   Width: {x1_render - x0_render:.4f}")
    print(f"   Height: {y1_render - y0_render:.4f}")
    
    # Verificar stroke adjustment
    stroke_width = 2
    stroke_half = stroke_width / 2
    adjusted_x0 = x0_render - stroke_half
    adjusted_x1 = x1_render + stroke_half
    
    print(f"\n[STROKE] Ajuste do Stroke (stroke_width={stroke_width}):")
    print(f"   stroke_half: {stroke_half}")
    print(f"   adjusted_x0: {adjusted_x0:.4f} (original: {x0_render:.4f})")
    print(f"   adjusted_x1: {adjusted_x1:.4f} (original: {x1_render:.4f})")
    print(f"   adjusted_width: {adjusted_x1 - adjusted_x0:.4f} (original: {x1_render - x0_render:.4f})")
    
    doc.close()

if __name__ == "__main__":
    debug_joanadarc()

