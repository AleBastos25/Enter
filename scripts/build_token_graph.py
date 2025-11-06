"""Script para construir grafo por tokens (palavras/frases) com coordenadas."""

import sys
import logging
from pathlib import Path
import json
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from src.io.pdf_loader import load_document
from src.layout.style_signature import compute_style_signatures, StyleSignature
from src.core.models import Block, InlineSpan


def extract_tokens_with_coords(pdf_path: str):
    """Extrai tokens (palavras/frases) com coordenadas do PDF.
    
    Returns:
        Lista de tokens: [{"id": int, "text": str, "bbox": [x0,y0,x1,y1], "block_id": int}]
    """
    doc = fitz.open(pdf_path)
    page = doc[0]
    width, height = page.rect.width, page.rect.height
    
    text_dict = page.get_text("dict")
    tokens = []
    token_id = 0
    
    for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
        if block_dict.get("type") != 0:  # 0 = text block
            continue
        
        for line_dict in block_dict.get("lines", []):
            spans = line_dict.get("spans", [])
            
            for span in spans:
                span_text = span.get("text", "").strip()
                if not span_text:
                    continue
                
                span_bbox = span.get("bbox")  # [x0, y0, x1, y1] em coordenadas da página
                if not span_bbox:
                    continue
                
                # Normalizar bbox
                # Adicionar padding APENAS NA DIREITA quando necessário
                # O PyMuPDF às vezes retorna bboxes que não incluem completamente os caracteres,
                # especialmente na borda direita (problema de kerning/espaçamento entre letras).
                # MAS alguns bboxes já têm espaço vazio extra - nesses casos, não devemos adicionar padding.
                # NÃO alteramos altura, borda esquerda ou superior - apenas expandimos à direita quando necessário.
                span_width = span_bbox[2] - span_bbox[0]
                span_height = span_bbox[3] - span_bbox[1]
                font_size = span.get("size", 0)
                
                # Sempre adicionar padding à direita para garantir cobertura completa
                # O PyMuPDF frequentemente retorna bboxes que não incluem completamente os caracteres,
                # especialmente na borda direita devido a kerning/espaçamento entre letras.
                # NÃO tentamos reduzir o bbox baseado em estimativas - isso causa problemas.
                # A estratégia é sempre adicionar padding, mas ajustar a quantidade baseado no tamanho:
                
                # Padding proporcional (12% da largura) + mínimo absoluto de 20 pontos
                # Isso garante que mesmo spans pequenos tenham padding suficiente
                # Testes mostraram que mesmo quando o bbox termina exatamente onde a palavra termina,
                # o kerning pode fazer o caractere final se estender além do bbox
                padding_factor_right = 0.12  # 12% de padding na largura
                min_padding_right = 20.0  # Mínimo de 20 pontos à direita
                
                padding_right = max(span_width * padding_factor_right, min_padding_right)
                
                # Aplicar padding apenas à direita (x1), manter tudo mais igual
                x0_norm = max(0.0, span_bbox[0] / width)  # Sem padding à esquerda
                y0_norm = max(0.0, span_bbox[1] / height)  # Sem padding no topo
                x1_norm = min(1.0, (span_bbox[2] + padding_right) / width)  # Padding apenas à direita
                y1_norm = min(1.0, span_bbox[3] / height)  # Sem padding embaixo
                
                # NÃO dividir spans - usar o span completo como um único token
                # Isso garante que palavras como "joanadarc" não sejam separadas
                
                # Extrair metadados de estilo adicionais
                flags = span.get("flags", 0)
                italic = bool(flags & 2)  # Flag 2 = italic
                bold = bool(flags & 16) or "bold" in (span.get("font", "") or "").lower()
                
                # Extrair cor (se disponível)
                color = span.get("color")
                if color is not None:
                    # Converter para string hex se for número
                    if isinstance(color, int):
                        color = f"#{color:06x}"
                
                # Verificar se o span contém ":" no meio e deve ser separado
                # Exemplo: "Data Referência: 05/09/2025" -> ["Data Referência:", "05/09/2025"]
                import re
                date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
                
                # Se contém ":" e depois tem uma data ou valor, separar
                if ":" in span_text and len(span_text) > 3:
                    # Procurar padrão "texto: valor" ou "texto: data"
                    colon_pos = span_text.find(":")
                    if colon_pos > 0 and colon_pos < len(span_text) - 1:
                        before_colon = span_text[:colon_pos + 1].strip()
                        after_colon = span_text[colon_pos + 1:].strip()
                        
                        # Se depois dos dois pontos tem uma data ou parece um valor
                        is_date_after = bool(date_pattern.search(after_colon))
                        is_value_after = bool(re.search(r"^\d|^[A-Z]", after_colon))  # Começa com dígito ou maiúscula
                        
                        if is_date_after or (is_value_after and len(after_colon) > 0):
                            # Separar em dois tokens
                            # Calcular proporção do texto antes e depois dos dois pontos
                            total_len = len(span_text)
                            before_ratio = len(before_colon) / total_len if total_len > 0 else 0.5
                            
                            # Primeiro token: texto antes dos dois pontos
                            x1_first = x0_norm + (x1_norm - x0_norm) * before_ratio
                            tokens.append({
                                "id": token_id,
                                "text": before_colon,
                                "bbox": [x0_norm, y0_norm, x1_first, y1_norm],
                                "block_id": block_idx,
                                "font_size": span.get("size"),
                                "bold": bold,
                                "italic": italic,
                                "color": color
                            })
                            token_id += 1
                            
                            # Segundo token: valor/data depois dos dois pontos
                            tokens.append({
                                "id": token_id,
                                "text": after_colon,
                                "bbox": [x1_first, y0_norm, x1_norm, y1_norm],
                                "block_id": block_idx,
                                "font_size": span.get("size"),
                                "bold": bold,
                                "italic": italic,
                                "color": color
                            })
                            token_id += 1
                            continue
                
                # Token normal (não separado)
                tokens.append({
                    "id": token_id,
                    "text": span_text,
                    "bbox": [x0_norm, y0_norm, x1_norm, y1_norm],
                    "block_id": block_idx,
                    "font_size": span.get("size"),
                    "bold": bold,
                    "italic": italic,
                    "color": color
                })
                token_id += 1
    
    doc.close()
    return tokens


def extract_tokens_from_page(pdf_path: str):
    """Extrai tokens da página do PDF (wrapper para compatibilidade).
    
    Returns:
        Lista de tokens como dicionários: [{"id": int, "text": str, "bbox": [x0,y0,x1,y1], ...}]
    """
    # Usar nova implementação OOP
    from src.graph_builder import TokenExtractor
    
    extractor = TokenExtractor()
    tokens = extractor.extract(pdf_path)
    # Converter para lista de dicionários para compatibilidade
    return [token.to_dict() for token in tokens]


def _compute_caps_ratio(text: str) -> float:
    """Compute ratio of uppercase letters."""
    if not text:
        return 0.0
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    uppercase = sum(1 for c in letters if c.isupper())
    return uppercase / len(letters)


def _compute_letter_spacing(text: str, bbox_width: float) -> float:
    """Compute average letter spacing."""
    if not text or bbox_width <= 0:
        return 0.0
    non_space_chars = len([c for c in text if not c.isspace()])
    if non_space_chars <= 1:
        return 0.0
    avg_char_width = bbox_width / len(text) if text else 0
    estimated_text_width = avg_char_width * non_space_chars
    if non_space_chars <= 1:
        return 0.0
    avg_spacing = (bbox_width - estimated_text_width) / max(1, non_space_chars - 1)
    return avg_spacing


def _quantile_bins(data: list[float], n_bins: int = 5) -> dict[float, int]:
    """Assign values to quantile bins."""
    if not data:
        return {}
    sorted_data = sorted(data)
    value_to_bin: dict[float, int] = {}
    for val in data:
        if len(sorted_data) == 1:
            bin_id = 0
        else:
            percentile = (sorted_data.index(val) / (len(sorted_data) - 1)) * 100
            bin_id = min(int(percentile / (100 / n_bins)), n_bins - 1)
        value_to_bin[val] = bin_id
    return value_to_bin


def _detect_alignment(bbox: list[float], tolerance: float = 0.02) -> str:
    """Detecta alinhamento do token (left/center/right).
    
    Args:
        bbox: [x0, y0, x1, y1] normalizado.
        tolerance: Tolerância para considerar alinhado (padrão 0.02 = 2% da página).
        
    Returns:
        'left', 'center', ou 'right'.
    """
    if len(bbox) < 4:
        return 'left'
    
    x0 = bbox[0]
    x1 = bbox[2]
    center_x = (x0 + x1) / 2.0
    
    # Left: x0 próximo de 0
    if x0 < tolerance:
        return 'left'
    # Right: x1 próximo de 1
    if x1 > (1.0 - tolerance):
        return 'right'
    # Center: centro próximo de 0.5
    if abs(center_x - 0.5) < tolerance:
        return 'center'
    
    # Por padrão, considerar left se x0 < 0.5, senão right
    return 'left' if x0 < 0.5 else 'right'


def _detect_label_value_patterns(tokens: list[dict], graph: dict, roles: dict[int, str]) -> list[dict]:
    """Detecta padrões repetitivos LABEL→VALUE baseado em estrutura.
    
    Retorna uma lista de padrões estruturais com alinhamento, font size, e posição.
    
    Args:
        tokens: Lista de tokens.
        graph: Grafo com edges.
        roles: Roles já classificados.
        
    Returns:
        Lista de dicionários com padrões: {'alignment': str, 'font_size': float, 'x0': float, 'y_pattern': float}.
    """
    patterns: list[dict] = []
    
    # Agrupar tokens por alinhamento e font size similar
    edges = graph.get("edges", [])
    edges_by_token: dict[int, list[dict]] = {}
    for edge in edges:
        from_id = edge.get("from")
        if from_id not in edges_by_token:
            edges_by_token[from_id] = []
        edges_by_token[from_id].append(edge)
    
    # Detectar padrões LABEL→VALUE conhecidos
    for token in tokens:
        token_id = token["id"]
        role = roles.get(token_id)
        
        if role != "LABEL":
            continue
        
        bbox = token.get("bbox", [0, 0, 0, 0])
        if len(bbox) < 4:
            continue
        
        alignment = _detect_alignment(bbox)
        font_size = token.get("font_size", 0) or 0
        x0 = bbox[0]
        y0 = bbox[1]
        
        # Procurar VALUE conectado abaixo (south) ou à direita (east)
        for edge in edges_by_token.get(token_id, []):
            if edge.get("relation") not in ("south", "east"):
                continue
            
            to_id = edge.get("to")
            to_role = roles.get(to_id)
            
            if to_role == "VALUE":
                # Encontramos um padrão LABEL→VALUE
                # Armazenar padrão com alinhamento, font size e posição X
                pattern = {
                    'alignment': alignment,
                    'font_size': font_size,
                    'x0': x0,  # Posição X do LABEL (para alinhamento preciso)
                    'y_pattern': y0,  # Posição Y do LABEL (para referência)
                }
                patterns.append(pattern)
                break
    
    return patterns


def _propagate_roles_by_patterns(tokens: list[dict], graph: dict, roles: dict[int, str], patterns: list[dict]) -> dict[int, str]:
    """Propaga roles baseado em padrões estruturais detectados.
    
    Args:
        tokens: Lista de tokens.
        graph: Grafo com edges.
        roles: Roles atuais.
        patterns: Lista de padrões detectados.
        
    Returns:
        Roles atualizados.
    """
    if not patterns:
        return roles
    
    roles_updated = roles.copy()
    tolerance_x = 0.02  # Tolerância para alinhamento X (2% da página)
    tolerance_font = 2.0  # Tolerância para font size (2pt)
    
    # Aplicar padrões para tokens não classificados ou mal classificados
    for token in tokens:
        token_id = token["id"]
        current_role = roles_updated.get(token_id)
        text = token.get("text", "").strip()
        
        if not text:
            continue
        
        bbox = token.get("bbox", [0, 0, 0, 0])
        if len(bbox) < 4:
            continue
        
        alignment = _detect_alignment(bbox)
        font_size = token.get("font_size", 0) or 0
        x0 = bbox[0]
        
        # Procurar padrão similar (mesmo alinhamento, font size similar, X similar)
        for pattern in patterns:
            if pattern['alignment'] != alignment:
                continue
            
            # Verificar se font size é similar
            font_diff = abs(font_size - pattern['font_size'])
            if font_diff > tolerance_font:
                continue
            
            # Verificar se X está alinhado (mesma coluna)
            x_diff = abs(x0 - pattern['x0'])
            if x_diff > tolerance_x:
                continue
            
            # Encontramos um padrão similar!
            # Se o padrão é LABEL→VALUE, então tokens na mesma coluna abaixo devem ser VALUE
            import re
            ends_with_separator = any(text.rstrip().endswith(sep) for sep in [":", "—", "–", ".", "•", "/"])
            
            # Se o token não tem role ou é LABEL mas deveria ser VALUE
            if current_role is None or (current_role == "LABEL" and not ends_with_separator):
                # Verificar se não é claramente um LABEL
                tokens_list = text.split()
                has_digits = bool(re.search(r"\d", text))
                
                # Se tem dígitos OU é texto longo OU é sigla, provavelmente é VALUE
                if has_digits or len(tokens_list) >= 2:
                    # Verificar se é sigla (2-3 letras maiúsculas)
                    is_acronym = bool(re.match(r"^[A-Z]{2,3}$", text))
                    if is_acronym or has_digits or len(tokens_list) >= 2:
                        roles_updated[token_id] = "VALUE"
                        break
    
    return roles_updated


