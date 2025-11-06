"""Script de debug para verificar detecção de edges verticais."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

def debug_vertical_edges(pdf_path: str, token1_id: int, token2_id: int):
    """Debug detecção de edge vertical entre dois tokens."""
    
    print(f"\n{'='*80}")
    print(f"DEBUG: Deteccao de Edge Vertical")
    print(f"{'='*80}\n")
    
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens)
    
    # Encontrar tokens
    token1 = next((t for t in tokens if t["id"] == token1_id), None)
    token2 = next((t for t in tokens if t["id"] == token2_id), None)
    
    if not token1:
        print(f"Token {token1_id} nao encontrado!")
        return
    if not token2:
        print(f"Token {token2_id} nao encontrado!")
        return
    
    print(f"Token {token1_id}: '{token1.get('text', '')}'")
    print(f"  BBox: {token1.get('bbox', [])}")
    bbox1 = token1.get("bbox", [0, 0, 0, 0])
    if len(bbox1) >= 4:
        print(f"  X: [{bbox1[0]:.4f}, {bbox1[2]:.4f}], Y: [{bbox1[1]:.4f}, {bbox1[3]:.4f}]")
        print(f"  Width: {bbox1[2] - bbox1[0]:.4f}, Height: {bbox1[3] - bbox1[1]:.4f}")
        print(f"  Center X: {(bbox1[0] + bbox1[2]) / 2.0:.4f}, Center Y: {(bbox1[1] + bbox1[3]) / 2.0:.4f}")
    
    print(f"\nToken {token2_id}: '{token2.get('text', '')}'")
    print(f"  BBox: {token2.get('bbox', [])}")
    bbox2 = token2.get("bbox", [0, 0, 0, 0])
    if len(bbox2) >= 4:
        print(f"  X: [{bbox2[0]:.4f}, {bbox2[2]:.4f}], Y: [{bbox2[1]:.4f}, {bbox2[3]:.4f}]")
        print(f"  Width: {bbox2[2] - bbox2[0]:.4f}, Height: {bbox2[3] - bbox2[1]:.4f}")
        print(f"  Center X: {(bbox2[0] + bbox2[2]) / 2.0:.4f}, Center Y: {(bbox2[1] + bbox2[3]) / 2.0:.4f}")
    
    # Verificar se há edge
    edges = graph.get("edges", [])
    has_edge = False
    for edge in edges:
        if edge.get("from") == token1_id and edge.get("to") == token2_id and edge.get("relation") == "south":
            has_edge = True
            print(f"\nOK Edge encontrado: {token1_id} -> {token2_id} (south)")
            break
    
    if not has_edge:
        print(f"\nX Edge NAO encontrado: {token1_id} -> {token2_id} (south)")
        
        # Calcular métricas
        if len(bbox1) >= 4 and len(bbox2) >= 4:
            x1_left = bbox1[0]
            x1_right = bbox1[2]
            y1_bottom = bbox1[3]
            y1_top = bbox1[1]
            width1 = x1_right - x1_left
            center1_x = (x1_left + x1_right) / 2.0
            
            x2_left = bbox2[0]
            x2_right = bbox2[2]
            y2_top = bbox2[1]
            y2_bottom = bbox2[3]
            width2 = x2_right - x2_left
            center2_x = (x2_left + x2_right) / 2.0
            
            # Calcular overlap
            overlap_x = max(0.0, min(x1_right, x2_right) - max(x1_left, x2_left))
            overlap_y = max(0.0, min(y1_bottom, y2_bottom) - max(y1_top, y2_top))
            
            print(f"\nMetricas:")
            print(f"  Overlap X: {overlap_x:.4f}")
            print(f"  Overlap Y: {overlap_y:.4f}")
            print(f"  Y overlap? {overlap_y > 0}")
            print(f"  Y2_top >= Y1_top - 0.02? {y2_top >= y1_top - 0.02} ({y2_top:.4f} >= {y1_top - 0.02:.4f})")
            
            min_width = min(width1, width2)
            max_width = max(width1, width2)
            center_diff = abs(center1_x - center2_x)
            is_aligned = center_diff < max_width * 0.6
            
            print(f"  Min width: {min_width:.4f}, Max width: {max_width:.4f}")
            print(f"  Center diff: {center_diff:.4f}")
            print(f"  Is aligned (60%)? {is_aligned} ({center_diff:.4f} < {max_width * 0.6:.4f})")
            
            # Verificar condições
            y_overlap = overlap_y > 0
            is_below = y2_top >= y1_top - 0.02
            
            print(f"\nCondicoes:")
            print(f"  y_overlap: {y_overlap}")
            print(f"  is_below: {is_below}")
            print(f"  (y_overlap or is_below): {y_overlap or is_below}")
            
            if y_overlap or is_below:
                if y_overlap:
                    print(f"  Com overlap Y: overlap_x > 0? {overlap_x > 0}, is_aligned? {is_aligned}")
                    print(f"  Condicao: {overlap_x > 0 or is_aligned}")
                else:
                    MIN_OVERLAP_X_RATIO = 0.1
                    print(f"  Sem overlap Y: overlap_x >= min_width * 0.1? {overlap_x >= min_width * MIN_OVERLAP_X_RATIO}")
                    print(f"  Condicao: {overlap_x >= min_width * MIN_OVERLAP_X_RATIO or is_aligned}")
            
            # Verificar em qual linha cada token está
            print(f"\nLinhas:")
            # Agrupar tokens por linha
            lines = {}
            for token in tokens:
                bbox = token.get("bbox", [0, 0, 0, 0])
                if len(bbox) >= 4:
                    y_center = (bbox[1] + bbox[3]) / 2.0
                    THRESHOLD_SAME_LINE = 0.005
                    line_id = None
                    min_distance = THRESHOLD_SAME_LINE
                    
                    for existing_line_id in lines.keys():
                        distance = abs(y_center - existing_line_id)
                        if distance < min_distance:
                            min_distance = distance
                            line_id = existing_line_id
                    
                    if line_id is None:
                        line_id = y_center
                    
                    if line_id not in lines:
                        lines[line_id] = []
                    lines[line_id].append(token["id"])
            
            # Encontrar linhas dos tokens
            token1_line = None
            token2_line = None
            for line_id, token_ids in lines.items():
                if token1_id in token_ids:
                    token1_line = line_id
                if token2_id in token_ids:
                    token2_line = line_id
            
            print(f"  Token {token1_id} linha: {token1_line:.4f}")
            print(f"  Token {token2_id} linha: {token2_line:.4f}")
            
            # Verificar se são linhas adjacentes
            sorted_line_ids = sorted(lines.keys())
            if token1_line and token2_line:
                try:
                    idx1 = sorted_line_ids.index(token1_line)
                    idx2 = sorted_line_ids.index(token2_line)
                    print(f"  Indices: {idx1}, {idx2}")
                    print(f"  Sao adjacentes? {abs(idx1 - idx2) == 1}")
                except ValueError:
                    print(f"  Erro ao encontrar indices")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "tela_sistema_1.pdf"
    
    # Debug token 5 -> token 10
    debug_vertical_edges(str(pdf_path), token1_id=5, token2_id=10)

