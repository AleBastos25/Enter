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
class LabelMemory:
    """Memory for a document label (e.g., "carteira_oab")."""

    label: str
    fields: Dict[str, FieldMemory] = field(default_factory=dict)

