"""Modelos base para construção do grafo de tokens."""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re


@dataclass
class BBox:
    """Bounding box normalizado (0-1)."""
    x0: float
    y0: float
    x1: float
    y1: float
    
    def width(self) -> float:
        """Largura do bbox."""
        return self.x1 - self.x0
    
    def height(self) -> float:
        """Altura do bbox."""
        return self.y1 - self.y0
    
    def center_x(self) -> float:
        """Centro X do bbox."""
        return (self.x0 + self.x1) / 2.0
    
    def center_y(self) -> float:
        """Centro Y do bbox."""
        return (self.y1 + self.y0) / 2.0
    
    def to_list(self) -> List[float]:
        """Converte para lista [x0, y0, x1, y1]."""
        return [self.x0, self.y0, self.x1, self.y1]
    
    @classmethod
    def from_list(cls, bbox_list: List[float]) -> 'BBox':
        """Cria BBox a partir de lista [x0, y0, x1, y1]."""
        if len(bbox_list) < 4:
            return cls(0.0, 0.0, 0.0, 0.0)
        return cls(bbox_list[0], bbox_list[1], bbox_list[2], bbox_list[3])


@dataclass
class Token:
    """Token (palavra/frase) extraído do PDF."""
    id: int
    text: str
    bbox: BBox
    font_size: Optional[float] = None
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None
    block_id: Optional[int] = None
    role: Optional[str] = None  # HEADER, LABEL, VALUE, None
    separated_pair: bool = False  # True se foi separado de um único span (ex: "Label: Value")
    
    # Padrões regex (compilados uma vez)
    _date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
    _numeric_code_pattern = re.compile(
        r"(?:R\s*\$|US\s*\$|\$|€|£)\s*\d|"
        r"\d+[.,]\d+|"
        r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|"
        r"\d+[.,]\d{2}|"
        r"\d+[./-]\d+(?:[./-]\d+)?(?!\d{1,2}[/-]\d{1,2})"
    )
    
    def ends_with_colon(self) -> bool:
        """Verifica se o texto termina com dois pontos."""
        return self.text.strip().endswith(":")
    
    def has_colon_in_middle(self) -> bool:
        """Verifica se tem ':' no meio do texto."""
        text = self.text.strip()
        colon_pos = text.find(":")
        return colon_pos > 0 and colon_pos < len(text) - 1
    
    def is_date(self) -> bool:
        """Verifica se o texto é uma data."""
        return bool(self._date_pattern.search(self.text.strip()))
    
    def is_numeric_code(self) -> bool:
        """Verifica se o texto é código numérico (não data)."""
        text_clean = self.text.strip()
        if not text_clean:
            return False
        if self.is_date():
            return False
        return bool(self._numeric_code_pattern.search(text_clean))
    
    def is_number(self) -> bool:
        """Verifica se o texto é apenas número."""
        return bool(re.match(r"^\d+$", self.text.strip()))
    
    def is_text_only(self) -> bool:
        """Verifica se o texto é apenas texto (não número, data ou código numérico)."""
        text_clean = self.text.strip()
        if not text_clean:
            return False
        if self.is_number():
            return False
        if self.is_date():
            return False
        if self.is_numeric_code():
            return False
        # Se tem pelo menos uma letra, é texto
        return bool(re.search(r"[A-Za-zÀ-ÿ]", text_clean))
    
    def ends_with_separator(self, separators: List[str] = None) -> bool:
        """Verifica se termina com separador."""
        if separators is None:
            separators = [":", "—", "–", ".", "•", "/"]
        text_stripped = self.text.rstrip()
        return any(text_stripped.endswith(sep) for sep in separators)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (compatibilidade)."""
        result = {
            "id": self.id,
            "text": self.text,
            "bbox": self.bbox.to_list(),
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "color": self.color,
        }
        if self.block_id is not None:
            result["block_id"] = self.block_id
        if self.role is not None:
            result["role"] = self.role
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Token':
        """Cria Token a partir de dicionário."""
        bbox = BBox.from_list(data.get("bbox", [0, 0, 0, 0]))
        return cls(
            id=data["id"],
            text=data.get("text", ""),
            bbox=bbox,
            font_size=data.get("font_size"),
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            color=data.get("color"),
            block_id=data.get("block_id"),
            role=data.get("role")
        )


@dataclass
class Edge:
    """Edge (conexão) entre dois tokens."""
    from_id: int
    to_id: int
    relation: str  # "east", "west", "north", "south"
    
    def reverse(self) -> 'Edge':
        """Retorna edge reverso."""
        reverse_map = {
            "east": "west",
            "west": "east",
            "north": "south",
            "south": "north"
        }
        return Edge(
            from_id=self.to_id,
            to_id=self.from_id,
            relation=reverse_map.get(self.relation, self.relation)
        )
    
    def is_horizontal(self) -> bool:
        """Verifica se é edge horizontal."""
        return self.relation in ("east", "west")
    
    def is_vertical(self) -> bool:
        """Verifica se é edge vertical."""
        return self.relation in ("north", "south")
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (compatibilidade)."""
        return {
            "from": self.from_id,
            "to": self.to_id,
            "relation": self.relation
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Edge':
        """Cria Edge a partir de dicionário."""
        return cls(
            from_id=data["from"],
            to_id=data["to"],
            relation=data.get("relation", "")
        )


class Graph:
    """Grafo de tokens com nodes e edges."""
    
    def __init__(self, nodes: Optional[List[Token]] = None, edges: Optional[List[Edge]] = None):
        self.nodes: List[Token] = nodes or []
        self.edges: List[Edge] = edges or []
        self._node_by_id: Dict[int, Token] = {}
        if nodes:
            for node in nodes:
                self._node_by_id[node.id] = node
    
    def add_node(self, node: Token) -> None:
        """Adiciona um nó ao grafo."""
        if node.id not in self._node_by_id:
            self.nodes.append(node)
            self._node_by_id[node.id] = node
    
    def add_edge(self, edge: Edge) -> None:
        """Adiciona uma edge ao grafo."""
        self.edges.append(edge)
    
    def remove_edge(self, from_id: int, to_id: int, relation: str) -> None:
        """Remove uma edge do grafo.
        
        Args:
            from_id: ID do token origem.
            to_id: ID do token destino.
            relation: Relação ("east", "west", "north", "south").
        """
        self.edges = [
            e for e in self.edges
            if not (e.from_id == from_id and e.to_id == to_id and e.relation == relation)
        ]
    
    def get_node(self, node_id: int) -> Optional[Token]:
        """Obtém um nó por ID."""
        return self._node_by_id.get(node_id)
    
    def get_edges_from(self, node_id: int) -> List[Edge]:
        """Obtém todas as edges que saem de um nó."""
        return [e for e in self.edges if e.from_id == node_id]
    
    def get_edges_to(self, node_id: int) -> List[Edge]:
        """Obtém todas as edges que chegam em um nó."""
        return [e for e in self.edges if e.to_id == node_id]
    
    def get_edges_connected(self, node_id: int) -> List[Edge]:
        """Obtém todas as edges conectadas a um nó (from ou to)."""
        return [e for e in self.edges if e.from_id == node_id or e.to_id == node_id]
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (compatibilidade)."""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Graph':
        """Cria Graph a partir de dicionário."""
        nodes = [Token.from_dict(n) for n in data.get("nodes", [])]
        edges = [Edge.from_dict(e) for e in data.get("edges", [])]
        return cls(nodes=nodes, edges=edges)

