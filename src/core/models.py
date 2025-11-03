from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Tuple, Dict, List, Optional


__all__ = [
    "Document",
    "SchemaField",
    "ExtractionSchema",
    "InlineSpan",
    "Block",
    "ReadingNode",
    "SpatialEdge",
    "TableStructure",
    "LayoutGraph",
    "FieldCandidate",
    "FieldResult",
]


@dataclass(frozen=True)
class Document:
    """Represents a one-page PDF input.

    Invariants:
    - Exactly one of `path` or `data` must be provided (not both None).
    - The document is one page (per challenge constraints).
    """

    id: str
    label: str
    path: Optional[str]
    data: Optional[bytes]
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaField:
    """Describes one requested output field from the schema.

    Invariants:
    - `name` must be unique inside an ExtractionSchema.
    - `type` must correspond to a known validator when validation runs (future work).
    """

    name: str
    description: str
    type: str = "text"  # allowed MVP0: "text" | "id_simple" | "date" | "money"
    regex: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionSchema:
    """Schema requested by the caller.

    Invariants:
    - All field names are unique.
    - `label` echoes the caller-provided label.
    """

    label: str
    fields: List[SchemaField]


@dataclass(frozen=True)
class InlineSpan:
    """Optional inline styling span within a block.

    Used later to drop bold label tokens while keeping values intact.
    """

    text: str
    bold: bool = False
    font_size: Optional[float] = None


@dataclass(frozen=True)
class Block:
    """Atomic text region with geometry.

    Invariants:
    - Coordinates are normalized to [0, 1] in page space.
    - 0 ≤ x0 < x1 ≤ 1 and 0 ≤ y0 < y1 ≤ 1.
    """

    id: int
    text: str
    bbox: Tuple[float, float, float, float]
    page: int = 0
    font_size: Optional[float] = None
    bold: bool = False
    rotation: int = 0
    spans: List[InlineSpan] = field(default_factory=list)


ReadingNodeType = Literal["page", "line"]


@dataclass(frozen=True)
class ReadingNode:
    """Minimal reading order node (MVP0: page → lines).

    Invariants:
    - Exactly one node of type "page" with parent=None.
    - All "line" nodes have parent set to that page node id.
    """

    id: int
    type: ReadingNodeType
    parent: Optional[int]
    children: List[int] = field(default_factory=list)
    ref_block_ids: List[int] = field(default_factory=list)


SpatialEdgeType = Literal["same_line_right_of", "first_below_same_column"]


@dataclass(frozen=True)
class SpatialEdge:
    """Directed relation from a label block (src) to a value block (dst).

    Invariants:
    - src_id != dst_id
    - IDs refer to valid Block.id in the same LayoutGraph.
    """

    src_id: int
    dst_id: int
    type: SpatialEdgeType
    weights: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TableStructure:
    """Placeholder table structure for future use (not used in MVP0)."""

    table_id: int
    rows: int
    cols: int
    cells: Dict[Tuple[int, int], int] = field(default_factory=dict)


@dataclass(frozen=True)
class LayoutGraph:
    """Aggregates geometry, reading order, and spatial relations.

    Invariants:
    - All references (Block.id, ReadingNode.id, SpatialEdge src/dst) are consistent.
    """

    blocks: List[Block]
    reading_nodes: List[ReadingNode]
    spatial_edges: List[SpatialEdge]
    tables: List[TableStructure] = field(default_factory=list)


@dataclass(frozen=True)
class FieldCandidate:
    """Candidate value for a field, linked to a source label block."""

    field: SchemaField
    node_id: int
    source_label_block_id: int
    relation: SpatialEdgeType
    scores: Dict[str, float] = field(default_factory=dict)
    local_context: Optional[str] = None


@dataclass(frozen=True)
class FieldResult:
    """Final result for one field.

    Invariants:
    - If value is None, set source="none" and confidence=0.0, with a "no_evidence" trace.
    """

    field: str
    value: Optional[str]
    confidence: float
    source: Literal["heuristic", "table", "llm", "none"]
    trace: Dict[str, object] = field(default_factory=dict)


