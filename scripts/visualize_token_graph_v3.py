"""Script para visualizar grafo de tokens v3.0 com todos os campos no HTML."""

import sys
import json
import base64
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph
import fitz  # PyMuPDF


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
        print(f"Erro ao converter PDF: {e}")
        return "", 0, 0, 0, 0


def create_token_graph_html_v3(pdf_path: str, output_path: str, label: Optional[str] = None):
    """Cria HTML com visualização do grafo de tokens v3.0 mostrando todos os campos."""
    
    # Extrair tokens e construir grafo
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens, max_distance=0.25, label=label)
    
    # Converter PDF para imagem
    pdf_img_base64, pdf_width, pdf_height, pdf_original_width, pdf_original_height = pdf_to_base64_image(pdf_path)
    
    if not pdf_img_base64:
        print("Erro ao converter PDF")
        return
    
    # Preparar dados para JavaScript
    tokens_data = []
    for node in graph["nodes"]:
        tokens_data.append({
            "id": node["id"],
            "text": node["text"],
            "bbox": node["bbox"],
            "font_size": node.get("font_size"),
            "bold": node.get("bold", False),
            "italic": node.get("italic", False),
            "color": node.get("color"),
            "role": node.get("role"),
            "style_signature": node.get("style_signature"),
            "line_index": node.get("line_index", 0),
            "component_id": node.get("component_id", node["id"]),
            "block_id": node.get("block_id"),
        })
    
    edges_data = [
        {
            "from": e["from"],
            "to": e["to"],
            "direction": e["relation"]  # "relation" mapeia para "direction"
        }
        for e in graph["edges"]
    ]
    
    tables_data = graph.get("tables", [])
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Grafo de Tokens v3.0 - {Path(pdf_path).name}</title>
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
            margin-bottom: 20px;
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
        .overlay-container {{
            position: relative;
            display: inline-block;
            border: 2px solid #ddd;
            margin: 20px 0;
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
            opacity: 0.8;
            pointer-events: none;
        }}
        .svg-overlay svg {{
            width: 100%;
            height: 100%;
            display: block;
        }}
        .token-info {{
            margin-top: 20px;
            padding: 15px;
            background: #f0f0f0;
            border-radius: 5px;
        }}
        .token-item {{
            margin: 10px 0;
            padding: 10px;
            background: white;
            border-left: 3px solid #4CAF50;
            border-radius: 3px;
            font-size: 12px;
        }}
        .token-item.HEADER {{
            border-left-color: #FF0000;
            background: #FFE5E5;
        }}
        .token-item.LABEL {{
            border-left-color: #0066FF;
            background: #E5F0FF;
        }}
        .token-item.VALUE {{
            border-left-color: #00AA00;
            background: #E5FFE5;
        }}
        .field-label {{
            font-weight: bold;
            color: #555;
            margin-right: 5px;
        }}
        .field-value {{
            color: #333;
        }}
        .style-signature {{
            font-family: monospace;
            font-size: 11px;
            background: #f9f9f9;
            padding: 5px;
            border-radius: 3px;
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Visualização do Grafo de Tokens v3.0 - {Path(pdf_path).name}</h1>
        
        <div class="controls">
            <label>Opacidade do Grafo:</label>
            <input type="range" id="opacitySlider" min="0" max="1" step="0.1" value="0.8" 
                   oninput="document.getElementById('svgOverlay').style.opacity = this.value">
            <span id="opacityValue">80%</span>
            
            <label style="margin-left: 30px;">Mostrar/Ocultar Grafo:</label>
            <input type="checkbox" id="toggleGraph" checked 
                   onchange="document.getElementById('svgOverlay').style.display = this.checked ? 'block' : 'none'">
            
            <label style="margin-left: 30px;">Filtrar por Role:</label>
            <select id="roleFilter" onchange="filterTokens()">
                <option value="ALL">Todos</option>
                <option value="HEADER">HEADER</option>
                <option value="LABEL">LABEL</option>
                <option value="VALUE">VALUE</option>
                <option value="null">Sem Role</option>
            </select>
        </div>
        
        <div class="overlay-container" id="overlayContainer">
            <img src="data:image/png;base64,{pdf_img_base64}" 
                 alt="PDF" class="pdf-image" id="pdfImage">
            <div id="svgOverlay" class="svg-overlay">
                <svg xmlns="http://www.w3.org/2000/svg" id="overlaySvg" style="width: 100%; height: 100%; position: absolute; top: 0; left: 0;">
                </svg>
            </div>
        </div>
        
        <div class="token-info">
            <h3>Tokens ({len(graph['nodes'])} tokens, {len(graph['edges'])} edges, {len(tables_data)} tabelas)</h3>
            {f'<p><strong>Tabelas Detectadas:</strong> {len(tables_data)}</p>' if tables_data else ''}
            <p><strong>Legenda:</strong></p>
            <ul>
                <li><span style="color: #FF0000;">■</span> HEADER (vermelho)</li>
                <li><span style="color: #0066FF;">■</span> LABEL (azul)</li>
                <li><span style="color: #00AA00;">■</span> VALUE (verde)</li>
                <li><span style="color: #4CAF50;">■</span> Sem role (verde-claro)</li>
            </ul>
            <p><strong>Edges:</strong></p>
            <ul>
                <li><span style="color: #00ff00;">━</span> East (→) - Verde</li>
                <li><span style="color: #0000ff;">┃</span> South (↓) - Azul</li>
            </ul>
            <h4>Lista de Tokens:</h4>
            <div id="tokenList" style="max-height: 500px; overflow-y: auto;"></div>
        </div>
    </div>
    
    <script>
        const tokensData = {json.dumps(tokens_data)};
        const edgesData = {json.dumps(edges_data)};
        const tablesData = {json.dumps(tables_data)};
        const pdfRenderedWidth = {pdf_width};
        const pdfRenderedHeight = {pdf_height};
        
        function renderTokenGraph() {{
            const svg = document.getElementById('overlaySvg');
            const img = document.getElementById('pdfImage');
            
            img.onload = function() {{
                const imgNaturalWidth = img.naturalWidth || img.width || pdfRenderedWidth;
                const imgNaturalHeight = img.naturalHeight || img.height || pdfRenderedHeight;
                const imgDisplayWidth = img.offsetWidth || imgNaturalWidth;
                const imgDisplayHeight = img.offsetHeight || imgNaturalHeight;
                
                const scaleX = imgDisplayWidth / imgNaturalWidth;
                const scaleY = imgDisplayHeight / imgNaturalHeight;
                
                const svgViewBoxWidth = pdfRenderedWidth;
                const svgViewBoxHeight = pdfRenderedHeight;
                
                svg.setAttribute('viewBox', `0 0 ${{svgViewBoxWidth}} ${{svgViewBoxHeight}}`);
                svg.setAttribute('width', '100%');
                svg.setAttribute('height', '100%');
                svg.setAttribute('preserveAspectRatio', 'none');
                
                const imgWidth = svgViewBoxWidth;
                const imgHeight = svgViewBoxHeight;
                
                svg.innerHTML = '';
                
                // Criar grupos
                const tablesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                tablesGroup.id = 'tables';
                
                const edgesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                edgesGroup.id = 'edges';
                edgesGroup.setAttribute('stroke-width', '2');
                
                const tokensGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                tokensGroup.id = 'tokens';
                
                // Desenhar tabelas primeiro (atrás de tudo)
                if (tablesData && tablesData.length > 0) {{
                    tablesData.forEach(function(table, tableIndex) {{
                        const bbox = table.bbox;
                        const x0 = bbox[0] * imgWidth;
                        const y0 = bbox[1] * imgHeight;
                        const x1 = bbox[2] * imgWidth;
                        const y1 = bbox[3] * imgHeight;
                        
                        // Retângulo da tabela
                        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                        rect.setAttribute('x', x0.toString());
                        rect.setAttribute('y', y0.toString());
                        rect.setAttribute('width', (x1 - x0).toString());
                        rect.setAttribute('height', (y1 - y0).toString());
                        rect.setAttribute('fill', table.orientation === 'horizontal' ? 'rgba(0, 255, 0, 0.1)' : 'rgba(0, 0, 255, 0.1)');
                        rect.setAttribute('stroke', table.orientation === 'horizontal' ? '#00ff00' : '#0000ff');
                        rect.setAttribute('stroke-width', '3');
                        rect.setAttribute('stroke-dasharray', '5,5');
                        rect.setAttribute('data-table-index', tableIndex.toString());
                        rect.setAttribute('data-table-orientation', table.orientation);
                        rect.setAttribute('data-table-size', table.rows + 'x' + table.cols);
                        
                        // Label da tabela
                        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                        label.setAttribute('x', (x0 + 5).toString());
                        label.setAttribute('y', (y0 + 15).toString());
                        label.setAttribute('font-size', '12');
                        label.setAttribute('fill', table.orientation === 'horizontal' ? '#00aa00' : '#0000aa');
                        label.setAttribute('font-weight', 'bold');
                        label.setAttribute('style', 'pointer-events: none;');
                        label.textContent = 'Tabela ' + (tableIndex + 1) + ' (' + table.orientation + ', ' + table.rows + 'x' + table.cols + ')';
                        
                        tablesGroup.appendChild(rect);
                        tablesGroup.appendChild(label);
                    }});
                }}
                
                // Desenhar edges (linhas conectando tokens)
                const edgeColors = {{
                    'east': '#00ff00',   // Verde para direita
                    'south': '#0000ff',  // Azul para baixo
                    'north': '#ff00ff',  // Magenta para cima
                    'west': '#ff8800'    // Laranja para esquerda
                }};
                
                edgesData.forEach(function(edge) {{
                    const tokenFrom = tokensData.find(t => t.id === edge.from);
                    const tokenTo = tokensData.find(t => t.id === edge.to);
                    
                    if (!tokenFrom || !tokenTo) return;
                    
                    const bboxFrom = tokenFrom.bbox;
                    const bboxTo = tokenTo.bbox;
                    
                    let x1, y1, x2, y2;
                    
                    if (edge.direction === 'south' || edge.direction === 'north') {{
                        x1 = ((bboxFrom[0] + bboxFrom[2]) / 2) * imgWidth;
                        x2 = ((bboxTo[0] + bboxTo[2]) / 2) * imgWidth;
                        
                        if (edge.direction === 'south') {{
                            y1 = bboxFrom[3] * imgHeight;
                            y2 = bboxTo[1] * imgHeight;
                        }} else {{
                            y1 = bboxFrom[1] * imgHeight;
                            y2 = bboxTo[3] * imgHeight;
                        }}
                    }} else {{
                        y1 = ((bboxFrom[1] + bboxFrom[3]) / 2) * imgHeight;
                        y2 = ((bboxTo[1] + bboxTo[3]) / 2) * imgHeight;
                        
                        if (edge.direction === 'east') {{
                            x1 = bboxFrom[2] * imgWidth;
                            x2 = bboxTo[0] * imgWidth;
                        }} else {{
                            x1 = bboxFrom[0] * imgWidth;
                            x2 = bboxTo[2] * imgWidth;
                        }}
                    }}
                    
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', x1.toString());
                    line.setAttribute('y1', y1.toString());
                    line.setAttribute('x2', x2.toString());
                    line.setAttribute('y2', y2.toString());
                    line.setAttribute('stroke', edgeColors[edge.direction] || '#000000');
                    line.setAttribute('stroke-opacity', '0.6');
                    edgesGroup.appendChild(line);
                }});
                
                // Desenhar tokens (retângulos) com cores por role
                tokensData.forEach(function(token) {{
                    const bbox = token.bbox;
                    const x0 = bbox[0] * imgWidth;
                    const y0 = bbox[1] * imgHeight;
                    const x1 = bbox[2] * imgWidth;
                    const y1 = bbox[3] * imgHeight;
                    
                    const strokeWidth = 2;
                    const strokeHalf = strokeWidth / 2;
                    const adjustedX0 = x0;
                    const adjustedY0 = y0;
                    const adjustedX1 = x1 + strokeHalf;
                    const adjustedY1 = y1;
                    
                    const rectWidth = Math.max(1, adjustedX1 - adjustedX0);
                    const rectHeight = Math.max(1, adjustedY1 - adjustedY0);
                    
                    // Cor baseada no role
                    let fillColor = 'rgba(255, 0, 0, 0.2)';
                    let strokeColor = '#ff0000';
                    if (token.role === 'HEADER') {{
                        fillColor = 'rgba(255, 0, 0, 0.3)';
                        strokeColor = '#FF0000';
                    }} else if (token.role === 'LABEL') {{
                        fillColor = 'rgba(0, 102, 255, 0.3)';
                        strokeColor = '#0066FF';
                    }} else if (token.role === 'VALUE') {{
                        fillColor = 'rgba(0, 170, 0, 0.3)';
                        strokeColor = '#00AA00';
                    }}
                    
                    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    rect.setAttribute('x', adjustedX0.toString());
                    rect.setAttribute('y', adjustedY0.toString());
                    rect.setAttribute('width', rectWidth.toString());
                    rect.setAttribute('height', rectHeight.toString());
                    rect.setAttribute('fill', fillColor);
                    rect.setAttribute('stroke', strokeColor);
                    rect.setAttribute('stroke-width', strokeWidth.toString());
                    rect.setAttribute('data-token-id', token.id.toString());
                    tokensGroup.appendChild(rect);
                    
                    // Texto do token (ID pequeno no canto)
                    const textId = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    textId.setAttribute('x', (x0 + 5).toString());
                    textId.setAttribute('y', (y0 + 15).toString());
                    textId.setAttribute('font-size', '10px');
                    textId.setAttribute('fill', '#000');
                    textId.setAttribute('font-weight', 'bold');
                    textId.setAttribute('pointer-events', 'none');
                    textId.textContent = token.id.toString();
                    tokensGroup.appendChild(textId);
                }});
                
                svg.appendChild(tablesGroup);
                svg.appendChild(edgesGroup);
                svg.appendChild(tokensGroup);
                
                updateTokenList();
            }};
            
            if (img.complete && img.naturalWidth > 0) {{
                img.onload();
            }}
        }}
        
        function updateTokenList() {{
            const tokenList = document.getElementById('tokenList');
            const roleFilter = document.getElementById('roleFilter').value;
            
            tokenList.innerHTML = '';
            
            let filteredTokens = tokensData;
            if (roleFilter !== 'ALL') {{
                if (roleFilter === 'null') {{
                    filteredTokens = tokensData.filter(t => !t.role);
                }} else {{
                    filteredTokens = tokensData.filter(t => t.role === roleFilter);
                }}
            }}
            
            filteredTokens.forEach(function(token) {{
                const div = document.createElement('div');
                div.className = 'token-item ' + (token.role || '');
                
                // Encontrar edges conectados
                const edgesFrom = edgesData.filter(function(e) {{ return e.from === token.id || e.to === token.id; }});
                const connections = edgesFrom.map(function(e) {{
                    const otherId = e.from === token.id ? e.to : e.from;
                    const otherToken = tokensData.find(function(t) {{ return t.id === otherId; }});
                    return otherId + ' (' + (otherToken ? otherToken.text.substring(0, 15) : '') + ') [' + e.direction + ']';
                }}).join(', ');
                
                let html = '<strong>Token #' + token.id + '</strong><br>';
                html += '<span class="field-label">Texto:</span><span class="field-value">' + escapeHtml(token.text) + '</span><br>';
                html += '<span class="field-label">Role:</span><span class="field-value">' + (token.role || 'None') + '</span><br>';
                html += '<span class="field-label">BBox:</span><span class="field-value">[' + 
                    token.bbox[0].toFixed(4) + ', ' + token.bbox[1].toFixed(4) + ', ' + 
                    token.bbox[2].toFixed(4) + ', ' + token.bbox[3].toFixed(4) + ']</span><br>';
                html += '<span class="field-label">Font Size:</span><span class="field-value">' + (token.font_size || 'N/A') + '</span><br>';
                html += '<span class="field-label">Bold:</span><span class="field-value">' + (token.bold ? 'Yes' : 'No') + '</span><br>';
                html += '<span class="field-label">Italic:</span><span class="field-value">' + (token.italic ? 'Yes' : 'No') + '</span><br>';
                html += '<span class="field-label">Color:</span><span class="field-value">' + (token.color || 'N/A') + '</span><br>';
                html += '<span class="field-label">Line Index:</span><span class="field-value">' + token.line_index + '</span><br>';
                html += '<span class="field-label">Component ID:</span><span class="field-value">' + token.component_id + '</span><br>';
                
                if (token.style_signature) {{
                    html += '<div class="style-signature">';
                    html += '<strong>Style Signature:</strong><br>';
                    html += 'Font Family ID: ' + token.style_signature.font_family_id + '<br>';
                    html += 'Font Size Bin: ' + token.style_signature.font_size_bin + '<br>';
                    html += 'Bold: ' + (token.style_signature.is_bold ? 'Yes' : 'No') + '<br>';
                    html += 'Italic: ' + (token.style_signature.is_italic ? 'Yes' : 'No') + '<br>';
                    html += 'Color Cluster: ' + token.style_signature.color_cluster + '<br>';
                    html += 'Caps Ratio Bin: ' + token.style_signature.caps_ratio_bin + '<br>';
                    html += 'Letter Spacing Bin: ' + token.style_signature.letter_spacing_bin;
                    html += '</div>';
                }}
                
                html += '<br><span class="field-label">Conectado a:</span><span class="field-value">' + 
                    (connections || 'nenhum') + '</span>';
                
                div.innerHTML = html;
                tokenList.appendChild(div);
            }});
        }}
        
        function filterTokens() {{
            updateTokenList();
        }}
        
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
        
        // Atualizar valor do slider
        document.getElementById('opacitySlider').addEventListener('input', function(e) {{
            document.getElementById('opacityValue').textContent = Math.round(e.target.value * 100) + '%';
        }});
        
        // Renderizar quando carregar
        if (document.readyState === 'loading') {{
            window.addEventListener('load', renderTokenGraph);
        }} else {{
            setTimeout(renderTokenGraph, 100);
        }}
    </script>
</body>
</html>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Visualização HTML v3.0 criada em: {output_path}")


def main():
    """Gera visualização do grafo de tokens v3.0 para todos os PDFs."""
    project_root = Path(__file__).parent.parent
    samples_dir = project_root / "data" / "samples"
    
    print("="*80)
    print("GERANDO VISUALIZACAO DO GRAFO DE TOKENS v3.0 PARA TODOS OS PDFs")
    print("="*80)
    
    # Encontrar todos os PDFs na pasta samples
    pdf_files = sorted(samples_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"ERRO: Nenhum PDF encontrado em {samples_dir}")
        return
    
    print(f"\nEncontrados {len(pdf_files)} PDF(s):")
    for pdf_file in pdf_files:
        print(f"  - {pdf_file.name}")
    
    print("\n" + "="*80)
    
    # Mapear PDFs para labels (baseado no nome do arquivo)
    pdf_to_label = {
        "oab_1": "carteira_oab",
        "oab_2": "carteira_oab",
        "oab_3": "carteira_oab",
        "tela_sistema_1": "tela_sistema",
        "tela_sistema_2": "tela_sistema",
        "tela_sistema_3": "tela_sistema",
    }
    
    # Gerar HTML para cada PDF
    for pdf_file in pdf_files:
        pdf_name = pdf_file.stem  # Nome sem extensão
        output_html = project_root / f"token_graph_overlay_v3_{pdf_name}.html"
        label = pdf_to_label.get(pdf_name, None)
        
        print(f"\nProcessando: {pdf_file.name} (label: {label or 'unknown'})")
        try:
            create_token_graph_html_v3(str(pdf_file), str(output_html), label=label)
            print(f"  OK: {output_html.name}")
        except Exception as e:
            print(f"  ERRO ao processar {pdf_file.name}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("CONCLUIDO!")
    print("\nCores das edges:")
    print("  Verde: east (->)")
    print("  Azul: south (v)")
    print("\nCores dos tokens por role:")
    print("  Vermelho: HEADER")
    print("  Azul: LABEL")
    print("  Verde: VALUE")
    print("  Verde: Sem role")


if __name__ == "__main__":
    main()

