"""Gerenciamento de adjacências bidirecionais do grafo."""

from typing import Dict, List, Optional
from src.graph_builder.models import Edge, Graph


class AdjacencyMatrix:
    """Matriz de adjacência bidirecional para o grafo."""
    
    def __init__(self, graph: Optional[Graph] = None):
        """Inicializa a matriz de adjacência.
        
        Args:
            graph: Grafo opcional para construir adjacências inicialmente.
        """
        # adj[token_id][direction] = [lista de token_ids]
        self.adj: Dict[int, Dict[str, List[int]]] = {}
        self._reverse_relation = {
            "east": "west",
            "west": "east",
            "south": "north",
            "north": "south"
        }
        
        if graph:
            self._build_from_graph(graph)
    
    def _build_from_graph(self, graph: Graph) -> None:
        """Constrói adjacências a partir do grafo."""
        # Inicializar todos os nós
        for node in graph.nodes:
            if node.id not in self.adj:
                self.adj[node.id] = {
                    "east": [],
                    "south": [],
                    "north": [],
                    "west": []
                }
        
        # Adicionar edges
        for edge in graph.edges:
            self.add_edge(edge)
    
    def add_edge(self, edge: Edge) -> None:
        """Adiciona uma edge à matriz de adjacência (bidirecional)."""
        from_id = edge.from_id
        to_id = edge.to_id
        relation = edge.relation
        
        # Garantir que os nós existem
        if from_id not in self.adj:
            self.adj[from_id] = {"east": [], "south": [], "north": [], "west": []}
        if to_id not in self.adj:
            self.adj[to_id] = {"east": [], "south": [], "north": [], "west": []}
        
        # Adicionar relação direta
        if relation in self.adj[from_id]:
            if to_id not in self.adj[from_id][relation]:
                self.adj[from_id][relation].append(to_id)
        
        # Adicionar relação reversa
        reverse_relation = self._reverse_relation.get(relation)
        if reverse_relation and reverse_relation in self.adj[to_id]:
            if from_id not in self.adj[to_id][reverse_relation]:
                self.adj[to_id][reverse_relation].append(from_id)
    
    def get_neighbors(self, token_id: int, direction: str) -> List[int]:
        """Obtém vizinhos em uma direção específica.
        
        Args:
            token_id: ID do token.
            direction: Direção ("east", "west", "north", "south").
        
        Returns:
            Lista de IDs de tokens vizinhos.
        """
        return self.adj.get(token_id, {}).get(direction, [])
    
    def has_connection(self, from_id: int, to_id: int, relation: str) -> bool:
        """Verifica se existe conexão específica.
        
        Args:
            from_id: ID do token origem.
            to_id: ID do token destino.
            relation: Relação ("east", "west", "north", "south").
        
        Returns:
            True se existe a conexão.
        """
        return to_id in self.get_neighbors(from_id, relation)
    
    def get_all_neighbors(self, token_id: int) -> List[int]:
        """Obtém todos os vizinhos em todas as direções.
        
        Args:
            token_id: ID do token.
        
        Returns:
            Lista de IDs de tokens vizinhos (sem duplicatas).
        """
        neighbors = set()
        for direction in ["east", "west", "north", "south"]:
            neighbors.update(self.get_neighbors(token_id, direction))
        return list(neighbors)
    
    def remove_edge(self, from_id: int, to_id: int, relation: str) -> None:
        """Remove uma edge da matriz de adjacência (bidirecional).
        
        Args:
            from_id: ID do token origem.
            to_id: ID do token destino.
            relation: Relação ("east", "west", "north", "south").
        """
        # Remover relação direta
        if from_id in self.adj and relation in self.adj[from_id]:
            if to_id in self.adj[from_id][relation]:
                self.adj[from_id][relation].remove(to_id)
        
        # Remover relação reversa
        reverse_relation = self._reverse_relation.get(relation)
        if reverse_relation and to_id in self.adj and reverse_relation in self.adj[to_id]:
            if from_id in self.adj[to_id][reverse_relation]:
                self.adj[to_id][reverse_relation].remove(from_id)
    
    def are_neighbors(self, token_id1: int, token_id2: int) -> bool:
        """Verifica se dois tokens são vizinhos em qualquer direção.
        
        Args:
            token_id1: ID do primeiro token.
            token_id2: ID do segundo token.
        
        Returns:
            True se são vizinhos, False caso contrário.
        """
        if token_id1 not in self.adj:
            return False
        
        for direction in ["east", "west", "north", "south"]:
            if token_id2 in self.adj[token_id1].get(direction, []):
                return True
        
        return False
    
    def clear(self) -> None:
        """Limpa a matriz de adjacência."""
        self.adj.clear()

