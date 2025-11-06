"""Schema for pattern memory data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

Relation = Literal["same_line_right_of", "same_table_row", "same_block"]


@dataclass
class SynonymObs:
    """Observed synonym for a field label."""

    text: str  # synonym seen (normalized)
    weight: float = 1.0  # accumulated confidence (with decay)


@dataclass
class OffsetObs:
    """Observed spatial offset from label to value (normalized space)."""

    relation: Relation
    dx: float  # (x_val_center - x_label_center)
    dy: float  # (y_val_center - y_label_center)
    tol: float = 0.06  # normalized tolerance (default)
    weight: float = 1.0


@dataclass
class FingerprintObs:
    """Light layout signature for page/area (4x4 grid of label and value)."""

    grid_label: Tuple[int, int]  # (gx, gy) for label center
    grid_value: Tuple[int, int]  # (gx, gy) for value center
    section_hint: Optional[int] = None
    column_hint: Optional[int] = None
    weight: float = 1.0


@dataclass
class ValueShapeObs:
    """Format/shape of the value (regex-id, enum key, length range, has digits?)."""

    regex_id: Optional[str] = None  # ex.: "cpf", "cnpj", "cep"
    enum_key: Optional[str] = None  # ex.: "REGULAR"
    has_digits: Optional[bool] = None
    length_range: Optional[Tuple[int, int]] = None
    weight: float = 1.0


@dataclass
class FieldMemory:
    """Memory for a single field (across multiple documents of same label)."""

    field_name: str
    synonyms: List[SynonymObs] = field(default_factory=list)
    offsets: List[OffsetObs] = field(default_factory=list)
    fingerprints: List[FingerprintObs] = field(default_factory=list)
    value_shapes: List[ValueShapeObs] = field(default_factory=list)


@dataclass
class StrategyStats:
    """Statistics for a matching strategy (v2).

    Tracks success rate, offsets, shapes, and style for each strategy.
    """

    strategy: str  # 'table_row', 'same_line', 'same_block', 'south_of', 'semantic'
    n_total: int = 0
    n_success: int = 0  # conf >= 0.85
    success_rate: float = 0.0
    
    # Deslocamentos médios e σ
    dx_mean: float = 0.0
    dy_mean: float = 0.0
    dx_sigma: float = 0.0
    dy_sigma: float = 0.0
    dx_samples: List[float] = field(default_factory=list)
    dy_samples: List[float] = field(default_factory=list)
    
    # Formas (set de regex/charclass) com contagem
    shapes: Dict[str, int] = field(default_factory=dict)  # shape -> count
    
    # Co-style (font_z médio/σ)
    font_z_mean: float = 0.0
    font_z_sigma: float = 0.0
    font_z_samples: List[float] = field(default_factory=list)


@dataclass
class FieldMemoryV2:
    """Memory v2 for a single field with StrategyStats (v2)."""

    field_name: str
    label_text: str  # Label text for this field
    strategies: Dict[str, StrategyStats] = field(default_factory=dict)  # strategy -> stats
    synonyms: List[SynonymObs] = field(default_factory=list)  # Keep for compatibility
    offsets: List[OffsetObs] = field(default_factory=list)  # Keep for compatibility
    fingerprints: List[FingerprintObs] = field(default_factory=list)  # Keep for compatibility
    value_shapes: List[ValueShapeObs] = field(default_factory=list)  # Keep for compatibility


@dataclass
class LabelMemory:
    """Memory for a document label (e.g., "carteira_oab")."""

    label: str
    fields: Dict[str, FieldMemory] = field(default_factory=dict)
    fields_v2: Dict[str, FieldMemoryV2] = field(default_factory=dict)  # v2 StrategyStats

