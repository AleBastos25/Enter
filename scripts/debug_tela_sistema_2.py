"""Script para debugar tokens específicos do tela_sistema_2."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

# Carregar PDF
pdf_path = Path("data/samples/tela_sistema_2.pdf")
print(f"Carregando PDF: {pdf_path}")

# Extrair tokens
tokens = extract_tokens_from_page(str(pdf_path))
print(f"Total de tokens: {len(tokens)}")

# Construir grafo
graph = build_token_graph(tokens, label="tela_sistema")
print(f"Total de nós: {len(graph['nodes'])}")
print(f"Total de edges: {len(graph['edges'])}")

# Encontrar tokens 1 e 9
token_1 = None
token_9 = None

for node in graph["nodes"]:
    if node["id"] == 1:
        token_1 = node
    elif node["id"] == 9:
        token_9 = node

print("\n" + "="*80)
print("TOKEN 1:")
print("="*80)
if token_1:
    print(f"ID: {token_1['id']}")
    print(f"Texto: {repr(token_1.get('text', ''))}")
    print(f"BBox: {token_1.get('bbox', [])}")
    print(f"Role: {token_1.get('role')}")
    print(f"Termina com dois pontos: {token_1.get('text', '').strip().endswith(':')}")
    print("\nEdges do token 1:")
    for edge in graph["edges"]:
        if edge.get("from") == 1 or edge.get("to") == 1:
            other_id = edge.get("to") if edge.get("from") == 1 else edge.get("from")
            other_token = next((n for n in graph["nodes"] if n["id"] == other_id), None)
            other_text = other_token.get("text", "") if other_token else "?"
            other_role = other_token.get("role") if other_token else "?"
            relation = edge.get("relation")
            direction = "->" if edge.get("from") == 1 else "<-"
            print(f"  {edge.get('from')} --[{relation}]--> {edge.get('to')} {direction} ({repr(other_text)}, role={other_role})")
            if other_token:
                print(f"    Termina com dois pontos: {other_text.strip().endswith(':')}")
else:
    print("Token 1 não encontrado!")

print("\n" + "="*80)
print("TOKEN 9:")
print("="*80)
if token_9:
    print(f"ID: {token_9['id']}")
    print(f"Texto: {repr(token_9.get('text', ''))}")
    print(f"BBox: {token_9.get('bbox', [])}")
    print(f"Role: {token_9.get('role')}")
    print(f"Termina com dois pontos: {token_9.get('text', '').strip().endswith(':')}")
else:
    print("Token 9 não encontrado!")

