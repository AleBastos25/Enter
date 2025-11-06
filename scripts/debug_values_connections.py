"""Script para debugar VALUES e suas conexões south/east."""

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

# Encontrar todos os VALUES e verificar suas conexões south/east
print("\n" + "="*80)
print("VALUES e suas conexões south/east:")
print("="*80)

values_with_label_connections = []

for node in graph["nodes"]:
    if node.get("role") == "VALUE":
        token_id = node["id"]
        token_text = node.get("text", "")
        
        # Verificar conexões south e east
        south_connections = []
        east_connections = []
        
        for edge in graph["edges"]:
            if edge.get("from") == token_id:
                to_id = edge.get("to")
                relation = edge.get("relation")
                to_token = next((n for n in graph["nodes"] if n["id"] == to_id), None)
                to_text = to_token.get("text", "") if to_token else "?"
                to_role = to_token.get("role") if to_token else "?"
                
                if relation == "south":
                    south_connections.append((to_id, to_text, to_role))
                elif relation == "east":
                    east_connections.append((to_id, to_text, to_role))
        
        # Verificar se tem conexões com LABELs
        has_label_connections = False
        label_connections = []
        
        for conn_id, conn_text, conn_role in south_connections + east_connections:
            if conn_role == "LABEL":
                has_label_connections = True
                label_connections.append((conn_id, conn_text, conn_role))
        
        if has_label_connections:
            print(f"\nToken {token_id}: {repr(token_text)}")
            print(f"  Role: VALUE")
            print(f"  CONEXÕES COM LABELs (PROBLEMA!):")
            for conn_id, conn_text, conn_role in label_connections:
                direction = "south" if (conn_id, conn_text, conn_role) in south_connections else "east"
                print(f"    {direction}: {conn_id} ({repr(conn_text)}, role={conn_role})")
            values_with_label_connections.append((token_id, token_text, label_connections))
        elif south_connections or east_connections:
            print(f"\nToken {token_id}: {repr(token_text)}")
            print(f"  Role: VALUE")
            if south_connections:
                print(f"  Conexões south (OK - apenas VALUES):")
                for conn_id, conn_text, conn_role in south_connections:
                    print(f"    {conn_id} ({repr(conn_text)}, role={conn_role})")
            if east_connections:
                print(f"  Conexões east (OK - apenas VALUES):")
                for conn_id, conn_text, conn_role in east_connections:
                    print(f"    {conn_id} ({repr(conn_text)}, role={conn_role})")

if values_with_label_connections:
    print(f"\n{'='*80}")
    print(f"Total de VALUES com conexões south/east para LABELs: {len(values_with_label_connections)}")
    print(f"{'='*80}")
else:
    print(f"\n{'='*80}")
    print("Nenhum VALUE com conexões south/east para LABELs encontrado (OK)")
    print(f"{'='*80}")

