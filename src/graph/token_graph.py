"""Wrapper para usar grafo de tokens no pipeline."""

from typing import Dict, List, Any, Optional
from pathlib import Path
import sys

# Importar funções de build_token_graph
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.build_token_graph import extract_tokens_from_page, build_token_graph


def build_token_graph_for_pipeline(pdf_path: str, label: Optional[str] = None) -> Dict[str, Any]:
    """Constrói grafo de tokens para uso no pipeline.
    
    Args:
        pdf_path: Caminho para o arquivo PDF.
        label: Label do documento para memória de padrões.
    
    Returns:
        Dict com 'nodes' e 'edges', onde cada nó tem:
        - id, text, bbox
        - style_signature, role, font_size, bold, italic, color
        - line_index, component_id
    """
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens, label=label)
    return graph

