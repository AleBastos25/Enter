"""Script para visualizar grafo de tokens no HTML."""

import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph
import fitz  # PyMuPDF


def pdf_to_base64_image(pdf_path: str) -> tuple[str, float, float, float, float]:
    """Converte primeira página do PDF para imagem base64.
    
    Returns:
        tuple: (img_base64, rendered_width, rendered_height, original_width, original_height)
    """
    try:
        import fitz  # PyMuPDF
        
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


def create_token_graph_html(pdf_path: str, output_path: str):
    """Cria HTML com visualização do grafo de tokens."""
    
    # Extrair tokens e construir grafo
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens, max_distance=0.25)
    
    # Converter PDF para imagem
    pdf_img_base64, pdf_width, pdf_height, pdf_original_width, pdf_original_height = pdf_to_base64_image(pdf_path)
    
    if not pdf_img_base64:
        print("Erro ao converter PDF")
        return
    
    # Preparar dados para JavaScript
    tokens_data = [
        {
            "id": t["id"],
            "text": t["text"],
            "bbox": t["bbox"]  # bbox já está normalizado [0,1]
        }
        for t in graph["nodes"]
    ]
    
    edges_data = [
        {
            "from": e["from"],
            "to": e["to"],
            "direction": e["relation"]  # "relation" mapeia para "direction"
        }
        for e in graph["edges"]
    ]
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Grafo de Tokens - oab_1.pdf</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
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
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Visualização do Grafo de Tokens</h1>
        
        <div class="controls">
            <label>Opacidade do Grafo:</label>
            <input type="range" id="opacitySlider" min="0" max="1" step="0.1" value="0.8" 
                   oninput="document.getElementById('svgOverlay').style.opacity = this.value">
            <span id="opacityValue">80%</span>
            
            <label style="margin-left: 30px;">Mostrar/Ocultar Grafo:</label>
            <input type="checkbox" id="toggleGraph" checked 
                   onchange="document.getElementById('svgOverlay').style.display = this.checked ? 'block' : 'none'">
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
            <h3>Tokens ({len(graph['nodes'])} tokens, {len(graph['edges'])} edges)</h3>
            <div id="tokenList"></div>
        </div>
    </div>
    
    <script>
        const tokensData = {json.dumps(tokens_data)};
        const edgesData = {json.dumps(edges_data)};
        const pdfRenderedWidth = {pdf_width};
        const pdfRenderedHeight = {pdf_height};
        
        function renderTokenGraph() {{
            const svg = document.getElementById('overlaySvg');
            const img = document.getElementById('pdfImage');
            
            img.onload = function() {{
                // IMPORTANTE: Usar as dimensões REAIS da imagem após redimensionamento pelo CSS
                // A imagem pode ter sido redimensionada pelo CSS (width: 100%), então precisamos
                // usar as dimensões reais, não as dimensões originais renderizadas
                const imgNaturalWidth = img.naturalWidth || img.width || pdfRenderedWidth;
                const imgNaturalHeight = img.naturalHeight || img.height || pdfRenderedHeight;
                const imgDisplayWidth = img.offsetWidth || imgNaturalWidth;
                const imgDisplayHeight = img.offsetHeight || imgNaturalHeight;
                
                // Fator de escala entre dimensões naturais e dimensões exibidas
                const scaleX = imgDisplayWidth / imgNaturalWidth;
                const scaleY = imgDisplayHeight / imgNaturalHeight;
                
                // Usar dimensões naturais para o viewBox (coordenadas originais)
                // Mas aplicar escala nas coordenadas se necessário
                const svgViewBoxWidth = pdfRenderedWidth;
                const svgViewBoxHeight = pdfRenderedHeight;
                
                // Configurar SVG com viewBox baseado nas dimensões renderizadas originais
                svg.setAttribute('viewBox', `0 0 ${{svgViewBoxWidth}} ${{svgViewBoxHeight}}`);
                svg.setAttribute('width', '100%');
                svg.setAttribute('height', '100%');
                svg.setAttribute('preserveAspectRatio', 'none');
                
                // Para o cálculo das coordenadas, usar as dimensões do viewBox (renderizadas)
                // O SVG vai escalar automaticamente para o tamanho da imagem
                const imgWidth = svgViewBoxWidth;
                const imgHeight = svgViewBoxHeight;
                
                // Limpar SVG
                svg.innerHTML = '';
                
                // Criar grupos
                const edgesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                edgesGroup.id = 'edges';
                edgesGroup.setAttribute('stroke-width', '2');
                
                const tokensGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                tokensGroup.id = 'tokens';
                
                // Desenhar edges (linhas conectando tokens)
                const edgeColors = {{
                    'north': '#00ff00',  // Verde para cima
                    'south': '#0000ff',  // Azul para baixo
                    'east': '#ff00ff',   // Magenta para direita
                    'west': '#ff8800'    // Laranja para esquerda
                }};
                
                edgesData.forEach(function(edge) {{
                    const tokenFrom = tokensData.find(t => t.id === edge.from);
                    const tokenTo = tokensData.find(t => t.id === edge.to);
                    
                    if (!tokenFrom || !tokenTo) return;
                    
                    const bboxFrom = tokenFrom.bbox;
                    const bboxTo = tokenTo.bbox;
                    
                    // Calcular pontos de conexão
                    let x1, y1, x2, y2;
                    
                    if (edge.direction === 'north' || edge.direction === 'south') {{
                        // Conexão vertical: centro X
                        x1 = ((bboxFrom[0] + bboxFrom[2]) / 2) * imgWidth;
                        x2 = ((bboxTo[0] + bboxTo[2]) / 2) * imgWidth;
                        
                        if (edge.direction === 'north') {{
                            y1 = bboxFrom[1] * imgHeight;  // Topo do token origem
                            y2 = bboxTo[3] * imgHeight;   // Base do token destino
                        }} else {{
                            y1 = bboxFrom[3] * imgHeight;  // Base do token origem
                            y2 = bboxTo[1] * imgHeight;   // Topo do token destino
                        }}
                    }} else {{
                        // Conexão horizontal: centro Y
                        y1 = ((bboxFrom[1] + bboxFrom[3]) / 2) * imgHeight;
                        y2 = ((bboxTo[1] + bboxTo[3]) / 2) * imgHeight;
                        
                        if (edge.direction === 'east') {{
                            x1 = bboxFrom[2] * imgWidth;   // Direita do token origem
                            x2 = bboxTo[0] * imgWidth;     // Esquerda do token destino
                        }} else {{
                            x1 = bboxFrom[0] * imgWidth;  // Esquerda do token origem
                            x2 = bboxTo[2] * imgWidth;     // Direita do token destino
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
                
                // Desenhar tokens (retângulos)
                tokensData.forEach(function(token) {{
                    const bbox = token.bbox;
                    // Usar dimensões exatas da imagem renderizada
                    const x0 = bbox[0] * imgWidth;
                    const y0 = bbox[1] * imgHeight;
                    const x1 = bbox[2] * imgWidth;
                    const y1 = bbox[3] * imgHeight;
                    
                    // Garantir que o retângulo cubra completamente o texto
                    // O stroke-width de 2 pixels desenha metade para dentro e metade para fora
                    // IMPORTANTE: Expandir APENAS À DIREITA para compensar o stroke, já que o padding
                    // foi aplicado apenas à direita no Python. Não expandir à esquerda, topo ou base.
                    const strokeWidth = 2;
                    const strokeHalf = strokeWidth / 2; // Metade do stroke fica para fora
                    
                    // Expandir APENAS À DIREITA (x1) para compensar o stroke externo
                    // Manter borda esquerda, topo e base inalteradas
                    const adjustedX0 = x0; // Sem ajuste à esquerda
                    const adjustedY0 = y0; // Sem ajuste no topo
                    const adjustedX1 = x1 + strokeHalf; // Ajuste apenas à direita
                    const adjustedY1 = y1; // Sem ajuste embaixo
                    
                    const rectWidth = Math.max(1, adjustedX1 - adjustedX0);
                    const rectHeight = Math.max(1, adjustedY1 - adjustedY0);
                    
                    // Retângulo do token
                    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    rect.setAttribute('x', adjustedX0.toString());
                    rect.setAttribute('y', adjustedY0.toString());
                    rect.setAttribute('width', rectWidth.toString());
                    rect.setAttribute('height', rectHeight.toString());
                    rect.setAttribute('fill', 'rgba(255, 0, 0, 0.2)');
                    rect.setAttribute('stroke', '#ff0000');
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
                    
                    // Nome do token (texto completo, se couber)
                    const tokenText = token.text.length > 20 ? token.text.substring(0, 17) + '...' : token.text;
                    const textLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    textLabel.setAttribute('x', ((x0 + x1) / 2).toString());
                    textLabel.setAttribute('y', ((y0 + y1) / 2 + 5).toString());
                    textLabel.setAttribute('text-anchor', 'middle');
                    textLabel.setAttribute('dominant-baseline', 'middle');
                    textLabel.setAttribute('font-size', '8px');
                    textLabel.setAttribute('fill', '#000');
                    textLabel.setAttribute('pointer-events', 'none');
                    textLabel.textContent = tokenText;
                    tokensGroup.appendChild(textLabel);
                }});
                
                // Adicionar grupos ao SVG (edges primeiro, depois tokens por cima)
                svg.appendChild(edgesGroup);
                svg.appendChild(tokensGroup);
                
                // Atualizar lista de tokens
                const tokenList = document.getElementById('tokenList');
                tokenList.innerHTML = '';
                tokensData.forEach(function(token) {{
                    const div = document.createElement('div');
                    div.className = 'token-item';
                    
                    // Encontrar edges conectados
                    const edgesFrom = edgesData.filter(function(e) {{ return e.from === token.id || e.to === token.id; }});
                    const connections = edgesFrom.map(function(e) {{
                        const otherId = e.from === token.id ? e.to : e.from;
                        const otherToken = tokensData.find(function(t) {{ return t.id === otherId; }});
                        return otherId + ' (' + (otherToken ? otherToken.text.substring(0, 15) : '') + ')';
                    }}).join(', ');
                    
                    div.innerHTML = '<strong>Token ' + token.id + '</strong>: ' + token.text + '<br>BBox: [' + 
                        token.bbox[0].toFixed(4) + ', ' + token.bbox[1].toFixed(4) + ', ' + 
                        token.bbox[2].toFixed(4) + ', ' + token.bbox[3].toFixed(4) + ']<br>Conectado a: ' + 
                        (connections || 'nenhum');
                    tokenList.appendChild(div);
                }});
            }};
            
            if (img.complete && img.naturalWidth > 0) {{
                img.onload();
            }}
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
    
    print(f"Visualização HTML criada em: {output_path}")


def main():
    """Gera visualização do grafo de tokens."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    output_html = project_root / "token_graph_overlay.html"
    
    print("="*80)
    print("GERANDO VISUALIZACAO DO GRAFO DE TOKENS")
    print("="*80)
    
    create_token_graph_html(str(pdf_path), str(output_html))
    
    print(f"\nVisualização criada em: {output_html}")
    print("\nCores das edges:")
    print("  Verde: north (para cima)")
    print("  Azul: south (para baixo)")
    print("  Magenta: east (para direita)")
    print("  Laranja: west (para esquerda)")


if __name__ == "__main__":
    main()