def classify_initial_roles(tokens: list[dict], graph: dict, label: Optional[str] = None) -> dict[int, str]:
    """Classificação de papéis baseada em relações estruturais LABEL→VALUE.
    
    Lógica estrutural:
    1. Identificar LABELs (terminam com ":" ou têm ":" no meio)
    2. Para cada LABEL, procurar VALUE à direita (east) ou abaixo (south)
    3. Cada LABEL deve ter um único VALUE, cada VALUE só se liga a um LABEL
    4. Se um nó não consegue ligar a um VALUE, é HEADER
    5. Se um nó só se conecta a LABELs, é HEADER
    6. Usar heurísticas para desempates
    
    Args:
        tokens: Lista de tokens.
        graph: Grafo com nodes e edges.
        label: Label do documento para memória.
        
    Returns:
        Dictionary mapping token_id -> role (HEADER/LABEL/VALUE/None).
    """
    import re
    roles: dict[int, str] = {}
    LABEL_SEPARATORS = [":", "—", "–", ".", "•", "/"]
    
    # Construir adjacência do grafo (bidirecional)
    node_by_id = {node["id"]: node for node in graph.get("nodes", [])}
    adj = {node["id"]: {"east": [], "south": [], "north": [], "west": []} for node in graph.get("nodes", [])}
    # Mapeamento reverso de relações
    reverse_relation = {"east": "west", "west": "east", "south": "north", "north": "south"}
    for edge in graph.get("edges", []):
        relation = edge.get("relation", "")
        from_id = edge.get("from")
        to_id = edge.get("to")
        if relation in adj.get(from_id, {}):
            adj[from_id][relation].append(to_id)
        # Adicionar relação reversa para bidirecionalidade
        reverse_rel = reverse_relation.get(relation)
        if reverse_rel and reverse_rel in adj.get(to_id, {}):
            adj[to_id][reverse_rel].append(from_id)
    
    # Calcular estatísticas de fonte
    font_sizes = [t.get("font_size") for t in tokens if t.get("font_size") and t.get("font_size") > 0]
    if not font_sizes:
        # Fallback: assumir média de 12
        avg_font_size = 12.0
        median_font_size = 12.0
    else:
        font_sizes_sorted = sorted(font_sizes)
        avg_font_size = sum(font_sizes) / len(font_sizes)
        median_font_size = font_sizes_sorted[len(font_sizes_sorted) // 2]
    
    # Criar lookup de edges por token (bidirecional)
    edges_by_token: dict[int, list[dict]] = {}
    for edge in graph.get("edges", []):
        from_id = edge.get("from")
        to_id = edge.get("to")
        
        if from_id not in edges_by_token:
            edges_by_token[from_id] = []
        edges_by_token[from_id].append(edge)
        
        if to_id not in edges_by_token:
            edges_by_token[to_id] = []
        # Criar edge reverso para lookup bidirecional
        reverse_edge = {"from": to_id, "to": from_id, "relation": edge.get("relation")}
        edges_by_token[to_id].append(reverse_edge)
    
    # PASSO 1: Identificar candidatos a LABEL (termina com ":" ou tem ":" no meio)
    label_candidates = []
    for token in tokens:
        token_id = token["id"]
        text = token.get("text", "").strip()
        
        if not text:
            continue
        
        text_stripped = text.rstrip()
        
        # É candidato a LABEL se termina com separador OU tem ":" no meio
        ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
        has_colon_in_middle = ":" in text and text.find(":") < len(text) - 1
        
        if ends_with_separator or has_colon_in_middle:
            label_candidates.append(token_id)
            roles[token_id] = "LABEL"
    
    # PASSO 2: Para cada LABEL, procurar VALUE à direita (east) ou abaixo (south)
    # Garantir que cada LABEL tem um único VALUE e cada VALUE só se liga a um LABEL
    label_to_value = {}  # label_id -> value_id
    value_to_label = {}  # value_id -> label_id
    
    date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
    
    for label_id in label_candidates:
        # Procurar VALUE à direita (east) primeiro, depois abaixo (south)
        for direction in ["east", "south"]:
            neighbors = adj.get(label_id, {}).get(direction, [])
            
            for neighbor_id in neighbors:
                # Se este VALUE já está ligado a outro LABEL, pular
                if neighbor_id in value_to_label:
                    continue
                
                neighbor_node = node_by_id.get(neighbor_id)
                if not neighbor_node:
                    continue
                
                neighbor_text = neighbor_node.get("text", "").strip()
                if not neighbor_text:
                    continue
                
                # Verificar se é um VALUE válido
                # É VALUE se: é número puro, é data, tem dígitos, ou é texto longo
                is_number = bool(re.match(r"^\d+$", neighbor_text))
                is_date = bool(date_pattern.search(neighbor_text))
                has_digits = bool(re.search(r"\d", neighbor_text))
                tokens_list = neighbor_text.split()
                is_long_text = len(tokens_list) >= 2
                
                # Não é VALUE se termina com separador (é LABEL)
                ends_with_sep = any(neighbor_text.rstrip().endswith(sep) for sep in LABEL_SEPARATORS)
                
                if (is_number or is_date or (has_digits and not ends_with_sep) or is_long_text) and not ends_with_sep:
                    # Encontrou um VALUE válido
                    label_to_value[label_id] = neighbor_id
                    value_to_label[neighbor_id] = label_id
                    roles[neighbor_id] = "VALUE"
                    break
            
            # Se já encontrou um VALUE para este LABEL, parar
            if label_id in label_to_value:
                break
    
    # PASSO 3: Classificar tokens restantes
    # Se um token não consegue ligar a um VALUE (não é LABEL nem VALUE), pode ser HEADER
    # Se um token só se conecta a LABELs, é HEADER
    
    for token in tokens:
        token_id = token["id"]
        
        # Se já foi classificado, pular
        if token_id in roles:
            continue
        
        text = token.get("text", "").strip()
        if not text:
            continue
        
        bbox = token.get("bbox", [0, 0, 0, 0])
        font_size = token.get("font_size", 0) or 0
        
        # Verificar conexões do token
        all_neighbors = []
        for direction in ["east", "south", "north", "west"]:
            all_neighbors.extend(adj.get(token_id, {}).get(direction, []))
        
        neighbor_roles = []
        for neighbor_id in all_neighbors:
            neighbor_role = roles.get(neighbor_id)
            if neighbor_role:
                neighbor_roles.append(neighbor_role)
        
        # Se só se conecta a LABELs, é HEADER
        if neighbor_roles and all(role == "LABEL" for role in neighbor_roles):
            roles[token_id] = "HEADER"
            continue
        
        # Verificar se deveria ser HEADER (fonte grande no topo)
        if len(bbox) >= 4 and font_size > 0:
            y_top = bbox[1]
            is_near_top = y_top < 0.20
            is_large_font = font_size >= avg_font_size * 1.2
            is_above_avg = font_size > avg_font_size
            tokens_list = text.split()
            
            if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                text_stripped = text.rstrip()
                ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
                if not ends_with_separator and not re.match(r"^\d+$", text.strip()):
                    roles[token_id] = "HEADER"
                    continue
        
        # Verificar se é VALUE (número, data, ou tem dígitos)
        is_number = bool(re.match(r"^\d+$", text.strip()))
        is_date = bool(date_pattern.search(text))
        has_digits = bool(re.search(r"\d", text))
        tokens_list = text.split()
        is_long_text = len(tokens_list) >= 2
        ends_with_sep = any(text.rstrip().endswith(sep) for sep in LABEL_SEPARATORS)
        
        if (is_number or is_date or (has_digits and not ends_with_sep) or is_long_text) and not ends_with_sep:
            # Mas só classificar como VALUE se não está conectado a um LABEL já
            # (para evitar conflitos)
            if token_id not in value_to_label:
                # Verificar se está conectado a algum LABEL
                connected_to_label = False
                for neighbor_id in all_neighbors:
                    if neighbor_id in label_candidates:
                        connected_to_label = True
                        break
                
                if connected_to_label:
                    # Pode ser VALUE, mas vamos deixar para depois
                    pass
                else:
                    roles[token_id] = "VALUE"
                    continue
        
        # Se não se encaixa em nenhuma categoria, deixar None por enquanto
        roles[token_id] = None
    
    # PASSO 4: Revisar - se um LABEL está conectado apenas a LABELs, é HEADER
    # Exemplo: nó 1 é LABEL e se conecta a nó 2 que também é LABEL (tem ":")
    # Então nó 1 é HEADER porque só se conecta a LABELs
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        # Se é LABEL, verificar se está conectado apenas a LABELs
        if current_role == "LABEL":
            east_neighbors = adj.get(token_id, {}).get("east", [])
            south_neighbors = adj.get(token_id, {}).get("south", [])
            all_neighbors = east_neighbors + south_neighbors
            
            # Verificar se todos os vizinhos à direita/abaixo são LABELs
            all_are_labels = True
            for neighbor_id in all_neighbors:
                if neighbor_id not in label_candidates:
                    all_are_labels = False
                    break
            
            # Se só se conecta a LABELs (e não tem VALUE), é HEADER
            if all_are_labels and len(all_neighbors) > 0 and token_id not in label_to_value:
                roles[token_id] = "HEADER"
                # Remover da lista de LABELs
                if token_id in label_candidates:
                    label_candidates.remove(token_id)
    
    # PASSO 5: Validar VALUES - todo VALUE deve ter um LABEL conectado
    # Se um VALUE não tem LABEL acima (north) nem à esquerda (west), reclassificar
    # OU classificar tokens acima/esquerda de VALUES como LABEL
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        # Se é VALUE, verificar se tem LABEL conectado
        if current_role == "VALUE":
            # Verificar se está ligado a um LABEL
            if token_id not in value_to_label:
                # Não está ligado a nenhum LABEL, verificar conexões
                north_neighbors = adj.get(token_id, {}).get("north", [])
                west_neighbors = adj.get(token_id, {}).get("west", [])
                all_neighbors = north_neighbors + west_neighbors
                
                # Verificar se algum vizinho é LABEL
                has_label_neighbor = False
                for neighbor_id in all_neighbors:
                    if neighbor_id in label_candidates:
                        # Encontrou um LABEL, criar ligação
                        label_to_value[neighbor_id] = token_id
                        value_to_label[token_id] = neighbor_id
                        has_label_neighbor = True
                        break
                
                # Se não tem LABEL conectado, verificar se algum vizinho pode ser classificado como LABEL
                if not has_label_neighbor:
                    for neighbor_id in all_neighbors:
                        neighbor_node = node_by_id.get(neighbor_id)
                        if not neighbor_node:
                            continue
                        
                        neighbor_text = neighbor_node.get("text", "").strip()
                        neighbor_role = roles.get(neighbor_id)
                        
                        # Se o vizinho não tem role ou é None, e está acima/esquerda de um VALUE, é LABEL
                        if neighbor_role is None or neighbor_role == "":
                            # Verificar se não é uma data ou número (esses são sempre VALUE)
                            is_date = bool(date_pattern.search(neighbor_text))
                            is_number = bool(re.match(r"^\d+$", neighbor_text.strip()))
                            
                            if not is_date and not is_number:
                                # Classificar como LABEL e criar ligação
                                roles[neighbor_id] = "LABEL"
                                label_candidates.append(neighbor_id)
                                label_to_value[neighbor_id] = token_id
                                value_to_label[token_id] = neighbor_id
                                has_label_neighbor = True
                                break
                    
                    # Se ainda não tem LABEL, reclassificar VALUE
                    if not has_label_neighbor:
                        # Verificar se deveria ser HEADER (fonte grande no topo)
                        bbox = token.get("bbox", [0, 0, 0, 0])
                        font_size = token.get("font_size", 0) or 0
                        text = token.get("text", "").strip()
                        
                        if len(bbox) >= 4 and font_size > 0:
                            y_top = bbox[1]
                            is_near_top = y_top < 0.20
                            is_large_font = font_size >= avg_font_size * 1.2
                            is_above_avg = font_size > avg_font_size
                            tokens_list = text.split()
                            
                            # Se está no topo e tem fonte maior que média, é HEADER
                            if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                                text_stripped = text.rstrip()
                                ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
                                if not ends_with_separator and not re.match(r"^\d+$", text.strip()):
                                    roles[token_id] = "HEADER"
                                    continue
                        
                        # Se não é HEADER, deixar como None (será classificado depois)
                        roles[token_id] = None
    
    # Segunda passagem: Aplicar memória ANTES de classificar VALUE
    # Isso garante que padrões aprendidos sejam aplicados, mas HEADER tem prioridade
    if label:
        try:
            from scripts.layout_memory import get_memory_manager
            memory_manager = get_memory_manager()
            # Aplicar memória agora, antes de classificar VALUE
            # A memória já verifica HEADER antes de aplicar padrões
            roles = memory_manager.apply_memory(label, tokens, roles, avg_font_size)
        except Exception as e:
            import logging
            logging.warning(f"Erro ao aplicar memória: {e}")
    
    # Terceira passagem: classificar VALUE baseado em padrões e contexto
    # IMPORTANTE: Verificar HEADER ANTES de qualquer classificação de VALUE
    for token in tokens:
        token_id = token["id"]
        
        # Se já foi classificado como HEADER, não mudar para VALUE
        current_role = roles.get(token_id)
        if current_role == "HEADER":
            continue
        
        text = token.get("text", "").strip()
        if not text:
            continue
        
        # PRIMEIRO: Verificar se deveria ser HEADER (nomes no topo com fonte grande)
        # Isso tem prioridade ABSOLUTA sobre VALUE
        bbox = token.get("bbox", [0, 0, 0, 0])
        font_size = token.get("font_size", 0) or 0
        if len(bbox) >= 4 and font_size > 0:
            y_top = bbox[1]
            is_near_top = y_top < 0.20
            # Mais permissivo: fonte maior que média OU ≥1.2x
            is_large_font = font_size >= avg_font_size * 1.2
            is_above_avg = font_size > avg_font_size
            
            # Se está no topo e tem fonte maior que média, é HEADER, não VALUE
            if is_near_top and (is_large_font or (is_above_avg and len(text.split()) >= 2)):
                text_stripped = text.rstrip()
                ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
                if not ends_with_separator:
                    # Verificar se não é número (números no topo podem ser VALUE)
                    if not re.match(r"^\d+$", text.strip()):
                        # FORÇAR HEADER - tem prioridade sobre tudo
                        roles[token_id] = "HEADER"
                        continue
        
        # Regra 3: VALUE
        # É número puro (só dígitos) - SEMPRE VALUE
        if re.match(r"^\d+$", text.strip()):
            roles[token_id] = "VALUE"
            continue
        
        # É uma data - SEMPRE VALUE
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        if date_pattern.search(text):
            roles[token_id] = "VALUE"
            continue
        
        # Se é sigla e está na mesma linha que um número ou VALUE, é VALUE
        is_acronym = bool(re.match(r"^[A-Z]{2,3}$", text))
        if is_acronym and current_role != "HEADER":
            bbox = token.get("bbox", [0, 0, 0, 0])
            if len(bbox) >= 4:
                alignment = _detect_alignment(bbox)
                x0 = bbox[0]
                y0 = bbox[1]
                y1 = bbox[3]
                
                # Procurar números ou VALUES na mesma linha
                for other_token in tokens:
                    if other_token["id"] == token_id:
                        continue
                    
                    other_text = other_token.get("text", "").strip()
                    other_role = roles.get(other_token["id"])
                    
                    # Verificar se é número puro OU já foi classificado como VALUE
                    is_number = bool(re.match(r"^\d+$", other_text))
                    is_value = other_role == "VALUE"
                    
                    if is_number or is_value:
                        other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                        if len(other_bbox) >= 4:
                            other_alignment = _detect_alignment(other_bbox)
                            other_x0 = other_bbox[0]
                            other_y0 = other_bbox[1]
                            other_y1 = other_bbox[3]
                            
                            # Se mesmo alinhamento e mesma linha (mais tolerante)
                            if other_alignment == alignment:
                                x_diff = abs(x0 - other_x0)
                                y_overlap = not (y1 < other_y0 or y0 > other_y1)
                                y_close = abs(y0 - other_y0) < 0.08  # Mais tolerante
                                
                                # Se está na mesma linha (sobreposição ou próximo) e mesmo alinhamento
                                if (y_overlap or y_close) and x_diff < 0.1:  # Mais tolerante para X
                                    # Está na mesma linha que um número/VALUE, é VALUE
                                    roles[token_id] = "VALUE"
                                    break
        
        if token_id in roles:  # Já classificado
            continue
        
        # Tem dígitos e não termina com separador
        has_digits = bool(re.search(r"\d", text))
        text_stripped = text.rstrip()
        ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
        
        if has_digits and not ends_with_separator:
            roles[token_id] = "VALUE"
            continue
        
        # Está conectado ortogonalmente a um LABEL (south ou east)
        # Verificar se tem edge para um LABEL (bidirecional)
        connected_to_label = False
        for edge in edges_by_token.get(token_id, []):
            other_id = edge.get("to") if edge.get("from") == token_id else edge.get("from")
            other_role = roles.get(other_id)
            relation = edge.get("relation", "")
            
            # Se o outro token é LABEL e a relação é south (abaixo do label) ou east (à direita do label)
            # Mas precisamos verificar a direção correta:
            # - Se edge.from == token_id e relation == "south", então token está acima do LABEL (não é value)
            # - Se edge.from == token_id e relation == "east", então token está à esquerda do LABEL (não é value)
            # - Se edge.to == token_id e relation == "south", então token está abaixo do LABEL (é value!)
            # - Se edge.to == token_id e relation == "east", então token está à direita do LABEL (é value!)
            
            if other_role == "LABEL":
                # Verificar direção: token deve estar abaixo (south) ou à direita (east) do LABEL
                if edge.get("from") == other_id and edge.get("to") == token_id:
                    # LABEL -> token (south ou east) = token é VALUE
                    if relation in ("south", "east"):
                        connected_to_label = True
                        break
        
        if connected_to_label:
            roles[token_id] = "VALUE"
            continue
        
        # Texto longo (≥4 palavras) que não parece label
        tokens_list = text.split()
        if len(tokens_list) >= 4 and not ends_with_separator:
            roles[token_id] = "VALUE"
            continue
        
        # Sigla/UF (2-3 letras maiúsculas) - geralmente é VALUE, não LABEL
        is_acronym = bool(re.match(r"^[A-Z]{2,3}$", text))
        if is_acronym:
            # Verificar contexto: se está na mesma linha/alinhamento que outros tokens
            bbox = token.get("bbox", [0, 0, 0, 0])
            if len(bbox) >= 4:
                alignment = _detect_alignment(bbox)
                x0 = bbox[0]
                y0 = bbox[1]
                y1 = bbox[3]
                
                # Procurar outros tokens na mesma linha
                found_value_context = False
                for other_token in tokens:
                    if other_token["id"] == token_id:
                        continue
                    
                    other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                    if len(other_bbox) < 4:
                        continue
                    
                    other_alignment = _detect_alignment(other_bbox)
                    other_x0 = other_bbox[0]
                    other_y0 = other_bbox[1]
                    other_y1 = other_bbox[3]
                    other_text = other_token.get("text", "").strip()
                    
                    # Se mesmo alinhamento e mesma linha
                    if other_alignment == alignment:
                        x_diff = abs(x0 - other_x0)
                        y_overlap = not (y1 < other_y0 or y0 > other_y1)
                        y_close = abs(y0 - other_y0) < 0.05
                        
                        if (y_overlap or y_close) and x_diff < 0.02:
                            # Verificar se o outro token parece VALUE
                            other_has_digits = bool(re.search(r"\d", other_text))
                            other_tokens_list = other_text.split()
                            other_is_long = len(other_tokens_list) >= 2
                            
                            if other_has_digits or other_is_long:
                                found_value_context = True
                                break
                
                # Se encontrou contexto de VALUE, classificar como VALUE
                if found_value_context:
                    roles[token_id] = "VALUE"
                    continue
        
        # Texto em MAIÚSCULAS longo (≥3 palavras) - geralmente é VALUE
        if text.isupper() and len(tokens_list) >= 3 and not ends_with_separator:
            roles[token_id] = "VALUE"
            continue
        
        # Texto médio (3 palavras) sem separador e não parece label
        if len(tokens_list) == 3 and not ends_with_separator:
            # Se contém maiúsculas ou parece um valor composto
            if text.isupper() or bool(re.search(r"[A-Z]{3,}", text)):
                roles[token_id] = "VALUE"
                continue
        
        # ANTES de deixar None, verificar se deveria ser HEADER (fonte grande no topo)
        # Isso pode ter sido perdido se não passou nas condições anteriores
        if token_id not in roles:
            bbox = token.get("bbox", [0, 0, 0, 0])
            font_size = token.get("font_size", 0) or 0
            
            if len(bbox) >= 4 and font_size > 0:
                y_top = bbox[1]
                is_near_top = y_top < 0.20
                is_large_font = font_size >= avg_font_size * 1.3
                is_very_large_font = font_size >= avg_font_size * 1.5
                
                # Se está no topo e tem fonte grande, é HEADER
                if is_near_top and (is_very_large_font or is_large_font):
                    text_stripped = text.rstrip()
                    ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
                    
                    # Não classificar como HEADER se termina com separador (é label)
                    # E não se é número puro
                    if not ends_with_separator and not re.match(r"^\d+$", text.strip()):
                        roles[token_id] = "HEADER"
                        continue
        
        # Se é sigla e ainda não foi classificada, verificar contexto uma última vez
        is_acronym = bool(re.match(r"^[A-Z]{2,3}$", text))
        if is_acronym and token_id not in roles:
            bbox = token.get("bbox", [0, 0, 0, 0])
            if len(bbox) >= 4:
                alignment = _detect_alignment(bbox)
                x0 = bbox[0]
                y0 = bbox[1]
                y1 = bbox[3]
                
                # Procurar qualquer token na mesma linha que possa ser VALUE
                for other_token in tokens:
                    if other_token["id"] == token_id:
                        continue
                    
                    other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                    if len(other_bbox) < 4:
                        continue
                    
                    other_alignment = _detect_alignment(other_bbox)
                    other_x0 = other_bbox[0]
                    other_y0 = other_bbox[1]
                    other_y1 = other_bbox[3]
                    other_text = other_token.get("text", "").strip()
                    
                    # Se mesmo alinhamento e mesma linha
                    if other_alignment == alignment:
                        x_diff = abs(x0 - other_x0)
                        y_overlap = not (y1 < other_y0 or y0 > other_y1)
                        y_close = abs(y0 - other_y0) < 0.1
                        
                        if (y_overlap or y_close) and x_diff < 0.15:
                            # Verificar se o outro token parece VALUE (número, texto longo, etc.)
                            other_has_digits = bool(re.search(r"\d", other_text))
                            other_tokens_list = other_text.split()
                            other_is_long = len(other_tokens_list) >= 2
                            
                            if other_has_digits or other_is_long:
                                roles[token_id] = "VALUE"
                                break
        
    # PASSO 4: Revisar classificação baseado em relações
    # Se descobrimos que um token que era LABEL na verdade tem ":" no meio e deveria ser separado,
    # ou se um VALUE está conectado a um LABEL que descobrimos ser LABEL, ajustar
    
    # Revisar: se um token que classificamos como VALUE está conectado a um LABEL,
    # mas esse LABEL já tem outro VALUE, então o primeiro pode ser HEADER
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        # Se é VALUE mas não está ligado a nenhum LABEL, verificar se deveria ser HEADER
        if current_role == "VALUE" and token_id not in value_to_label:
            # Verificar conexões
            all_neighbors = []
            for direction in ["east", "south", "north", "west"]:
                all_neighbors.extend(adj.get(token_id, {}).get(direction, []))
            
            # Se só se conecta a LABELs, é HEADER
            neighbor_roles = [roles.get(nid) for nid in all_neighbors if roles.get(nid)]
            if neighbor_roles and all(role == "LABEL" for role in neighbor_roles):
                roles[token_id] = "HEADER"
    
    # PASSO 5: Forçar mesmo role para tokens na mesma linha com mesmo estilo
    # Se dois tokens estão na mesma linha e têm mesmo tamanho de fonte, devem ter o mesmo role
    # Agrupar tokens por linha e estilo, depois propagar roles dominantes
    
    # Agrupar tokens por linha (Y) e estilo (font_size)
    line_style_groups = {}  # {(y_center, font_size): [token_ids]}
    
    for token in tokens:
        token_id = token["id"]
        bbox = token.get("bbox", [0, 0, 0, 0])
        font_size = token.get("font_size", 0) or 0
        
        if len(bbox) >= 4 and font_size > 0:
            y_center = (bbox[1] + bbox[3]) / 2.0
            # Arredondar Y e font_size para agrupar (tolerância)
            y_rounded = round(y_center, 3)  # 3 casas decimais
            font_rounded = round(font_size, 1)  # 1 casa decimal
            
            key = (y_rounded, font_rounded)
            if key not in line_style_groups:
                line_style_groups[key] = []
            line_style_groups[key].append(token_id)
    
    # Para cada grupo de mesma linha e estilo, verificar roles e forçar consistência
    for (y_center, font_size), token_ids in line_style_groups.items():
        if len(token_ids) < 2:
            continue  # Precisa de pelo menos 2 tokens para aplicar regra
        
        # Coletar roles dos tokens no grupo
        group_roles = {}
        for tid in token_ids:
            role = roles.get(tid)
            if role:
                group_roles[role] = group_roles.get(role, 0) + 1
        
        if not group_roles:
            continue  # Nenhum token tem role ainda
        
        # Encontrar role dominante (mais comum)
        dominant_role = max(group_roles.items(), key=lambda x: x[1])[0]
        dominant_count = group_roles[dominant_role]
        
        # Se há um role dominante claro (pelo menos 50% dos tokens classificados)
        total_classified = sum(group_roles.values())
        if dominant_count >= max(1, total_classified * 0.5):
            # Aplicar role dominante a todos os tokens do grupo que não têm role ou têm role diferente
            for tid in token_ids:
                current_role = roles.get(tid)
                token = next((t for t in tokens if t["id"] == tid), None)
                
                if not token:
                    continue
                
                text = token.get("text", "").strip()
                if not text:
                    continue
                
                # Verificar se não é uma data ou número (esses são sempre VALUE)
                date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
                is_date = bool(date_pattern.search(text))
                is_number = bool(re.match(r"^\d+$", text.strip()))
                
                # Se é data ou número, sempre VALUE (não aplicar regra de grupo)
                if is_date or is_number:
                    if current_role != "VALUE":
                        roles[tid] = "VALUE"
                    continue
                
                # Se não tem role ou tem role diferente do dominante, aplicar role dominante
                # EXCETO se já é HEADER (HEADER tem prioridade)
                if current_role != "HEADER":
                    if current_role != dominant_role:
                        roles[tid] = dominant_role
    
    # Quarta passagem: Detectar padrões estruturais e propagar
    patterns = _detect_label_value_patterns(tokens, graph, roles)
    roles = _propagate_roles_by_patterns(tokens, graph, roles, patterns)
    
    # PASSO 6: Validar VALUES novamente - todo VALUE deve ter um LABEL conectado
    # Executar DEPOIS de todas as classificações de VALUE para garantir que tokens acima/esquerda sejam LABELs
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        # Se é VALUE, verificar se tem LABEL conectado
        if current_role == "VALUE":
            # Verificar se está ligado a um LABEL
            if token_id not in value_to_label:
                # Não está ligado a nenhum LABEL, verificar conexões
                north_neighbors = adj.get(token_id, {}).get("north", [])
                west_neighbors = adj.get(token_id, {}).get("west", [])
                all_neighbors = north_neighbors + west_neighbors
                
                # Verificar se algum vizinho é LABEL
                has_label_neighbor = False
                for neighbor_id in all_neighbors:
                    neighbor_role = roles.get(neighbor_id)
                    if neighbor_role == "LABEL" or neighbor_id in label_candidates:
                        # Encontrou um LABEL, criar ligação
                        if neighbor_id not in label_candidates:
                            label_candidates.append(neighbor_id)
                        label_to_value[neighbor_id] = token_id
                        value_to_label[token_id] = neighbor_id
                        has_label_neighbor = True
                        break
                
                # Se não tem LABEL conectado, verificar se algum vizinho pode ser classificado como LABEL
                if not has_label_neighbor:
                    for neighbor_id in all_neighbors:
                        neighbor_node = node_by_id.get(neighbor_id)
                        if not neighbor_node:
                            continue
                        
                        neighbor_text = neighbor_node.get("text", "").strip()
                        neighbor_role = roles.get(neighbor_id)
                        
                        # Se o vizinho não tem role ou é None, e está acima/esquerda de um VALUE, é LABEL
                        if neighbor_role is None or neighbor_role == "":
                            # Verificar se não é uma data ou número (esses são sempre VALUE)
                            is_date = bool(date_pattern.search(neighbor_text))
                            is_number = bool(re.match(r"^\d+$", neighbor_text.strip()))
                            
                            if not is_date and not is_number:
                                # Classificar como LABEL e criar ligação
                                roles[neighbor_id] = "LABEL"
                                if neighbor_id not in label_candidates:
                                    label_candidates.append(neighbor_id)
                                label_to_value[neighbor_id] = token_id
                                value_to_label[token_id] = neighbor_id
                                has_label_neighbor = True
                                break
    
    # Quinta passagem: Aprender padrões para memória (se label disponível)
    if label:
        try:
            from scripts.layout_memory import get_memory_manager
            memory_manager = get_memory_manager()
            memory_manager.learn_patterns(label, tokens, graph, roles)
        except Exception as e:
            # Se falhar, continuar sem aprender
            import logging
            logging.warning(f"Erro ao aprender padrões: {e}")
    
    # Sexta passagem: Ajustar siglas/UF (2-3 letras maiúsculas) como VALUE quando em contexto
    # FORÇAR reclassificação de siglas que estão na mesma linha de VALUES
    for token in tokens:
        token_id = token["id"]
        text = token.get("text", "").strip()
        current_role = roles.get(token_id)
        
        # Se é LABEL mas parece ser uma sigla/UF, verificar contexto e FORÇAR VALUE se necessário
        import re
        is_acronym = bool(re.match(r"^[A-Z]{2,3}$", text))
        
        if is_acronym and current_role != "HEADER":
            bbox = token.get("bbox", [0, 0, 0, 0])
            if len(bbox) >= 4:
                alignment = _detect_alignment(bbox)
                x0 = bbox[0]
                y0 = bbox[1]
                y1 = bbox[3]
                
                # Procurar VALUES na mesma linha (mesmo Y) ou próxima linha com mesmo alinhamento
                found_value_in_line = False
                for other_token in tokens:
                    other_id = other_token["id"]
                    if other_id == token_id:
                        continue
                    
                    other_role = roles.get(other_id)
                    other_text = other_token.get("text", "").strip()
                    
                    # Verificar se é VALUE OU número puro
                    is_value = other_role == "VALUE"
                    is_number = bool(re.match(r"^\d+$", other_text))
                    
                    if is_value or is_number:
                        other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                        if len(other_bbox) >= 4:
                            other_alignment = _detect_alignment(other_bbox)
                            other_x0 = other_bbox[0]
                            other_y0 = other_bbox[1]
                            other_y1 = other_bbox[3]
                            
                            # Verificar se mesmo alinhamento e mesma linha (sobreposição Y)
                            if other_alignment == alignment:
                                # Verificar alinhamento X (tolerância mais ampla)
                                x_diff = abs(x0 - other_x0)
                                if x_diff < 0.1:  # Mais tolerante
                                    # Verificar se está na mesma linha (sobreposição Y)
                                    # OU na linha imediatamente acima/abaixo
                                    y_overlap = not (y1 < other_y0 or y0 > other_y1)
                                    y_close = abs(y0 - other_y0) < 0.08  # Mais tolerante
                                    
                                    if y_overlap or y_close:
                                        # FORÇAR VALUE - está na mesma linha que um VALUE/número
                                        found_value_in_line = True
                                        roles[token_id] = "VALUE"
                                        break
                
                # Se não encontrou VALUE na mesma linha, mas está em coluna de valores conhecidos
                if not found_value_in_line:
                    # Verificar se está na mesma coluna (X) que VALUES conhecidos
                    for other_token in tokens:
                        other_id = other_token["id"]
                        if other_id == token_id:
                            continue
                        
                        other_role = roles.get(other_id)
                        if other_role == "VALUE":
                            other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                            if len(other_bbox) >= 4:
                                other_x0 = other_bbox[0]
                                x_diff = abs(x0 - other_x0)
                                
                                # Se está na mesma coluna (X muito próximo)
                                if x_diff < 0.02:
                                    # E está próximo verticalmente (mesma seção)
                                    other_y0 = other_bbox[1]
                                    y_diff = abs(y0 - other_y0)
                                    if y_diff < 0.15:  # Próximo verticalmente
                                        roles[token_id] = "VALUE"
                                        break
        
        # Se ainda não foi classificado, verificar uma última vez se deveria ser HEADER
        if token_id not in roles or roles.get(token_id) is None:
            bbox = token.get("bbox", [0, 0, 0, 0])
            font_size = token.get("font_size", 0) or 0
            
            if len(bbox) >= 4 and font_size > 0:
                y_top = bbox[1]
                is_near_top = y_top < 0.20
                # Mais permissivo: fonte maior que média OU ≥1.2x
                is_large_font = font_size >= avg_font_size * 1.2
                is_above_avg = font_size > avg_font_size
                tokens_list = text.split()
                
                # Se está no topo e tem fonte maior que média, é HEADER
                if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                    text_stripped = text.rstrip()
                    ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
                    if not ends_with_separator and not re.match(r"^\d+$", text.strip()):
                        roles[token_id] = "HEADER"
                        continue
            
            # Se é sigla, classificar como VALUE por padrão
            # (siglas geralmente são valores, não labels)
            is_acronym_check = bool(re.match(r"^[A-Z]{2,3}$", text))
            if is_acronym_check:
                roles[token_id] = "VALUE"
    
    # Passagem FINAL: GARANTIR que HEADER não foi sobrescrito
    # Verificar TODOS os tokens no topo com fonte grande e FORÇAR HEADER
    # Isso tem prioridade ABSOLUTA sobre qualquer outra classificação
    for token in tokens:
        token_id = token["id"]
        text = token.get("text", "").strip()
        current_role = roles.get(token_id)
        
        if not text:
            continue
        
        bbox = token.get("bbox", [0, 0, 0, 0])
        font_size = token.get("font_size", 0) or 0
        
        if len(bbox) >= 4 and font_size > 0:
            y_top = bbox[1]
            is_near_top = y_top < 0.20
            # Mais permissivo: fonte maior que média OU ≥1.2x
            is_large_font = font_size >= avg_font_size * 1.2
            is_above_avg = font_size > avg_font_size
            tokens_list = text.split()
            
            # Se está no topo e tem fonte maior que média, DEVE ser HEADER
            if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                text_stripped = text.rstrip()
                ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
                if not ends_with_separator and not re.match(r"^\d+$", text.strip()):
                    # Se não é HEADER, forçar HEADER (pode ter sido sobrescrito por memória ou outras passagens)
                    if current_role != "HEADER":
                        roles[token_id] = "HEADER"
    
    # Passagem FINAL 2: Garantir que todo VALUE tem LABEL (OBRIGATÓRIO E ÚNICO)
    # REGRA: Se um token é VALUE (incluindo datas), obrigatoriamente acima (north) ou à esquerda (west) 
    # deve ter um único token que é LABEL. Se não existe, classificar o mais próximo como LABEL.
    # Executar no final para garantir que nenhum VALUE fique sem LABEL
    # IMPORTANTE: Isso também se aplica a datas (que são VALUE)
    import re
    date_pattern_final2 = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
    
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        token_text = token.get("text", "").strip()
        
        # Se é VALUE OU é uma data (datas também precisam de LABEL), verificar se tem LABEL conectado
        is_date = bool(date_pattern_final2.search(token_text))
        is_value = current_role == "VALUE"
        
        if is_value or is_date:
            # Se é data mas não foi classificado como VALUE ainda, classificar como VALUE
            if is_date and not is_value:
                roles[token_id] = "VALUE"
                current_role = "VALUE"
            
            # Verificar se está ligado a um LABEL
            if token_id not in value_to_label:
                # Não está ligado a nenhum LABEL, procurar por posição espacial
                value_bbox = token.get("bbox", [0, 0, 0, 0])
                if len(value_bbox) < 4:
                    continue
                
                value_x0 = value_bbox[0]
                value_x1 = value_bbox[2]
                value_y0 = value_bbox[1]
                value_y1 = value_bbox[3]
                value_center_x = (value_x0 + value_x1) / 2.0
                value_center_y = (value_y0 + value_y1) / 2.0
                
                # Procurar tokens acima (north) ou à esquerda (west) por posição espacial
                # Priorizar: primeiro acima (north), depois à esquerda (west)
                candidates_above = []  # Tokens acima (y < value_y0)
                candidates_left = []    # Tokens à esquerda (x1 < value_x0)
                
                for other_token in tokens:
                    other_id = other_token["id"]
                    if other_id == token_id:
                        continue
                    
                    other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                    if len(other_bbox) < 4:
                        continue
                    
                    other_x0 = other_bbox[0]
                    other_x1 = other_bbox[2]
                    other_y0 = other_bbox[1]
                    other_y1 = other_bbox[3]
                    other_center_x = (other_x0 + other_x1) / 2.0
                    other_center_y = (other_y0 + other_y1) / 2.0
                    
                    other_role = roles.get(other_id)
                    other_text = other_token.get("text", "").strip()
                    
                    # Verificar se é texto puro (não número, data, código numérico)
                    # Importar função is_text_only se necessário
                    def is_text_only_check(text: str) -> bool:
                        if not text or not text.strip():
                            return False
                        text_clean = text.strip()
                        if re.match(r"^\d+$", text_clean):
                            return False
                        date_check = date_pattern_final2.search(text_clean)
                        if date_check:
                            return False
                        # Verificar se tem pelo menos uma letra
                        if re.search(r"[A-Za-zÀ-ÿ]", text_clean):
                            return True
                        return False
                    
                    # Verificar se está acima (north) - token acima do VALUE
                    # Considerar se há sobreposição em X OU se está alinhado verticalmente
                    x_overlap = not (other_x1 < value_x0 or other_x0 > value_x1)
                    is_above = other_y1 < value_y0  # Token termina antes do VALUE começar
                    
                    if is_above and x_overlap:
                        # Só considerar se é texto puro (pode ser VALUE incorretamente classificado)
                        if is_text_only_check(other_text):
                            # Calcular distância vertical
                            vertical_distance = value_y0 - other_y1
                            # Calcular distância horizontal (centro)
                            horizontal_distance = abs(other_center_x - value_center_x)
                            # Priorizar tokens mais próximos verticalmente e alinhados horizontalmente
                            candidates_above.append((
                                other_id, other_token, other_role, other_text,
                                vertical_distance, horizontal_distance
                            ))
                    
                    # Verificar se está à esquerda (west) - token à esquerda do VALUE
                    # Considerar se há sobreposição em Y OU se está na mesma linha
                    y_overlap = not (other_y1 < value_y0 or other_y0 > value_y1)
                    is_left = other_x1 < value_x0  # Token termina antes do VALUE começar
                    
                    if is_left and y_overlap and not is_above:  # Não considerar se já está acima
                        # Só considerar se é texto puro (pode ser VALUE incorretamente classificado)
                        if is_text_only_check(other_text):
                            # Calcular distância horizontal
                            horizontal_distance = value_x0 - other_x1
                            # Calcular distância vertical (centro)
                            vertical_distance = abs(other_center_y - value_center_y)
                            # Priorizar tokens mais próximos horizontalmente e alinhados verticalmente
                            candidates_left.append((
                                other_id, other_token, other_role, other_text,
                                horizontal_distance, vertical_distance
                            ))
                
                # Priorizar tokens acima (north) sobre tokens à esquerda (west)
                best_candidate = None
                
                if candidates_above:
                    # Ordenar por: menor distância vertical, depois menor distância horizontal
                    candidates_above.sort(key=lambda c: (c[4], c[5]))
                    best_candidate = candidates_above[0]
                elif candidates_left:
                    # Ordenar por: menor distância horizontal, depois menor distância vertical
                    candidates_left.sort(key=lambda c: (c[4], c[5]))
                    best_candidate = candidates_left[0]
                
                # Se encontrou candidato, classificar como LABEL
                if best_candidate:
                    candidate_id, candidate_token, candidate_role, candidate_text, _, _ = best_candidate
                    
                    # Verificar se não é uma data ou número (esses são sempre VALUE)
                    is_date = bool(date_pattern.search(candidate_text))
                    is_number = bool(re.match(r"^\d+$", candidate_text.strip()))
                    
                    # Se o candidato já é LABEL, apenas criar ligação
                    if candidate_role == "LABEL":
                        label_to_value[candidate_id] = token_id
                        value_to_label[token_id] = candidate_id
                        if candidate_id not in label_candidates:
                            label_candidates.append(candidate_id)
                    # Se o candidato não tem role ou é None, e não é data/número, classificar como LABEL
                    elif (candidate_role is None or candidate_role == "") and not is_date and not is_number:
                        # Classificar como LABEL (já verificamos que não é HEADER, VALUE, data ou número)
                        roles[candidate_id] = "LABEL"
                        if candidate_id not in label_candidates:
                            label_candidates.append(candidate_id)
                        label_to_value[candidate_id] = token_id
                        value_to_label[token_id] = candidate_id
                    # Se o candidato foi classificado incorretamente como VALUE mas é texto puro, reclassificar como LABEL
                    elif candidate_role == "VALUE" and not is_date and not is_number:
                        # Reclassificar: token de texto acima/esquerda de VALUE/data deve ser LABEL
                        roles[candidate_id] = "LABEL"
                        if candidate_id not in label_candidates:
                            label_candidates.append(candidate_id)
                        label_to_value[candidate_id] = token_id
                        value_to_label[token_id] = candidate_id
                    # Se o candidato tem outro role mas não é VALUE, verificar se pode ser reclassificado
                    elif candidate_role not in ("VALUE", "HEADER") and not is_date and not is_number:
                        # Se não é claramente um VALUE ou HEADER, pode ser reclassificado como LABEL
                        # Mas só se não tiver outro VALUE já ligado
                        if candidate_id not in label_to_value:
                            roles[candidate_id] = "LABEL"
                            if candidate_id not in label_candidates:
                                label_candidates.append(candidate_id)
                            label_to_value[candidate_id] = token_id
                            value_to_label[token_id] = candidate_id
                else:
                    # Se não encontrou candidato por posição espacial, tentar por edges
                    north_neighbors = adj.get(token_id, {}).get("north", [])
                    west_neighbors = adj.get(token_id, {}).get("west", [])
                    all_neighbors = north_neighbors + west_neighbors
                    
                    # Verificar se algum vizinho pode ser classificado como LABEL
                    for neighbor_id in all_neighbors:
                        neighbor_node = node_by_id.get(neighbor_id)
                        if not neighbor_node:
                            continue
                        
                        neighbor_text = neighbor_node.get("text", "").strip()
                        neighbor_role = roles.get(neighbor_id)
                        
                        # Se o vizinho não tem role ou é None, e está acima/esquerda de um VALUE, é LABEL
                        # Também aceitar se o role é None (string) ou vazio
                        neighbor_role_clean = neighbor_role if neighbor_role else None
                        if neighbor_role_clean is None or neighbor_role_clean == "":
                            # Verificar se não é uma data ou número (esses são sempre VALUE)
                            is_date = bool(date_pattern.search(neighbor_text))
                            is_number = bool(re.match(r"^\d+$", neighbor_text.strip()))
                            
                            if not is_date and not is_number:
                                # Classificar como LABEL e criar ligação
                                roles[neighbor_id] = "LABEL"
                                if neighbor_id not in label_candidates:
                                    label_candidates.append(neighbor_id)
                                label_to_value[neighbor_id] = token_id
                                value_to_label[token_id] = neighbor_id
                                break
    
    # Passagem FINAL 3: Propagação de roles por hierarquia tipográfica
    # REGRA: Se um token tem um role (LABEL, VALUE, HEADER) e há tokens à direita (east) 
    # na mesma linha (com tolerância pequena de Y) e com o mesmo estilo (font_size, bold, italic, color),
    # então esses tokens devem ter o mesmo role (mesma hierarquia tipográfica).
    # Isso garante consistência visual - tokens com mesmo estilo na mesma linha têm mesmo papel.
    
    # Tolerâncias
    Y_TOLERANCE_SAME_LINE = 0.01  # 1% da altura da página para considerar mesma linha
    FONT_SIZE_TOLERANCE = 1.0     # 1.0pt de tolerância para tamanho de fonte (permite diferença de 1pt)
    
    # Agrupar tokens por linha (Y) e estilo
    # IMPORTANTE: Usar agrupamento flexível que considera font size dentro da tolerância
    line_style_groups = {}  # {(y_center_rounded, font_size_base, bold, italic, color): [token_ids]}
    
    for token in tokens:
        token_id = token["id"]
        bbox = token.get("bbox", [0, 0, 0, 0])
        if len(bbox) < 4:
            continue
        
        y_center = (bbox[1] + bbox[3]) / 2.0
        font_size = token.get("font_size", 0) or 0
        bold = token.get("bold", False)
        italic = token.get("italic", False)
        color = token.get("color")
        
        # Arredondar Y para agrupar por linha
        y_rounded = round(y_center / Y_TOLERANCE_SAME_LINE) * Y_TOLERANCE_SAME_LINE
        
        # Para font size, encontrar ou criar grupo com font size base similar (dentro da tolerância)
        # Estratégia: arredondar para múltiplo da tolerância, mas depois reagrupar tokens próximos
        if font_size > 0:
            # Arredondar para o múltiplo mais próximo da tolerância
            # Exemplo: 10.0 e 11.0 com tolerância 1.0 -> ambos arredondam para 10.0 ou 11.0
            # Mas queremos que sejam agrupados juntos, então vamos usar o menor múltiplo
            font_base = round(font_size / FONT_SIZE_TOLERANCE) * FONT_SIZE_TOLERANCE
        else:
            font_base = 0
        
        # Tentar encontrar grupo existente com font size dentro da tolerância
        found_group = False
        for (group_y, group_font, group_bold, group_italic, group_color), group_tokens in line_style_groups.items():
            # Verificar se está na mesma linha e tem mesmo estilo (exceto font size)
            if (group_y == y_rounded and group_bold == bold and 
                group_italic == italic and group_color == color):
                # Verificar se font size está dentro da tolerância
                if abs(font_size - group_font) <= FONT_SIZE_TOLERANCE:
                    group_tokens.append(token_id)
                    found_group = True
                    break
        
        # Se não encontrou grupo, criar novo
        if not found_group:
            key = (y_rounded, font_base, bold, italic, color)
            if key not in line_style_groups:
                line_style_groups[key] = []
            line_style_groups[key].append(token_id)
    
    # Para cada grupo de mesma linha e estilo, verificar se há tokens com roles definidos
    # e propagar para tokens sem role ou com role diferente (exceto HEADER - tem prioridade)
    # IMPORTANTE: Agrupar tokens com font size dentro da tolerância (1pt)
    for (y_rounded, font_rounded_base, bold, italic, color), token_ids_base in line_style_groups.items():
        # Agrupar tokens com font size dentro da tolerância
        # Criar grupos adicionais para font sizes próximos
        expanded_groups = {}  # {group_key: [token_ids]}
        
        for tid in token_ids_base:
            token_obj = next((t for t in tokens if t["id"] == tid), None)
            if not token_obj:
                continue
            
            token_font_size = token_obj.get("font_size", 0) or 0
            token_bbox = token_obj.get("bbox", [0, 0, 0, 0])
            
            # Encontrar grupo existente com font size similar (dentro da tolerância)
            found_group = False
            for (group_y, group_font, group_bold, group_italic, group_color), group_tokens in expanded_groups.items():
                # Verificar se font size está dentro da tolerância
                if abs(token_font_size - group_font) <= FONT_SIZE_TOLERANCE:
                    # Verificar se outros atributos são iguais
                    if (group_y == y_rounded and group_bold == bold and 
                        group_italic == italic and group_color == color):
                        group_tokens.append(tid)
                        found_group = True
                        break
            
            # Se não encontrou grupo, criar novo
            if not found_group:
                group_key = (y_rounded, token_font_size, bold, italic, color)
                if group_key not in expanded_groups:
                    expanded_groups[group_key] = []
                expanded_groups[group_key].append(tid)
        
        # Processar cada grupo expandido
        for (group_y, group_font, group_bold, group_italic, group_color), token_ids in expanded_groups.items():
            if len(token_ids) < 2:
                continue  # Precisa de pelo menos 2 tokens para propagar
            
            # Ordenar tokens por X (esquerda para direita)
            tokens_with_x = [(tid, next((t for t in tokens if t["id"] == tid), None)) for tid in token_ids]
            tokens_with_x = [(tid, t) for tid, t in tokens_with_x if t is not None]
            tokens_with_x.sort(key=lambda x: x[1].get("bbox", [0, 0, 0, 0])[0] if len(x[1].get("bbox", [])) >= 4 else 0)
            
            # Coletar roles dos tokens no grupo
            group_roles = {}
            for tid, token_obj in tokens_with_x:
                role = roles.get(tid)
                if role:
                    group_roles[role] = group_roles.get(role, 0) + 1
            
            if not group_roles:
                continue  # Nenhum token tem role ainda
            
            # Encontrar role dominante (mais comum, mas HEADER tem prioridade absoluta)
            has_header = "HEADER" in group_roles
            if has_header:
                dominant_role = "HEADER"
            else:
                # Escolher role mais comum
                dominant_role = max(group_roles.items(), key=lambda x: x[1])[0]
            
            # Verificar se há edge east conectando tokens consecutivos
            # Se sim, propagar role do primeiro para o segundo
            for i in range(len(tokens_with_x) - 1):
                token1_id, token1_obj = tokens_with_x[i]
                token2_id, token2_obj = tokens_with_x[i + 1]
                
                token1_role = roles.get(token1_id)
                token2_role = roles.get(token2_id)
                
                # Verificar se há edge east conectando token1 -> token2
                has_east_edge = False
                for edge in graph.get("edges", []):
                    if edge.get("from") == token1_id and edge.get("to") == token2_id and edge.get("relation") == "east":
                        has_east_edge = True
                        break
                
                # Se há edge east e token1 tem role definido, propagar para token2
                if has_east_edge and token1_role:
                    # Não sobrescrever HEADER (tem prioridade absoluta)
                    if token2_role != "HEADER":
                        # Se token1 é LABEL/VALUE e token2 não tem role ou tem role diferente, propagar
                        if token1_role in ("LABEL", "VALUE", "HEADER"):
                            # Verificar se token2 não é claramente um VALUE (número, data)
                            token2_text = token2_obj.get("text", "").strip()
                            import re
                            date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
                            is_date = bool(date_pattern.search(token2_text))
                            is_number = bool(re.match(r"^\d+$", token2_text.strip()))
                            
                            # Se token2 é número ou data, é VALUE (não propagar LABEL)
                            if is_date or is_number:
                                if token1_role == "LABEL":
                                    # Token1 é LABEL mas token2 é número/data, então token2 é VALUE
                                    roles[token2_id] = "VALUE"
                                # Se token1 é VALUE e token2 é número/data, manter VALUE
                            else:
                                # Token2 não é número/data, verificar se é código numérico
                                # IMPORTANTE: Não propagar LABEL para tokens que são código numérico
                                # (a regra de código numérico tem precedência sobre hierarquia tipográfica)
                                import re
                                numeric_code_pattern = re.compile(
                                    r"(?:R\s*\$|US\s*\$|\$|€|£)\s*\d|"
                                    r"\d+[.,]\d+|"
                                    r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|"
                                    r"\d+[.,]\d{2}|"
                                    r"\d+[./-]\d+(?:[./-]\d+)?(?!\d{1,2}[/-]\d{1,2})"
                                )
                                is_numeric_code_token2 = bool(numeric_code_pattern.search(token2_text)) and not is_date
                                
                                if is_numeric_code_token2:
                                    # Token2 é código numérico, não propagar LABEL (será classificado como VALUE pela Passagem FINAL 4)
                                    # Se token1 é LABEL, token2 deve ser VALUE (não LABEL)
                                    if token1_role == "LABEL":
                                        roles[token2_id] = "VALUE"
                                else:
                                    # Token2 não é código numérico, pode propagar role
                                    if token1_role == "LABEL":
                                        # Se token1 é LABEL e token2 não tem role ou é diferente, propagar LABEL
                                        # IMPORTANTE: Forçar propagação mesmo se token2 já é VALUE (pode ser incorreto)
                                        if token2_role is None or token2_role == "" or token2_role == "VALUE" or (token2_role != "HEADER"):
                                            roles[token2_id] = "LABEL"
                                            # Atualizar label_candidates se necessário
                                            if token2_id not in label_candidates:
                                                label_candidates.append(token2_id)
                                    elif token1_role == "VALUE":
                                        # Se token1 é VALUE e token2 não tem role, pode ser VALUE também
                                        if token2_role is None or token2_role == "":
                                            roles[token2_id] = "VALUE"
                                    elif token1_role == "HEADER":
                                        # HEADER tem prioridade, propagar apenas se token2 não tem role
                                        if token2_role is None or token2_role == "":
                                            roles[token2_id] = "HEADER"
    
    # Passagem FINAL 4: Detecção de código numérico e classificação de LABELs adjacentes
    # REGRA: Se um token tem formato de código numérico (números com separadores como .,/-)
    # como dinheiro (R$ 1.234,56), CPF (123.456.789-00), código de empresa (123/456), etc.
    # e está ligado a um token que é só texto acima (north), à esquerda (west) ou direita (east),
    # então esse token de texto é um LABEL.
    # IMPORTANTE: Excluir datas do padrão de código numérico (datas têm formato específico).
    # Se houver token acima também, priorizar acima (desempate).
    
    import re
    # Padrão para detectar datas (deve ser excluído do código numérico)
    date_pattern = re.compile(
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}"
    )
    
    # Padrão genérico para detectar código numérico: números com separadores (.,/-)
    # Inclui: dinheiro (R$ 1.234,56), CPF (123.456.789-00), códigos (123/456), etc.
    # EXCLUI: datas (formato DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD)
    # Nota: O padrão pode capturar datas, mas a função is_numeric_code() verifica primeiro se é data
    numeric_code_pattern = re.compile(
        r"(?:R\s*\$|US\s*\$|\$|€|£)\s*\d|"  # Moeda seguida de número
        r"\d+[.,]\d+|"  # Números com ponto ou vírgula: 123.456, 123,456
        r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|"  # Formato com milhares: 1.234.567,89 ou 1.234.567
        r"\d+[.,]\d{2}|"  # Decimal simples: 123,45 ou 123.45
        r"\d+[./-]\d+(?:[./-]\d+)?(?!\d{1,2}[/-]\d{1,2})"  # Códigos com / ou - mas não datas (não termina com DD/MM)
    )
    
    def is_numeric_code(text: str) -> bool:
        """Verifica se o texto é código numérico (não data)."""
        if not text or not text.strip():
            return False
        
        text_clean = text.strip()
        
        # Primeiro verificar se é data - se for, NÃO é código numérico
        if date_pattern.search(text_clean):
            return False
        
        # Depois verificar se é código numérico
        return bool(numeric_code_pattern.search(text_clean))
    
    # Padrão para detectar se é só texto (não número, não data, não dinheiro)
    def is_text_only(text: str) -> bool:
        """Verifica se o texto é apenas texto (não número, data ou dinheiro)."""
        if not text or not text.strip():
            return False
        
        text_clean = text.strip()
        
        # Não é número puro
        if re.match(r"^\d+$", text_clean):
            return False
        
        # Não é data
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        if date_pattern.search(text_clean):
            return False
        
        # Não é código numérico (dinheiro, CPF, códigos, etc.)
        numeric_code_pattern = re.compile(
            r"(?:R\s*\$|US\s*\$|\$|€|£)\s*\d|"
            r"\d+[.,/\-]\d+|"
            r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|"
            r"\d+[.,]\d{2}"
        )
        if numeric_code_pattern.search(text_clean):
            return False
        
        # Se tem pelo menos uma letra, é texto
        if re.search(r"[A-Za-zÀ-ÿ]", text_clean):
            return True
        
        return False
    
    # Para cada token, verificar se é dinheiro
    for token in tokens:
        token_id = token["id"]
        token_text = token.get("text", "").strip()
        
        if not token_text:
            continue
        
        # Verificar se é formato de código numérico (não data)
        if not is_numeric_code(token_text):
            continue
        
        # Token é código numérico, procurar tokens adjacentes que são só texto
        # Priorizar: acima (north) > esquerda (west) > direita (east)
        # IMPORTANTE: Não classificar tokens adjacentes a datas como LABEL
        
        candidates = []  # Lista de (neighbor_id, direction, neighbor_token)
        
        # 1. Verificar token acima (north) - maior prioridade
        north_neighbors = adj.get(token_id, {}).get("north", [])
        for neighbor_id in north_neighbors:
            neighbor_node = node_by_id.get(neighbor_id)
            if not neighbor_node:
                continue
            
            neighbor_text = neighbor_node.get("text", "").strip()
            # Verificar se o vizinho não é uma data
            if date_pattern.search(neighbor_text):
                continue  # Pular datas - não devem acionar regra de LABEL
            
            if is_text_only(neighbor_text):
                neighbor_role = roles.get(neighbor_id)
                # Se não tem role, é None, ou foi classificado incorretamente como VALUE, pode ser LABEL
                if neighbor_role is None or neighbor_role == "" or neighbor_role == "VALUE":
                    candidates.append((neighbor_id, "north", neighbor_node))
        
        # 2. Verificar token à esquerda (west) - segunda prioridade
        west_neighbors = adj.get(token_id, {}).get("west", [])
        for neighbor_id in west_neighbors:
            neighbor_node = node_by_id.get(neighbor_id)
            if not neighbor_node:
                continue
            
            neighbor_text = neighbor_node.get("text", "").strip()
            # Verificar se o vizinho não é uma data
            if date_pattern.search(neighbor_text):
                continue  # Pular datas - não devem acionar regra de LABEL
            
            if is_text_only(neighbor_text):
                neighbor_role = roles.get(neighbor_id)
                # Se não tem role, é None, ou foi classificado incorretamente como VALUE, pode ser LABEL
                if neighbor_role is None or neighbor_role == "" or neighbor_role == "VALUE":
                    candidates.append((neighbor_id, "west", neighbor_node))
        
        # 3. Verificar token à direita (east) - terceira prioridade
        east_neighbors = adj.get(token_id, {}).get("east", [])
        for neighbor_id in east_neighbors:
            neighbor_node = node_by_id.get(neighbor_id)
            if not neighbor_node:
                continue
            
            neighbor_text = neighbor_node.get("text", "").strip()
            # Verificar se o vizinho não é uma data
            if date_pattern.search(neighbor_text):
                continue  # Pular datas - não devem acionar regra de LABEL
            
            if is_text_only(neighbor_text):
                neighbor_role = roles.get(neighbor_id)
                # Se não tem role, é None, ou foi classificado incorretamente como VALUE, pode ser LABEL
                if neighbor_role is None or neighbor_role == "" or neighbor_role == "VALUE":
                    candidates.append((neighbor_id, "east", neighbor_node))
        
        # Se há candidatos, classificar o de maior prioridade como LABEL
        if candidates:
            # Ordenar por prioridade: north > west > east
            priority_order = {"north": 0, "west": 1, "east": 2}
            candidates.sort(key=lambda x: priority_order.get(x[1], 99))
            
            # Pegar o primeiro (maior prioridade)
            best_candidate_id, best_direction, best_neighbor = candidates[0]
            
            # Verificar se o candidato foi classificado incorretamente como VALUE
            # Se sim, reclassificar como LABEL (tem prioridade sobre VALUE quando adjacente a código numérico)
            current_role = roles.get(best_candidate_id)
            if current_role == "VALUE":
                # Reclassificar: token de texto adjacente a código numérico deve ser LABEL, não VALUE
                roles[best_candidate_id] = "LABEL"
            elif current_role is None or current_role == "":
                # Classificar como LABEL
                roles[best_candidate_id] = "LABEL"
            
            if best_candidate_id not in label_candidates:
                label_candidates.append(best_candidate_id)
            
            # Criar ligação LABEL -> VALUE (código numérico)
            label_to_value[best_candidate_id] = token_id
            value_to_label[token_id] = best_candidate_id
            
            # IMPORTANTE: Garantir que o token de código numérico seja VALUE
            # Mesmo que tenha sido classificado como LABEL pela Passagem FINAL 3 (hierarquia tipográfica),
            # a regra de código numérico tem precedência sobre hierarquia tipográfica
            roles[token_id] = "VALUE"
            
            # Se o token de código numérico estava em label_candidates, remover
            if token_id in label_candidates:
                label_candidates.remove(token_id)
    
    # Passagem FINAL 5: Limpeza - remover classificação LABEL incorreta de tokens adjacentes apenas a datas
    # Se um token foi classificado como LABEL mas está adjacente apenas a datas (não códigos numéricos),
    # remover a classificação LABEL (datas não devem acionar regra de LABEL)
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        # Se é LABEL, verificar se está adjacente apenas a datas
        if current_role == "LABEL":
            # Verificar todos os vizinhos
            all_neighbors = []
            for direction in ["north", "south", "east", "west"]:
                all_neighbors.extend(adj.get(token_id, {}).get(direction, []))
            
            # Verificar se tem vizinho que é VALUE mas NÃO é data (datas não devem acionar regra de LABEL)
            # OU se foi classificado como LABEL por outras razões (termina com ":")
            has_numeric_code_neighbor = False  # Código numérico (não data)
            has_date_neighbor = False  # Data (não deve acionar regra de LABEL)
            
            for neighbor_id in all_neighbors:
                neighbor_node = node_by_id.get(neighbor_id)
                if not neighbor_node:
                    continue
                
                neighbor_text = neighbor_node.get("text", "").strip()
                neighbor_role = roles.get(neighbor_id)
                
                # Verificar se é data primeiro
                if date_pattern.search(neighbor_text):
                    has_date_neighbor = True
                    continue  # Não contar como código numérico
                
                # Se o vizinho é VALUE e não é data, então está correto ser LABEL
                if neighbor_role == "VALUE":
                    # Verificar se é código numérico (não data)
                    if is_numeric_code(neighbor_text):
                        has_numeric_code_neighbor = True
                        break
            
            # Se tem apenas vizinho que é data (não código numérico), verificar se deve remover LABEL
            # IMPORTANTE: Não remover se foi classificado pela Passagem FINAL 2 (datas também precisam de LABEL)
            # Só remover se foi classificado incorretamente pela Passagem FINAL 4 (código numérico)
            if has_date_neighbor and not has_numeric_code_neighbor:
                # Verificar se foi classificado como LABEL por outras razões (termina com ":")
                token_text = token.get("text", "").strip()
                LABEL_SEPARATORS = [":", "—", "–", ".", "•", "/"]
                ends_with_separator = any(token_text.rstrip().endswith(sep) for sep in LABEL_SEPARATORS)
                has_colon_in_middle = ":" in token_text and token_text.find(":") < len(token_text) - 1
                
                # Verificar se está ligado a uma data na estrutura value_to_label
                # Se sim, foi classificado pela Passagem FINAL 2 e deve manter LABEL
                is_linked_to_date = False
                for neighbor_id in all_neighbors:
                    if neighbor_id in value_to_label and value_to_label[neighbor_id] == token_id:
                        # Este token é LABEL de um VALUE (pode ser data)
                        neighbor_node = node_by_id.get(neighbor_id)
                        if neighbor_node:
                            neighbor_text = neighbor_node.get("text", "").strip()
                            if date_pattern.search(neighbor_text):
                                is_linked_to_date = True
                                break
                
                # Se não termina com separador, não tem ":" no meio, e NÃO está ligado a data, remover LABEL
                if not ends_with_separator and not has_colon_in_middle and not is_linked_to_date:
                    # Remover da lista de label_candidates se estiver lá
                    if token_id in label_candidates:
                        label_candidates.remove(token_id)
                    # Remover role (deixar None)
                    roles[token_id] = None
    
    # Passagem FINAL 6: Reclassificar LABELs sem edges como HEADER
    # REGRA: Se um token é LABEL mas não tem nenhum edge conectado (não se liga a nenhum VALUE),
    # então deve ser HEADER (labels sempre se ligam a valores).
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        # Se é LABEL, verificar se tem edges
        if current_role == "LABEL":
            # Verificar todos os edges
            has_edges = False
            for edge in graph.get("edges", []):
                if edge.get("from") == token_id or edge.get("to") == token_id:
                    has_edges = True
                    break
            
            # Se não tem edges, reclassificar como HEADER
            if not has_edges:
                roles[token_id] = "HEADER"
                # Remover da lista de label_candidates se estiver lá
                if token_id in label_candidates:
                    label_candidates.remove(token_id)
    
    # Passagem FINAL 7: Garantir que tokens de texto acima de VALUE/datas sejam LABEL
    # Esta passagem é executada DEPOIS de todas as outras para garantir que nenhum VALUE fique sem LABEL
    # e que tokens de texto acima de VALUE/datas sejam sempre LABEL, mesmo se foram classificados como VALUE antes
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        token_text = token.get("text", "").strip()
        
        # Verificar se é VALUE ou data
        is_date = bool(date_pattern_final2.search(token_text))
        is_value = current_role == "VALUE"
        
        if is_value or is_date:
            # Se é data mas não foi classificado como VALUE ainda, classificar como VALUE
            if is_date and not is_value:
                roles[token_id] = "VALUE"
                current_role = "VALUE"
            
            # Verificar se está ligado a um LABEL CORRETO
            # IMPORTANTE: Mesmo se já está ligado, verificar se o LABEL está correto
            # Se o LABEL atual é VALUE (incorreto), remover ligação e procurar novo LABEL
            current_label_id = value_to_label.get(token_id)
            needs_new_label = False
            if current_label_id is not None:
                current_label_role = roles.get(current_label_id)
                # Se o LABEL atual é VALUE (incorreto), remover ligação e procurar novo LABEL
                if current_label_role == "VALUE":
                    # Remover ligação incorreta
                    if current_label_id in label_to_value:
                        del label_to_value[current_label_id]
                    if token_id in value_to_label:
                        del value_to_label[token_id]
                    needs_new_label = True
            else:
                needs_new_label = True
            
            if needs_new_label:
                # Não está ligado a nenhum LABEL, procurar por posição espacial
                value_bbox = token.get("bbox", [0, 0, 0, 0])
                if len(value_bbox) < 4:
                    continue
                
                value_x0 = value_bbox[0]
                value_x1 = value_bbox[2]
                value_y0 = value_bbox[1]
                value_y1 = value_bbox[3]
                value_center_x = (value_x0 + value_x1) / 2.0
                value_center_y = (value_y0 + value_y1) / 2.0
                
                # Procurar tokens acima (north) ou à esquerda (west) por posição espacial
                # Priorizar: primeiro acima (north), depois à esquerda (west)
                candidates_above = []  # Tokens acima (y < value_y0)
                candidates_left = []    # Tokens à esquerda (x1 < value_x0)
                
                for other_token in tokens:
                    other_id = other_token["id"]
                    if other_id == token_id:
                        continue
                    
                    other_bbox = other_token.get("bbox", [0, 0, 0, 0])
                    if len(other_bbox) < 4:
                        continue
                    
                    other_x0 = other_bbox[0]
                    other_x1 = other_bbox[2]
                    other_y0 = other_bbox[1]
                    other_y1 = other_bbox[3]
                    other_center_x = (other_x0 + other_x1) / 2.0
                    other_center_y = (other_y0 + other_y1) / 2.0
                    
                    other_role = roles.get(other_id)
                    other_text = other_token.get("text", "").strip()
                    
                    # Verificar se é texto puro (não número, data, código numérico)
                    def is_text_only_check(text: str) -> bool:
                        if not text or not text.strip():
                            return False
                        text_clean = text.strip()
                        if re.match(r"^\d+$", text_clean):
                            return False
                        date_check = date_pattern_final2.search(text_clean)
                        if date_check:
                            return False
                        # Verificar se tem pelo menos uma letra
                        if re.search(r"[A-Za-zÀ-ÿ]", text_clean):
                            return True
                        return False
                    
                    # Verificar se está acima (north) - token acima do VALUE
                    # Considerar se há sobreposição em X OU se está alinhado verticalmente
                    x_overlap = not (other_x1 < value_x0 or other_x0 > value_x1)
                    is_above = other_y1 < value_y0  # Token termina antes do VALUE começar
                    
                    if is_above and x_overlap:
                        # Só considerar se é texto puro (pode ser VALUE incorretamente classificado)
                        if is_text_only_check(other_text):
                            # Calcular distância vertical
                            vertical_distance = value_y0 - other_y1
                            # Calcular distância horizontal (centro)
                            horizontal_distance = abs(other_center_x - value_center_x)
                            # Priorizar tokens mais próximos verticalmente e alinhados horizontalmente
                            candidates_above.append((
                                other_id, other_token, other_role, other_text,
                                vertical_distance, horizontal_distance
                            ))
                    
                    # Verificar se está à esquerda (west) - token à esquerda do VALUE
                    # Considerar se há sobreposição em Y OU se está na mesma linha
                    y_overlap = not (other_y1 < value_y0 or other_y0 > value_y1)
                    is_left = other_x1 < value_x0  # Token termina antes do VALUE começar
                    
                    if is_left and y_overlap and not is_above:  # Não considerar se já está acima
                        # Só considerar se é texto puro (pode ser VALUE incorretamente classificado)
                        if is_text_only_check(other_text):
                            # Calcular distância horizontal
                            horizontal_distance = value_x0 - other_x1
                            # Calcular distância vertical (centro)
                            vertical_distance = abs(other_center_y - value_center_y)
                            # Priorizar tokens mais próximos horizontalmente e alinhados verticalmente
                            candidates_left.append((
                                other_id, other_token, other_role, other_text,
                                horizontal_distance, vertical_distance
                            ))
                
                # Priorizar tokens acima (north) sobre tokens à esquerda (west)
                best_candidate = None
                
                if candidates_above:
                    # Ordenar por: menor distância vertical, depois menor distância horizontal
                    candidates_above.sort(key=lambda c: (c[4], c[5]))
                    best_candidate = candidates_above[0]
                elif candidates_left:
                    # Ordenar por: menor distância horizontal, depois menor distância vertical
                    candidates_left.sort(key=lambda c: (c[4], c[5]))
                    best_candidate = candidates_left[0]
                
                # Se encontrou candidato, classificar como LABEL (FORÇAR mesmo se já é VALUE)
                if best_candidate:
                    candidate_id, candidate_token, candidate_role, candidate_text, _, _ = best_candidate
                    
                    # Verificar se não é uma data ou número (esses são sempre VALUE)
                    is_date_candidate = bool(date_pattern_final2.search(candidate_text))
                    is_number = bool(re.match(r"^\d+$", candidate_text.strip()))
                    
                    # Se o candidato já é LABEL, apenas criar ligação
                    if candidate_role == "LABEL":
                        label_to_value[candidate_id] = token_id
                        value_to_label[token_id] = candidate_id
                        if candidate_id not in label_candidates:
                            label_candidates.append(candidate_id)
                    # Se o candidato não tem role ou é None, e não é data/número, classificar como LABEL
                    elif (candidate_role is None or candidate_role == "") and not is_date_candidate and not is_number:
                        # Classificar como LABEL (já verificamos que não é HEADER, VALUE, data ou número)
                        roles[candidate_id] = "LABEL"
                        if candidate_id not in label_candidates:
                            label_candidates.append(candidate_id)
                        label_to_value[candidate_id] = token_id
                        value_to_label[token_id] = candidate_id
                    # Se o candidato foi classificado incorretamente como VALUE mas é texto puro, FORÇAR LABEL
                    elif candidate_role == "VALUE" and not is_date_candidate and not is_number:
                        # FORÇAR reclassificação: token de texto acima/esquerda de VALUE/data DEVE ser LABEL
                        roles[candidate_id] = "LABEL"
                        if candidate_id not in label_candidates:
                            label_candidates.append(candidate_id)
                        label_to_value[candidate_id] = token_id
                        value_to_label[token_id] = candidate_id
                    # Se o candidato tem outro role mas não é VALUE, verificar se pode ser reclassificado
                    elif candidate_role not in ("VALUE", "HEADER") and not is_date_candidate and not is_number:
                        # Se não é claramente um VALUE ou HEADER, pode ser reclassificado como LABEL
                        # Mas só se não tiver outro VALUE já ligado
                        if candidate_id not in label_to_value:
                            roles[candidate_id] = "LABEL"
                            if candidate_id not in label_candidates:
                                label_candidates.append(candidate_id)
                            label_to_value[candidate_id] = token_id
                            value_to_label[token_id] = candidate_id
                else:
                    # Se não encontrou candidato por posição espacial, tentar por edges
                    north_neighbors = adj.get(token_id, {}).get("north", [])
                    west_neighbors = adj.get(token_id, {}).get("west", [])
                    all_neighbors = north_neighbors + west_neighbors
                    
                    # Verificar se algum vizinho pode ser classificado como LABEL
                    for neighbor_id in all_neighbors:
                        neighbor_node = node_by_id.get(neighbor_id)
                        if not neighbor_node:
                            continue
                        
                        neighbor_text = neighbor_node.get("text", "").strip()
                        neighbor_role = roles.get(neighbor_id)
                        
                        # Verificar se é texto puro
                        def is_text_only_neighbor(text: str) -> bool:
                            if not text or not text.strip():
                                return False
                            text_clean = text.strip()
                            if re.match(r"^\d+$", text_clean):
                                return False
                            date_check = date_pattern_final2.search(text_clean)
                            if date_check:
                                return False
                            if re.search(r"[A-Za-zÀ-ÿ]", text_clean):
                                return True
                            return False
                        
                        # Se o vizinho não tem role ou é None, e está acima/esquerda de um VALUE, é LABEL
                        # Também aceitar se o role é None (string) ou vazio, OU se foi classificado incorretamente como VALUE
                        neighbor_role_clean = neighbor_role if neighbor_role else None
                        if (neighbor_role_clean is None or neighbor_role_clean == "" or neighbor_role_clean == "VALUE") and is_text_only_neighbor(neighbor_text):
                            # Verificar se não é uma data ou número (esses são sempre VALUE)
                            is_date_neighbor = bool(date_pattern_final2.search(neighbor_text))
                            is_number_neighbor = bool(re.match(r"^\d+$", neighbor_text.strip()))
                            
                            if not is_date_neighbor and not is_number_neighbor:
                                # Classificar como LABEL e criar ligação (FORÇAR mesmo se já é VALUE)
                                roles[neighbor_id] = "LABEL"
                                if neighbor_id not in label_candidates:
                                    label_candidates.append(neighbor_id)
                                label_to_value[neighbor_id] = token_id
                                value_to_label[token_id] = neighbor_id
                                break
    
    # Passagem FINAL 8: Regra recursiva para tokens que terminam com dois pontos
    # REGRA: Se um token termina com ":", ele deve levar a um VALUE.
    # Se tem edges abaixo (south) ou à direita (east), seguir recursivamente:
    # - Se o token conectado também termina com ":", continuar seguindo
    # - Se o token conectado não termina com ":", classificar como VALUE
    # - O token original (que termina com ":") deve ser LABEL
    
    def find_value_recursive(token_id: int, visited: set[int]) -> Optional[int]:
        """Encontra recursivamente um VALUE seguindo edges south/east de tokens que terminam com ':'."""
        if token_id in visited:
            return None  # Evitar loops
        
        visited.add(token_id)
        token_obj = node_by_id.get(token_id)
        if not token_obj:
            return None
        
        token_text = token_obj.get("text", "").strip()
        ends_with_colon = token_text.endswith(":")
        
        # Se não termina com ":", este é o VALUE
        if not ends_with_colon:
            return token_id
        
        # Se termina com ":", seguir pelos edges south e east
        # Prioridade: south primeiro, depois east
        for direction in ["south", "east"]:
            neighbors = adj.get(token_id, {}).get(direction, [])
            for neighbor_id in neighbors:
                result = find_value_recursive(neighbor_id, visited.copy())
                if result is not None:
                    return result
        
        return None
    
    # Para cada token que termina com ":", encontrar seu VALUE recursivamente
    for token in tokens:
        token_id = token["id"]
        token_text = token.get("text", "").strip()
        
        if not token_text.endswith(":"):
            continue
        
        # Encontrar VALUE recursivamente
        value_id = find_value_recursive(token_id, set())
        
        if value_id is not None:
            # Classificar o token original como LABEL
            roles[token_id] = "LABEL"
            if token_id not in label_candidates:
                label_candidates.append(token_id)
            
            # Classificar o VALUE encontrado como VALUE
            # IMPORTANTE: Mesmo que seja HEADER, se foi encontrado pela busca recursiva,
            # deve ser reclassificado como VALUE (a regra de dois pontos tem precedência)
            value_role = roles.get(value_id)
            value_token = node_by_id.get(value_id)
            value_text = value_token.get("text", "").strip() if value_token else ""
            
            # Verificar se o token encontrado realmente não termina com ":"
            # (pode ter sido classificado incorretamente como HEADER)
            if not value_text.endswith(":"):
                roles[value_id] = "VALUE"
                # Criar ligação LABEL -> VALUE
                label_to_value[token_id] = value_id
                value_to_label[value_id] = token_id
                
                # Se estava em label_candidates, remover
                if value_id in label_candidates:
                    label_candidates.remove(value_id)
    
    # Passagem FINAL 9: HEADERs não devem ter conexões verticais para cima (north)
    # REGRA: Um HEADER não deve ter conexões north. HEADERs estão no topo, então não devem ter nada acima.
    # Se um token é HEADER e tem conexões north, reclassificar como LABEL ou VALUE.
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        if current_role != "HEADER":
            continue
        
        # Verificar se tem conexões north
        has_north_connections = False
        north_neighbors = adj.get(token_id, {}).get("north", [])
        
        # Também verificar edges reversos (se alguém tem south para este token)
        for edge in graph.get("edges", []):
            if edge.get("to") == token_id and edge.get("relation") == "south":
                has_north_connections = True
                break
        
        if north_neighbors:
            has_north_connections = True
        
        if has_north_connections:
            # HEADER com conexões north - reclassificar
            token_text = token.get("text", "").strip()
            
            # Verificar se termina com ":" - se sim, é LABEL
            if token_text.endswith(":"):
                roles[token_id] = "LABEL"
                if token_id not in label_candidates:
                    label_candidates.append(token_id)
            else:
                # Verificar se é texto puro ou tem características de VALUE
                import re
                date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
                is_date = bool(date_pattern.search(token_text))
                is_number = bool(re.match(r"^\d+$", token_text.strip()))
                
                numeric_code_pattern = re.compile(
                    r"(?:R\s*\$|US\s*\$|\$|€|£)\s*\d|"
                    r"\d+[.,]\d+|"
                    r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|"
                    r"\d+[.,]\d{2}|"
                    r"\d+[./-]\d+(?:[./-]\d+)?(?!\d{1,2}[/-]\d{1,2})"
                )
                is_numeric_code = bool(numeric_code_pattern.search(token_text)) and not is_date
                
                if is_date or is_number or is_numeric_code:
                    # É VALUE
                    roles[token_id] = "VALUE"
                else:
                    # É texto puro - verificar se tem conexões south/east que são LABELs
                    # Se sim, pode ser LABEL; senão, pode ser VALUE
                    has_label_connections = False
                    south_neighbors = adj.get(token_id, {}).get("south", [])
                    east_neighbors = adj.get(token_id, {}).get("east", [])
                    
                    for neighbor_id in south_neighbors + east_neighbors:
                        neighbor_role = roles.get(neighbor_id)
                        if neighbor_role == "LABEL":
                            has_label_connections = True
                            break
                    
                    if has_label_connections:
                        # Tem LABELs conectados abaixo/direita, então este é VALUE
                        roles[token_id] = "VALUE"
                    else:
                        # Não tem LABELs conectados, pode ser LABEL
                        roles[token_id] = "LABEL"
                        if token_id not in label_candidates:
                            label_candidates.append(token_id)
            
            # Remover da lista de HEADERs se houver
            # (não há lista específica de HEADERs, então só removemos o role)
    
    # Passagem FINAL 10: VALUES não devem ligar para baixo (south) ou direita (east) com LABELs
    # REGRA: VALUES só se conectam com outros VALUES nessas direções, não com LABELs.
    # Se um VALUE está conectado a um LABEL abaixo ou à direita, esse LABEL deve ser reclassificado como VALUE.
    for token in tokens:
        token_id = token["id"]
        current_role = roles.get(token_id)
        
        if current_role != "VALUE":
            continue
        
        # Verificar conexões south e east
        south_neighbors = adj.get(token_id, {}).get("south", [])
        east_neighbors = adj.get(token_id, {}).get("east", [])
        
        # Verificar se algum vizinho south/east é LABEL
        for neighbor_id in south_neighbors + east_neighbors:
            neighbor_role = roles.get(neighbor_id)
            
            if neighbor_role == "LABEL":
                # VALUE conectado a LABEL abaixo/direita - reclassificar LABEL como VALUE
                neighbor_token = node_by_id.get(neighbor_id)
                if neighbor_token:
                    neighbor_text = neighbor_token.get("text", "").strip()
                    
                    # Verificar se o LABEL não é claramente um LABEL (ex: termina com ":")
                    # Se termina com ":", manter como LABEL (pode ser um caso especial)
                    if not neighbor_text.endswith(":"):
                        # Reclassificar como VALUE
                        roles[neighbor_id] = "VALUE"
                        
                        # Remover da lista de label_candidates se estiver lá
                        if neighbor_id in label_candidates:
                            label_candidates.remove(neighbor_id)
                        
                        # Remover ligações LABEL->VALUE se existirem
                        if neighbor_id in label_to_value:
                            old_value_id = label_to_value[neighbor_id]
                            if old_value_id in value_to_label:
                                del value_to_label[old_value_id]
                            del label_to_value[neighbor_id]
    
    return roles


