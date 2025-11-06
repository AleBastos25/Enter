"""Script para debugar edges específicos."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph
import json

# Carregar PDF
pdf_path = Path("data/samples/tela_sistema_1.pdf")
print(f"Carregando PDF: {pdf_path}")

# Extrair tokens
tokens = extract_tokens_from_page(str(pdf_path))
print(f"Total de tokens: {len(tokens)}")

# Construir grafo
graph = build_token_graph(tokens, label="tela_sistema")
print(f"Total de nós: {len(graph['nodes'])}")
print(f"Total de edges: {len(graph['edges'])}")

# Encontrar tokens 17, 22 e 23
token_17 = None
token_22 = None
token_23 = None

for node in graph["nodes"]:
    if node["id"] == 17:
        token_17 = node
    elif node["id"] == 22:
        token_22 = node
    elif node["id"] == 23:
        token_23 = node

print("\n" + "="*80)
print("TOKEN 17:")
print("="*80)
if token_17:
    print(f"ID: {token_17['id']}")
    print(f"Texto: {repr(token_17.get('text', ''))}")
    bbox = token_17.get('bbox', [])
    print(f"BBox: {bbox}")
    if len(bbox) >= 4:
        print(f"Y: {bbox[1]} a {bbox[3]} (altura: {bbox[3] - bbox[1]})")
    print(f"Role: {token_17.get('role')}")
    # Verificar edges
    print("\nEdges do token 17:")
    for edge in graph["edges"]:
        if edge.get("from") == 17 or edge.get("to") == 17:
            other_id = edge.get("to") if edge.get("from") == 17 else edge.get("from")
            other_token = next((n for n in graph["nodes"] if n["id"] == other_id), None)
            other_text = other_token.get("text", "") if other_token else "?"
            other_bbox = other_token.get("bbox", []) if other_token else []
            if len(other_bbox) >= 4:
                # Calcular distância vertical
                if edge.get("relation") in ("south", "north"):
                    if edge.get("from") == 17:
                        vertical_dist = other_bbox[1] - bbox[3]  # Distância do bottom do 17 ao top do outro
                    else:
                        vertical_dist = bbox[1] - other_bbox[3]  # Distância do bottom do outro ao top do 17
                    print(f"  {edge.get('from')} --[{edge.get('relation')}]--> {edge.get('to')} ({repr(other_text)}, dist_vertical={vertical_dist:.4f})")
                else:
                    print(f"  {edge.get('from')} --[{edge.get('relation')}]--> {edge.get('to')} ({repr(other_text)})")
else:
    print("Token 17 não encontrado!")

print("\n" + "="*80)
print("TOKEN 22:")
print("="*80)
if token_22:
    print(f"ID: {token_22['id']}")
    print(f"Texto: {repr(token_22.get('text', ''))}")
    bbox = token_22.get('bbox', [])
    print(f"BBox: {bbox}")
    if len(bbox) >= 4:
        print(f"X: {bbox[0]} a {bbox[2]} (largura: {bbox[2] - bbox[0]})")
        print(f"Y: {bbox[1]} a {bbox[3]} (altura: {bbox[3] - bbox[1]})")
    print(f"Role: {token_22.get('role')}")
    # Verificar edges
    print("\nEdges do token 22:")
    for edge in graph["edges"]:
        if edge.get("from") == 22 or edge.get("to") == 22:
            other_id = edge.get("to") if edge.get("from") == 22 else edge.get("from")
            other_token = next((n for n in graph["nodes"] if n["id"] == other_id), None)
            other_text = other_token.get("text", "") if other_token else "?"
            print(f"  {edge.get('from')} --[{edge.get('relation')}]--> {edge.get('to')} ({repr(other_text)})")
else:
    print("Token 22 não encontrado!")

print("\n" + "="*80)
print("TOKEN 23:")
print("="*80)
if token_23:
    print(f"ID: {token_23['id']}")
    print(f"Texto: {repr(token_23.get('text', ''))}")
    bbox = token_23.get('bbox', [])
    print(f"BBox: {bbox}")
    if len(bbox) >= 4:
        print(f"X: {bbox[0]} a {bbox[2]} (largura: {bbox[2] - bbox[0]})")
        print(f"Y: {bbox[1]} a {bbox[3]} (altura: {bbox[3] - bbox[1]})")
    print(f"Role: {token_23.get('role')}")
    # Verificar edges
    print("\nEdges do token 23:")
    for edge in graph["edges"]:
        if edge.get("from") == 23 or edge.get("to") == 23:
            other_id = edge.get("to") if edge.get("from") == 23 else edge.get("from")
            other_token = next((n for n in graph["nodes"] if n["id"] == other_id), None)
            other_text = other_token.get("text", "") if other_token else "?"
            print(f"  {edge.get('from')} --[{edge.get('relation')}]--> {edge.get('to')} ({repr(other_text)})")
else:
    print("Token 23 não encontrado!")

# Verificar se 22 e 23 deveriam estar ligados
if token_22 and token_23:
    print("\n" + "="*80)
    print("ANÁLISE: Token 22 e 23 deveriam estar ligados?")
    print("="*80)
    bbox22 = token_22.get('bbox', [])
    bbox23 = token_23.get('bbox', [])
    if len(bbox22) >= 4 and len(bbox23) >= 4:
        # Verificar se estão na mesma linha (Y similar)
        y22_center = (bbox22[1] + bbox22[3]) / 2.0
        y23_center = (bbox23[1] + bbox23[3]) / 2.0
        y_diff = abs(y22_center - y23_center)
        print(f"Y centro 22: {y22_center:.4f}")
        print(f"Y centro 23: {y23_center:.4f}")
        print(f"Diferença Y: {y_diff:.4f}")
        THRESHOLD_SAME_LINE = 0.005
        same_line = y_diff < THRESHOLD_SAME_LINE
        print(f"Mesma linha? {same_line} (threshold: {THRESHOLD_SAME_LINE})")
        
        # Verificar gap horizontal
        x22_right = bbox22[2]
        x23_left = bbox23[0]
        gap = x23_left - x22_right
        print(f"Gap horizontal: {gap:.4f}")
        
        width22 = bbox22[2] - bbox22[0]
        width23 = bbox23[2] - bbox23[0]
        avg_width = (width22 + width23) / 2.0
        print(f"Largura média: {avg_width:.4f}")
        print(f"Gap < 2 * largura média? {gap < avg_width * 2}")

