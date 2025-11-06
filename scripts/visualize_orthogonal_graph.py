"""Script para visualizar grafo ortogonal no HTML."""

import sys
import json
import base64
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from src.io.pdf_loader import load_document, extract_blocks
from src.layout.builder import build_layout
from src.graph.spacing_model import compute_spacing_thresholds
from src.graph.orthogonal_edges import build_orthogonal_graph
from src.graph.roles_rules import assign_roles
from src.layout.style_signature import compute_style_signatures
from src.core.schema import enrich_schema, build_lexicon


def pdf_to_base64_image(pdf_path: str) -> tuple[str, float, float, float, float]:
    """Converte primeira página do PDF para imagem base64.
    
    Returns:
        tuple: (img_base64, rendered_width, rendered_height, original_width, original_height)
    """
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return "", 0, 0, 0, 0
        
        page = doc[0]
        original_width = page.rect.width
        original_height = page.rect.height
        
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        rendered_width = pix.width
        rendered_height = pix.height
        
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        doc.close()
        return img_base64, rendered_width, rendered_height, original_width, original_height
    except Exception as e:
        print(f"Erro ao converter PDF: {e}", file=sys.stderr)
        return "", 0, 0, 0, 0


def create_orthogonal_graph_html(
    pdf_path: str,
    label: str,
    schema_dict: Dict[str, str],
    output_path: str
):
    """Cria HTML com visualização do grafo ortogonal."""
    
    print(f"Carregando PDF: {pdf_path}", file=sys.stderr)
    doc = load_document(pdf_path, label=label)
    blocks = extract_blocks(doc)
    print(f"  ✓ {len(blocks)} blocos extraídos", file=sys.stderr)
    
    # Build layout
    print("Construindo layout...", file=sys.stderr)
    layout = build_layout(doc, blocks)
    
    # Enrich schema
    print("Enriquecendo schema...", file=sys.stderr)
    enriched = enrich_schema(label, schema_dict)
    schema_fields = enriched.fields
    
    # Build thresholds
    print("Calculando thresholds...", file=sys.stderr)
    thresholds = compute_spacing_thresholds(blocks)
    
    # Build orthogonal graph
    print("Construindo grafo ortogonal...", file=sys.stderr)
    orthogonal_graph = build_orthogonal_graph(blocks, thresholds)
    
    # Compute style signatures
    print("Calculando assinaturas de estilo...", file=sys.stderr)
    style_signatures = compute_style_signatures(blocks)
    
    # Build lexicons and field types
    schema_lexicons = {}
    field_types = {}
    for field in schema_fields:
        lexicon = build_lexicon(field)
        schema_lexicons[field.name] = lexicon
        field_types[field.name] = field.type or "text"
    
    # Assign roles
    print("Atribuindo roles...", file=sys.stderr)
    block_roles = assign_roles(
        blocks,
        orthogonal_graph,
        style_signatures,
        schema_lexicons=schema_lexicons,
        field_types=field_types,
    )
    
    # Get block_by_id from graph
    block_by_id = orthogonal_graph.get("block_by_id", {})
    adj = orthogonal_graph.get("adj", {})
    
    # Converter PDF para imagem
    pdf_img_base64, pdf_width, pdf_height, pdf_original_width, pdf_original_height = pdf_to_base64_image(pdf_path)
    
    if not pdf_img_base64:
        print("Erro ao converter PDF", file=sys.stderr)
        return
    
    # Preparar dados para JavaScript
    nodes_data = []
    for block in blocks:
        role = block_roles.get(block.id, "OTHER")
        x0, y0, x1, y1 = block.bbox
        
        # Normalizar bbox para coordenadas da imagem renderizada
        # bbox está em [0,1], preciso converter para pixels da imagem
        norm_x0 = x0 * pdf_width
        norm_y0 = y0 * pdf_height
        norm_x1 = x1 * pdf_width
        norm_y1 = y1 * pdf_height
        
        nodes_data.append({
            "id": block.id,
            "text": (block.text or "")[:100],  # Limitar texto
            "bbox": [norm_x0, norm_y0, norm_x1, norm_y1],
            "role": role,
            "font_size": block.font_size or 0,
        })
    
    # Preparar arestas
    edges_data = []
    for block_id, neighbors in adj.items():
        for direction, neighbor_ids in neighbors.items():
            for neighbor_id in neighbor_ids:
                edges_data.append({
                    "from": block_id,
                    "to": neighbor_id,
                    "direction": direction,  # "up", "down", "left", "right"
                })
    
    # Contar roles
    role_counts = {}
    for role in block_roles.values():
        role_counts[role] = role_counts.get(role, 0) + 1
    
    # Estatísticas do grafo
    stats = {
        "total_blocks": len(blocks),
        "total_edges": len(edges_data),
        "role_counts": role_counts,
        "directions": {
            "up": sum(1 for e in edges_data if e["direction"] == "up"),
            "down": sum(1 for e in edges_data if e["direction"] == "down"),
            "left": sum(1 for e in edges_data if e["direction"] == "left"),
            "right": sum(1 for e in edges_data if e["direction"] == "right"),
        }
    }
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Grafo Ortogonal - {Path(pdf_path).name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
        }}
        .stats {{
            margin-bottom: 20px;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}
        .stat-item {{
            display: flex;
            flex-direction: column;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}
        .stat-value {{
            font-size: 18px;
            font-weight: bold;
            color: #333;
        }}
        .controls {{
            margin-bottom: 20px;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
        }}
        .controls label {{
            margin-right: 15px;
            font-weight: bold;
        }}
        .controls input[type="checkbox"] {{
            margin-right: 5px;
        }}
        .overlay-container {{
            position: relative;
            display: inline-block;
            border: 2px solid #ddd;
            margin: 20px 0;
            background: white;
        }}
        .pdf-image {{
            display: block;
            width: 100%;
            height: auto;
        }}
        .svg-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            opacity: 0.9;
            pointer-events: none;
        }}
        .svg-overlay svg {{
            width: 100%;
            height: 100%;
            display: block;
        }}
        .block-info {{
            margin-top: 20px;
            padding: 15px;
            background: #f0f0f0;
            border-radius: 5px;
        }}
        .block-item {{
            margin: 10px 0;
            padding: 10px;
            background: white;
            border-left: 3px solid #4CAF50;
            border-radius: 3px;
        }}
        .role-header {{
            color: #FF5722;
            font-weight: bold;
        }}
        .role-label {{
            color: #2196F3;
            font-weight: bold;
        }}
        .role-value {{
            color: #4CAF50;
            font-weight: bold;
        }}
        .role-other {{
            color: #9E9E9E;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Grafo Ortogonal - {Path(pdf_path).name}</h1>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-label">Total de Blocos</div>
                <div class="stat-value">{stats['total_blocks']}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Total de Arestas</div>
                <div class="stat-value">{stats['total_edges']}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">HEADER</div>
                <div class="stat-value">{stats['role_counts'].get('HEADER', 0)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">LABEL</div>
                <div class="stat-value">{stats['role_counts'].get('LABEL', 0)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">VALUE</div>
                <div class="stat-value">{stats['role_counts'].get('VALUE', 0)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Arestas ↑</div>
                <div class="stat-value">{stats['directions']['up']}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Arestas ↓</div>
                <div class="stat-value">{stats['directions']['down']}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Arestas ←</div>
                <div class="stat-value">{stats['directions']['left']}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Arestas →</div>
                <div class="stat-value">{stats['directions']['right']}</div>
            </div>
        </div>
        
        <div class="controls">
            <label>
                <input type="checkbox" id="show-blocks" checked> Mostrar Blocos
            </label>
            <label>
                <input type="checkbox" id="show-edges" checked> Mostrar Arestas
            </label>
            <label>
                <input type="checkbox" id="show-header" checked> HEADER
            </label>
            <label>
                <input type="checkbox" id="show-label" checked> LABEL
            </label>
            <label>
                <input type="checkbox" id="show-value" checked> VALUE
            </label>
            <label>
                <input type="checkbox" id="show-other" checked> OTHER
            </label>
        </div>
        
        <div class="overlay-container">
            <img src="data:image/png;base64,{pdf_img_base64}" class="pdf-image" id="pdf-image">
            <div class="svg-overlay" id="svg-overlay">
                <svg id="graph-svg" xmlns="http://www.w3.org/2000/svg"></svg>
            </div>
        </div>
        
        <div class="block-info">
            <h3>Blocos ({len(nodes_data)})</h3>
            <div id="block-list"></div>
        </div>
    </div>
    
    <script>
        const nodes = {json.dumps(nodes_data, ensure_ascii=False)};
        const edges = {json.dumps(edges_data, ensure_ascii=False)};
        const pdfWidth = {pdf_width};
        const pdfHeight = {pdf_height};
        
        // Cores por role
        const roleColors = {{
            "HEADER": "#FF5722",
            "LABEL": "#2196F3",
            "VALUE": "#4CAF50",
            "OTHER": "#9E9E9E"
        }};
        
        // Cores por direção
        const directionColors = {{
            "up": "#FF9800",
            "down": "#00BCD4",
            "left": "#9C27B0",
            "right": "#F44336"
        }};
        
        // Símbolos por direção
        const directionSymbols = {{
            "up": "↑",
            "down": "↓",
            "left": "←",
            "right": "→"
        }};
        
        function renderGraph() {{
            const svg = document.getElementById("graph-svg");
            svg.innerHTML = "";
            
            const showBlocks = document.getElementById("show-blocks").checked;
            const showEdges = document.getElementById("show-edges").checked;
            const showHeader = document.getElementById("show-header").checked;
            const showLabel = document.getElementById("show-label").checked;
            const showValue = document.getElementById("show-value").checked;
            const showOther = document.getElementById("show-other").checked;
            
            const roleVisibility = {{
                "HEADER": showHeader,
                "LABEL": showLabel,
                "VALUE": showValue,
                "OTHER": showOther
            }};
            
            // Renderizar arestas primeiro (para ficarem atrás)
            if (showEdges) {{
                edges.forEach(edge => {{
                    const fromNode = nodes.find(n => n.id === edge.from);
                    const toNode = nodes.find(n => n.id === edge.to);
                    
                    if (!fromNode || !toNode) return;
                    
                    const fromRole = fromNode.role;
                    const toRole = toNode.role;
                    
                    if (!roleVisibility[fromRole] || !roleVisibility[toRole]) return;
                    
                    const fx0 = fromNode.bbox[0];
                    const fy0 = fromNode.bbox[1];
                    const fx1 = fromNode.bbox[2];
                    const fy1 = fromNode.bbox[3];
                    
                    const tx0 = toNode.bbox[0];
                    const ty0 = toNode.bbox[1];
                    const tx1 = toNode.bbox[2];
                    const ty1 = toNode.bbox[3];
                    
                    // Calcular pontos médios dos blocos
                    const fromCenterX = (fx0 + fx1) / 2;
                    const fromCenterY = (fy0 + fy1) / 2;
                    const toCenterX = (tx0 + tx1) / 2;
                    const toCenterY = (ty0 + ty1) / 2;
                    
                    // Determinar ponto de saída baseado na direção
                    let startX, startY, endX, endY;
                    
                    if (edge.direction === "right") {{
                        startX = fx1;
                        startY = fromCenterY;
                        endX = tx0;
                        endY = toCenterY;
                    }} else if (edge.direction === "left") {{
                        startX = fx0;
                        startY = fromCenterY;
                        endX = tx1;
                        endY = toCenterY;
                    }} else if (edge.direction === "down") {{
                        startX = fromCenterX;
                        startY = fy1;
                        endX = toCenterX;
                        endY = ty0;
                    }} else if (edge.direction === "up") {{
                        startX = fromCenterX;
                        startY = fy0;
                        endX = toCenterX;
                        endY = ty1;
                    }}
                    
                    const color = directionColors[edge.direction] || "#000";
                    const arrowId = `arrow-${{edge.direction}}`;
                    
                    // Criar defs para setas se não existir
                    let defs = svg.querySelector("defs");
                    if (!defs) {{
                        defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
                        svg.appendChild(defs);
                    }}
                    
                    // Criar marcador de seta se não existir
                    if (!document.getElementById(arrowId)) {{
                        const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
                        marker.setAttribute("id", arrowId);
                        marker.setAttribute("markerWidth", "10");
                        marker.setAttribute("markerHeight", "10");
                        marker.setAttribute("refX", "9");
                        marker.setAttribute("refY", "3");
                        marker.setAttribute("orient", "auto");
                        marker.setAttribute("markerUnits", "strokeWidth");
                        
                        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                        path.setAttribute("d", "M0,0 L0,6 L9,3 z");
                        path.setAttribute("fill", color);
                        marker.appendChild(path);
                        defs.appendChild(marker);
                    }}
                    
                    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                    line.setAttribute("x1", startX);
                    line.setAttribute("y1", startY);
                    line.setAttribute("x2", endX);
                    line.setAttribute("y2", endY);
                    line.setAttribute("stroke", color);
                    line.setAttribute("stroke-width", "2");
                    line.setAttribute("opacity", "0.6");
                    line.setAttribute("marker-end", `url(#${{arrowId}})`);
                    svg.appendChild(line);
                    
                    // Adicionar símbolo de direção no meio da linha
                    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
                    text.setAttribute("x", (startX + endX) / 2);
                    text.setAttribute("y", (startY + endY) / 2);
                    text.setAttribute("font-size", "16");
                    text.setAttribute("fill", color);
                    text.setAttribute("font-weight", "bold");
                    text.setAttribute("text-anchor", "middle");
                    text.setAttribute("dominant-baseline", "middle");
                    text.textContent = directionSymbols[edge.direction];
                    svg.appendChild(text);
                }});
            }}
            
            // Renderizar blocos
            if (showBlocks) {{
                nodes.forEach(node => {{
                    if (!roleVisibility[node.role]) return;
                    
                    const [x0, y0, x1, y1] = node.bbox;
                    const width = x1 - x0;
                    const height = y1 - y0;
                    
                    const color = roleColors[node.role] || "#000";
                    
                    // Retângulo do bloco
                    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                    rect.setAttribute("x", x0);
                    rect.setAttribute("y", y0);
                    rect.setAttribute("width", width);
                    rect.setAttribute("height", height);
                    rect.setAttribute("fill", color);
                    rect.setAttribute("opacity", "0.2");
                    rect.setAttribute("stroke", color);
                    rect.setAttribute("stroke-width", "2");
                    svg.appendChild(rect);
                    
                    // ID do bloco
                    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
                    text.setAttribute("x", x0 + 5);
                    text.setAttribute("y", y0 + 15);
                    text.setAttribute("font-size", "12");
                    text.setAttribute("fill", color);
                    text.setAttribute("font-weight", "bold");
                    text.textContent = `#${{node.id}} (${{node.role}})`;
                    svg.appendChild(text);
                }});
            }}
        }}
        
        function renderBlockList() {{
            const blockList = document.getElementById("block-list");
            blockList.innerHTML = "";
            
            const showHeader = document.getElementById("show-header").checked;
            const showLabel = document.getElementById("show-label").checked;
            const showValue = document.getElementById("show-value").checked;
            const showOther = document.getElementById("show-other").checked;
            
            const roleVisibility = {{
                "HEADER": showHeader,
                "LABEL": showLabel,
                "VALUE": showValue,
                "OTHER": showOther
            }};
            
            nodes.forEach(node => {{
                if (!roleVisibility[node.role]) return;
                
                const div = document.createElement("div");
                div.className = "block-item";
                div.innerHTML = `
                    <strong>Bloco #${{node.id}}</strong> 
                    <span class="role-${{node.role.toLowerCase()}}">[${{node.role}}]</span>
                    <br>
                    <small>${{node.text}}</small>
                `;
                blockList.appendChild(div);
            }});
        }}
        
        // Event listeners
        document.getElementById("show-blocks").addEventListener("change", renderGraph);
        document.getElementById("show-edges").addEventListener("change", renderGraph);
        document.getElementById("show-header").addEventListener("change", () => {{ renderGraph(); renderBlockList(); }});
        document.getElementById("show-label").addEventListener("change", () => {{ renderGraph(); renderBlockList(); }});
        document.getElementById("show-value").addEventListener("change", () => {{ renderGraph(); renderBlockList(); }});
        document.getElementById("show-other").addEventListener("change", () => {{ renderGraph(); renderBlockList(); }});
        
        // Renderizar inicialmente
        renderGraph();
        renderBlockList();
    </script>
</body>
</html>"""
    
    # Salvar HTML
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"HTML gerado: {output_path}", file=sys.stderr)


def main():
    """CLI entry point."""
    import argparse
    
    ap = argparse.ArgumentParser(
        description="Visualiza grafo ortogonal em HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--pdf", type=str, required=True, help="Caminho do PDF")
    ap.add_argument("--label", type=str, required=True, help="Label do documento")
    ap.add_argument("--schema", type=str, required=True, help="Caminho do dataset.json")
    ap.add_argument("--out", type=str, required=True, help="Caminho de saída do HTML")
    
    args = ap.parse_args()
    
    # Carregar schema
    dataset_path = Path(args.schema)
    if not dataset_path.exists():
        print(f"Erro: {dataset_path} não encontrado", file=sys.stderr)
        sys.exit(1)
    
    dataset_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    pdf_name = Path(args.pdf).name
    
    # Encontrar schema para este PDF
    schema_dict = None
    for entry in dataset_data:
        if entry.get("pdf_path") == pdf_name:
            schema_dict = entry.get("extraction_schema", {})
            break
    
    if not schema_dict:
        print(f"Erro: Schema não encontrado para {pdf_name}", file=sys.stderr)
        sys.exit(1)
    
    create_orthogonal_graph_html(args.pdf, args.label, schema_dict, args.out)


if __name__ == "__main__":
    main()