def _compute_style_signatures_for_tokens(tokens: list[dict]) -> dict[int, StyleSignature]:
    """Compute style signatures for tokens directly.
    
    Args:
        tokens: List of token dicts with text, bbox, font_size, bold, italic, color.
        
    Returns:
        Dictionary mapping token_id -> StyleSignature.
    """
    if not tokens:
        return {}
    
    # Cluster colors (simple: same color = same cluster)
    colors = set()
    for token in tokens:
        color = token.get("color")
        colors.add(color)
    color_to_cluster = {color: idx for idx, color in enumerate(sorted(colors, key=lambda x: str(x) if x else ""))}
    
    # Collect font sizes for binning
    font_sizes = [t.get("font_size") for t in tokens if t.get("font_size") is not None]
    font_size_bins = _quantile_bins(font_sizes, n_bins=5) if font_sizes else {}
    
    # Collect caps ratios for binning
    caps_ratios = [_compute_caps_ratio(t.get("text", "")) for t in tokens]
    caps_ratio_bins = _quantile_bins(caps_ratios, n_bins=5)
    
    # Collect letter spacing for binning
    letter_spacings = []
    for token in tokens:
        bbox = token.get("bbox", [0, 0, 0, 0])
        bbox_width = bbox[2] - bbox[0] if len(bbox) >= 4 else 0.0
        spacing = _compute_letter_spacing(token.get("text", ""), bbox_width)
        letter_spacings.append(spacing)
    letter_spacing_bins = _quantile_bins(letter_spacings, n_bins=5)
    
    # Compute signatures
    signatures: dict[int, StyleSignature] = {}
    font_family_id = 0  # Simplified: all tokens get same family ID for now
    
    for token in tokens:
        font_size = token.get("font_size") or 0.0
        font_size_bin = font_size_bins.get(font_size, 0)
        
        is_bold = token.get("bold", False)
        is_italic = token.get("italic", False)
        
        color = token.get("color")
        color_cluster = color_to_cluster.get(color, 0)
        
        text = token.get("text", "")
        caps_ratio = _compute_caps_ratio(text)
        caps_ratio_bin = caps_ratio_bins.get(caps_ratio, 0)
        
        bbox = token.get("bbox", [0, 0, 0, 0])
        bbox_width = bbox[2] - bbox[0] if len(bbox) >= 4 else 0.0
        letter_spacing = _compute_letter_spacing(text, bbox_width)
        letter_spacing_bin = letter_spacing_bins.get(letter_spacing, 0)
        
        signatures[token["id"]] = StyleSignature(
            font_family_id=font_family_id,
            font_size_bin=font_size_bin,
            is_bold=is_bold,
            is_italic=is_italic,
            color_cluster=color_cluster,
            caps_ratio_bin=caps_ratio_bin,
            letter_spacing_bin=letter_spacing_bin,
        )
    
    return signatures


