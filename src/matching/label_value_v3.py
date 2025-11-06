"""Emparelhamento LABEL→VALUE usando grafo ortogonal (v3.0)."""

from typing import Dict, List, Any, Optional, Set
import re

from ..validation.patterns import type_gate_generic


def _build_simple_lexicon(field_name: str, field_description: str) -> Set[str]:
    """Constrói léxico simples para um campo.
    
    Inclui:
    - Variações da chave (nº, no, num, com/sem :)
    - Tokens curtos da descrição (não stopwords)
    
    Args:
        field_name: Nome do campo.
        field_description: Descrição do campo.
        
    Returns:
        Set de strings para matching exato.
    """
    lexicon: Set[str] = set()
    
    # Adicionar variações da chave
    field_lower = field_name.lower()
    lexicon.add(field_lower)
    lexicon.add(field_lower.replace("_", " "))
    
    # Variações com/sem separadores
    for sep in [":", "—", "–", "."]:
        lexicon.add(field_lower + sep)
        lexicon.add(field_lower.replace("_", " ") + sep)
    
    # Variações numéricas
    if "numero" in field_lower or "num" in field_lower:
        lexicon.add("nº")
        lexicon.add("no")
        lexicon.add("num")
    
    # Tokens da descrição (palavras com 3+ letras, não stopwords)
    stopwords = {"do", "da", "de", "em", "no", "na", "para", "com", "por", "que", "o", "a", "os", "as"}
    desc_tokens = re.findall(r"\b\w{3,}\b", field_description.lower())
    for token in desc_tokens:
        if token not in stopwords:
            lexicon.add(token)
    
    return lexicon


def _find_label_candidates(
    token_graph: Dict[str, Any],
    lexicon: Set[str]
) -> List[Dict[str, Any]]:
    """Encontra LABELs candidatos que contêm tokens do léxico.
    
    Args:
        token_graph: Grafo de tokens com nodes e edges.
        lexicon: Léxico de palavras-chave.
        
    Returns:
        Lista de nós candidatos a LABEL.
    """
    candidates = []
    nodes = token_graph.get("nodes", [])
    
    for node in nodes:
        role = node.get("role")
        text = node.get("text", "").lower()
        
        # Se já é LABEL, adicionar
        if role == "LABEL":
            candidates.append(node)
            continue
        
        # Verificar se contém token do léxico
        text_tokens = set(re.findall(r"\b\w+\b", text))
        if text_tokens & lexicon:  # Intersecção não vazia
            candidates.append(node)
    
    return candidates


def _search_orthogonal_values(
    token_graph: Dict[str, Any],
    label_node: Dict[str, Any],
    field_type: str,
    max_hops: int = 3
) -> List[Dict[str, Any]]:
    """Busca VALUES ortogonalmente a partir de um LABEL.
    
    Estratégia:
    1. Buscar nas direções → (east) e ↓ (south)
    2. Limitar a max_hops saltos
    3. Filtrar por type-gate
    
    Args:
        token_graph: Grafo de tokens.
        label_node: Nó LABEL de origem.
        field_type: Tipo do campo para type-gate.
        max_hops: Número máximo de saltos.
        
    Returns:
        Lista de nós VALUE candidatos.
    """
    nodes_by_id = {node["id"]: node for node in token_graph.get("nodes", [])}
    edges = token_graph.get("edges", [])
    
    # Criar lookup de edges por origem
    edges_from: Dict[int, List[Dict[str, Any]]] = {}
    for edge in edges:
        from_id = edge.get("from")
        if from_id not in edges_from:
            edges_from[from_id] = []
        edges_from[from_id].append(edge)
    
    # BFS restrita nas direções → e ↓
    visited = set()
    queue = [(label_node["id"], 0)]  # (node_id, hops)
    candidates = []
    
    while queue:
        current_id, hops = queue.pop(0)
        
        if current_id in visited or hops > max_hops:
            continue
        
        visited.add(current_id)
        current_node = nodes_by_id.get(current_id)
        
        if not current_node:
            continue
        
        # Se não é o label original, verificar se é VALUE
        if current_id != label_node["id"]:
            text = current_node.get("text", "").strip()
            role = current_node.get("role")
            
            # Se já é VALUE ou passa type-gate, adicionar como candidato
            if role == "VALUE" or type_gate_generic(text, field_type):
                candidates.append({
                    "node": current_node,
                    "hops": hops,
                    "direction": "east" if hops == 1 else "south"  # Simplificado
                })
        
        # Adicionar vizinhos nas direções → e ↓
        for edge in edges_from.get(current_id, []):
            relation = edge.get("relation")
            to_id = edge.get("to")
            
            if relation in ("east", "south") and to_id not in visited:
                queue.append((to_id, hops + 1))
    
    return candidates


def find_label_value_pairs_v3(
    token_graph: Dict[str, Any],
    field_name: str,
    field_description: str,
    field_type: str
) -> Optional[Dict[str, Any]]:
    """Encontra par LABEL→VALUE para um campo.
    
    Estratégia simplificada:
    1. Encontrar LABELs que contenham palavras-chave do campo
    2. Buscar VALUES ortogonalmente (→, ↓) a partir do LABEL
    3. Filtrar por type-gate básico
    4. Retornar melhor candidato
    
    Args:
        token_graph: Grafo de tokens com nodes e edges.
        field_name: Nome do campo.
        field_description: Descrição do campo.
        field_type: Tipo do campo.
        
    Returns:
        Dict com 'label_node', 'value_node', 'hops', 'direction', ou None se não encontrar.
    """
    if not token_graph or not token_graph.get("nodes"):
        return None
    
    # Construir léxico
    lexicon = _build_simple_lexicon(field_name, field_description)
    
    # Encontrar LABELs candidatos
    label_candidates = _find_label_candidates(token_graph, lexicon)
    
    if not label_candidates:
        return None
    
    # Para cada LABEL, buscar VALUES
    best_candidate = None
    best_hops = float("inf")
    
    for label_node in label_candidates:
        value_candidates = _search_orthogonal_values(
            token_graph,
            label_node,
            field_type,
            max_hops=3
        )
        
        if value_candidates:
            # Escolher o candidato com menos saltos
            for cand in value_candidates:
                hops = cand.get("hops", 999)
                if hops < best_hops:
                    best_hops = hops
                    best_candidate = {
                        "label_node": label_node,
                        "value_node": cand["node"],
                        "hops": hops,
                        "direction": cand.get("direction", "unknown")
                    }
    
    return best_candidate


