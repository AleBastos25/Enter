"""Script para debugar HEADERs e suas conexões."""

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

# Encontrar todos os HEADERs e verificar suas conexões
print("\n" + "="*80)
print("HEADERs e suas conexões:")
print("="*80)

headers_with_north = []

for node in graph["nodes"]:
    if node.get("role") == "HEADER":
        token_id = node["id"]
        token_text = node.get("text", "")
        
        # Verificar conexões
        north_connections = []
        south_connections = []
        east_connections = []
        west_connections = []
        
        for edge in graph["edges"]:
            if edge.get("from") == token_id:
                to_id = edge.get("to")
                relation = edge.get("relation")
                to_token = next((n for n in graph["nodes"] if n["id"] == to_id), None)
                to_text = to_token.get("text", "") if to_token else "?"
                to_role = to_token.get("role") if to_token else "?"
                
                if relation == "north":
                    north_connections.append((to_id, to_text, to_role))
                elif relation == "south":
                    south_connections.append((to_id, to_text, to_role))
                elif relation == "east":
                    east_connections.append((to_id, to_text, to_role))
                elif relation == "west":
                    west_connections.append((to_id, to_text, to_role))
            
            elif edge.get("to") == token_id:
                from_id = edge.get("from")
                relation = edge.get("relation")
                from_token = next((n for n in graph["nodes"] if n["id"] == from_id), None)
                from_text = from_token.get("text", "") if from_token else "?"
                from_role = from_token.get("role") if from_token else "?"
                
                # Para edges reversos, a relação é invertida
                if relation == "south":  # Se alguém tem south para este token, este token tem north
                    north_connections.append((from_id, from_text, from_role))
                elif relation == "north":
                    south_connections.append((from_id, from_text, from_role))
                elif relation == "west":
                    east_connections.append((from_id, from_text, from_role))
                elif relation == "east":
                    west_connections.append((from_id, from_text, from_role))
        
        print(f"\nToken {token_id}: {repr(token_text)}")
        print(f"  Role: HEADER")
        
        if north_connections:
            print(f"  CONEXÕES NORTH (PROBLEMA!):")
            for conn_id, conn_text, conn_role in north_connections:
                print(f"    {conn_id} ({repr(conn_text)}, role={conn_role})")
            headers_with_north.append((token_id, token_text, north_connections))
        else:
            print(f"  Sem conexões north (OK)")
        
        if south_connections:
            print(f"  Conexões south:")
            for conn_id, conn_text, conn_role in south_connections:
                print(f"    {conn_id} ({repr(conn_text)}, role={conn_role})")
        
        if east_connections:
            print(f"  Conexões east:")
            for conn_id, conn_text, conn_role in east_connections:
                print(f"    {conn_id} ({repr(conn_text)}, role={conn_role})")
        
        if west_connections:
            print(f"  Conexões west:")
            for conn_id, conn_text, conn_role in west_connections:
                print(f"    {conn_id} ({repr(conn_text)}, role={conn_role})")

if headers_with_north:
    print(f"\n{'='*80}")
    print(f"Total de HEADERs com conexões north: {len(headers_with_north)}")
    print(f"{'='*80}")
else:
    print(f"\n{'='*80}")
    print("Nenhum HEADER com conexões north encontrado (OK)")
    print(f"{'='*80}")