def build_token_graph(tokens, max_distance=None, label: Optional[str] = None):
    """Constrói grafo de tokens com edges ortogonais.
    
    Args:
        tokens: Lista de tokens com bbox (dicts ou objetos Token).
        max_distance: Não usado (mantido para compatibilidade).
        label: Label do documento (opcional, para memória).
        
    Returns:
        dict com:
        - nodes: lista de nós enriquecidos
        - edges: lista de edges {from: int, to: int, relation: str}
    """
    # Converter tokens para objetos Token se necessário
    from src.graph_builder import Token, GraphBuilder, RoleClassifier
    
    token_objects = []
    for token_data in tokens:
        if isinstance(token_data, Token):
            token_objects.append(token_data)
        else:
            # Converter dict para Token
            token_objects.append(Token.from_dict(token_data))
    
    # Construir grafo usando GraphBuilder
    builder = GraphBuilder()
    graph = builder.build(token_objects)
    
    # Classificar roles usando RoleClassifier
    classifier = RoleClassifier()
    roles, tables = classifier.classify(token_objects, graph, label=label)
    
    # Calcular style signatures
    style_signatures = _compute_style_signatures_for_tokens(tokens)
    
    # Calcular line_index (ordem Y, de cima para baixo)
    tokens_with_y = [(t, t.bbox.y0 if isinstance(t, Token) else t["bbox"][1]) for t in token_objects]
    tokens_with_y.sort(key=lambda x: x[1])
    line_index_map = {t[0].id: idx for idx, t in enumerate(tokens_with_y)}
    
    # Adicionar campos aos nós (enriquecer)
    enriched_nodes = []
    for token in token_objects:
        # Converter Token para dict
        node = token.to_dict()
        
        # Adicionar style_signature (serializado como dict)
        sig = style_signatures.get(token.id)
        if sig:
            node["style_signature"] = {
                "font_family_id": sig.font_family_id,
                "font_size_bin": sig.font_size_bin,
                "is_bold": sig.is_bold,
                "is_italic": sig.is_italic,
                "color_cluster": sig.color_cluster,
                "caps_ratio_bin": sig.caps_ratio_bin,
                "letter_spacing_bin": sig.letter_spacing_bin,
            }
        else:
            node["style_signature"] = None
        
        # Adicionar role (já foi aplicado ao token, mas garantir no dict)
        node["role"] = roles.get(token.id) or token.role
        
        # Adicionar line_index
        node["line_index"] = line_index_map.get(token.id, 0)
        
        # Adicionar component_id (inicialmente = token_id, será calculado depois)
        node["component_id"] = token.id
        
        enriched_nodes.append(node)
    
    # Converter edges para dicts
    edges_dict = [edge.to_dict() for edge in graph.edges]
    
    # Converter tabelas para dicts
    tables_dict = []
    for table in tables:
        tables_dict.append({
            "cells": [
                {
                    "token_id": cell.token_id,
                    "row": cell.row,
                    "col": cell.col
                }
                for cell in table.cells
            ],
            "rows": table.rows,
            "cols": table.cols,
            "orientation": table.orientation.value,
            "bbox": table.bbox.to_list()
        })
    
    return {
        "nodes": enriched_nodes,
        "edges": edges_dict,
        "tables": tables_dict
    }


