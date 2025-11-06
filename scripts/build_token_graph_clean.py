"""Script para construir grafo por tokens (palavras/frases) com coordenadas."""

import sys
import json
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph_builder import TokenExtractor, Token, GraphBuilder, RoleClassifier


def extract_tokens_from_page(pdf_path: str):
    """Extrai tokens da página do PDF.
    
    Returns:
        Lista de tokens como dicionários: [{"id": int, "text": str, "bbox": [x0,y0,x1,y1], ...}]
    """
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


class StyleSignature:
    """Assinatura de estilo de um token."""
    def __init__(self, font_family_id, font_size_bin, is_bold, is_italic, 
                 color_cluster, caps_ratio_bin, letter_spacing_bin):
        self.font_family_id = font_family_id
        self.font_size_bin = font_size_bin
        self.is_bold = is_bold
        self.is_italic = is_italic
        self.color_cluster = color_cluster
        self.caps_ratio_bin = caps_ratio_bin
        self.letter_spacing_bin = letter_spacing_bin


def _compute_style_signatures_for_tokens(tokens: list[dict]) -> dict[int, StyleSignature]:
    """Calcula style signatures para tokens."""
    # Coletar dados para quantização
    font_sizes = []
    font_families = set()
    colors = set()
    caps_ratios = []
    letter_spacings = []
    
    for token in tokens:
        font_size = token.get("font_size")
        if font_size and font_size > 0:
            font_sizes.append(font_size)
        
        font_family = token.get("font_family", "")
        if font_family:
            font_families.add(font_family)
        
        color = token.get("color")
        if color:
            colors.add(color)
        
        text = token.get("text", "")
        bbox = token.get("bbox", [])
        bbox_width = bbox[2] - bbox[0] if len(bbox) >= 4 else 0.0
        
        caps_ratio = _compute_caps_ratio(text)
        caps_ratios.append(caps_ratio)
        
        letter_spacing = _compute_letter_spacing(text, bbox_width)
        letter_spacings.append(letter_spacing)
    
    # Criar bins
    font_size_bins = _quantile_bins(font_sizes, 5)
    caps_ratio_bins = _quantile_bins(caps_ratios, 5)
    letter_spacing_bins = _quantile_bins(letter_spacings, 5)
    
    # Mapear font families e colors para IDs
    font_family_to_id = {fam: idx for idx, fam in enumerate(sorted(font_families))}
    color_to_cluster = {col: idx for idx, col in enumerate(sorted(colors))}
    
    # Calcular signatures
    signatures = {}
    for token in tokens:
        token_id = token.get("id")
        if token_id is None:
            continue
        
        font_family = token.get("font_family", "")
        font_family_id = font_family_to_id.get(font_family, 0)
        
        font_size = token.get("font_size", 0) or 0
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
        
        signatures[token_id] = StyleSignature(
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
        - tables: lista de tabelas detectadas
    """
    # Converter tokens para objetos Token se necessário
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

