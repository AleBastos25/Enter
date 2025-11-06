"""Script de debug para verificar classificação de roles."""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

def debug_token_role(pdf_path: str, label: Optional[str] = None, token_text: str = None):
    """Debug classificação de roles para um token específico."""
    
    print(f"\n{'='*80}")
    print(f"DEBUG: Classificacao de Roles - {Path(pdf_path).name}")
    print(f"{'='*80}\n")
    
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens, label=label)
    
    # Encontrar token pelo texto
    target_token = None
    if token_text:
        for token in tokens:
            if token_text.lower() in token.get("text", "").lower():
                target_token = token
                break
    
    if not target_token and token_text:
        print(f"Token '{token_text}' nao encontrado!")
        return
    
    # Mostrar estatísticas gerais
    roles_count = {}
    for node in graph["nodes"]:
        role = node.get("role")
        roles_count[role] = roles_count.get(role, 0) + 1
    
    print(f"Estatisticas de Roles:")
    for role, count in sorted(roles_count.items()):
        print(f"  {role or 'None'}: {count}")
    
    # Mostrar tokens no topo com fonte grande
    print(f"\nTokens no topo (y < 0.20) com fonte grande:")
    font_sizes = [t.get("font_size", 0) for t in tokens if t.get("font_size") and t.get("font_size") > 0]
    avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
    
    top_tokens = []
    for token in tokens:
        bbox = token.get("bbox", [0, 0, 0, 0])
        font_size = token.get("font_size", 0) or 0
        if len(bbox) >= 4:
            y_top = bbox[1]
            is_near_top = y_top < 0.20
            is_large_font = font_size >= avg_font_size * 1.3
            
            if is_near_top and is_large_font:
                role = next((n.get("role") for n in graph["nodes"] if n["id"] == token["id"]), None)
                top_tokens.append({
                    "id": token["id"],
                    "text": token.get("text", ""),
                    "y": y_top,
                    "font_size": font_size,
                    "role": role,
                    "avg_font": avg_font_size,
                    "is_large": is_large_font
                })
    
    top_tokens.sort(key=lambda x: x["y"])
    for t in top_tokens:
        print(f"  Token #{t['id']}: '{t['text'][:30]}'")
        print(f"    Y: {t['y']:.4f}, Font: {t['font_size']:.1f} (avg: {t['avg_font']:.1f}, large: {t['is_large']})")
        print(f"    Role: {t['role']}")
        print()
    
    # Se token específico foi encontrado, mostrar detalhes
    if target_token:
        token_id = target_token["id"]
        node = next((n for n in graph["nodes"] if n["id"] == token_id), None)
        
        if node:
            print(f"\n{'='*80}")
            print(f"Token Especifico: '{token_text}'")
            print(f"{'='*80}\n")
            print(f"ID: {token_id}")
            print(f"Texto: {node.get('text', '')}")
            print(f"Role: {node.get('role')}")
            print(f"BBox: {node.get('bbox', [])}")
            print(f"Font Size: {node.get('font_size', 0)}")
            print(f"Bold: {node.get('bold', False)}")
            print(f"Y Top: {node.get('bbox', [0,0,0,0])[1]:.4f}")
            print(f"Avg Font Size: {avg_font_size:.1f}")
            print(f"Is Near Top (y < 0.20): {node.get('bbox', [0,0,0,0])[1] < 0.20}")
            print(f"Is Large Font (>= {avg_font_size * 1.3:.1f}): {node.get('font_size', 0) >= avg_font_size * 1.3}")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_2.pdf"
    
    # Debug para o nome (primeiro token geralmente)
    debug_token_role(str(pdf_path), label="carteira_oab", token_text="LUIS")


