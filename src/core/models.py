from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict


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
    "PageContext",
    "Grid",
    "GraphV2",
    "Candidate",
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
    type: str = "text"  # allowed MVP0: "text" | "id_simple" | "date" | "money" | "enum" | "text_multiline" | ...
    regex: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)  # position_hint, enum_options, etc.


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


ReadingNodeType = Literal["page", "column", "section", "paragraph", "line"]


@dataclass(frozen=True)
class ReadingNode:
    """Reading order node with hierarchy support.

    Hierarchy: page → column → section → paragraph → line

    Invariants:
    - Exactly one node of type "page" per page with parent=None.
    - All "line" nodes have parent set to paragraph (or page if no paragraph).
    - Paragraph nodes group consecutive lines in same section/column.
    - Section and column nodes are optional metadata nodes.
    """

    id: int
    type: ReadingNodeType
    parent: Optional[int]
    children: List[int] = field(default_factory=list)
    ref_block_ids: List[int] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)  # bbox, column_id, section_id, paragraph_id, page_index, etc.


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
class TableCell:
    """A cell in a table structure."""

    id: int
    row_id: int
    col_id: int
    bbox: Tuple[float, float, float, float]
    block_ids: List[int] = field(default_factory=list)  # blocks contained in this cell
    text: str = ""  # joined text from blocks/lines within
    header: bool = False


@dataclass(frozen=True)
class TableRow:
    """A row in a table structure."""

    id: int
    bbox: Tuple[float, float, float, float]
    cell_ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class TableStructure:
    """Table structure (KV-list or grid table)."""

    id: int
    type: Literal["kv", "grid"]
    bbox: Tuple[float, float, float, float]
    row_ids: List[int] = field(default_factory=list)
    col_count: int = 0
    cells: List[TableCell] = field(default_factory=list)
    rows: List[TableRow] = field(default_factory=list)


@dataclass(frozen=True)
class LayoutGraph:
    """Aggregates geometry, reading order, and spatial relations for a single page.

    Invariants:
    - All references (Block.id, ReadingNode.id, SpatialEdge src/dst) are consistent.
    - column_id_by_block, section_id_by_block, paragraph_id_by_block are optional metadata (attached via setattr).
    - page_index indicates which page this graph represents.
    """

    blocks: List[Block]
    reading_nodes: List[ReadingNode]
    spatial_edges: List[SpatialEdge]
    tables: List[TableStructure] = field(default_factory=list)
    page_index: int = 0
    # Optional metadata (attached via setattr to avoid breaking frozen dataclass)
    # column_id_by_block: Dict[int, int] = field(default_factory=dict)
    # section_id_by_block: Dict[int, int] = field(default_factory=dict)
    # paragraph_id_by_block: Dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FieldCandidate:
    """Candidate value for a field, linked to a source label block."""

    field: SchemaField
    node_id: int
    source_label_block_id: int
    relation: SpatialEdgeType | Literal["same_table_row", "same_block", "global_enum_scan"]
    scores: Dict[str, float] = field(default_factory=dict)
    local_context: Optional[str] = None


@dataclass(frozen=True)
class FieldResult:
    """Final result for one field.

    Invariants:
    - If value is None, set source="none" and confidence=0.0, with a "no_evidence" trace.
    - page_index indicates which page this result came from (if multi-page).
    """

    field: str
    value: Optional[str]
    confidence: float
    source: Literal["heuristic", "table", "llm", "none"]
    trace: Dict[str, object] = field(default_factory=dict)
    page_index: int = 0  # Page index where this result was found


@dataclass
class PageContext:
    """Context for a single page during processing.

    Holds layout graph (embeddings removed).
    """

    page_index: int
    layout: LayoutGraph
    # Embeddings removed - embedding_index and signals_by_field no longer used


# ============================================================================
# v2 Types: Grid, GraphV2, Candidate
# ============================================================================


class Grid(TypedDict):
    """Virtual grid structure for layout analysis.

    Auto-calibrated grid with spans support.
    """

    row_y: List[float]  # y-centers of virtual rows
    col_x: List[Tuple[float, float]]  # column boundaries as [(x0, x1), ...]
    cell_map: Dict[int, List[Tuple[int, int]]]  # block_id -> [(row_idx, col_idx), ...]
    spans: Dict[int, Tuple[int, int]]  # block_id -> (first_col, last_col)
    thresholds: Dict[str, float]  # δ_line, τ_col_iou, etc.


class GraphV2(TypedDict):
    """V2 graph with directional edges and connected components.

    Provides spatial topology beyond simple Grid.
    """

    adj: Dict[int, Dict[str, List[int]]]  # id -> {'same_line':[...], 'same_col':[...], 'north':[...], 'south':[...], 'east':[...], 'west':[...]}
    component_id: Dict[int, int]  # block_id -> component_id
    style: Dict[int, Tuple[float, bool]]  # block_id -> (font_z, bold)


class Candidate(TypedDict):
    """Candidate value for a field with relation and scoring.

    Used in v2 matcher tournament system.
    """

    block_id: int
    relation: str  # 'same_line', 'same_col', 'south_of', 'same_block', 'table_row', 'semantic'
    label_block_id: Optional[int]
    score_tuple: Tuple  # filled in selector (lexicographic ordering)
    text_window: str  # raw text (may be multiline/same block)
    roi_info: Dict[str, Any]  # how ROI was built (for debug)


