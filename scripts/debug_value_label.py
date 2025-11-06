"""Script de debug para verificar VALUE sem LABEL."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

def debug_value_without_label(pdf_path: str, value_token_id: int):
    """Debug VALUE sem LABEL conectado."""
    
    print(f"\n{'='*80}")
    print(f"DEBUG: VALUE sem LABEL - Token {value_token_id}")
    print(f"{'='*80}\n")
    
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens)
    
    # Encontrar token VALUE
    value_token = next((t for t in tokens if t["id"] == value_token_id), None)
    
    if not value_token:
        print(f"Token {value_token_id} nao encontrado!")
        return
    
    print(f"Token {value_token_id} (VALUE): '{value_token.get('text', '')}'")
    print(f"  BBox: {value_token.get('bbox', [])}")
    bbox_value = value_token.get("bbox", [0, 0, 0, 0])
    if len(bbox_value) >= 4:
        print(f"  X: [{bbox_value[0]:.4f}, {bbox_value[2]:.4f}], Y: [{bbox_value[1]:.4f}, {bbox_value[3]:.4f}]")
        print(f"  Center X: {(bbox_value[0] + bbox_value[2]) / 2.0:.4f}, Center Y: {(bbox_value[1] + bbox_value[3]) / 2.0:.4f}")
    
    # Verificar role
    nodes = graph.get("nodes", [])
    value_node = next((n for n in nodes if n["id"] == value_token_id), None)
    if value_node:
        print(f"  Role: {value_node.get('role')}")
    
    # Verificar edges
    edges = graph.get("edges", [])
    print(f"\nEdges conectados ao token {value_token_id}:")
    
    # Construir adjacência
    adj = {node["id"]: {"east": [], "south": [], "north": [], "west": []} for node in nodes}
    for edge in edges:
        relation = edge.get("relation", "")
        from_id = edge.get("from")
        to_id = edge.get("to")
        if relation in adj.get(from_id, {}):
            adj[from_id][relation].append(to_id)
        # Bidirecional
        reverse_relation = {"east": "west", "west": "east", "south": "north", "north": "south"}.get(relation, relation)
        if reverse_relation in adj.get(to_id, {}):
            adj[to_id][reverse_relation].append(from_id)
    
    # Verificar vizinhos acima (north) e à esquerda (west)
    north_neighbors = adj.get(value_token_id, {}).get("north", [])
    west_neighbors = adj.get(value_token_id, {}).get("west", [])
    
    print(f"  North (acima): {north_neighbors}")
    print(f"  West (esquerda): {west_neighbors}")
    
    # Verificar roles dos vizinhos
    print(f"\nVizinhos acima (north):")
    for neighbor_id in north_neighbors:
        neighbor_node = next((n for n in nodes if n["id"] == neighbor_id), None)
        if neighbor_node:
            print(f"  Token {neighbor_id}: '{neighbor_node.get('text', '')}' - Role: {neighbor_node.get('role')}")
            neighbor_bbox = neighbor_node.get("bbox", [0, 0, 0, 0])
            if len(neighbor_bbox) >= 4:
                print(f"    BBox: {neighbor_bbox}")
                print(f"    Y: [{neighbor_bbox[1]:.4f}, {neighbor_bbox[3]:.4f}]")
    
    print(f"\nVizinhos à esquerda (west):")
    for neighbor_id in west_neighbors:
        neighbor_node = next((n for n in nodes if n["id"] == neighbor_id), None)
        if neighbor_node:
            print(f"  Token {neighbor_id}: '{neighbor_node.get('text', '')}' - Role: {neighbor_node.get('role')}")
            neighbor_bbox = neighbor_node.get("bbox", [0, 0, 0, 0])
            if len(neighbor_bbox) >= 4:
                print(f"    BBox: {neighbor_bbox}")
                print(f"    X: [{neighbor_bbox[0]:.4f}, {neighbor_bbox[2]:.4f}]")
    
    # Verificar se algum vizinho é LABEL
    all_neighbors = north_neighbors + west_neighbors
    label_neighbors = []
    for neighbor_id in all_neighbors:
        neighbor_node = next((n for n in nodes if n["id"] == neighbor_id), None)
        if neighbor_node and neighbor_node.get("role") == "LABEL":
            label_neighbors.append(neighbor_id)
    
    print(f"\nVizinhos que sao LABEL: {label_neighbors}")
    
    if not label_neighbors:
        print(f"\nPROBLEMA: Token {value_token_id} (VALUE) nao tem LABEL conectado!")
        print(f"  Deveria ter um LABEL acima ou à esquerda.")
        
        # Procurar tokens próximos que poderiam ser LABELs
        print(f"\nProcurando tokens proximos que poderiam ser LABELs:")
        for token in tokens:
            if token["id"] == value_token_id:
                continue
            
            token_bbox = token.get("bbox", [0, 0, 0, 0])
            if len(token_bbox) < 4:
                continue
            
            # Verificar se está acima ou à esquerda
            is_above = token_bbox[3] < bbox_value[1]  # Bottom do token < top do value
            is_left = token_bbox[2] < bbox_value[0]  # Right do token < left do value
            is_above_and_aligned = is_above and abs((token_bbox[0] + token_bbox[2]) / 2.0 - (bbox_value[0] + bbox_value[2]) / 2.0) < 0.05
            is_left_and_aligned = is_left and abs((token_bbox[1] + token_bbox[3]) / 2.0 - (bbox_value[1] + bbox_value[3]) / 2.0) < 0.05
            
            if is_above_and_aligned or is_left_and_aligned:
                token_node = next((n for n in nodes if n["id"] == token["id"]), None)
                role = token_node.get("role") if token_node else None
                print(f"  Token {token['id']}: '{token.get('text', '')}' - Role: {role}")
                print(f"    BBox: {token_bbox}")
                print(f"    Acima? {is_above_and_aligned}, Esquerda? {is_left_and_aligned}")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "tela_sistema_1.pdf"
    
    # Debug token 17 (VALUE) e token 12 (deveria ser LABEL)
    debug_value_without_label(str(pdf_path), value_token_id=17)