def main():
    """Gera grafo de tokens e visualização HTML."""
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "data" / "samples" / "oab_1.pdf"
    
    print("="*80)
    print("CONSTRUINDO GRAFO DE TOKENS")
    print("="*80)
    
    # Extrair tokens
    print("\nExtraindo tokens do PDF...")
    tokens = extract_tokens_with_coords(str(pdf_path))
    print(f"Total de tokens extraídos: {len(tokens)}")
    
    # Construir grafo
    print("\nConstruindo grafo...")
    graph = build_token_graph(tokens)
    print(f"Total de nós: {len(graph['nodes'])}")
    print(f"Total de edges: {len(graph['edges'])}")
    
    # Mostrar alguns exemplos
    print("\nPrimeiros 10 tokens:")
    for token in graph['nodes'][:10]:
        print(f"  Token {token['id']}: '{token['text'][:30]}' bbox={token['bbox']}")
    
    print("\nPrimeiros 10 edges:")
    for edge in graph['edges'][:10]:
        from_token = next(t for t in graph['nodes'] if t['id'] == edge['from'])
        to_token = next(t for t in graph['nodes'] if t['id'] == edge['to'])
        print(f"  {edge['from']} ('{from_token['text'][:20]}') --[{edge['relation']}]--> {edge['to']} ('{to_token['text'][:20]}')")
    
    # Salvar JSON
    output_json = project_root / "token_graph.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print(f"\nGrafo salvo em: {output_json}")
    
    # Converter PDF para imagem base64
    print("\nConvertendo PDF para imagem...")
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    import base64
    pdf_img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    pdf_width = pix.width
    pdf_height = pix.height
    doc.close()
    
    # Criar HTML
    print("\nCriando visualização HTML...")
    create_token_graph_html(graph, pdf_img_base64, pdf_width, pdf_height, project_root / "token_graph_overlay.html")
    print("Visualização HTML criada!")


