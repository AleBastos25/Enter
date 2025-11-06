"""Script para debugar o token 'Telefone Profissional'."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from scripts.build_token_graph import extract_tokens_from_page

def debug_telefone():
    """Debuga o token 'Telefone Profissional'."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    print("="*80)
    print("DEBUG: TELEFONE PROFISSIONAL")
    print("="*80)
    
    # Extrair tokens
    tokens = extract_tokens_from_page(str(pdf_path))
    
    # Abrir PDF
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pdf_original_width = page.rect.width
    pdf_original_height = page.rect.height
    
    # Encontrar token
    telefone_token = None
    for token in tokens:
        if "Telefone" in token["text"] and "Profissional" in token["text"]:
            telefone_token = token
            break
    
    if not telefone_token:
        print("\n[ERRO] Token não encontrado!")
        doc.close()
        return
    
    print(f"\n[OK] Token encontrado: '{telefone_token['text']}'")
    print(f"  ID: {telefone_token['id']}")
    print(f"  BBox Normalizado: {telefone_token['bbox']}")
    
    # Obter span RAW
    text_dict = page.get_text("dict")
    telefone_span_raw = None
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:
            continue
        
        for line_dict in block_dict.get("lines", []):
            for span in line_dict.get("spans", []):
                span_text = span.get("text", "").strip()
                if "Telefone" in span_text and "Profissional" in span_text:
                    telefone_span_raw = span
                    break
    
    if not telefone_span_raw:
        print("\n[ERRO] Span não encontrado!")
        doc.close()
        return
    
    print(f"\n[OK] Span RAW encontrado:")
    print(f"  Text: '{telefone_span_raw.get('text', '').strip()}'")
    span_bbox_raw = telefone_span_raw.get("bbox")
    print(f"  BBox RAW: {span_bbox_raw}")
    print(f"  Font: {telefone_span_raw.get('font', 'N/A')}")
    print(f"  Font Size: {telefone_span_raw.get('size', 'N/A')}")
    
    span_width = span_bbox_raw[2] - span_bbox_raw[0]
    span_height = span_bbox_raw[3] - span_bbox_raw[1]
    font_size = telefone_span_raw.get("size", 0)
    span_text = telefone_span_raw.get("text", "").strip()
    
    print(f"\n[ANÁLISE]")
    print(f"  Width: {span_width:.4f} pontos")
    print(f"  Height: {span_height:.4f} pontos")
    print(f"  Font Size: {font_size}")
    print(f"  Text Length: {len(span_text)} caracteres")
    
    # Calcular estimativa
    avg_char_width = font_size * 0.6 if font_size > 0 else span_width / max(len(span_text), 1)
    estimated_text_width = len(span_text) * avg_char_width
    extra_space = span_width - estimated_text_width
    
    print(f"\n[ESTIMATIVA]")
    print(f"  Avg Char Width (font_size * 0.6): {avg_char_width:.4f}")
    print(f"  Estimated Text Width: {estimated_text_width:.4f}")
    print(f"  Extra Space: {extra_space:.4f}")
    print(f"  Extra Space %: {(extra_space / span_width * 100) if span_width > 0 else 0:.2f}%")
    
    # Verificar lógica de padding (NOVA LÓGICA)
    estimated_text_width_conservative = len(span_text) * font_size * 0.5 if font_size > 0 else span_width
    is_bbox_tight = span_width < estimated_text_width_conservative * 0.9
    
    print(f"\n[LÓGICA DE PADDING (NOVA)]")
    print(f"  Estimated (conservative, 0.5): {estimated_text_width_conservative:.4f}")
    print(f"  Is bbox tight (<90% do estimado): {is_bbox_tight}")
    
    # NOVA LÓGICA: sempre adicionar padding
    padding_factor_right = 0.12
    min_padding_right = 20.0
    padding_right = max(span_width * padding_factor_right, min_padding_right)
    print(f"  Padding aplicado: +{padding_right:.4f} pontos")
    
    # Verificar resultado
    x1_original = span_bbox_raw[2]
    x1_after = x1_original + padding_right
    
    print(f"\n[RESULTADO]")
    print(f"  x1 original: {x1_original:.4f}")
    print(f"  x1 após ajuste: {x1_after:.4f}")
    print(f"  Diferença: {x1_after - x1_original:.4f}")
    
    # Normalizar
    x1_norm_expected = x1_after / pdf_original_width
    x1_norm_actual = telefone_token['bbox'][2]
    
    print(f"\n[VERIFICAÇÃO]")
    print(f"  x1 normalizado esperado: {x1_norm_expected:.8f}")
    print(f"  x1 normalizado obtido: {x1_norm_actual:.8f}")
    print(f"  Diferença: {abs(x1_norm_actual - x1_norm_expected):.8f}")
    
    # Renderizado
    zoom = 2.0
    pdf_rendered_width = pdf_original_width * zoom
    
    x1_render_original = x1_original * zoom
    x1_render_after = x1_after * zoom
    
    print(f"\n[RENDERIZADO (zoom {zoom}x)]")
    print(f"  x1 renderizado original: {x1_render_original:.4f} pixels")
    print(f"  x1 renderizado após ajuste: {x1_render_after:.4f} pixels")
    print(f"  Diferença: {x1_render_after - x1_render_original:.4f} pixels")
    
    # Verificar se o problema é a estimativa
    print(f"\n[PROBLEMA POTENCIAL]")
    if padding_right < 0:
        print(f"  [AVISO] O bbox foi REDUZIDO em {abs(padding_right):.4f} pontos")
        print(f"          Isso pode estar cortando o texto!")
    elif padding_right < 5:
        print(f"  [INFO] Padding mínimo aplicado: {padding_right:.4f} pontos")
    else:
        print(f"  [OK] Padding adequado aplicado: {padding_right:.4f} pontos")
    
    # Verificar palavras individuais
    print(f"\n[VERIFICAÇÃO DE PALAVRAS]")
    words = page.get_text("words")
    telefone_words = [w for w in words if "Telefone" in w[4] or "Profissional" in w[4]]
    
    if len(telefone_words) > 1:
        print(f"  Encontradas {len(telefone_words)} palavras relacionadas:")
        for i, word in enumerate(telefone_words):
            print(f"    Palavra {i}: '{word[4]}' bbox: {word[0]:.2f}, {word[1]:.2f}, {word[2]:.2f}, {word[3]:.2f}")
            print(f"               width: {word[2] - word[0]:.2f}")
        
        # Verificar se "Profissional" está completamente dentro do bbox
        if len(telefone_words) >= 2:
            profissional_word = telefone_words[-1] if "Profissional" in telefone_words[-1][4] else None
            if profissional_word:
                print(f"\n  Verificação 'Profissional':")
                print(f"    x1 da palavra: {profissional_word[2]:.4f}")
                print(f"    x1 do span: {span_bbox_raw[2]:.4f}")
                print(f"    x1 após ajuste: {x1_after:.4f}")
                print(f"    'Profissional' cabe no span original: {profissional_word[2] <= span_bbox_raw[2]}")
                print(f"    'Profissional' cabe após ajuste: {profissional_word[2] <= x1_after}")
    
    doc.close()

if __name__ == "__main__":
    debug_telefone()

