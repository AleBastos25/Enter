"""DSL for describing page layouts with primitives and flows."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Union


class Choice:
    """Choose randomly from options."""

    def __init__(self, *options: Any):
        self.options = options

    def sample(self) -> Any:
        return random.choice(self.options)


class Rand:
    """Sample from a range (int or float)."""

    def __init__(self, min_val: Union[int, float], max_val: Union[int, float], is_int: bool = True):
        self.min_val = min_val
        self.max_val = max_val
        self.is_int = is_int

    def sample(self) -> Union[int, float]:
        if self.is_int:
            return random.randint(int(self.min_val), int(self.max_val))
        return random.uniform(self.min_val, self.max_val)


class Sample:
    """Reference to a sampled value (deferred evaluation)."""

    def __init__(self, key: str, **kwargs):
        self.key = key
        self.kwargs = kwargs


# Flow regions
@dataclass
class Top:
    """Top region of page."""

    height: Union[str, int] = "auto"  # "auto" or pixels


@dataclass
class Bottom:
    """Bottom region of page."""

    height: Union[str, int] = "auto"


@dataclass
class Columns:
    """Multi-column region."""

    k: Union[int, Choice] = 1
    gap: Union[int, Rand] = 12


@dataclass
class Flow:
    """A flow region (header, main, footer, etc.)."""

    name: str
    region: Union[Top, Bottom, Columns]
    margin: Optional[Union[int, Dict[str, int]]] = None


# Widgets
@dataclass
class Widget:
    """Base widget class."""

    flow: str
    id_prefix: str = ""
    style: Dict[str, Any] = field(default_factory=dict)

    def get_id(self, suffix: str = "") -> str:
        """Generate unique ID for this widget."""
        if not self.id_prefix:
            return f"w_{id(self)}_{suffix}"
        return f"{self.id_prefix}_{suffix}"


@dataclass
class Heading(Widget):
    """Heading/title widget."""

    level: Union[int, Choice] = 1
    text: Union[str, Sample] = "Título"
    font_size: Optional[Union[int, Rand]] = None
    bold: Union[bool, Choice] = True


@dataclass
class Paragraph(Widget):
    """Paragraph widget with Lorem-like text."""

    lines: Union[int, Rand] = 3
    text: Optional[Union[str, Sample]] = None


@dataclass
class KVList(Widget):
    """Key-value list widget."""

    pairs: Union[List[tuple], Sample] = field(default_factory=list)
    mode: Union[str, Choice] = "right_of"  # right_of, below, same_block
    gap: Union[int, Rand] = 8


@dataclass
class Table(Widget):
    """Table widget (grid)."""

    shape: Union[tuple, Sample] = (3, 3)  # (rows, cols)
    headers: Union[bool, Choice] = True
    with_rules: Union[bool, Choice] = True  # grid lines
    data: Optional[List[List[str]]] = None


@dataclass
class Badge(Widget):
    """Badge/chip widget (enum display)."""

    text: Union[str, Sample] = "BADGE"
    anchor: Union[str, Choice] = "bottom-right"  # corner position
    style_type: str = "badge"  # badge, chip, tag


@dataclass
class FormGrid(Widget):
    """Form grid widget (label-value pairs in grid)."""

    rows: Union[int, Rand] = 3
    cols: Union[int, Choice] = 2
    pairs: Optional[List[tuple]] = None
    underline: Union[bool, Choice] = True


@dataclass
class Watermark(Widget):
    """Watermark overlay."""

    text: Union[str, Choice] = "CONFIDENCIAL"
    angle: Union[float, Rand] = -15.0
    opacity: float = 0.1


@dataclass
class Page:
    """Page layout description."""

    size: str = "A4"  # A4, Letter, etc.
    margin: Union[int, Dict[str, int]] = 12
    flows: List[Flow] = field(default_factory=list)
    widgets: List[Widget] = field(default_factory=list)
    orientation: Literal["portrait", "landscape"] = "portrait"


def resolve_value(val: Any, context: Optional[Dict[str, Any]] = None) -> Any:
    """Resolve a value (Choice, Rand, Sample, etc.) to concrete value."""
    if isinstance(val, Choice):
        return val.sample()
    if isinstance(val, Rand):
        return val.sample()
    if isinstance(val, Sample):
        # Look up in context
        if context and val.key in context:
            return context[val.key]
        # Fallback: return key as string
        return val.key
    return val


def resolve_widget(widget: Widget, context: Optional[Dict[str, Any]] = None) -> Widget:
    """Resolve all deferred values in a widget."""
    # Create a copy with resolved values
    resolved_attrs = {}
    for attr_name, attr_value in widget.__dict__.items():
        resolved_attrs[attr_name] = resolve_value(attr_value, context)
    # Create new instance of same type
    return type(widget)(**resolved_attrs)