def create_token_graph_html(graph, pdf_img_base64, pdf_width, pdf_height, output_path):
    """Cria HTML com visualização do grafo de tokens."""
    
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
        .controls input[type="range"] {{
            width: 200px;
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
            overflow: visible;
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
            margin: 5px 0;
            padding: 5px;
            background: white;
            border-left: 3px solid #4CAF50;
            border-radius: 3px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Grafo de Tokens - oab_1.pdf</h1>
        
        <div class="controls">
            <label>Opacidade:</label>
            <input type="range" id="opacitySlider" min="0" max="1" step="0.1" value="0.8" 
                   oninput="updateOpacity(this.value)">
            <span id="opacityValue">80%</span>
            
            <label style="margin-left: 30px;">Mostrar/Ocultar:</label>
            <input type="checkbox" id="toggleGraph" checked 
                   onchange="toggleGraph(this.checked)">
        </div>
        
        <div class="overlay-container" id="overlayContainer">
            <img src="data:image/png;base64,{pdf_img_base64}" 
                 alt="PDF" class="pdf-image" id="pdfImage">
            <div id="svgOverlay" class="svg-overlay">
                <svg xmlns="http://www.w3.org/2000/svg" id="overlaySvg"></svg>
            </div>
        </div>
        
        <div class="token-info">
            <h3>Estatísticas do Grafo</h3>
            <p>Total de tokens (nós): {len(graph['nodes'])}</p>
            <p>Total de edges: {len(graph['edges'])}</p>
            <p><strong>Legenda:</strong></p>
            <ul>
                <li><span style="color: #ff0000;">■</span> Retângulos vermelhos = Tokens (nós)</li>
                <li><span style="color: #0066ff;">━</span> Linhas azuis horizontais = Edges East/West</li>
                <li><span style="color: #0066ff;">┃</span> Linhas azuis verticais = Edges North/South</li>
            </ul>
            <h4>Tokens (primeiros 15):</h4>
            <div style="max-height: 300px; overflow-y: auto;">"""
    
    # Adicionar lista de tokens
    for i, node in enumerate(graph['nodes'][:15]):
        html_content += f"""
                <div class="token-item">
                    <strong>#{node['id']}</strong>: {json.dumps(node['text'][:50])}<br>
                    <small>BBox: [{node['bbox'][0]:.4f}, {node['bbox'][1]:.4f}, {node['bbox'][2]:.4f}, {node['bbox'][3]:.4f}]</small>
                </div>"""
    
    html_content += """
            </div>
        </div>
    </div>
    
    <script>
        const graphData = {json.dumps(graph)};
        const pdfWidth = {pdf_width};
        const pdfHeight = {pdf_height};
        
        function renderTokenGraph() {{
            const svg = document.getElementById('overlaySvg');
            const img = document.getElementById('pdfImage');
            
            img.onload = function() {{
                const imgWidth = img.offsetWidth;
                const imgHeight = img.offsetHeight;
                
                svg.setAttribute('viewBox', `0 0 ${{imgWidth}} ${{imgHeight}}`);
                svg.setAttribute('width', '100%');
                svg.setAttribute('height', '100%');
                svg.setAttribute('preserveAspectRatio', 'none');
                
                svg.innerHTML = '';
                
                // Criar grupos
                const edgesHorizontalGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                edgesHorizontalGroup.id = 'edgesHorizontal';
                edgesHorizontalGroup.setAttribute('stroke', '#0066ff');
                edgesHorizontalGroup.setAttribute('stroke-width', '2');
                edgesHorizontalGroup.setAttribute('stroke-opacity', '0.7');
                
                const edgesVerticalGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                edgesVerticalGroup.id = 'edgesVertical';
                edgesVerticalGroup.setAttribute('stroke', '#0066ff');
                edgesVerticalGroup.setAttribute('stroke-width', '2');
                edgesVerticalGroup.setAttribute('stroke-opacity', '0.7');
                
                const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                nodesGroup.id = 'nodes';
                
                // Desenhar edges
                graphData.edges.forEach(function(edge) {{
                    const fromNode = graphData.nodes.find(n => n.id === edge.from);
                    const toNode = graphData.nodes.find(n => n.id === edge.to);
                    
                    if (!fromNode || !toNode) return;
                    
                    const fromBbox = fromNode.bbox;
                    const toBbox = toNode.bbox;
                    
                    // Calcular pontos de conexão baseado na relação
                    let x1, y1, x2, y2;
                    
                    let line;
                    
                    if (edge.relation === 'east') {{
                        // Linha HORIZONTAL: da direita do from para esquerda do to
                        x1 = fromBbox[2] * imgWidth;
                        y1 = (fromBbox[1] + fromBbox[3]) / 2 * imgHeight;
                        x2 = toBbox[0] * imgWidth;
                        y2 = y1; // Mesma altura (linha horizontal)
                        
                        line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        line.setAttribute('x1', x1.toString());
                        line.setAttribute('y1', y1.toString());
                        line.setAttribute('x2', x2.toString());
                        line.setAttribute('y2', y2.toString());
                        edgesHorizontalGroup.appendChild(line);
                    }} else if (edge.relation === 'south') {{
                        // Linha VERTICAL: de baixo do from para cima do to
                        x1 = (fromBbox[0] + fromBbox[2]) / 2 * imgWidth;
                        y1 = fromBbox[3] * imgHeight;
                        x2 = x1; // Mesma posição X (linha vertical)
                        y2 = toBbox[1] * imgHeight;
                        
                        line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        line.setAttribute('x1', x1.toString());
                        line.setAttribute('y1', y1.toString());
                        line.setAttribute('x2', x2.toString());
                        line.setAttribute('y2', y2.toString());
                        edgesVerticalGroup.appendChild(line);
                    }} else {{
                        // Fallback: linha ortogonal (horizontal ou vertical baseado na relação)
                        const fromCenterX = (fromBbox[0] + fromBbox[2]) / 2;
                        const fromCenterY = (fromBbox[1] + fromBbox[3]) / 2;
                        const toCenterX = (toBbox[0] + toBbox[2]) / 2;
                        const toCenterY = (toBbox[1] + toBbox[3]) / 2;
                        
                        // Decidir se é mais horizontal ou vertical
                        const dx = Math.abs(toCenterX - fromCenterX);
                        const dy = Math.abs(toCenterY - fromCenterY);
                        
                        line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        
                        if (dx > dy) {{
                            // Mais horizontal
                            x1 = fromBbox[2] * imgWidth;
                            y1 = (fromBbox[1] + fromBbox[3]) / 2 * imgHeight;
                            x2 = toBbox[0] * imgWidth;
                            y2 = y1;
                            edgesHorizontalGroup.appendChild(line);
                        }} else {{
                            // Mais vertical
                            x1 = (fromBbox[0] + fromBbox[2]) / 2 * imgWidth;
                            y1 = fromBbox[3] * imgHeight;
                            x2 = x1;
                            y2 = toBbox[1] * imgHeight;
                            edgesVerticalGroup.appendChild(line);
                        }}
                        
                        line.setAttribute('x1', x1.toString());
                        line.setAttribute('y1', y1.toString());
                        line.setAttribute('x2', x2.toString());
                        line.setAttribute('y2', y2.toString());
                    }}
                }});
                
                // Desenhar nós (retângulos)
                graphData.nodes.forEach(function(node) {{
                    const bbox = node.bbox;
                    const x0 = bbox[0] * imgWidth;
                    const y0 = bbox[1] * imgHeight;
                    const x1 = bbox[2] * imgWidth;
                    const y1 = bbox[3] * imgHeight;
                    
                    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    rect.setAttribute('x', x0.toString());
                    rect.setAttribute('y', y0.toString());
                    rect.setAttribute('width', (x1 - x0).toString());
                    rect.setAttribute('height', (y1 - y0).toString());
                    rect.setAttribute('fill', 'rgba(255, 0, 0, 0.1)');
                    rect.setAttribute('stroke', '#ff0000');
                    rect.setAttribute('stroke-width', '2');
                    rect.setAttribute('data-token-id', node.id.toString());
                    rect.setAttribute('data-token-text', node.text);
                    
                    // Adicionar ID do token (pequeno, acima do retângulo)
                    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    text.setAttribute('x', ((bbox[0] + bbox[2]) / 2 * imgWidth).toString());
                    text.setAttribute('y', (bbox[1] * imgHeight - 5).toString());
                    text.setAttribute('font-size', '12');
                    text.setAttribute('fill', '#ff0000');
                    text.setAttribute('text-anchor', 'middle');
                    text.setAttribute('font-weight', 'bold');
                    text.setAttribute('style', 'pointer-events: none;');
                    text.textContent = '#' + node.id.toString();
                    
                    nodesGroup.appendChild(rect);
                    nodesGroup.appendChild(text);
                }});
                
                svg.appendChild(edgesVerticalGroup);
                svg.appendChild(edgesHorizontalGroup);
                svg.appendChild(nodesGroup);
            }};
            
            if (img.complete && img.naturalWidth > 0) {{
                img.onload();
            }}
        }}
        
        function updateOpacity(value) {{
            document.getElementById('opacityValue').textContent = Math.round(value * 100) + '%';
            document.getElementById('svgOverlay').style.opacity = value;
        }}
        
        function toggleGraph(show) {{
            document.getElementById('svgOverlay').style.display = show ? 'block' : 'none';
        }}
        
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
    
    print(f"HTML criado em: {output_path}")


if __name__ == "__main__":
    main()

